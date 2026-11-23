"""Starting the web server where HOST (the machine's file) says, on every port of the apps this copy runs
(iosuite_shared.host).

    HOST=0.0.0.0                     every address of the machine (the default)
    HOST=127.0.0.1                   this machine only: everything through a reverse proxy on the same server
    HOST=192.168.1.151               one of the machine's addresses, when it has several
    HOST=127.0.0.1,192.168.1.151     several of them (commas or spaces)

The other settings go to uvicorn as they are. The apps read X-Forwarded-* themselves (from this machine and the
reverse proxies listed under Settings › People), so uvicorn must not rewrite the peer (proxy_headers=False).

A copy with a certificate (iosuite_shared.certs) answers HTTPS on some of its ports. Those ports go on answering
plain HTTP as well: a connection that begins with a TLS handshake gets HTTPS, any other is served as before, so what
talked to the port without HTTPS (a device set up with the server's address, the suite's other servers, a reverse
proxy) is not cut off the day a certificate arrives."""
import asyncio
import logging
import socket
import ssl
import sys

log = logging.getLogger("iosuite_shared.serve")
FIRST_BYTE_S = 15.0    # how long a connection may stay silent before it says whether it speaks TLS
HANDSHAKE_S = 20.0


def hosts(host: str) -> list:
    """The addresses HOST names, in its order; the default when it names none."""
    return [h for h in (host or "").replace(",", " ").split() if h] or ["0.0.0.0"]


def _socket(host: str, port: int) -> socket.socket:
    name = host.strip("[]")
    fam, _, _, _, addr = socket.getaddrinfo(name, port, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE)[0]
    sk = socket.socket(fam, socket.SOCK_STREAM)
    try:
        sk.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if fam == socket.AF_INET6:
            sk.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)  # beside a v4 address on the same port
        sk.bind(addr)
    except OSError:
        sk.close()
        raise
    sk.set_inheritable(True)
    return sk


def free(host: str, port: int) -> bool:
    """Whether this port can be opened on every address HOST names (nothing else on the machine holds it)."""
    for h in hosts(host):
        try:
            _socket(h, port).close()
        except OSError:
            return False
    return True


def _bind(names: list, ports: list, host: str, made: list) -> list:
    socks = []
    for p in ports:
        for h in names:
            try:
                socks.append(_socket(h, p))
            except OSError as e:
                for s in (*made, *socks):
                    s.close()
                sys.exit(f"HOST={host}: cannot listen on {h} port {p}: {e}")
    return socks


CONTEXT: ssl.SSLContext | None = None  # the certificate of the HTTPS doors while they are open: reload() renews it


def context(certfile: str, keyfile: str = None) -> ssl.SSLContext:
    """What the HTTPS doors answer with: the certificate and its chain (and the key, in the same file or its own)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile, keyfile or None)
    ctx.set_alpn_protocols(["http/1.1"])
    return ctx


def run(target, host: str, ports, secure=None, **settings) -> None:
    """Serve the ASGI application `target` on every address HOST names and every port of `ports` (one, or a list).

    `secure`: the ports among them that answer HTTPS too, with the certificate in `ssl_certfile` (and `ssl_keyfile`,
    when the key is not in the same file); None: all of them, when a certificate is given."""
    import uvicorn
    global CONTEXT
    names = hosts(host)
    ports = [ports] if isinstance(ports, int) else list(ports)
    certfile, keyfile = settings.pop("ssl_certfile", None), settings.pop("ssl_keyfile", None)
    secure = [p for p in ports if secure is None or p in set(secure)] if certfile else []
    plain = [p for p in ports if p not in secure]
    first = names[0].strip("[]")
    if not secure and len(names) == 1 and len(ports) == 1:
        uvicorn.run(target, host=first, port=ports[0], **settings)
        return
    said = f"listening on {', '.join(names)} port {', '.join(str(p) for p in ports)}"  # uvicorn names no address for sockets it is handed
    if not secure:
        socks = _bind(names, ports, host, [])
        print(said, file=sys.stderr)
        uvicorn.Server(uvicorn.Config(target, host=first, port=ports[0], **settings)).run(sockets=socks)
        return
    try:
        CONTEXT = context(certfile, keyfile)
    except (OSError, ssl.SSLError) as e:
        sys.exit(f"the certificate cannot be used ({certfile}): {e}")
    plain_socks = _bind(names, plain, host, [])
    secure_socks = _bind(names, secure, host, plain_socks)
    print(f"{said}; HTTPS on port {', '.join(str(p) for p in secure)}", file=sys.stderr)
    server = uvicorn.Server(uvicorn.Config(target, host=first, port=ports[0], **settings))

    async def both() -> None:
        doors = asyncio.create_task(_https_doors(server, secure_socks, CONTEXT), name="https-doors")
        try:
            await server.serve(sockets=plain_socks)
        finally:
            doors.cancel()
            await asyncio.gather(doors, return_exceptions=True)

    try:
        from uvicorn._compat import asyncio_run
        asyncio_run(both(), loop_factory=server.config.get_loop_factory())
    except (ImportError, AttributeError):  # an older uvicorn
        server.config.setup_event_loop()
        asyncio.run(both())


async def _https_doors(server, socks: list, ctx: ssl.SSLContext) -> None:
    """The ports that answer HTTPS and plain HTTP both, beside the web server's own: every connection is looked at
    before it is read (its first byte tells a TLS handshake from a request) and then handed to the web server as one
    of its own, so it is counted, logged and closed at shutdown like the others."""
    loop = asyncio.get_running_loop()
    while not server.started:  # the apps have had their start (lifespan), as for the web server's own ports
        if server.should_exit:
            for s in socks:
                s.close()
            return
        await asyncio.sleep(0.05)
    taking: set = set()

    def make():
        return server.config.http_protocol_class(config=server.config, server_state=server.server_state, app_state=server.lifespan.state)

    async def take(conn: socket.socket) -> None:
        try:
            first = await asyncio.wait_for(_first_byte(loop, conn), FIRST_BYTE_S)
            if not first:
                conn.close()
            elif first[0] == 0x16:  # a TLS handshake record
                await loop.connect_accepted_socket(make, sock=conn, ssl=ctx, ssl_handshake_timeout=HANDSHAKE_S)
            else:
                await loop.connect_accepted_socket(make, sock=conn)
        except (OSError, ssl.SSLError, asyncio.TimeoutError, ConnectionError):  # hung up, or not TLS after all
            conn.close()
        except asyncio.CancelledError:
            conn.close()
            raise

    async def accept(sock: socket.socket) -> None:
        sock.listen(server.config.backlog)
        sock.setblocking(False)
        while True:
            try:
                conn, _ = await loop.sock_accept(sock)
            except OSError as e:  # out of file descriptors, as a rule: the ones open go on
                log.warning("a connection could not be accepted (%s)", e)
                await asyncio.sleep(0.2)
                continue
            conn.setblocking(False)
            t = loop.create_task(take(conn))
            taking.add(t)
            t.add_done_callback(taking.discard)

    accepting = [loop.create_task(accept(s)) for s in socks]
    try:
        while not server.should_exit:
            await asyncio.sleep(0.1)
    finally:
        for t in (*accepting, *taking):
            t.cancel()
        await asyncio.gather(*accepting, *taking, return_exceptions=True)
        for s in socks:
            s.close()


async def _first_byte(loop, conn: socket.socket) -> bytes:
    """The first byte the other side sends, left on the socket for whoever reads next; b"" when it hung up."""
    fd = conn.fileno()
    got = loop.create_future()

    def ready() -> None:
        try:
            data = conn.recv(1, socket.MSG_PEEK)
        except (BlockingIOError, InterruptedError):
            return  # not yet: asked again when there is something
        except OSError as e:
            if not got.done():
                got.set_exception(e)
            return
        if not got.done():
            got.set_result(data)

    loop.add_reader(fd, ready)
    try:
        return await got
    finally:
        loop.remove_reader(fd)


def reload(certfile: str, keyfile: str = None) -> bool:
    """Give the open HTTPS doors a renewed certificate: connections made from now on get it, the open ones go on.
    False when this process has no HTTPS door."""
    if CONTEXT is None:
        return False
    CONTEXT.load_cert_chain(certfile, keyfile or None)
    return True

"""Starting the web server where HOST (the machine's file) says, on every port of the apps this copy runs
(iosuite_shared.host).

    HOST=0.0.0.0                     every address of the machine (the default)
    HOST=127.0.0.1                   this machine only: everything through a reverse proxy on the same server
    HOST=192.168.1.151               one of the machine's addresses, when it has several
    HOST=127.0.0.1,192.168.1.151     several of them (commas or spaces)

The other settings go to uvicorn as they are. The apps read X-Forwarded-* themselves (from this machine and the
reverse proxies listed under Settings › Security), so uvicorn must not rewrite the peer (proxy_headers=False)."""
import socket
import sys


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


def run(target, host: str, ports, **settings) -> None:
    """Serve the ASGI application `target` on every address HOST names and every port of `ports` (one, or a list)."""
    import uvicorn
    names = hosts(host)
    ports = [ports] if isinstance(ports, int) else list(ports)
    if len(names) == 1 and len(ports) == 1:
        uvicorn.run(target, host=names[0].strip("[]"), port=ports[0], **settings)
        return
    socks = []
    for p in ports:
        for h in names:
            try:
                socks.append(_socket(h, p))
            except OSError as e:
                for s in socks:
                    s.close()
                sys.exit(f"HOST={host}: cannot listen on {h} port {p}: {e}")
    print(f"listening on {', '.join(names)} port {', '.join(str(p) for p in ports)}", file=sys.stderr)  # uvicorn names no address for sockets it is handed
    uvicorn.Server(uvicorn.Config(target, host=names[0].strip("[]"), port=ports[0], **settings)).run(sockets=socks)

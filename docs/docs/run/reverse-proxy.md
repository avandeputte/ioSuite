---
description: HTTPS for ioSuite behind Caddy, nginx, HAProxy or Traefik, one address for the whole suite or a name per app, the addresses for devices and MCP, and one sign-in across them.
---

# Reverse proxy and HTTPS

ioSuite speaks plain HTTP on three ports: the pages (80), phones, native apps and devices (8443), and MCP clients
(8444); see [The three ports](../reference/configuration.md#the-three-ports). To reach it from outside your network,
put a reverse proxy in front that terminates HTTPS: Caddy, nginx (or Nginx Proxy Manager), HAProxy, Traefik, or a
[Cloudflare Tunnel](cloudflare.md). Phones want HTTPS for CalDAV and CardDAV accounts away from home, and the browser
wants it to install the web app. The suite can also answer HTTPS itself, with
[a certificate it asks for and renews](https.md), and then needs no proxy for that.

## One address for the suite

The start page answers at the address itself and every app in its folder: `https://home.example.com/calendar/`,
`https://home.example.com/notes/`. One DNS name and one certificate cover the suite, and the proxy has **one upstream
per port**, whatever the number of apps and wherever they run (an app that runs in
[another copy](../start/several-apps.md) is passed across by the copy that was asked).

| What | Address at the proxy | Upstream |
| --- | --- | --- |
| The pages | `https://home.example.com` | `192.168.1.10:80` |
| Phones, native apps, devices | `https://home.example.com:8443` | `192.168.1.10:8443` |
| MCP clients | `https://home.example.com:8444` | `192.168.1.10:8444` |

Then tell the suite its three addresses, once, under **Settings › Apps › All settings** (or with the command):

```sh
iosuite set suite PUBLIC_URL https://home.example.com
iosuite set suite SYNC_URL   https://home.example.com:8443
iosuite set suite MCP_URL    https://home.example.com:8444
```

The apps write these into everything they hand out: the CalDAV and CardDAV addresses, the Apple profile, the address
an MCP client is given, the links in notifications. Without them an app gives the address it was asked at, with the
port of the kind of traffic.

When your proxy or tunnel serves port 443 only, give devices and MCP **a name of their own** instead of a port:

| What | Address at the proxy | Upstream | Setting |
| --- | --- | --- | --- |
| The pages | `https://home.example.com` | `192.168.1.10:80` | `PUBLIC_URL` |
| Phones, native apps, devices | `https://sync.example.com` | `192.168.1.10:8443` | `SYNC_URL` |
| MCP clients | `https://mcp.example.com` | `192.168.1.10:8444` | `MCP_URL` |

A phone's calendar account is then `https://sync.example.com/calendar/dav/`.

## A name per app

An app can have a host name of its own beside its folder, and both work at the same time:
`https://calendar.example.com` and `https://home.example.com/calendar/` reach the same ioCalendar. Point the name at
the same upstream as the suite's (the app is chosen by the name asked for) and store it as the app's own address:

```sh
iosuite set iocalendar PUBLIC_URL https://calendar.example.com
iosuite set suite COOKIE_DOMAIN example.com      # one sign-in for every name under example.com
```

With `COOKIE_DOMAIN`, someone signed in at `home.example.com` is signed in at `calendar.example.com` too. Without it,
each name keeps its own sign-in (still with the same accounts). An app answers with links in the style it was asked
in: asked at its own name, its links are there; asked in its folder, they stay in the folder.

An app's own name can serve its devices too, so that a phone set up with `https://calendar.example.com/dav/` keeps
working. Send the app's device paths to the device port, the rest to the pages, and store the same name as the app's
address for devices:

| App | Paths for devices |
| --- | --- |
| ioCalendar | `/dav`, `/.well-known/`, `/ics/` |
| ioTask | `/dav`, `/.well-known/` |
| ioContact | `/dav`, `/.well-known/`, `/cal/` |
| ioHealth | `/v1/` |
| ioStart | `/dav/` (bookmark sync) |
| every app | `/mcp` to the MCP port |

```sh
iosuite set iocalendar SYNC_URL https://calendar.example.com
iosuite set iocalendar MCP_URL  https://calendar.example.com
```

Store an app's `SYNC_URL` or `MCP_URL` at its own name **only when the proxy sends those paths to those ports**: a
device path that arrives with the pages is sent on to the address stored for devices, and that would be the same
address again.

!!! note "`/api/` from outside"
    An app password or a token is taken on the pages' port from inside your network only. From outside, a native
    app, a widget, a script or an e-ink screen uses the address for devices (`SYNC_URL`), where `/api/` answers to
    an app password and no browser cookie is read.

## Caddy

Caddy gets the certificates by itself. One address for the suite:

```caddy
home.example.com {
    reverse_proxy 192.168.1.10:80
}
home.example.com:8443 {
    reverse_proxy 192.168.1.10:8443
}
home.example.com:8444 {
    reverse_proxy 192.168.1.10:8444
}
```

A name per app, its device paths included:

```caddy
calendar.example.com {
    @devices path /dav /dav/* /.well-known/* /ics/*
    reverse_proxy @devices 192.168.1.10:8443
    reverse_proxy /mcp* 192.168.1.10:8444
    reverse_proxy 192.168.1.10:80
}
```

## nginx

```nginx
map $server_port $iosuite_upstream {
    443   192.168.1.10:80;
    8443  192.168.1.10:8443;
    8444  192.168.1.10:8444;
}
server {
    listen 443 ssl;
    listen 8443 ssl;
    listen 8444 ssl;
    server_name home.example.com;
    # ssl_certificate / ssl_certificate_key ...
    client_max_body_size 0;               # uploads: the apps have their own limits
    location / {
        proxy_pass http://$iosuite_upstream;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;              # MCP and the live pages stream their answers
        proxy_request_buffering off;      # an upload goes straight through
        proxy_read_timeout 1h;
    }
}
```

## The proxy as the only way in

With the proxy on the same server as the suite, the program can listen on that machine only, so nobody on your
network goes around the proxy. In the [machine's file](../reference/configuration.md#the-machines-file):

```sh
HOST=127.0.0.1
```

and restart the service. The proxy then forwards to `127.0.0.1` and the three ports. `HOST` can also name one address
of a machine that has several, or several with commas between them. In Docker, leave `HOST` alone and publish the
ports on the machine only: `ports: ["127.0.0.1:80:80"]`.

## Tell the suite where the proxy is

A reverse proxy on another machine connects from a private address, like any visitor in your home. The suite has to
know which address is the proxy to tell someone at home from someone on the internet. Until it does, **everyone who
comes through the proxy counts as outside your network**, which is the safe side: from outside, the first account
cannot be made, an install without accounts shows nothing but its sign-in screen, and an account without a password
gets no one-click sign-in.

Set it once, as a suite admin, in any app: **Settings › People › Sign-in at the proxy › Reverse proxy addresses**.
Enter the address the proxy connects from (`192.168.1.2`), several of them, or a network (`172.18.0.0/16` for a
Docker network). Leave *Proxy* at Off unless the proxy also signs people in ([below](#sign-in-at-the-proxy)).

- The proxy must send `X-Forwarded-For`: Caddy, Traefik and Nginx Proxy Manager do by themselves, nginx with the
  `proxy_set_header` line above, HAProxy with `option forwardfor`. The suite reads the visitor's address from it: a
  private address is at home, a public one is outside.
- A proxy on the same machine as the suite (`127.0.0.1`) is known already; nothing to set. So are the suite's own
  servers when it runs on several: they are in the suite's list of apps.
- A [Cloudflare Tunnel](cloudflare.md) needs nothing here: what comes through Cloudflare is always outside.
- On a new install, the installer makes the first admin. Where it did not, make the first account at the server's
  own address (`http://192.168.1.10`) and not through the proxy: see [First run](../start/first-run.md).

## Things to know on any proxy

- **MCP and the live pages stream** (server-sent events): the proxy must not buffer them.
- **`X-Forwarded-For` and `X-Forwarded-Proto`** tell the suite the visitor's address and that the request came over
  HTTPS (which marks the session cookie Secure). They are believed from the proxies the suite was told about, the
  reverse proxy addresses [above](#tell-the-suite-where-the-proxy-is), and from a proxy on the same machine; from
  anyone else they are ignored. That one list decides both what the suite shows and logs as the visitor's address
  and whether a visitor counts as inside your network.
- **The suite in a folder of a site** (`https://example.com/suite/`): store that as the suite's `PUBLIC_URL`, and the
  proxy may leave the folder on the path or take it off and say so with `X-Forwarded-Prefix: /suite`.
- **A request at the wrong port is sent on to the right one**: a CalDAV address asked with the pages goes to the
  address for devices, a page asked at the device port goes to the pages.
- **ioContact's LDAP** is not HTTP: keep it on the home network, or put a TLS proxy (stunnel, HAProxy, nginx stream)
  in front for `ldaps://`.

## HTTPS without a proxy

The suite can ask for a certificate itself (Let's Encrypt), renew it, and answer HTTPS on its own ports, or use a
certificate you name in the machine's file: [The suite's own certificate](https.md).

## Sign-in at the proxy

When the proxy already makes people sign in (Cloudflare Access, Authelia, Authentik, oauth2-proxy...), the suite can
take that sign-in instead of asking again: the proxy names the person in a header, and the suite signs in the account
with that email (or name). It is one setting for the whole suite, under **Settings › People › Sign-in at the
proxy** in any app:

| Setting | |
| --- | --- |
| Proxy | `cloudflare`, `haproxy`, `nginx`, `caddy`, `traefik` or `header` |
| Header | the header with the user (`Remote-User`, `X-Forwarded-User`, `X-Auth-Request-Email`...; for Cloudflare `Cf-Access-Authenticated-User-Email`) |
| Reverse proxy addresses | the addresses the proxy connects from ([above](#tell-the-suite-where-the-proxy-is)): the header is believed from there only, and a proxy that names the user in a header cannot be saved without them |
| New people | `viewer`, `member` or `editor` to make an account for someone the proxy lets in, `deny` for a "No access" page |
| Cloudflare team and AUD | for Cloudflare Access: the signed token is checked against your team's keys |

The header must not be fakeable: the proxy must replace it on every request, and the suite must be reachable only
through the proxy. It is read on the pages' port only: at the ports for devices and MCP an app password or a token is
what counts. The suite's own sign-in keeps working beside it, for anyone the proxy doesn't vouch for.

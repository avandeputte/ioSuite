---
description: Run ioSuite behind a Cloudflare Tunnel and Cloudflare Access, with names for the pages, for devices and for MCP.
---

# Cloudflare Tunnel and Access

A [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) publishes the
suite without opening a port on your router, and [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/policies/access/)
makes people sign in at Cloudflare before a request reaches it. The suite works with both, and the Access setup is
done once.

## The tunnel

In Cloudflare Zero Trust › Networks › Tunnels, create a tunnel and run `cloudflared` on a machine in your network. A
tunnel publishes host names on port 443, so the suite's three ports get **three names**:

| Public hostname | Service | Stored as |
| --- | --- | --- |
| `home.example.com` | `http://192.168.1.10:80` | `PUBLIC_URL` of the suite |
| `sync.example.com` | `http://192.168.1.10:8443` | `SYNC_URL` of the suite |
| `mcp.example.com` | `http://192.168.1.10:8444` | `MCP_URL` of the suite |

```sh
iosuite set suite PUBLIC_URL https://home.example.com
iosuite set suite SYNC_URL   https://sync.example.com
iosuite set suite MCP_URL    https://mcp.example.com
```

Every app is then at `https://home.example.com/calendar/`, a phone's calendar account at
`https://sync.example.com/calendar/dav/`, and an MCP client connects to `https://mcp.example.com/mcp`.

An app can have a name of its own as well (`calendar.example.com`): add it as a public hostname with the same
service as `home.example.com` and store it as the app's own `PUBLIC_URL`, with `COOKIE_DOMAIN` for one sign-in across
the names; see [A name per app](reverse-proxy.md#a-name-per-app). For that name to serve the app's devices too, add
the hostname a second time **above** the first with a path, pointing at the device port: `calendar.example.com`,
path `^/(dav|\.well-known|ics)(/|$)`, service `http://192.168.1.10:8443`.

## Access: one application for the pages

1. In Zero Trust › Access › Applications, add a **self-hosted** application for `home.example.com` (and the apps'
   own names: `*.example.com` covers them) with a policy that lets your family in.
2. Copy the application's **AUD tag** (Overview › Application Audience tag).
3. In any app, as a suite admin: **Settings › Security › Sign-in at the proxy** › Cloudflare Access, with your team
   (`myteam.cloudflareaccess.com`) and the AUD tag. Several AUD tags, comma-separated, if you made an application
   per host.

That setting is kept in the Shared ioSuite database, so every app picks it up. The signed token Cloudflare adds to
every request (`Cf-Access-Jwt-Assertion`) is checked against your team's keys and signs in the account with that
email, then that name. Sign out also ends the Access session. Keep **Sign-in required** (Settings › Global settings ›
Apps) on, as it is by default, so nobody gets in without it. Requests through Cloudflare never get one-click sign-in
for passwordless accounts.

## The names for devices and MCP stay outside Access

Phones and sync apps can't open the Access sign-in page. With names of their own for devices and MCP, that is one
rule: **no Access application on `sync.example.com` and `mcp.example.com`** (with a wildcard application, add one for
each of the two names with a policy whose action is **Bypass**, Include: Everyone). They stay protected by the
suite's own sign-in, which reads no browser cookie and no proxy header on those ports:

| At the name for devices | Used by | Protected by |
| --- | --- | --- |
| `/calendar/dav/`, `/tasks/dav/`, `/contacts/dav/`, `/.well-known/…` | CalDAV and CardDAV clients, the Apple profile | user name and app password |
| `/calendar/ics/…`, `/contacts/cal/…` | subscription links, free/busy, the birthdays feed | the private token in the link |
| `/dav/…` | bookmark sync: the browser extension, the iPhone app | an app password |
| `/health/v1/…` | the ioHealthSync iPhone app | user name and password |
| `/…/api/…` | native apps, widgets, e-ink screens, the wall display, scripts | an app password or the device's token |

| At the name for MCP | Used by | Protected by |
| --- | --- | --- |
| `/mcp`, `/calendar/mcp`, … | AI assistants, if MCP is on | an app password |

Where an app's own name serves its devices by path (above), those paths need the same Bypass at that name:

| App | Path |
| --- | --- |
| ioCalendar | `/dav/*`, `/.well-known/caldav`, `/ics/*` |
| ioTask | `/dav/*`, `/.well-known/caldav` |
| ioContact | `/dav/*`, `/.well-known/carddav`, `/cal/*` |
| ioHealth | `/v1/*` |

Everything at the pages' names stays behind Access, with one exception: the Apple profile's download link, which a
phone opens in a browser sheet that has none of the page's cookies. Add a Bypass for `/calendar/profile/*`,
`/tasks/profile/*` and `/contacts/profile/*` at `home.example.com` (`/profile/*` at an app's own name); the link
holds a short-lived secret and gives one profile.

## Optional: checking app passwords at the edge

Since the name for devices is outside Access, a small **Cloudflare Worker** can check the app password there and
turn wrong ones away before they reach your server. The suite keeps a Workers KV namespace up to date with a SHA-256
of each app password (never an account password). Store the three settings once under Settings › Global settings ›
Keys and tokens:

```sh
iosuite edge --account-id … --namespace-id … --token-file token.txt
```

The Worker, its `wrangler.toml`, the rollout (monitor first, then enforce) and a WAF rate-limit rule are in
[cloudflare/edge-auth](https://github.com/avandeputte/iosuite/blob/main/cloudflare/edge-auth/README.md). Once it
enforces, sync clients must use an app password, not the account password.

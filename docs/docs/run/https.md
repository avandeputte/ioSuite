---
description: Let ioSuite ask for its own certificate (Let's Encrypt), renew it, and answer HTTPS itself, without a reverse proxy in front.
---

# The suite's own certificate

ioSuite can answer HTTPS itself. It asks a certificate authority ([Let's Encrypt](https://letsencrypt.org), unless you
choose another) for a certificate for the names of its addresses, keeps it in the Shared ioSuite database, renews it
before it runs out, and every server of the suite answers with it. No reverse proxy is needed for HTTPS then; if you
have one that does this already ([Reverse proxy and HTTPS](reverse-proxy.md),
[Cloudflare Tunnel](cloudflare.md)), you do not need this page.

It is one switch for the whole suite, under **Settings › Global settings › Certificate** in any app.

## What changes when it is on

| Port | Before | With a certificate |
| --- | --- | --- |
| 80 (`PORT`) | the pages | the same, and the certificate authority's check is answered here |
| 443 (`HTTPS_PORT`) | not opened | the pages over HTTPS |
| 8443 (`SYNC_PORT`) | phones, native apps, devices | the same, and over HTTPS as well, on the same port |
| 8444 (`MCP_PORT`) | MCP clients | the same, and over HTTPS as well, on the same port |

Nothing that works without HTTPS stops working. The ports for devices and MCP answer both ways, so a phone, a wall
display or an e-ink screen set up with `http://192.168.1.151:8443` goes on as it is, and the suite's other servers
and a reverse proxy are served as before. Only one thing is sent on to HTTPS: a browser that asks the pages without
it, by one of the certificate's names.

The addresses stored for the suite change with it: `http://home.example.com` becomes `https://home.example.com`, and
`http://home.example.com:8443` becomes `https://home.example.com:8443`. The apps then hand out the HTTPS addresses
(the CalDAV address for a new phone, the links in notifications). Switching the certificate off puts back what was
there.

## Before you switch it on

- **A name.** A certificate is for a name, such as `home.example.com`: one that DNS points at your server. The
  server's own address (`192.168.1.151`) and a name of the home network (`nas.lan`) cannot have one.
- **The suite's address says that name.** Under **Settings › Global settings › Settings**, the suite's address is
  `http://home.example.com`, or from a shell:

    ```sh
    iosuite set suite PUBLIC_URL http://home.example.com
    ```

    The certificate is asked for every name in the addresses stored: the suite's, and each app's own
    (`calendar.example.com`) when it has one.
- **A way to prove the names are yours.** One of the two below.

## Proving the names are yours

**Over HTTP** is the default and needs no account anywhere. The authority asks
`http://home.example.com/.well-known/acme-challenge/…` on port 80, and the suite answers. For that, port 80 of each
name has to reach the suite from the internet: on a home connection, a port forward on the router (80 to the
server's 80). For people outside to use HTTPS afterwards, forward 443 as well.

**Through Cloudflare's DNS** needs nothing to be reachable from outside: the suite puts a record into the zone and
takes it away again. Use it when the names resolve inside your network only, or for a name with a star
(`*.example.com`, which covers `calendar.example.com`, `photos.example.com` and so on, and can only be proven this
way). It needs an API token for Cloudflare: **My Profile › API Tokens › Create Token**, the template *Edit zone
DNS*, limited to the zones of your names. The token goes into the Certificate screen and is kept with the other keys
(it can be replaced, never read back).

## Switching it on

Under **Settings › Global settings › Certificate**: tick *Ask for a certificate*, choose the authority and the proof,
and press **Save and ask now**. The screen says what the authority answered: the certificate's names and the day it
holds until, or the authority's own words when it said no.

For a first try, choose **Let's Encrypt's test authority**. It gives certificates browsers do not trust, and it does
not count failed tries the way the real one does (which refuses a name for an hour after five failures). When that
works, choose Let's Encrypt and ask again.

The same from a shell:

```sh
iosuite cert --on --staging --email you@example.com --now     # a try with the test authority
iosuite cert --ca letsencrypt --now                           # then the real one
iosuite cert                                                  # what is set, what is stored, until when
iosuite cert --on --cloudflare --token-file token.txt --names '*.example.com'
iosuite cert --off
```

Once a certificate is stored, every server of the suite starts again, once, to open its HTTPS ports: the one you
asked from within seconds, the others within two minutes. After that `https://home.example.com` answers.

## Renewing

Nothing to do. A certificate from Let's Encrypt holds for 90 days; the suite asks for the next one when a third of
that time is left, and the servers take it over without starting again. When the authority says no, the suite asks
again an hour later at the earliest, and goes on with the certificate it has. The Certificate screen shows the last
answer, and it is in the log.

A new certificate is also asked for when a name is added: an app given an address of its own, or a name added on the
screen.

## Several servers

The certificate is in the Shared ioSuite database, so every copy of the program serves the same one, and whichever
copy the authority reaches answers its check. Two lines of a machine's `config.env` are about it:

```sh
HTTPS_PORT=443      # the pages over HTTPS on this machine; another number when 443 is taken
HTTPS_PORT=off      # this copy stays without HTTPS whatever the suite has
```

A copy that finds port 443 taken by another program on its machine (a reverse proxy, a second copy) goes on without
the pages over HTTPS and says so on the Certificate screen; devices and MCP are still answered over HTTPS there.

## In Docker

Publish port 443 beside the others in the stack file, and the rest is as above:

```yaml
    ports:
      - "80:80"
      - "443:443"
      - "8443:8443"
      - "8444:8444"
```

## A certificate of your own

When you have a certificate from elsewhere (your own authority, a wildcard you already pay for), name its files in
the machine's file instead, and leave the switch off:

```sh
TLS_CERT_FILE=/etc/ssl/home.example.com/fullchain.pem
TLS_KEY_FILE=/etc/ssl/home.example.com/privkey.pem
```

The ports then behave as in the table above. The files are read when the service starts: restart it after renewing
them (`systemctl restart iosuite`). The addresses are yours to set (`iosuite set suite PUBLIC_URL https://…`).

## Another certificate authority

Any authority that speaks ACME can be used: choose *Another authority* and give the address of its directory
(`https://acme.zerossl.com/v2/DV90`, or your own [step-ca](https://smallstep.com/docs/step-ca/)). For a private
authority that no public one signed, name its root certificate in the machine's file so the suite trusts it:
`ACME_CA_FILE=/etc/ssl/my-root.pem`.

## When it does not work

- **"Connection refused" or "Timeout during connect"** from the authority: port 80 of that name does not reach the
  suite from the internet. Check the port forward, and that the name points at your connection. Or prove the names
  through Cloudflare's DNS.
- **"No valid IP addresses found"** or **NXDOMAIN**: the name does not exist in public DNS.
- **The pages do not answer on 443**: the Certificate screen says when another program holds the port on that
  server. Stop that program, or give the suite another port with `HTTPS_PORT`.
- **A browser warns about the certificate**: it came from the test authority (ask again from Let's Encrypt), or the
  address you typed is not one of its names (the server's address instead of `home.example.com`).
- **Behind a reverse proxy or a tunnel that already does HTTPS** there is nothing to gain: leave the switch off.
- **To go back**: `iosuite cert --off`, from a shell on the server when the pages cannot be reached. The servers go
  back to plain HTTP within two minutes and the addresses say `http://` again.

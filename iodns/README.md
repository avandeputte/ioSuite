# ioDNS

*The DNS console of ioSuite ([ioStart](../iostart/), [ioCalendar](../iocalendar/),
[ioContact](../iocontact/), [ioNote](../ionote/), [ioPix](../iopix/), [ioHealth](../iohealth/)).*

One master list of the house's DNS names, kept in sync on every DNS server: two AdGuard Homes, a Pi-hole, the UniFi
gateway, Cloudflare. Add a name once, see where the servers disagree, pick who is right, push. FastAPI and a
single-page vanilla JS app, built the same way as the other io apps, signed in with the suite's shared accounts
([`iosuite_shared`](../iosuite_shared/)), with its data in MariaDB / MySQL.

## What it does

- **A master list**: a row per name (`calendar.example.com`), with a note, and its records (A, AAAA, CNAME, or a Cloudflare
  Tunnel hostname) per **view**.
- **Views (split-horizon DNS)**: a view is one answer to "who is asking". Internal (the house), External (the internet)
  and Tailscale (the tailnet) to begin with; add more in Settings › Views. Each server answers for one view, so
  `calendar.example.com` can be `192.168.1.151` inside, a public address or a tunnel outside and `100.x` on the
  tailnet, all on one row. A name without an External record is never pushed to public DNS.
- **Compare**: per view, every server is read and compared with the master list name by name: in sync, missing on a
  server, different, or only on a server. Unreachable servers are shown, not fatal; a server only holds some types (or,
  for Cloudflare, some zones), and only those are compared.
- **Resolve**: a decision per name: use the master list, use one server's records (they become the master list's),
  delete everywhere, or leave it. A preview lists every change (the master list and each server's add / change /
  remove) before anything is done. **Push all** makes every server of a view hold the master list (and, if asked,
  removes the names only the servers hold). A changed address is changed in place where the server can (AdGuard
  Home, Cloudflare keeps its proxy setting), so the name never goes unanswered.
- **Push right away**: after an entry is added, changed, renamed or deleted (or the list is imported), ioDNS lists what
  that would change on the servers, in every view, and asks whether to push it now. **Later** leaves it for Compare.
- **Import** from any server, into its view of the master list: merge (add what is missing), merge with the server
  winning, or replace. Also export / import the whole list as JSON (Settings › Export and import).
- **Dynamic DNS**: a record's value can be "Public address": ioDNS finds the house's public IPv4 / IPv6 every few
  minutes (an address-echo service, the UniFi gateway's WAN address, or a page of your own) and, when it changes,
  updates those records and pushes them straight away (Cloudflare…).
- **Cloudflare Tunnel**: a name in the External view can be a tunnel's public hostname (`TUNNEL home|http://192.168.1.151:80`:
  the tunnel and the service behind it) instead of an address. ioDNS keeps both halves as the dashboard does: the
  tunnel's ingress rule and the proxied CNAME to `<tunnel id>.cfargotunnel.com`. Existing hostnames are compared and
  imported like any other record; a rule with a path, the origin settings and the catch-all are left as they are.
- **Tailscale**: a record's value can be "Tailscale device": the device's tailnet address, read from the Tailscale API
  before every comparison, so the record follows the device. The Tailscale entry also sets up **split DNS** (send
  `example.com` queries on the tailnet to the DNS server that holds the Tailscale view).
- **History**: every change to the list, every push, import and dynamic DNS update, by whom.
- **A background check** compares every view every 30 minutes, so the sidebar shows which views have differences
  and each server's dot says whether it is reachable.
- **For suite admins only**: ioDNS is an **admin tool**, so only the suite admins can use it (everybody else has no
  access here, and it takes no roles or default role); only they see it in the start page's gear menu (under Admin tools)
  and the app switchers, apart from the other apps. The servers' passwords and API keys are kept with the suite's
  keys and tokens in the Shared ioSuite database (Settings › Keys), never shown back.
- **Updates, the log and Restart** under Settings › Servers, as in every app of the suite; light and dark, a phone layout,
  installable as a web app.

## DNS servers

| Kind | What ioDNS keeps there | How it signs in |
| --- | --- | --- |
| **AdGuard Home** | Filters › DNS rewrites (`/control/rewrite/*`) | the web interface's user and password |
| **Pi-hole v6** | Local DNS records and CNAME records (`/api/config/dns/hosts`, `cnameRecords`) | an app password (Settings › Web interface / API). Pi-hole 5 has no API for this. |
| **UniFi gateway** | the gateway's DNS records | an API key (Network 9.3 and later: Settings › Control Plane › Integrations), through the official integration API's DNS policies; or a local admin account, through the web app's static DNS |
| **Cloudflare DNS** | the zones' A, AAAA and CNAME records | an API token with Zone › DNS › Edit; list the zones (empty: every zone the token sees). New records proxied or not, as set. The tunnels' CNAMEs are left to the Cloudflare Tunnel entry. |
| **Cloudflare Tunnel** | the public hostnames of remotely managed tunnels (ingress rules) and their CNAMEs | an API token with Account › Cloudflare Tunnel › Edit and Zone › DNS › Edit; the account ID if the token sees several. Tunnels run from a config.yml can't be changed through the API and are left out. |
| **Tailscale** | nothing is pushed: device addresses and split DNS | an API access token (`tskey-api-…`) or an OAuth client secret |

Every server also has **Names to leave out** (`nas.example.com, *.guest.lan`): names it is never compared on or sent.
A UniFi gateway refuses a record for a name it answers itself (a client of a network with a domain name); ioDNS adds such a
name there by itself.

Adding another kind is one module in `iodns/providers/`: a `Provider` subclass that lists, adds and deletes records
(`iodns/providers/__init__.py` says how). A certificate of its own (a UniFi gateway's) is not checked unless asked.

## Run

ioDNS is one of the apps of [ioSuite](../README.md), one program that runs the apps it is told to. Install the suite
with ioDNS in it, alone or with the others, on any Linux machine:

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash -s -- --apps iodns
```

It asks for the MariaDB server, the first admin and the suite's address, then starts the service; leave `--apps` out
for the list of every app, to tick. On a server that already runs the suite:

```sh
iosuite install --add iodns       # --remove iodns stops running it; what it stored stays
```

In Docker, name it in `APPS` in the stack file ([docker-compose.yml](../docker-compose.yml); empty there: every app); on
Proxmox VE, tick it in the list the container's script shows. The guide has each way in full:
[any Linux or Mac](../docs/docs/start/linux-mac.md), [Docker](../docs/docs/start/docker.md), [Proxmox VE](../docs/docs/start/proxmox.md)
and [one app or all of them](../docs/docs/start/one-or-all.md).

| | |
| --- | --- |
| Address | `/dns/` at the suite's address (`https://home.example.com/dns/`), and a name of its own if you give it one |
| Database | `iodns`, beside the Shared ioSuite database (the accounts and every setting), both under the suite's one login; the tables are made on the first start and brought up to date by later versions by themselves |

From a shell, in the program folder (`/opt/iosuite` when installed as root):

```sh
.venv/bin/python -m iodns.cli check                     # connect to the databases and say what is there
.venv/bin/python -m iodns.cli compare VIEW              # compare the servers of a view (internal, external…) with the master list
.venv/bin/python -m iodns.cli push VIEW [--prune]       # make every server of the view hold the master list (--prune: also remove what only they hold)
.venv/bin/python -m iodns.cli import SERVER-ID [MODE]   # the master list from one server (MODE: merge, overwrite or replace; default merge)
.venv/bin/python -m iodns.cli ddns [--push]             # find the public address now and update the records that follow it
.venv/bin/python -m iodns.cli export                    # the master list as JSON, on standard output
```

Accounts are the suite's: `iosuite admin NAME --app iodns` makes someone an admin of ioDNS only (`iosuite admin NAME`: of
the whole suite), `iosuite password NAME` sets a password; see [Accounts and roles](../docs/docs/run/accounts.md).

## Configuration

ioDNS has no file of settings. The machine's one file (`config.env` in the program folder) says how to reach the Shared
ioSuite database and which apps run here; everything else is kept in that database. Suite admins change it under
**Settings › Apps › All settings**, which has a section for the whole suite and one for ioDNS, or from a shell;
a change applies when the app starts again:

```sh
iosuite settings iodns        # what may be set, with the value stored now
iosuite set iodns PUBLIC_URL https://dns.example.com    # no value: back to the default
```

| Setting | Meaning |
| --- | --- |
| `PUBLIC_URL`, `SYNC_URL`, `MCP_URL` | an address of its own for the pages, for devices and for MCP clients (`https://dns.example.com`), beside its folder at the suite's address |
| `DATA_DIR` | where the app writes on its own (`iodns/` in the machine's `DATA_DIR`) |
| `DB_NAME` | the name of its database (`iodns`) |
| `CHECK_MINUTES` | minutes between checks (`30`). How often the servers are compared with the master list on their own; 0: only when someone looks |
| `BACKGROUND` | compare the servers and keep dynamic DNS current in the background (`1` or `0`; on by default). Off: nothing is compared and no address is updated until someone asks from the pages |

The suite's own settings (its address, the domain the sign-in is shared on, the time zone, how long deletions are kept), the
machine's file and the three ports are in the guide's [Configuration](../docs/docs/reference/configuration.md).

The DNS servers, their passwords and keys, the views and dynamic DNS are set in the app itself.

## API

The paths below are ioDNS's own: at the suite's address they are inside its folder (`https://home.example.com/dns/api/…`), at a name of its own they are as written. A script signs in with an app password at the pages' address. The [address for devices](../docs/docs/reference/configuration.md#the-three-ports) (port 8443), the one to open to the internet for phones and native apps, serves nothing of ioDNS. MCP clients use the address for MCP (port 8444).

Everything the web app does is a JSON API under `/api/` (documented at `/api/docs`), open to any client signed in with
the user name and an app password (HTTP Basic or a bearer token): `GET /api/entries`, `POST /api/entries`,
`GET /api/sync/<view>`, `POST /api/sync/<view>/apply` (`{decisions: {name: master | server:<id> | delete | skip}, dryRun}`),
`POST /api/sync/<view>/push`, `POST /api/push` (`{names: [...] | null, dryRun}`: those names in every view), `POST /api/servers/<id>/import`, `POST /api/ddns/run`, `GET /api/history`.

## Tests

```sh
pip install -e '.[all,test]'          # in the program folder, once
python -m pytest iodns/tests     # on a test MariaDB of its own: a Docker container it starts, or IOSUITE_TEST_DB=host:port:user:password
```

The comparison and every provider (against a stand-in of its API) are tested without a database; the API tests need a
MariaDB (a Docker container, or the server `IOSUITE_TEST_DB` names) and use in-memory DNS servers (`tests/fake.py`).

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later), see [LICENSE](../LICENSE).

# ioContact

*Contacts for the family, in the ioThing suite (with [ioPix](../iopix/), [ioNote](../ionote/), [ioCalendar](../iocalendar/), [ioHealth](../iohealth/) and the [ioStart](../iostart/) start page).*

A self-hosted contact manager: a web app for the whole family, and the standard protocols every mail, contacts and calendar app already speaks, so the same contacts show up on phones, in Apple Contacts, Outlook, Thunderbird and anywhere else. FastAPI and a single-page vanilla JS app, with everything stored in MariaDB / MySQL, and the suite's shared library (`iosuite_shared`, in [iosuite_shared/](../iosuite_shared/)).

## What it does

- **Contacts** with names (prefix, first, middle, last, suffix, nickname, maiden name, phonetic names), any number of phone numbers, emails and addresses (with labels and a preferred one), birthday (with or without the year), anniversaries and other dates, company, department, job title, social profiles (LinkedIn, Facebook, Instagram, X, Threads, Bluesky, Mastodon, TikTok, YouTube, GitHub, WhatsApp, Telegram, Signal and more), websites, labels, notes and a photo.
- **Relations** between contacts: parents, children, siblings, spouses and partners, grandparents, aunts and uncles, cousins, in-laws, step-family, godparents, friends, colleagues, managers… The other side is kept automatically (make Tim Mary's son and Mary becomes Tim's mother), labels follow the other person's gender (Brother, Sister, Sibling), and a **family tree** page lays the family out by generation. A relation can also name someone who is not a contact.
- **The family and private books**: everyone shares the Family address book; each member also has a private Personal one and can make more private ones; editors also make shared ones. Roles as in the rest of the suite: viewers only read the shared books, members (the default) also keep their own private books, editors change shared contacts, admins also manage users and settings.
- **Sign-in as in iopix**: the sign-in screen is a pick list of the accounts (each with the face of the contact it is linked to as *me*). Sign-in, passwords, sessions, app passwords and the users admin are iosuite_shared's routes (`/api/auth/*`, `/api/suite-admin/*`), the same in every app; repeated wrong passwords are slowed down per visitor and name, at the web sign-in, over HTTP Basic / Bearer and at the LDAP bind. An account whose password an admin removed (Settings › Security › People › No password) signs in with one click, but only at home: from outside those accounts are not offered and their sessions do not work. *Other* types a user name.
- **Birthdays**: the upcoming birthdays and anniversaries, with ages, and a **family birthday calendar** to subscribe to.
- **ioPix**: link a contact to a person named in ioPix. The face from ioPix is the contact's photo, and the only one: ioContact stores no photos of its own, and serves the ioPix face to the web app, phones (CardDAV), vCard exports and the LDAP directory (`jpegPhoto`). A photo in an imported or synced vCard is not kept. The contact links to that person's photos, and *Link by name* links every contact whose name matches exactly one ioPix person. The ioPix people page lists everyone in ioPix and makes a contact from any of them.
- **Duplicates** (same name, email or phone) and merging, **bulk** favorite, label, move, export and delete, search across names, emails, phone digits, companies, addresses, labels and notes.
- **Settings › Security** and **Global settings** (suite admins): the whole suite's people and their role in every app, app passwords and sign-in at the proxy; the apps, keys and tokens; the same panel as on the start page and in every io app (iosuite_shared's `/api/suite-admin/ui.js`).
- Light and dark, phone-sized screens, installable as an app.

## Run

ioContact is one of the apps of [ioSuite](../README.md), one program that runs the apps it is told to. Install the suite
with ioContact in it, alone or with the others, on any Linux machine:

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash -s -- --apps iocontact
```

It asks for the MariaDB server, the first admin and the suite's address, then starts the service; leave `--apps` out
for the list of every app, to tick. On a server that already runs the suite:

```sh
iosuite install --add iocontact       # --remove iocontact stops running it; what it stored stays
```

In Docker, name it in `APPS` in the stack file ([docker-compose.yml](../docker-compose.yml); empty there: every app); on
Proxmox VE, tick it in the list the container's script shows. The guide has each way in full:
[any Linux or Mac](../docs/docs/start/linux-mac.md), [Docker](../docs/docs/start/docker.md), [Proxmox VE](../docs/docs/start/proxmox.md)
and [one app or all of them](../docs/docs/start/one-or-all.md).

| | |
| --- | --- |
| Address | `/contacts/` at the suite's address (`https://home.example.com/contacts/`), and a name of its own if you give it one |
| Devices | CardDAV at `/contacts/dav/`, the birthdays feed at `/contacts/cal/…`; LDAP on its own port (3890), at the [address for devices](../docs/docs/reference/configuration.md#the-three-ports) |
| MCP | `/contacts/mcp` at the address for MCP ([AI assistants](../docs/docs/run/assistants.md)) |
| Database | `iocontact`, beside the Shared ioSuite database (the accounts and every setting), both under the suite's one login; the tables are made on the first start and brought up to date by later versions by themselves |

From a shell, in the program folder (`/opt/iosuite` when installed as root):

```sh
.venv/bin/python -m iocontact.cli check   # connect to the database and say what is there
```

Accounts are the suite's: `iosuite admin NAME --app iocontact` makes someone an admin of ioContact only (`iosuite admin NAME`: of
the whole suite), `iosuite password NAME` sets a password; see [Accounts and roles](../docs/docs/run/accounts.md).

## Configuration

ioContact has no file of settings. The machine's one file (`config.env` in the program folder) says how to reach the Shared
ioSuite database and which apps run here; everything else is kept in that database. Suite admins change it under
**Settings › Global settings › Settings**, which has a section for the whole suite and one for ioContact, or from a shell;
a change applies when the app starts again:

```sh
iosuite settings iocontact        # what may be set, with the value stored now
iosuite set iocontact PUBLIC_URL https://contacts.example.com    # no value: back to the default
```

| Setting | Meaning |
| --- | --- |
| `PUBLIC_URL`, `SYNC_URL`, `MCP_URL` | an address of its own for the pages, for devices and for MCP clients (`https://contacts.example.com`), beside its folder at the suite's address |
| `DATA_DIR` | where the app writes on its own (`iocontact/` in the machine's `DATA_DIR`) |
| `DB_NAME` | the name of its database (`iocontact`) |
| `LDAP_PORT` | LDAP directory: port (`3890`). The read-only address book for mail apps and phones. 0 turns it off |
| `LDAP_HOST` | LDAP directory: listen address. Empty: where the web app listens |
| `LDAP_BASE` | LDAP directory: base (`dc=iocontact`). The search base a client is given |

The suite's own settings (its address, the domain the sign-in is shared on, the time zone, how long deletions are kept), the
machine's file and the three ports are in the guide's [Configuration](../docs/docs/reference/configuration.md).

### ioPix

Nothing to set up: ioContact finds ioPix in the suite's list of apps (the Shared ioSuite database) and reads from it from the server as its own service account (`iocontact-app`) with a read-only app password, both made by itself on first use and listed on the start page's Settings › Security, where a suite admin can revoke them (a new one is made the next time). Behind Cloudflare Access, the suite's Cloudflare Access service token (Settings › Global settings › Keys and tokens) goes along. The people list comes from ioPix's People (the named people with photos) and the faces from ioPix's face crops.

## Updates

The suite is one program with one version, so every app is updated together: **Settings › Global settings › Updates**
(suite admins, in any app) shows the installed version and the newest one, with one **Update** button; from a shell it is
`update.sh` in the program folder, and in Docker the image is pulled. See [Updates](../docs/docs/run/updates.md).

**Settings › Server** shows the version ioContact runs and has **Restart**. The log is one for the whole copy of the program,
each line marked with its app: suite admins read it under **Settings › Global settings › Logs**.

Everything about the app is under one Settings page (the sidebar and the avatar menu; a change is saved the moment it
is made): your own tabs (account, display, apps and devices, address books), then for admins server, and for suite admins
security and global settings. Tidying the contacts is **Clean up** in the sidebar (below).

## Reverse proxy and HTTPS

ioContact is reached through the suite's three ports: the pages (80), devices (8443) and MCP (8444). A reverse proxy gives each
a name and HTTPS, for the whole suite at once, and can make people sign in first (Cloudflare Access, Authelia, oauth2-proxy):
[Reverse proxy and HTTPS](../docs/docs/run/reverse-proxy.md) and [Cloudflare Tunnel and Access](../docs/docs/run/cloudflare.md) in the
guide have the set-up, with Caddy and nginx examples, sign-in at the proxy and the optional check of app passwords at
Cloudflare's edge ([cloudflare/edge-auth](../cloudflare/edge-auth/README.md)).

iOS and macOS want HTTPS for a CardDAV account outside the home network, and a password travels with every CardDAV request. The LDAP directory speaks plain LDAP on a port of its own (3890): keep it on the home network, or put a TLS proxy (stunnel, HAProxy, nginx stream) in front for `ldaps://`. Because it is not encrypted it takes an **app password** only, never the account's own password (which opens every app of the suite); it closes a connection that has been silent for ten minutes and takes at most 16 connections from one address.

## API

The paths below are ioContact's own: at the suite's address they are inside its folder (`https://home.example.com/contacts/api/…`), at a name of its own they are as written. Phones, native apps and scripts use the [address for devices](../docs/docs/reference/configuration.md#the-three-ports) (port 8443; `https://sync.example.com/contacts/api/…` behind a reverse proxy), which takes app passwords and tokens and nothing else; from inside the home network an app password also works at the pages' address. MCP clients use the address for MCP (port 8444).

| For | Standard | Where |
| --- | --- | --- |
| Contacts apps: Apple Contacts (Mac, iPhone, iPad), DAVx⁵ on Android, Thunderbird, Evolution, GNOME Contacts, KDE | **CardDAV** (RFC 6352) with sync-collection (RFC 6578), ctag, discovery via `/.well-known/carddav` (RFC 6764) and current-user-principal | `/dav/` |
| Any app that reads contact files | **vCard 3.0** (RFC 2426) and **4.0** (RFC 6350), with Apple's extensions (relations, dates, social profiles and custom labels survive in Apple Contacts); vCard 2.1 is read | CardDAV, `/api/…?format=vcard`, import/export |
| Web and JSON clients | **REST/JSON** with **jCard** (RFC 7095) by content negotiation (`Accept: application/vcard+json` or `text/vcard; version=4.0`) | `/api/`, OpenAPI docs at `/api/docs` |
| Mail apps, desk phones, printers | **LDAP v3** (RFC 4511), read-only, inetOrgPerson plus Thunderbird's mozillaAbPersonAlpha attributes | port 3890 (389 in the Docker stack) |
| Calendars: Apple Calendar, Google Calendar, Outlook, Thunderbird | **iCalendar** (RFC 5545) subscription of birthdays and anniversaries, yearly events: each link has a secret of its own, made in Settings › Apps and devices and shown once (an Apple profile gets its own; only a hash is kept, in the Shared ioSuite database) | `/cal/<secret>/family.ics`, `/cal/<secret>/all.ics` |
| Moving in and out | vCard files, jCard, and **CSV in Google Contacts' and Outlook's layouts** | Import and export page, `/api/import`, `/api/export` |
| AI assistants: Claude and anything else that speaks MCP | **Model Context Protocol** (streamable HTTP, and stdio) | `/mcp` (switched on in Settings › Server) |

**iPhone, iPad and Mac in one step:** Settings › Apps and devices › *Download the profile* gives a configuration profile
(`.mobileconfig`) with the CardDAV account and, if you like, the birthday calendar subscription (and the LDAP
directory for Mail on a Mac), with a new app password for that device inside (or none, and the device asks). That password works for CardDAV and LDAP
only, so a lost phone or a leaked profile file does not reach the web app, the REST API or MCP. Open the
page in Safari on the iPhone, tap Download, then Settings › Profile Downloaded › Install.

Where the suite has more than one app that syncs (ioCalendar, ioContact, ioTask), *Set up* in the same box offers
**All apps**: one profile with the account of each, and an app password of its own per app (the birthday calendar and
the LDAP directory are in ioContact's own profile only).

Settings › Apps and devices shows the exact addresses to type; Settings › Account makes **app passwords**: one per phone or app, revocable on its own, used with your user name for CardDAV, LDAP and the REST API (HTTP Basic, or `Authorization: Bearer <app password>`). *Contacts apps only* (ticked by default) limits a password to CardDAV and LDAP: the web sign-in, the REST API and MCP answer it with 403. Untick it for a script or an AI assistant.

```sh
curl -u alex:iocontact-xxxxxxxx-… -H 'Accept: application/vcard+json' https://sync.example.com/contacts/api/contacts?q=smith
curl -u alex:iocontact-xxxxxxxx-… https://sync.example.com/contacts/api/contacts/12?format=vcard4
curl -u alex:iocontact-xxxxxxxx-… -X POST -H 'Content-Type: text/vcard' --data-binary @card.vcf 'https://sync.example.com/contacts/api/contacts?book=1'
```

## MCP server

ioContact is also an MCP server, as iopix is, so an assistant such as Claude can work with the contacts: look people up,
read everything about one, add and correct contacts, link relatives and walk the family tree, list birthdays, find and
merge duplicates, import and export vCard and CSV, link contacts to ioPix people, and, for admins, check the server's
health, look for a new version and install it.

It is off until an admin turns it on in **Settings › Server**; off, `/mcp` does not answer
at all. Every assistant signs in with an **app password** (Settings › Account › App passwords), as HTTP Basic or
`Authorization: Bearer <app password>`, and acts as that account: it sees the shared books and that account's private
ones, and may change what the account may change in the web app. The server tools need an admin.

```sh
claude mcp add --transport http iocontact https://mcp.example.com/contacts/mcp --header "Authorization: Bearer iocontact-xxxxxxxx-…"
```

Apps that take a JSON configuration and only start local processes (Claude Desktop, for example) can reach it through
`mcp-remote`: `{"mcpServers": {"iocontact": {"command": "npx", "args": ["-y", "mcp-remote", "https://mcp.example.com/contacts/mcp", "--header", "Authorization: Bearer ioc-…"]}}}`.
On the server itself, `.venv/bin/python -m iocontact.mcp --user NAME` serves the same tools over stdio.

The tools: `overview`, `list_address_books`, `search_contacts`, `get_contact`, `get_contacts`, `get_vcard`, `view_photo`,
`get_relatives`, `family_tree`, `upcoming_dates`, `birthdays_in_month`, `list_labels`, `relation_types`, `social_services`,
`find_duplicates`, `export_contacts`, `connection_details`, `list_iopix_people`; `create_contact`, `update_contact`,
`delete_contact`, `add_relation`, `remove_relation`, `set_labels`, `set_favorite`, `move_contacts`, `merge_contacts`,
`import_contacts`, `link_iopix_person`, `auto_link_iopix`, `create_address_book`; upkeep:
`find_duplicates`, `preview_merge`, `merge_contacts`, `mark_not_duplicates`, `list_merges`, `undo_merge`,
`data_quality_report`, `fix_data_quality`; enrichment: `lookup_contact`, `suggest_contact_update`, `list_suggestions`
(an assistant proposes; only a person accepts, in the web app); and for admins `diagnostics`, `test_iopix`,
`list_accounts`. An app password cannot make more app passwords over MCP.

## Clean up and enrichment

**Clean up** in the web app's sidebar has four tabs, for everyone, on the address books they can see:

- **Duplicates.** Contacts that are probably one person, scored, with the reasons: the same email or phone (written with
  or without the country code), the same name (accents, case and swapped first and last names do not matter), a
  nickname (Bob for Robert, Liesbeth for Elisabeth…), a similar spelling, the same birthday or company. Other
  birthdays, other genders, a Sr./Jr. or a relation between the two count against. The first name has to fit: people
  in one household who share a last name, an address, a home phone or a family email are never offered as
  duplicates, and an email or number on three or more contacts is treated as the household's. **Compare and merge** shows them side by side: which to keep, and for every field where they
  disagree (name, birthday, company, ioPix person…) which value; phones, emails, addresses, profiles, labels and relations
  are combined, each with a box to leave one out. **Not duplicates** keeps two people apart for good.
- **Data quality.** Contacts without a name, email addresses and phone numbers that do not look right, impossible
  birthdays, NAMES IN CAPITALS, the same email or phone twice on a contact, relations to a name that is now a
  contact, numbers without the country code, contacts with no way to reach them; with
  one-click fixes where a fix is safe (capitalising, removing repeats, linking, adding the country code you give).
- **Suggestions.** Enrichment that waits for you: nothing changes a contact until you accept it (one by one, or all for
  a contact), and what you dismiss is not offered again. **Look up** on a contact (or *Look up all contacts*) asks the
  public interfaces that allow it: Gravatar by email (sent as a hash) for the name, job, company, place and the
  profiles the person verified there, and the contact's GitHub, Mastodon and Bluesky profiles. LinkedIn, Facebook,
  Instagram and X have no lookup apps may use; an assistant connected over MCP can research people there and file
  what it finds with `suggest_contact_update`, with the page it found it on.
- **Merge history.** Every merge keeps the contacts as they were for 30 days, so **Undo** brings them back, relations included. After 30 days, or once a merged contact is purged for good, the merge is forgotten.

## Tests

```sh
pip install -e '.[all,test]'          # in the program folder, once
python -m pytest iocontact/tests     # on a test MariaDB of its own: a Docker container it starts, or IOSUITE_TEST_DB=host:port:user:password
```

Covered: vCard 2.1/3.0/4.0 and jCard reading and writing (an Apple Contacts card round-trips with relations, dates, social profiles, custom labels and unknown properties), relations and their inverse side, search, content negotiation, Google and Outlook CSV import and every export format, roles and private books, app passwords over Basic and Bearer and the CardDAV/LDAP-only limit, the birthday calendar, duplicates and merging, CardDAV discovery, PUT with preconditions and UID conflicts, multiget, addressbook-query, sync-collection with deletions, LDAP bind (and its throttle) and search with substring, phone and size-limit cases, CardDAV bodies with XML entities (refused), the MCP server (switch, sign-in, reading, changing, relations, a viewer's limits), duplicate scoring (nicknames, shared home numbers, other birthdays), merging with choices and undo, the data quality checks and fixes, and enrichment (lookups, suggestions that wait, accepting and dismissing, over MCP too). CI runs them against MariaDB.

## Layout

The package `iocontact/` of the repository:

```
main.py            the application: start-up (tables, first admin, LDAP), the suite's middleware, status and routes
access.py          who may call a route: the markers every /api route carries (public, signed_in, admin)
config.py          the settings: the suite's standard names (iosuite_shared.config) and ioContact's own
auth.py            iosuite_shared's Auth for this app, and the updater
api.py             the REST API, import/export, calendar feed and ioPix routes (sign-in and accounts: iosuite_shared's routers)
carddav.py         CardDAV / WebDAV
ldapd.py           the LDAP directory (asyncio, its own BER)
vcard.py           vCard 2.1/3.0/4.0 and jCard
csvio.py           Google and Outlook CSV
model.py           address books and contacts in MariaDB, relations, duplicates, merging
relations.py       relation types, inverses and labels
calendar.py        the iCalendar birthday feed
iopix.py           the ioPix client
quality.py         duplicates (scored), merging with choices and undo, data quality checks and fixes
enrich.py          enrichment: the public lookups and the suggestions queue
mcp/               the MCP server: base (who is asking, finding contacts), read, write and admin tools
users.py           accounts as ioContact sees them (the Shared ioSuite database's, through iosuite_shared): roles, the "me" contact, every account's private book, the calendar links
static/            the web app (index.html, app.js, app.css, icons)
```

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later), see [LICENSE](../LICENSE).

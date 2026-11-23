# ioNote

*Your notes, clipboard snippets and screenshots, searchable everywhere.*

The server behind ioNote: a web app for reading, writing and organising notes from any browser, and the API the
ioNote apps for Mac and iPhone/iPad use ([iosuite-apps](https://github.com/avandeputte/iosuite-apps/tree/main/ionote)). Everything is kept
in one MariaDB/MySQL database, pictures included. It is built the same way as its sibling
[iopix](../iopix/): FastAPI with a single-page vanilla JS app, the same accounts, roles
and sign-in (Cloudflare Access too), the same installer, updater, Docker image and MCP server.

## What it does

- **Notes**: a title, text, tags, a folder, a pin, and optionally a picture (a screenshot, a photo) with the text
  read from it. Notes come from the Mac (clipboard, screenshots, right-click › Save to ioNote), the iPhone (paste,
  photos, the share sheet), the web app, or an assistant through MCP.
- **Web app**: folders and tags in the sidebar (right-click one to rename it, give it a colour or delete it; drag a
  note onto a folder to file it), all notes / pinned / pictures / no folder / trash, sorting, full-text search,
  editing that saves as you type, pictures pasted (⌘V) or dropped anywhere become notes, copy text or picture,
  download. Installs like an app on a phone (PWA); light, dark or the device's theme. Laid out like iopix: the
  sidebar (dockable) has the views, Folders, Tags and Manage (trash, change log, import and export), with Settings at its
  foot; the search, New note and your account are along the top. On a phone the sidebar is a bottom bar with More.
- **Markdown and checklists**: a note's text is shown formatted (headings, **bold**, lists, links, code, quotes), and
  `- [ ]` lines are boxes you tick right there, on the list card as progress (2/5). The pencil (or a click on the text)
  edits it, with a formatting bar above the text: bold (⌘B), italic (⌘I), strikethrough (⇧⌘X), code (⌘E), link (⌘K),
  heading (⇧⌘H, again for ## and ###), bulleted (⇧⌘8) and numbered (⇧⌘7) lists, checklist (⇧⌘L), quote (⇧⌘.), code
  block and divider. Each one toggles (bold text turns plain again) and ⌘Z undoes it; Enter continues a list.
- **Attached files**: besides its picture a note holds up to 50 files (PDFs, more pictures, documents; up to
  `MAX_IMAGE_MB` each), kept in the database too. A PDF's text, a text file's and (with RapidOCR) a picture's are read
  for search. Drop files on an open note to attach them, or on the list to make a note of each.
- **Templates** (Manage › Templates, New note ▾): a title, text, tags and a folder for new notes; `{{date}}`,
  `{{time}}`, `{{datetime}}`, `{{weekday}}`, `{{month}}`, `{{year}}`, `{{tomorrow}}` and `{{yesterday}}` are filled in
  when a note is made. The apps sync them. Every account starts with six standard ones (Meeting notes, Daily journal,
  To-do list, Weekly review, Project plan, Shopping list); deleted ones stay deleted until "Add back any you deleted".
- **Related notes and suggestions**: under each note, the notes most like it (words and tags in common), and the tags
  and folder those notes suggest for it, one click to apply.
- **Trash**: deleted notes stay 30 days, then they are deleted for good (text, picture, files; a tombstone stays so
  every device drops the note too). Empty trash and Delete for good do it at once.
- **Search**: every word you type must match (prefix) in the title, the text, the text in the picture or the tags,
  or in one of its attached files, through MariaDB's full-text index.
- **Text in pictures**: read on the device where the picture was taken (Apple's Vision framework, on the Mac and
  iPhone), and sent along; for pictures added in the web app the server reads it itself with RapidOCR.
- **Settings**: Account (with your app passwords) and Display for everyone signed in (the same panels as every io app), Server for admins; a change is saved the moment it is made.
- **Settings › People** (suite admins): the whole suite's people and their role in every app, app passwords, keys and tokens, the apps (default role, sign-in required) and sign-in at the proxy; the same panel as on the start page and in every io app (iosuite_shared's `/api/suite-admin/ui.js`).
- **Offline**: the apps keep a full copy and send their changes when the server can be reached; the API settles
  conflicts per note by the time of the edit (below).
- **The clipboard Inbox stays on each device.** Only notes you save go to the server.

## Run

ioNote is one of the apps of [ioSuite](../README.md), one program that runs the apps it is told to. Install the suite
with ioNote in it, alone or with the others, on any Linux machine:

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash -s -- --apps ionote
```

It asks for the MariaDB server, the first admin and the suite's address, then starts the service; leave `--apps` out
for the list of every app, to tick. On a server that already runs the suite:

```sh
iosuite install --add ionote       # --remove ionote stops running it; what it stored stays
```

In Docker, name it in `APPS` in the stack file ([docker-compose.yml](../docker-compose.yml); empty there: every app); on
Proxmox VE, tick it in the list the container's script shows. The guide has each way in full:
[any Linux or Mac](../docs/docs/start/linux-mac.md), [Docker](../docs/docs/start/docker.md), [Proxmox VE](../docs/docs/start/proxmox.md)
and [one app or all of them](../docs/docs/start/one-or-all.md).

| | |
| --- | --- |
| Address | `/notes/` at the suite's address (`https://home.example.com/notes/`), and a name of its own if you give it one |
| Devices | the Mac and iPhone apps at `/notes/api/…`, at the [address for devices](../docs/docs/reference/configuration.md#the-three-ports) |
| MCP | `/notes/mcp` at the address for MCP ([AI assistants](../docs/docs/run/assistants.md)) |
| Database | `ionote`, beside the Shared ioSuite database (the accounts and every setting), both under the suite's one login; the tables are made on the first start and brought up to date by later versions by themselves |
| On the server | libheif, for pictures from an iPhone (`libheif1`); the installer, the Proxmox script and the container image have them |

From a shell, in the program folder (`/opt/iosuite` when installed as root):

```sh
.venv/bin/python -m ionote.cli check   # connect to the databases and say what is there
```

Accounts are the suite's: `iosuite admin NAME --app ionote` makes someone an admin of ioNote only (`iosuite admin NAME`: of
the whole suite), `iosuite password NAME` sets a password; see [Accounts and roles](../docs/docs/run/accounts.md).

## Configuration

ioNote has no file of settings. The machine's one file (`config.env` in the program folder) says how to reach the Shared
ioSuite database and which apps run here; everything else is kept in that database. Suite admins change it under
**Settings › Apps › All settings**, which has a section for the whole suite and one for ioNote, or from a shell;
a change applies when the app starts again:

```sh
iosuite settings ionote        # what may be set, with the value stored now
iosuite set ionote PUBLIC_URL https://notes.example.com    # no value: back to the default
```

| Setting | Meaning |
| --- | --- |
| `PUBLIC_URL`, `SYNC_URL`, `MCP_URL` | an address of its own for the pages, for devices and for MCP clients (`https://notes.example.com`), beside its folder at the suite's address |
| `DATA_DIR` | where the app writes on its own (`ionote/` in the machine's `DATA_DIR`) |
| `DB_NAME` | the name of its database (`ionote`) |
| `MAX_IMAGE_MB` | largest image (MB) (`15`). MariaDB's max_allowed_packet (16 MB by default) must be larger |
| `THUMB_SIZE` | thumbnail size (pixels) (`480`) |
| `THUMB_QUALITY` | thumbnail quality (`80`). JPEG quality, 1 to 95 |

The suite's own settings (its address, the domain the sign-in is shared on, the time zone, how long deletions are kept), the
machine's file and the three ports are in the guide's [Configuration](../docs/docs/reference/configuration.md).

## Updates

The suite is one program with one version, so every app is updated together: **Settings › Servers › Updates**
(suite admins, in any app) shows the installed version and the newest one, with one **Update** button; from a shell it is
`update.sh` in the program folder, and in Docker the image is pulled. See [Updates](../docs/docs/run/updates.md).

The suite runs one version, so **Settings › Servers › Updates** shows it with a line and a **Restart** button for each server the suite runs on. The log is one for the whole copy of the program,
each line marked with its app: suite admins read it under **Settings › Servers › Logs**.

## Reverse proxy and HTTPS

ioNote is reached through the suite's three ports: the pages (80), devices (8443) and MCP (8444). A reverse proxy gives each
a name and HTTPS, for the whole suite at once, and can make people sign in first (Cloudflare Access, Authelia, oauth2-proxy):
[Reverse proxy and HTTPS](../docs/docs/run/reverse-proxy.md) and [Cloudflare Tunnel and Access](../docs/docs/run/cloudflare.md) in the
guide have the set-up, with Caddy and nginx examples, sign-in at the proxy and the optional check of app passwords at
Cloudflare's edge ([cloudflare/edge-auth](../cloudflare/edge-auth/README.md)).

The Mac and iPhone apps use the address for devices, which stays outside a sign-in at the proxy.

## Users and permissions

Accounts are the **ioThing suite's shared accounts**, kept in the **Shared ioSuite database** (a MariaDB database
shared with iopix and ioContact, used through the ioSuite shared library, [`iosuite_shared`](../iosuite_shared/); besides the accounts it holds sessions,
roles, the suite's list of apps and the suite-wide settings), so one name, password and session serve every app, and
someone signed in at `photo.example.com` is signed in at `notes.example.com` too when the apps share a domain
(`COOKIE_DOMAIN`). What is ioNote's own is kept per app: the role an account holds here and its settings. A
*suite admin* is admin in every app. The machine's file (`config.env` in the program folder) says how to
reach that database; its tables are created at start. The installer (or `ADMIN_USER` / `ADMIN_PASSWORD` in a container's
environment, or the person icon in the web app) creates the admin. Once an
account exists:

**Notes are private to each account.** Every note, folder, tag colour and change-log line belongs to the account
that made it; nobody else sees, searches, syncs, exports or changes it, admins included (their extra rights are
about the server, not other people's notes). The notes made while the install was still open (before the first
account) stay with the open install: export them before making the first account and import them after. A note id that belongs to another account is answered as if it did not exist.

**The Family space is the exception.** A note marked Family (the wifi password, the bin days, the packing list) is
everyone's who has a role here: viewers and members read and search it, editors and admins write it, change it,
delete it, and take it back out. In the web app it is the **Family** view in the sidebar; a note is put there, or
made one's own again, with the folder menu on the note (a family note is in no folder, since folders are each
account's own; tags group them). Taking a note out makes it the editor's who did it, and it disappears from the
others' devices at their next sync. In the API a note carries `family` (true or false); `GET /api/notes?family=1`
lists the Family space, `/api/meta` and `/api/sync` say `familyWrite` (whether this account may change family
notes), and a change to a family note by someone who only reads it is answered like an older edit: 409 with the
server's copy (`stale` in a sync push), which a device takes. When an account is deleted its own notes go; what
it put in the Family space stays.

| Who | Can |
| --- | --- |
| Not signed in | nothing but the sign-in screen |
| **viewer** | read and search their own notes and the family's; their own settings kept on the server |
| **member** (the default) | plus every change to their own notes, folders, tags and templates, and export/import of them (Import and export; the Mac and iPhone apps sign in as a member or more) |
| **without a password** | a member at most; signs in with one click from the account picker, on the home network only |
| **editor** | plus the Family space: add notes to it, change and delete them, take them back out |
| **admin** | plus settings, accounts, updates and the server log |

**Sign-in required** (Settings › Apps › The apps, on by default) also closes the open routes to visitors, but for the app shell, `/api/status` and the sign-in routes (the MCP endpoint wants an app password either way).
Sessions are random tokens in an HttpOnly cookie (`iothing_session`, shared by the apps on the domain) valid for
30 days and renewed while in use; each records where it began and was last seen (address, through Cloudflare or
not, web or which app): `GET /api/auth/sessions` for your own, `GET /api/suite-admin/users/<id>/sessions` for suite admins. Passwords
are Argon2id-hashed; wrong passwords cost a growing wait. Write requests from another site are refused.

ioNote writes its row in the **suite's list of apps** (name, version, colour, icon, address, the copy of the program it
runs in) as it starts, so the start page and the other apps find it without anyone typing an address: its folder at
the suite's address, or its own `PUBLIC_URL` when it has one.

## API

The paths below are ioNote's own: at the suite's address they are inside its folder (`https://home.example.com/notes/api/…`), at a name of its own they are as written. Phones, native apps and scripts use the [address for devices](../docs/docs/reference/configuration.md#the-three-ports) (port 8443; `https://sync.example.com/notes/api/…` behind a reverse proxy), which takes app passwords and tokens and nothing else; from inside the home network an app password also works at the pages' address. MCP clients use the address for MCP (port 8444).

Every route is under `/api`; `GET /api/docs` lists them. JSON in and out; times are seconds since 1970 (UTC); ids are
UUID strings the device chooses (`UUID().uuidString`).

| | |
| --- | --- |
| `GET /api/status` | version, whether sign-in is required, and (signed in) the current `rev` |
| `POST /api/auth/login` `{name, password}` | signs in; the session cookie follows. `GET /api/auth/me`, `POST /api/auth/logout` |
| `GET /api/sync?since=<rev>&limit=500` | every note, folder, tag colour and template changed after `rev`, deletions included (`deleted: true`), oldest change first; ask again with `since=<rev>` while `more` is true. A new device starts from 0 |
| `PUT /api/notes/{id}` | create or update a note: any of `title, body, ocrText, source, sourceApp, createdAt, tags, pinned, folderID, deleted`, plus `updatedAt`, when the edit was made on the device |
| `POST /api/sync/push` `{notes:[], folders:[], tags:[]}` | a device's queued offline changes in one request; each answered with `ok` or `stale` and the server's copy |
| `PUT /api/notes/{id}/image` | the picture as the raw body (`Content-Type: image/png`...); `GET` it back, or `/thumb` for a 480 px JPEG. `imageSHA` on the note changes with the picture |
| `DELETE /api/notes/{id}?ts=` | to the trash (a tombstone that syncs); `POST /api/notes/{id}/restore` |
| `PUT /api/folders/{id}` `{name, color, deleted, updatedAt}` | folders; `PUT /api/tags/{name}/color` `{color, updatedAt}` for tag colours |
| `GET /api/notes?q=&folder=&tag=&pinned=&image=&sort=` | search and list (the web app's view) |
| `PUT /api/notes/{id}/attachments/{aid}?name=` | attach a file (raw body, its `Content-Type`; `X-Ionote-Text`: text the device read from it, percent-encoded). Each note lists its files under `attachments` (`id, name, mime, bytes, sha, width, height`); `GET …/{aid}` (`?download=1`), `…/{aid}/thumb`, `…/{aid}/text`, `PATCH {name}`, `DELETE` |
| `PUT /api/templates/{id}` `{name, title, body, tags, folderID, deleted, updatedAt}` | templates (also in `/api/sync` as `templates`, and in a push); `POST /api/notes {template: id}` makes a note from one |
| `POST /api/templates/standard` | adds back the standard templates that are missing |
| `GET /api/notes/{id}/related` | notes like this one, and the tags and folder they suggest: `{notes, tags, folder}` |
| `POST /api/trash/empty`, `DELETE /api/trash/{id}` | delete for good; notes in the trash are purged after 30 days anyway (they sync as tombstones with nothing in them) |

**Conflicts**: each note, folder and tag colour is settled on its own by `updatedAt`. The server never takes an `updatedAt` later than its own clock, so a device whose clock runs ahead does not win every conflict. A change older than what the
server has is answered with 409 (or `stale` in a push) and the server's copy, which the device then keeps. An empty
`ocrText` never erases text read earlier. Every change gets a new `rev`, from one counter, which is what `since` counts.

## MCP server

Settings › Apps turns on an MCP endpoint at `/mcp` (off by default), the same in every app of the
suite. An assistant such as Claude can then:

- read: `notes_overview`, `search_notes` (words, folder, tag, pinned, picture, source, dates, sort), `get_note`,
  `view_note_image` (the picture itself, small or large), `read_attachment` (a file's text, or the picture),
  `list_folders`, `list_tags`, `list_templates`, `recent_changes`, `list_trash`
- help: `related_notes` (notes like one, with the tags and folder they suggest), `suggest_organization` (tags and
  folders for unfiled notes), `notes_digest` (a period's notes with their text, to summarise); and three prompts the
  client can offer: *Summarise a note*, *Weekly review*, *Tidy up unfiled notes*
- write, as a member: `create_note` (optionally with a picture, or from a template), `update_note` (replace or append
  text, tags, folder, pin), `organize_notes` (many notes at once), `delete_note`, `restore_note`, `manage_folder`,
  `manage_tag`, `manage_template`, `attach_file`, `remove_attachment`, `empty_trash`; family notes are changed, and
  notes put in or taken out of the Family space (`family` on `create_note` and `update_note`), as an editor
- operate, as an admin: `diagnostics`, `server_log`

Every assistant signs in with an **app password** (Settings › Account › App passwords), as HTTP Basic or
`Authorization: Bearer <app password>`, and acts as that account: it sees that account's notes and the family's, and changes
what that account may change (`notes_overview` names the account and says whether it may change family notes). Off, `/mcp` does not answer at all.

```sh
claude mcp add --transport http ionote https://mcp.example.com/notes/mcp --header "Authorization: Bearer ionote-xxxxxxxx-…"
```

Apps that take a JSON configuration and only start local processes (Claude Desktop, for example) can reach it through
`mcp-remote`: `{"mcpServers": {"ionote": {"command": "npx", "args": ["-y", "mcp-remote", "https://mcp.example.com/notes/mcp", "--header", "Authorization: Bearer ionote-…"]}}}`.
`python -m ionote.mcp --user NAME` (or `MCP_USER`) serves the same tools on stdio, as that account.

## Export, import and backups

Import and export (the sidebar) › Export downloads every note as Markdown (with front matter: id, dates, tags, source) next to its picture and its files,
in a directory per folder, plus `notes.json` with everything. Such a zip imports again on any ioNote server (Import
and export › Import): records keep their ids, and a newer copy on the server wins (a zip from another account on the same server comes in as new notes). For backups, back the database up
(`mariadb-dump --single-transaction ionote`): notes, pictures, accounts and settings are all in it.

## Tests

```sh
pip install -e '.[all,test]'          # in the program folder, once
python -m pytest ionote/tests     # on a test MariaDB of its own: a Docker container it starts, or IOSUITE_TEST_DB=host:port:user:password
```

The notes (`ionote_test`) and the Shared ioSuite database
(`ionote_test_auth`) go to a test MariaDB of their own: a Docker container the suite starts (`iosuite-test-mariadb`),
or `IOSUITE_TEST_DB=host:port:user:password`; never a live database.
CI runs both.

## Layout

The package `ionote/` of the repository:

```
main.py          the FastAPI app: the suite's middleware (who is asking, require sign-in, cross-site writes), whose notes, status, /mcp, static files
access.py        who may call a route: the markers every /api route carries
config.py        the settings: the suite's standard names (iosuite_shared.config) and ioNote's own
db.py            the database (MariaDB/MySQL, through iosuite_shared.db), its tables, the rev counter
notes.py         notes, folders, tag colours, templates, search, related notes, the trash, sync and conflicts
images.py        pictures as BLOBs with a thumbnail
attachments.py   files attached to notes (PDFs and the like), with the text read from them
ocr.py           RapidOCR for pictures added in the web app
backup.py        export and import
auth.py          accounts, sessions and roles, the updater (iosuite_shared; proxy sign-in: iosuite_shared.proxyauth through auth.proxy)
routes/          the HTTP API
mcp/             the MCP server: read, write and operator tools
static/            the web app (index.html, app.css, js/*.js modules, service worker, icons)
tests/             pytest, on a test MariaDB
```

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later), see [LICENSE](../LICENSE).

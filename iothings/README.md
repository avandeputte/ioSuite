# ioThings

*Everything you own, in the ioThing suite (with [ioPix](../iopix/), [ioNote](../ionote/), [ioContact](../iocontact/), [ioCalendar](../iocalendar/), [ioTask](../iotask/), [ioRecipe](../iorecipe/), [ioMoney](../iomoney/), [ioHealth](../iohealth/) and the [ioStart](../iostart/) start page).*

A self-hosted inventory of everything you own, in place of Homebox: what the family has and where it is (the appliances,
the tools, the furniture, the electronics, the car, the books, the camping gear, what is stored in the attic), with the manuals, receipts, photos and warranties, and the upkeep each thing
needs (the boiler's yearly service, the car's MOT, the fridge's water filter) with a maintenance log. FastAPI and a
single-page vanilla JS app, with everything stored in MariaDB / MySQL (the files too), and the suite's shared library
([`iosuite_shared/`](../iosuite_shared/)).

## What it does

- **Things** with a name, a description, how many, maker, model and serial number, an asset id, a link, the purchase
  (when, where, the price), the warranty (until a day, or for life, and its details), insured or not, notes, and
  **fields of their own** (filter size, paint colour, the code of the safe). Searching finds words in any of them, in
  the place and in the labels.
- **Places** as a tree (House / Kitchen / Drawer by the sink): deleting one moves what was in it one level up.
  **Labels** with a colour. Both in the sidebar, with how many things each holds.
- **Whose it is**: a thing can be marked as one or more people's of the family (Emma's bike, Dad's laptop, the
  children's games console); marked as nobody's, it is the household's. The family is the suite's one list
  (Settings › Security › Family, suite admins), with the same colours, initials and faces as in ioTask and
  ioCalendar, and everyone in it can be given a thing, whether or not they use ioThings. The sidebar's **Family**
  lists each person with how many things are theirs and shows them; the cards and the table show their faces;
  searching a name ("emma", "emma's") finds their things too. The REST API (`people` on a thing, `?person=` on the
  list) and the MCP tools (`people`, `search_items(person=...)`) do the same.
- **Files**: photos (turned upright, with a small copy for the cards), manuals, receipts, warranty cards and anything
  else, picked, dropped on the thing or taken with the phone. Up to `MAX_FILE_MB` each (100). They are kept in the
  database in 4 MB parts, so a backup of the database has them and nothing else needs one.
- **Upkeep**: what a thing needs every so many days, weeks, months or years, and when it is next due. **Done** (the
  day, the cost, who did it) writes a line in the thing's **maintenance log** and moves the upkeep on (a month after
  31 January is the last day of February). The Upkeep page lists everything by when it is due: late, this week, this
  month, later. One-off lines (a repair, a part replaced) go in the log too.
- **ioTask**, when it is part of the suite: an upkeep can also be a repeating task in one of your task lists (made as
  you, with a link back to the thing). Ticked off in ioTask, the new due day shows in ioThings the next time the thing
  is opened; **Done** in ioThings moves the task on; removing the upkeep removes its task. Nothing to set up.
- **Warranties**: a badge on each thing, a page of the ones ending within 30 days, and a word in the morning
  notification 30 days, 7 days and on the day before one ends.
- **Archive** for a thing sold, given away or thrown out: it keeps its story, and who it went to for how much.
- **The things as cards or a table**, by name, the newest, recently changed, price, when bought or when the warranty
  ends; what they cost together on the front page. **Duplicate** makes the next one of a kind quickly. **Print** gives
  one thing on paper.
- **For the insurer: everything in one PDF** (Import and export, anyone): every thing with all its details, its photos
  and its receipts (pictures shown, PDFs put in whole after the thing's page; no manuals, warranty cards or log),
  behind a front page with the total paid and a list of everything that links to each thing. The PDF's bookmarks go
  by place and thing. Keep it away from the house and make a new one now and then. Photos are made smaller so the
  file stays easy to copy. It is made in
  the background; the last one is kept until the next one or a restart. DejaVu Sans writes it when the system has it
  (the installer installs `fonts-dejavu-core` when it is missing and it runs as root; the container image has it), Helvetica otherwise.
- **Homebox, straight from the server** (editors, Import and export › From a Homebox server): give Homebox's address
  and the email and password you sign in to it with, and ioThings reads everything through Homebox's API: the things
  with all their details, the places, the labels with their colours, the own fields, the **photos, manuals, receipts
  and warranties**, and the completed **maintenance log**. It runs in the background with its progress on the page.
  Running it again brings things up to date (the same bytes, the same log line are not added twice), and things from
  an earlier CSV import are taken over (same name, same place). The Homebox password is used for the import and not
  kept. Both shapes of Homebox's API are read: `/api/v1/items` (up to v0.2x) and the newer `/api/v1/entities`.
  Maintenance that was only scheduled is listed as left out (add it as upkeep). The server must reach Homebox: one
  behind Cloudflare Access needs the address it has on the home network.
- **Homebox's CSV**: Tools › Export inventory in Homebox gives a CSV file; Import and export takes it, with its places
  (made as needed), labels and `HB.field.*` fields. Importing the same file again changes what it brought instead of
  adding it twice (Homebox's `HB.import_ref`). The export writes Homebox's format, so it goes back into Homebox, or
  into a spreadsheet. Homebox's CSV has no photos, manuals or log: the import from the server brings those.
- **Notifications** (Settings › Account › Notifications): at your morning time, the upkeep that is due and is not an
  ioTask task (ioTask reminds of those itself), and the warranties ending.
- **Linked**: a thing can be linked to events, tasks, notes, contacts, recipes and photos of the other apps, and they
  to it; the start page's search finds things too. Linked to the ioMoney transaction that paid for it, the thing
  shows the amount, the day and the account, and the transaction shows the thing with how long its warranty runs.
- **Roles as in the other io apps**: viewers look; members (the default) add things, attach files and keep the upkeep
  and the log; editors change and delete everything, and keep the places and labels in order; admins also choose the
  currency (Settings › Things) and run the server. The same accounts, passwords and app passwords as the other io apps.
- **Settings › Security** and **Global settings** (suite admins): the suite's people, their role in every app, app
  passwords and sign-in at the proxy; the apps, keys and tokens (iosuite_shared's panel, the same in every app).
- Light and dark, phone-sized screens, installable as an app.

## Run

ioThings is one of the apps of [ioSuite](../README.md), one program that runs the apps it is told to. Install the suite
with ioThings in it, alone or with the others, on any Linux machine:

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite2/main/install.sh | bash -s -- --apps iothings
```

It asks for the MariaDB server, the first admin and the suite's address, then starts the service; leave `--apps` out
for the list of every app, to tick. On a server that already runs the suite:

```sh
iosuite install --add iothings       # --remove iothings stops running it; what it stored stays
```

In Docker, name it in `APPS` in the stack file ([docker-compose.yml](../docker-compose.yml); empty there: every app); on
Proxmox VE, tick it in the list the container's script shows. The guide has each way in full:
[any Linux or Mac](../docs/docs/start/linux-mac.md), [Docker](../docs/docs/start/docker.md), [Proxmox VE](../docs/docs/start/proxmox.md)
and [one app or all of them](../docs/docs/start/one-or-all.md).

| | |
| --- | --- |
| Address | `/things/` at the suite's address (`https://home.example.com/things/`), and a name of its own if you give it one |
| MCP | `/things/mcp` at the address for MCP ([AI assistants](../docs/docs/run/assistants.md)) |
| Database | `iothings`, beside the Shared ioSuite database (the accounts and every setting), both under the suite's one login; the tables are made on the first start and brought up to date by later versions by themselves |
| On the server | the DejaVu fonts, for names in every script in the insurance PDF (`fonts-dejavu-core`); the installer, the Proxmox script and the container image have them |

From a shell, in the program folder (`/opt/iosuite` when installed as root):

```sh
.venv/bin/python -m iothings.cli check                        # connect to the databases and say what is there
.venv/bin/python -m iothings.cli import-homebox FILE [NAME]   # the things in a Homebox CSV export, added as NAME (or the first admin)
```

Accounts are the suite's: `iosuite admin NAME --app iothings` makes someone an admin of ioThings only (`iosuite admin NAME`: of
the whole suite), `iosuite password NAME` sets a password; see [Accounts and roles](../docs/docs/run/accounts.md).

## Configuration

ioThings has no file of settings. The machine's one file (`config.env` in the program folder) says how to reach the Shared
ioSuite database and which apps run here; everything else is kept in that database. Suite admins change it under
**Settings › Global settings › Settings**, which has a section for the whole suite and one for ioThings, or from a shell;
a change applies when the app starts again:

```sh
iosuite settings iothings        # what may be set, with the value stored now
iosuite set iothings PUBLIC_URL https://things.example.com    # no value: back to the default
```

| Setting | Meaning |
| --- | --- |
| `PUBLIC_URL`, `SYNC_URL`, `MCP_URL` | an address of its own for the pages, for devices and for MCP clients (`https://things.example.com`), beside its folder at the suite's address |
| `DATA_DIR` | where the app writes on its own (`iothings/` in the machine's `DATA_DIR`) |
| `DB_NAME` | the name of its database (`iothings`) |
| `MAX_FILE_MB` | largest attachment (MB) (`100`). One manual, receipt or photo as uploaded |

The suite's own settings (its address, the domain the sign-in is shared on, the time zone, how long deletions are kept), the
machine's file and the three ports are in the guide's [Configuration](../docs/docs/reference/configuration.md).

## Updates

The suite is one program with one version, so every app is updated together: **Settings › Global settings › Updates**
(suite admins, in any app) shows the installed version and the newest one, with one **Update** button; from a shell it is
`update.sh` in the program folder, and in Docker the image is pulled. See [Updates](../docs/docs/run/updates.md).

**Settings › Server** shows the version ioThings runs and has **Restart**. The log is one for the whole copy of the program,
each line marked with its app: suite admins read it under **Settings › Global settings › Logs**.

## API

The paths below are ioThings' own: at the suite's address they are inside its folder (`https://home.example.com/things/api/…`), at a name of its own they are as written. Phones, native apps and scripts use the [address for devices](../docs/docs/reference/configuration.md#the-three-ports) (port 8443; `https://sync.example.com/things/api/…` behind a reverse proxy), which takes app passwords and tokens and nothing else; from inside the home network an app password also works at the pages' address. MCP clients use the address for MCP (port 8444).

| For | Standard | Where |
| --- | --- | --- |
| Web and JSON clients | **REST/JSON**: things (list, search, by place or label, archived), one thing, add, change, duplicate, delete, its files (each gets a name of its own, such as iothings-000123.jpg, never the one it was uploaded under), upkeep and log; places and labels | `/api/`, OpenAPI docs at `/api/docs` |
| Inventory PDF | everything, photos and receipts included, as one PDF | `POST`/`GET /api/export-pdf`, `GET /api/export-pdf/file` |
| Homebox | Homebox's CSV, in and out; everything from a Homebox server, files and log too | `POST /api/import/homebox`, `GET /api/export.csv`, `POST`/`GET /api/import/homebox-server` |
| AI assistants | **Model Context Protocol** (streamable HTTP, and stdio) | `/mcp` (switched on in Settings › Server), or every app's tools at ioStart's `/mcp` |

Settings › Account makes **app passwords**, for the REST API (HTTP Basic, or `Authorization: Bearer <app password>`)
and for MCP.

```sh
curl -u alex:APP-PASSWORD "https://sync.example.com/things/api/items?q=boiler"
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: application/json' \
  -d '{"name": "Dishwasher", "manufacturer": "Bosch", "location": "House / Kitchen", "warrantyExpires": "2028-06-01"}' \
  https://sync.example.com/things/api/items
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: text/csv' --data-binary @homebox.csv https://sync.example.com/things/api/import/homebox
```

The MCP tools: `overview`, `search_items`, `get_item`, `create_item`, `update_item`, `delete_item`, `list_locations`,
`create_location`, `warranties_ending`, `list_upkeep`, `add_upkeep`, `upkeep_done`, `log_maintenance`, `diagnostics`.

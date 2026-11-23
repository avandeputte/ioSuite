# ioTask

*The family's task lists, in the ioThing suite (with [ioPix](../iopix/), [ioNote](../ionote/), [ioContact](../iocontact/), [ioCalendar](../iocalendar/), [ioHealth](../iohealth/) and the [ioStart](../iostart/) start page).*

Self-hosted task lists: a web app for the whole family, and the standard protocol reminders apps already speak, so the same lists show up in Apple Reminders on iPhone, iPad and Mac, in Tasks.org or jtx Board on Android, in Thunderbird and anywhere else that syncs to-dos over CalDAV. FastAPI and a single-page vanilla JS app, with everything stored in MariaDB / MySQL, and the suite's shared library (`iosuite_shared`, in [iosuite_shared/](../iosuite_shared/)).

## What it does

- **Tasks** with a title, notes, a due date (a day, or a day and a time), a **priority**, **alerts**, a link, and a box to tick them off.
- **Repeating tasks**: every day, weekday, week, two weeks, month or year, every so many of them (and whatever rule another app gave it). Ticking one off moves it on to its next date, as Apple Reminders does, instead of closing it; a rule with a number of times counts down.
- **Repeat after completion**: "two weeks after I tick it off" instead of "every two weeks": the task comes back that long after the day it was done, at its usual time. Reminders has no such repeat, so the rule is ioTask's own (`X-IOTASK-AFTER-DONE:P2W` on the task); a task ticked off on a phone still comes back.
- **Subtasks**: a task under another one, shown indented under it with a count (2/5). Deleting or moving a task takes its subtasks along.
- **Lists**: a shared **Family** list, a private **Personal** one for each account, and as many more as you like (shared or private), each with its colour and its count of open tasks (red when something is overdue).
- **Today, Scheduled, All and Completed** across every list you see: Today has what is due today and what is overdue, Scheduled everything with a date, day by day. "Today" is the day where you are, not where the server is.
- **Smart quick add**: type a line on top of any list and press Enter. Plain English becomes the task's fields: "Pay rent every month on the 1st 9am !high" is *Pay rent*, due on the next 1st at 9:00, monthly, high priority. It reads when (`tomorrow 5pm`, `friday`, `15 nov`, `in 2 weeks`, `the 20th`, `tonight`), how often (`daily`, `every monday and thursday`, `every 2 weeks after done`), how important (`!high`, `!!`), which list (`#groceries`) and for whom (`@emma`); what it understood shows under the line while you type, and the rest is the title. It can be switched off in Settings › Display.
- **Postpone**: a button on every task that is due puts it off to tomorrow, the weekend or next week (it keeps its time, and its alerts move along), and "Move all to today" on Overdue does that for everything that is late. The task form has the same days one click away.
- **Order by hand**: a list can be sorted by due date or put in your own order by dragging (a task takes its subtasks along; subtasks move within their task). The order is kept as `X-APPLE-SORT-ORDER`, the property Apple Reminders uses for its manual order. Lists are dragged into order too, in the sidebar or in Settings › Lists.
- **Activity and undo**: who added, changed, ticked off, moved or deleted what, in the web app, in a reminders app or through an assistant, per list or for all of them. Every change can be taken back: **Undo** shows for ten seconds after a change, and on the Activity page for as long as the task is still as that change left it. Deleting a task with its subtasks, "Clear completed" or adding a template is one step, undone as one.
- **Templates**: save a list's tasks (with notes, priorities, links, people and subtasks) as a template, and add them to a list again later, or start a new list with them: the packing list, the weekly shop. Shared with everyone, or your own.
- **Print**: a list prints as a checklist (the list's ⋯ menu, or the browser's Print).
- **Family members on tasks**: tag a task with the people of the family it is for. The tags show as coloured initials, the sidebar's Family list shows only one person's (or a few people's) tasks, and the tag is kept as an iCalendar `CATEGORIES` value with the member's name. The REST API (`?member=emma`) and MCP filter by member as well. The family is the suite's one list (Settings › People › Family, suite admins), the same in every app: each member's colour, initials and face (their ioPix person, else their ioContact card) match everywhere. An account that is not a person (an admin or guest) can be taken out there: it is not offered as a tag and gets no private list.
- **Search** across titles and notes, **import** of .ics files with to-dos, **export** of each list, and keyboard shortcuts (`n` new, `t` today, `s` scheduled, `a` all, `/` search).
- **Roles as in the other io apps**: viewers only read the shared lists, members (the default) also keep their own private lists, editors change the shared lists too, admins also manage users and settings. The same accounts, passwords and app passwords as the other io apps; one sign-in for all of them with a shared cookie domain.
- **Settings › People, Apps, Servers and Keys** (suite admins): the whole suite's people and their role in every app, app passwords and sign-in at the proxy; the apps, keys and tokens; the same panel as on the start page and in every io app (iosuite_shared's `/api/suite-admin/ui.js`).
- Light and dark, phone-sized screens, installable as an app.

No events: those belong in [ioCalendar](../iocalendar/).

## Run

ioTask is one of the apps of [ioSuite](../README.md), one program that runs the apps it is told to. Install the suite
with ioTask in it, alone or with the others, on any Linux machine:

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash -s -- --apps iotask
```

It asks for the MariaDB server, the first admin and the suite's address, then starts the service; leave `--apps` out
for the list of every app, to tick. On a server that already runs the suite:

```sh
iosuite install --add iotask       # --remove iotask stops running it; what it stored stays
```

In Docker, name it in `APPS` in the stack file ([docker-compose.yml](../docker-compose.yml); empty there: every app); on
Proxmox VE, tick it in the list the container's script shows. The guide has each way in full:
[any Linux or Mac](../docs/docs/start/linux-mac.md), [Docker](../docs/docs/start/docker.md), [Proxmox VE](../docs/docs/start/proxmox.md)
and [one app or all of them](../docs/docs/start/one-or-all.md).

| | |
| --- | --- |
| Address | `/tasks/` at the suite's address (`https://home.example.com/tasks/`), and a name of its own if you give it one |
| Devices | CalDAV (Apple Reminders) at `/tasks/dav/`, at the [address for devices](../docs/docs/reference/configuration.md#the-three-ports) |
| MCP | `/tasks/mcp` at the address for MCP ([AI assistants](../docs/docs/run/assistants.md)) |
| Database | `iotask`, beside the Shared ioSuite database (the accounts and every setting), both under the suite's one login; the tables are made on the first start and brought up to date by later versions by themselves |

From a shell, in the program folder (`/opt/iosuite` when installed as root):

```sh
.venv/bin/python -m iotask.cli check                     # connect to the databases and say what is there
.venv/bin/python -m iotask.cli import LIST-ID FILE.ics   # tasks (VTODOs) from an .ics file into a list
```

Accounts are the suite's: `iosuite admin NAME --app iotask` makes someone an admin of ioTask only (`iosuite admin NAME`: of
the whole suite), `iosuite password NAME` sets a password; see [Accounts and roles](../docs/docs/run/accounts.md).

## Configuration

ioTask has no file of settings. The machine's one file (`config.env` in the program folder) says how to reach the Shared
ioSuite database and which apps run here; everything else is kept in that database. Suite admins change it under
**Settings › Apps › All settings**, which has a section for the whole suite and one for ioTask, or from a shell;
a change applies when the app starts again:

```sh
iosuite settings iotask        # what may be set, with the value stored now
iosuite set iotask PUBLIC_URL https://tasks.example.com    # no value: back to the default
```

| Setting | Meaning |
| --- | --- |
| `PUBLIC_URL`, `SYNC_URL`, `MCP_URL` | an address of its own for the pages, for devices and for MCP clients (`https://tasks.example.com`), beside its folder at the suite's address |
| `DATA_DIR` | where the app writes on its own (`iotask/` in the machine's `DATA_DIR`) |
| `DB_NAME` | the name of its database (`iotask`) |

The suite's own settings (its address, the domain the sign-in is shared on, the time zone, how long deletions are kept), the
machine's file and the three ports are in the guide's [Configuration](../docs/docs/reference/configuration.md).

## Updates

The suite is one program with one version, so every app is updated together: **Settings › Servers › Updates**
(suite admins, in any app) shows the installed version and the newest one, with one **Update** button; from a shell it is
`update.sh` in the program folder, and in Docker the image is pulled. See [Updates](../docs/docs/run/updates.md).

The suite runs one version, so **Settings › Servers › Updates** shows it with a line and a **Restart** button for each server the suite runs on. The log is one for the whole copy of the program,
each line marked with its app: suite admins read it under **Settings › Servers › Logs**.

Everything is under one Settings page (the sidebar and the avatar menu); a change is saved the moment it is made: your own tabs (account, display, apps and
devices, lists), then for admins family and server (with Export: each list as an
.ics file), and for suite admins security and global settings. Import is a page of its own in the sidebar.

## Reverse proxy and HTTPS

ioTask is reached through the suite's three ports: the pages (80), devices (8443) and MCP (8444). A reverse proxy gives each
a name and HTTPS, for the whole suite at once, and can make people sign in first (Cloudflare Access, Authelia, oauth2-proxy):
[Reverse proxy and HTTPS](../docs/docs/run/reverse-proxy.md) and [Cloudflare Tunnel and Access](../docs/docs/run/cloudflare.md) in the
guide have the set-up, with Caddy and nginx examples, sign-in at the proxy and the optional check of app passwords at
Cloudflare's edge ([cloudflare/edge-auth](../cloudflare/edge-auth/README.md)).

iOS and macOS want HTTPS for a CalDAV account outside the home network, and a password travels with every CalDAV request. Reminders apps cannot open a sign-in page at the proxy (Cloudflare Access, Authelia): the address for devices stays outside it, and takes app passwords only.

## API

The paths below are ioTask's own: at the suite's address they are inside its folder (`https://home.example.com/tasks/api/…`), at a name of its own they are as written. Phones, native apps and scripts use the [address for devices](../docs/docs/reference/configuration.md#the-three-ports) (port 8443; `https://sync.example.com/tasks/api/…` behind a reverse proxy), which takes app passwords and tokens and nothing else; from inside the home network an app password also works at the pages' address. MCP clients use the address for MCP (port 8444).

| For | Standard | Where |
| --- | --- | --- |
| Reminders and tasks apps, two-way: Apple Reminders (iPhone, iPad, Mac), DAVx⁵ with Tasks.org, jtx Board or OpenTasks on Android, Thunderbird, Evolution, GNOME, KDE | **CalDAV** (RFC 4791) with to-dos (`VTODO`): each list is a calendar collection that takes only to-dos, which is how Reminders tells a task list from a calendar; sync-collection (RFC 6578), getctag, MKCALENDAR and extended MKCOL (a list made in Reminders is made here), PROPPATCH (name, colour, description, order), calendar-query, calendar-multiget, If-Match / If-None-Match, discovery via `/.well-known/caldav` (RFC 6764) and current-user-principal | `/dav/` |
| Any app that reads calendar files | **iCalendar** (RFC 5545): every task is kept as the `VTODO` it came in as, so properties ioTask does not edit (other apps' X- properties, Apple's sort order) survive a round trip; `DUE`, `RRULE`, `VALARM`, `PRIORITY`, `RELATED-TO` (subtasks) and `CATEGORIES` included | CalDAV, `/api/tasks/<id>?format=ics`, import/export |
| Web and JSON clients | **REST/JSON**, and iCalendar by content negotiation (`Accept: text/calendar`): lists, tasks with filters (due, a range of days, status, member, words), a task from one line of plain English (`{"text": …}`, previewed by `/api/quick`), ticking off, postponing, subtasks, the order by hand, the activity log and undo, templates, import/export | `/api/`, OpenAPI docs at `/api/docs` |
| iPhone, iPad and Mac in one step | **Apple configuration profile** (`com.apple.caldav.account`) | Settings › Apps and devices |
| AI assistants: Claude and anything else that speaks MCP | **Model Context Protocol** (streamable HTTP, and stdio) | `/mcp` (switched on in Settings › Apps) |

**iPhone, iPad and Mac in one step:** Settings › Apps and devices › *Download the profile* gives a configuration profile
(`.mobileconfig`) with the CalDAV account and a new CalDAV-only app password for that device inside (or none, and the device asks).
Open the page in Safari on the iPhone, tap Download, then Settings › Profile Downloaded › Install. The lists then appear
in Reminders under the account "ioTask".

Where the suite has more than one app that syncs (ioCalendar, ioContact, ioTask), *Set up* in the same box offers
**All apps**: one profile with the account of each, and an app password of its own per app.

What Reminders keeps for an account that is not iCloud is the standard part: title, notes, due date and time, repeat,
alert, priority, done. Subtasks made here arrive there as ordinary tasks of the list, and Reminders' own tags, flags
and sections stay on iCloud lists.

Settings › Apps and devices shows the exact addresses to type; Settings › Account makes **app passwords**: one per phone or app,
revocable on its own, used with your user name for CalDAV and the REST API (HTTP Basic, or
`Authorization: Bearer <app password>`). An app password can be made **CalDAV only**: it opens `/dav` and nothing
else, so one lifted from a phone cannot reach the REST API, MCP or the web app (403). The Apple profile's password is
always CalDAV only; scripts and AI assistants need one without that limit. The scope is kept with the password in
the Shared ioSuite database (`ios_app_passwords.scope`), the same for every app of the suite.

```sh
curl -u alex:APP-PASSWORD "https://sync.example.com/tasks/api/tasks?due=today"
curl -u alex:APP-PASSWORD -H 'Accept: text/calendar' https://sync.example.com/tasks/api/tasks/12
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: application/json' \
  -d '{"title": "Take out the bins", "due": "2026-11-12T19:00", "rrule": "FREQ=WEEKLY", "priority": "high"}' \
  https://sync.example.com/tasks/api/tasks
curl -u alex:APP-PASSWORD -X POST https://sync.example.com/tasks/api/tasks/7/complete
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: application/json' \
  -d '{"text": "Call the bank tomorrow 5pm !high", "timezone": "Europe/Brussels"}' https://sync.example.com/tasks/api/tasks
curl -u alex:APP-PASSWORD "https://sync.example.com/tasks/api/tasks?from=2026-11-16&to=2026-11-22"   # due that week
curl -u alex:APP-PASSWORD "https://sync.example.com/tasks/api/activity?limit=20"
```

Every change answers with `undo`, the step it was; `POST /api/undo/<step>` takes it back (400 once the task was changed again).

## MCP server

ioTask is also an MCP server, as the other io apps are, so an assistant such as Claude can work with the lists:
read what is due, search tasks, add, change, tick off, move and delete them, make lists, add a template's tasks,
import iCalendar files, see who did what lately and take a change back (undo), and, for admins, check the server's
health, look for a new version and install it.

It is off until a suite admin turns it on in **Settings › Apps**; off, `/mcp` does not answer
at all. Every assistant signs in with an **app password** (Settings › Account › App passwords), as HTTP Basic or
`Authorization: Bearer <app password>`, and acts as that account, with its rights.

```sh
claude mcp add --transport http iotask https://mcp.example.com/tasks/mcp --header "Authorization: Bearer APP-PASSWORD"
```

On the server itself, `.venv/bin/python -m iotask.mcp --user NAME` serves the same tools over stdio.

The tools: `overview`, `list_lists`, `list_family_members`, `list_tasks`, `search_tasks`, `get_task`, `get_ics`,
`connection_details`; `create_task`, `update_task`, `complete_task`, `delete_task`, `move_task`, `create_list`,
`import_ics`; and for admins `diagnostics`, `list_accounts`.

## Tests

```sh
pip install -e '.[all,test]'          # in the program folder, once
python -m pytest iotask/tests     # on a test MariaDB of its own: a Docker container it starts, or IOSUITE_TEST_DB=host:port:user:password
```

Covered: lists and roles, every task field round-tripping through JSON and iCalendar, the due filters and counts,
ticking off (and a repeating task moving on), subtasks, family members, import and export, the Apple profile, app
passwords, CalDAV discovery, PUT with preconditions (and events refused), calendar-query, multiget, sync-collection
with deletions, MKCALENDAR and PROPPATCH, and the MCP server (switch, sign-in, the tools). CI runs
them against MariaDB.

## Layout

The package `iotask/` of the repository:

```
main.py            the application: start-up (tables, first admin), who is asking, routes
api.py             the REST API: lists, tasks, ticking off, postponing, activity and undo, templates, import/export, connection details, Apple profile
caldav.py          CalDAV / WebDAV (to-dos)
ical.py            iCalendar: reading, indexing, editing and writing VTODOs, moving a repeating task on
quick.py           smart quick add: a line of plain English as a task's fields
model.py           lists and tasks in MariaDB, sync tokens and tombstones for CalDAV, the activity log and undo, the order by hand, templates
members.py         family members on tasks (kept as CATEGORIES), and the member filter
mcp/               the MCP server: base (the server, finding tasks; who is asking comes from iosuite_shared.mcp), read, write and admin tools
access.py          who may call a route (the markers come from iosuite_shared)
users.py           accounts and app passwords (the suite's, through iosuite_shared)
static/            the web app (index.html, app.js, app.css, icons)
```

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later), see [LICENSE](../LICENSE).

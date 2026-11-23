# ioCalendar

*The family calendar, in ioSuite (with [ioPix](../iopix/), [ioNote](../ionote/), [ioContact](../iocontact/), [ioTask](../iotask/), [ioHealth](../iohealth/) and the [ioStart](../iostart/) start page).*

A self-hosted calendar: a web app for the whole family, and the standard protocols every calendar app already speaks, so the same events show up on phones, in Apple Calendar, Google Calendar, Outlook, Thunderbird and anywhere else. FastAPI and a single-page vanilla JS app, with everything stored in MariaDB / MySQL, and the suite's shared library (`iosuite_shared`, in [iosuite_shared/](../iosuite_shared/)).

## What it does

- **Events** with a title, a place (address), start and end (or all day, over one day or many), a time zone, notes, the **people** who are there, **reminders**, a link, tentative or cancelled, busy or free.
- **Repeating events**: every day, week (on chosen days), weekday, month (on a date, or the second Tuesday, the last Friday…), year, every few of them, until a date or a number of times. Changing or deleting one asks, as phones do: **this one**, **this and later** (the series is split in two) or **all of them**. Exceptions made in other apps (moved or removed occurrences) are kept. A series repeats every half hour at most (more often only when it ends within 1000 times): one that a calendar app sends for every second or minute is refused.
- **Calendars**: a shared **Family** calendar, a private **Personal** one for each account, and as many more as you like (shared or private), each with its colour. The calendars in the sidebar are check boxes: tick to show, untick to hide (remembered per account).
- **Views**: month, week, day and agenda, with a small month to jump around, drag and drop to move an event (to another day, or another time in the week and day views), a line at the current time, search across titles, places, people and notes, and keyboard shortcuts (`t` today, `n` new, `d`/`w`/`m`/`a` the views, ←/→ earlier and later, `/` search, `e` change the open event).
- **ioContact (optional)**: the people on an event come from your contacts (picked as you type, with a link back to each), and a shared, read-only **Birthdays** calendar shows the birthdays and anniversaries kept in ioContact, brought up to date every six hours.
- **ioTask (optional)**: the tasks that are due show on their day, beside the events, in every view: a round tick in the list's colour, at their time when they have one. Tick one off (or open it again) right on the calendar; a repeating task moves on to its next day. Click the title to open the task in ioTask. Each person sees the lists they see in ioTask, the Family filter applies to tasks too, and **Tasks due** in the sidebar hides them.
- **Place suggestions**: typing an event's place suggests addresses and places from Google Places, near the start page's weather place, when the suite has a Google key (ioPix's Google server key, else its Google Maps API key, in Settings › People › Keys and tokens; it needs Places API (New) enabled). The key stays on the server: the page asks ioCalendar, ioCalendar asks Google. No key: a plain text field.
- **Weather**: the forecast on each of the next seven days (the day headers of the month, week and agenda views) at the start page's weather place, and on an event that has a place, the weather there at its time. Nothing to set up: the place comes from ioStart (Settings › Weather), the forecast from Open-Meteo (free, no key), an event's place is looked up once with OpenStreetMap's Nominatim (only the place's text leaves the server). No ioStart place: no weather on the days; events with a place still get theirs.
- **ioMoney (optional)**: the household's coming bills (Monarch Money's recurring transactions) show on the day they are due, with the payee and the amount, to the people who have a role in ioMoney; nobody else sees them or the sidebar's **Bills due**, which hides them. Click one to see its payments in ioMoney.
- **ioDocs (optional)**: the day a passport, a driver's license or an insurance policy expires shows on the calendar,
  for the people ioDocs shows that document to; **Documents expiring** in the sidebar hides them.
- **Public holidays**: shared, read-only **Holidays** calendars with the public holidays of one or more countries and, if you like, a state or province for each (Settings › Holidays and birthdays; it starts with the country of the family's time zone, else the United States). Worked out on the server with the `holidays` package (nothing is fetched), last year to three years ahead, renewed daily; anyone can hide each one in the sidebar.
- **Outside calendars**: subscribe to a calendar by its web address (`https://`, `http://` or `webcal://`: a school's, a sports club's, the bin collection) from the + beside Shared or Mine. It is kept as a read-only calendar beside the family's own, fetched again on a schedule (hourly to weekly, Settings › Calendars, or Fetch now), with its reminders dropped. The server only fetches hosts on the internet (not itself, the home network or link-local; every redirect checked the same way), at most 16 MB within 20 s; the address is shown only to those who manage the calendar (members their own, editors the shared ones).
- **Family members on events**: tag an event with the people of the family it is for ("For Emma"). The tags show as coloured initials on the calendar, the sidebar's Family list shows only one person's (or a few people's) events, and the tag is kept as an iCalendar `CATEGORIES` value with the member's name, so phones and calendar apps show it and a category typed there tags the event here too. The REST API, the subscription links (`?member=emma`) and MCP filter by member as well. The family is the suite's one list (Settings › People › Family, suite admins), the same in every app: each member's colour, initials and face (their ioPix person, else their ioContact card) match everywhere. An account that is not a person (an admin or guest) can be taken out there: it is not offered as a tag and gets no private calendar.
- **Roles as in the other io apps**: viewers only read the shared calendars, members (the default) also keep their own private calendars, editors change shared events, admins also manage users and settings. The same accounts, passwords and app passwords as ioPix, ioNote and ioContact; one sign-in for all of them with a shared cookie domain.
- **Settings › People, Apps, Servers and Keys** (suite admins): the whole suite's people and their role in every app, app passwords and sign-in at the proxy; the apps, keys and tokens; the same panel as on the start page and in every io app (iosuite_shared's `/api/suite-admin/ui.js`).
- Light and dark, phone-sized screens, installable as an app.

No tasks or to-dos: those belong in their own app.

## Run

ioCalendar is one of the apps of [ioSuite](../README.md), one program that runs the apps it is told to. Install the suite
with ioCalendar in it, alone or with the others, on any Linux machine:

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash -s -- --apps iocalendar
```

It asks for the MariaDB server, the first admin and the suite's address, then starts the service; leave `--apps` out
for the list of every app, to tick. On a server that already runs the suite:

```sh
iosuite install --add iocalendar       # --remove iocalendar stops running it; what it stored stays
```

In Docker, name it in `APPS` in the stack file ([docker-compose.yml](../docker-compose.yml); empty there: every app); on
Proxmox VE, tick it in the list the container's script shows. The guide has each way in full:
[any Linux or Mac](../docs/docs/start/linux-mac.md), [Docker](../docs/docs/start/docker.md), [Proxmox VE](../docs/docs/start/proxmox.md)
and [one app or all of them](../docs/docs/start/one-or-all.md).

| | |
| --- | --- |
| Address | `/calendar/` at the suite's address (`https://home.example.com/calendar/`), and a name of its own if you give it one |
| Devices | CalDAV at `/calendar/dav/`, subscription links at `/calendar/ics/…`, at the [address for devices](../docs/docs/reference/configuration.md#the-three-ports) |
| MCP | `/calendar/mcp` at the address for MCP ([AI assistants](../docs/docs/run/assistants.md)) |
| Database | `iocalendar`, beside the Shared ioSuite database (the accounts and every setting), both under the suite's one login; the tables are made on the first start and brought up to date by later versions by themselves |

From a shell, in the program folder (`/opt/iosuite` when installed as root):

```sh
.venv/bin/python -m iocalendar.cli check                         # connect to the databases and say what is there
.venv/bin/python -m iocalendar.cli import CALENDAR-ID FILE.ics   # events from an .ics file into a calendar
.venv/bin/python -m iocalendar.cli sync-birthdays                # bring the Birthdays calendar up to date from ioContact
.venv/bin/python -m iocalendar.cli sync-holidays                 # bring the Holidays calendars up to date (Settings › Holidays and birthdays)
```

Accounts are the suite's: `iosuite admin NAME --app iocalendar` makes someone an admin of ioCalendar only (`iosuite admin NAME`: of
the whole suite), `iosuite password NAME` sets a password; see [Accounts and roles](../docs/docs/run/accounts.md).

## Configuration

ioCalendar has no file of settings. The machine's one file (`config.env` in the program folder) says how to reach the Shared
ioSuite database and which apps run here; everything else is kept in that database. Suite admins change it under
**Settings › Apps › All settings**, which has a section for the whole suite and one for ioCalendar, or from a shell;
a change applies when the app starts again:

```sh
iosuite settings iocalendar        # what may be set, with the value stored now
iosuite set iocalendar PUBLIC_URL https://calendar.example.com    # no value: back to the default
```

| Setting | Meaning |
| --- | --- |
| `PUBLIC_URL`, `SYNC_URL`, `MCP_URL` | an address of its own for the pages, for devices and for MCP clients (`https://calendar.example.com`), beside its folder at the suite's address |
| `DATA_DIR` | where the app writes on its own (`iocalendar/` in the machine's `DATA_DIR`) |
| `DB_NAME` | the name of its database (`iocalendar`) |
| `HOLIDAYS_COUNTRY` | public holidays: countries. Until Settings › Holidays and birthdays is chosen: a two-letter country code or several (BE,NL); off: none. Empty: the time zone's |
| `HOLIDAYS_REGION` | public holidays: region. A state or province code of the first country |
| `HOLIDAYS_LANGUAGE` | public holidays: language. The language of the holidays' names |

The suite's own settings (its address, the domain the sign-in is shared on, the time zone, how long deletions are kept), the
machine's file and the three ports are in the guide's [Configuration](../docs/docs/reference/configuration.md).

### ioContact

Nothing to set up. ioCalendar finds ioContact in the suite's list of apps (the Shared ioSuite database) and reads from
it from the server as its own service account (`iocalendar-app`) with a read-only app password, both made by itself on
first use and listed on the start page's Settings › People, where a suite admin can revoke them (a new one is made the
next time). Behind Cloudflare Access, the suite's Cloudflare Access service token (Settings › Keys)
goes along. The Birthdays calendar is filled from ioContact's birthday feed and brought up to date every six hours
(and on request from Settings › Holidays and birthdays, which has the Birthdays switch, or `python -m iocalendar.cli sync-birthdays`).

### ioTask

Nothing to set up. ioCalendar finds ioTask in the suite's list of apps and asks it for the tasks due in the days on
screen (`GET /api/tasks?start=&end=&tz=` here), on the viewer's behalf: the request goes out from this server with
the viewer's own session (or the app password they came with), so ioTask answers with the lists that person sees and
takes a tick (`POST /api/tasks/<id>/complete`) only from someone who may change the list. Nothing about tasks is kept
here. Behind Cloudflare Access, the suite's service token goes along. When ioTask is away, the calendar draws without
the tasks and the sidebar's **Tasks due** says why.

### ioMoney

The same way: ioMoney is found in the suite's list of apps and asked for the bills due in the days on screen
(`GET /api/bills?start=&end=` here) as the viewer, so ioMoney answers only to someone with a role there, with the bills
of the accounts that person sees. Without a role, there are no bills and no **Bills due** in the sidebar.

### ioDocs

The same way again: ioDocs is found in the suite's list of apps and asked for the documents that expire in the days on
screen (`GET /api/papers?start=&end=` here, ioDocs' `/api/expiring`) as the viewer, so each person sees the passports,
licenses and policies ioDocs shows them, on the day they expire. **Documents expiring** in the sidebar hides them.

## Updates

The suite is one program with one version, so every app is updated together: **Settings › Servers › Updates**
(suite admins, in any app) shows the installed version and the newest one, with one **Update** button; from a shell it is
`update.sh` in the program folder, and in Docker the image is pulled. See [Updates](../docs/docs/run/updates.md).

The suite runs one version, so **Settings › Servers › Updates** shows it with a line and a **Restart** button for each server the suite runs on. The log is one for the whole copy of the program,
each line marked with its app: suite admins read it under **Settings › Servers › Logs**.

Everything is under one Settings page (the sidebar and the avatar menu); a change is saved the moment it is made: your own tabs (account, display, apps and
devices, calendars, holidays and birthdays), then for admins family and server (with Export: each calendar as an
.ics file), and for suite admins security and global settings. Import is a page of its own in the sidebar.

## Reverse proxy and HTTPS

ioCalendar is reached through the suite's three ports: the pages (80), devices (8443) and MCP (8444). A reverse proxy gives each
a name and HTTPS, for the whole suite at once, and can make people sign in first (Cloudflare Access, Authelia, oauth2-proxy):
[Reverse proxy and HTTPS](../docs/docs/run/reverse-proxy.md) and [Cloudflare Tunnel and Access](../docs/docs/run/cloudflare.md) in the
guide have the set-up, with Caddy and nginx examples, sign-in at the proxy and the optional check of app passwords at
Cloudflare's edge ([cloudflare/edge-auth](../cloudflare/edge-auth/README.md)).

iOS and macOS want HTTPS for a CalDAV account outside the home network, and a password travels with every CalDAV request. Calendar apps cannot open a sign-in page at the proxy (Cloudflare Access, Authelia): the address for devices stays outside it, and takes app passwords only.

## API

The paths below are ioCalendar's own: at the suite's address they are inside its folder (`https://home.example.com/calendar/api/…`), at a name of its own they are as written. Phones, native apps and scripts use the [address for devices](../docs/docs/reference/configuration.md#the-three-ports) (port 8443; `https://sync.example.com/calendar/api/…` behind a reverse proxy), which takes app passwords and tokens and nothing else; from inside the home network an app password also works at the pages' address. MCP clients use the address for MCP (port 8444).

| For | Standard | Where |
| --- | --- | --- |
| Calendar apps, two-way: Apple Calendar (Mac, iPhone, iPad), DAVx⁵ on Android, Thunderbird, Evolution, GNOME Calendar, KDE, Outlook with a CalDAV add-in | **CalDAV** (RFC 4791) with sync-collection (RFC 6578), getctag, MKCALENDAR and extended MKCOL, PROPPATCH (name, colour, description, time zone), calendar-query with time ranges and `expand`, calendar-multiget, free-busy-query, If-Match / If-None-Match, discovery via `/.well-known/caldav` (RFC 6764) and current-user-principal | `/dav/` |
| Any app that reads calendar files | **iCalendar** (RFC 5545): every event is kept as the iCalendar object it came in as, so properties ioCalendar does not edit (attachments, other apps' X- properties) survive a round trip; VTIMEZONE, RRULE / RDATE / EXDATE, RECURRENCE-ID overrides and VALARM included | CalDAV, `/api/events/<id>?format=ics`, import/export |
| Calendars that cannot sign in: Google Calendar, Outlook, Apple Calendar subscriptions | **iCalendar subscriptions** (`webcal://`), one calendar or all of them, and **free/busy** (VFREEBUSY): each link has a secret of its own, made in Settings › Apps and devices and shown once (one per app or device, stopped one at a time; only a hash of it is kept, in the Shared ioSuite database) | `/ics/<token>/<calendar>.ics`, `/ics/<token>/all.ics`, `/ics/<token>/freebusy.vfb` |
| Web and JSON clients | **REST/JSON** with **jCal** (RFC 7265) and iCalendar by content negotiation (`Accept: application/calendar+json` or `text/calendar`): occurrences in a range (repeating events expanded), events, calendars, free/busy, import/export | `/api/`, OpenAPI docs at `/api/docs` |
| iPhone, iPad and Mac in one step | **Apple configuration profile** (`com.apple.caldav.account`) | Settings › Apps and devices |
| AI assistants: Claude and anything else that speaks MCP | **Model Context Protocol** (streamable HTTP, and stdio) | `/mcp` (switched on in Settings › Apps) |

**iPhone, iPad and Mac in one step:** Settings › Apps and devices › *Download the profile* gives a configuration profile
(`.mobileconfig`) with the CalDAV account and a new CalDAV-only app password for that device inside (or none, and the device asks).
Open the page in Safari on the iPhone, tap Download, then Settings › Profile Downloaded › Install.

Where the suite has more than one app that syncs (ioCalendar, ioContact, ioTask), *Set up* in the same box offers
**All apps**: one profile with the account of each, and an app password of its own per app.

Settings › Apps and devices shows the exact addresses to type; Settings › Account makes **app passwords**: one per phone or app,
revocable on its own, used with your user name for CalDAV and the REST API (HTTP Basic, or
`Authorization: Bearer <app password>`). An app password can be made **CalDAV only**: it opens `/dav` and nothing
else, so one lifted from a phone cannot reach the REST API, MCP or the web app (403). The Apple profile's password is
always CalDAV only; scripts and AI assistants need one without that limit. The scope is kept with the password in
the Shared ioSuite database (`ios_app_passwords.scope`), the same for every app of the suite.

```sh
curl -u alex:APP-PASSWORD "https://sync.example.com/calendar/api/occurrences?start=2026-11-01&end=2026-12-01"
curl -u alex:APP-PASSWORD -H 'Accept: text/calendar' https://sync.example.com/calendar/api/events/12
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: application/json' \
  -d '{"title": "Dentist", "start": "2026-11-12T09:00", "end": "2026-11-12T10:00", "location": "12 Oak Street", "reminders": [60]}' \
  https://sync.example.com/calendar/api/events
curl -u alex:APP-PASSWORD -X PATCH -H 'Content-Type: application/json' -d '{"title": "Soccer (at the school)"}' \
  "https://sync.example.com/calendar/api/events/7?scope=this&recurrenceId=2026-11-19T17:30:00-05:00"
```

## MCP server

ioCalendar is also an MCP server, as the other io apps are, so an assistant such as Claude can work with the calendars:
read the agenda, search events, find when people are free, add, change, move and delete events (one occurrence, the
ones after it, or the whole series), make calendars, import iCalendar files, and, for admins, check the server's health,
bring the birthdays up to date, look for a new version and install it.

It is off until a suite admin turns it on in **Settings › Apps**; off, `/mcp` does not answer
at all. Every assistant signs in with an **app password** (Settings › Account › App passwords), as HTTP Basic or
`Authorization: Bearer <app password>`, and acts as that account, with its rights.

```sh
claude mcp add --transport http iocalendar https://mcp.example.com/calendar/mcp --header "Authorization: Bearer APP-PASSWORD"
```

On the server itself, `.venv/bin/python -m iocalendar.mcp --user NAME` serves the same tools over stdio.

The tools: `overview`, `list_calendars`, `list_family_members`, `agenda`, `search_events`, `get_event`, `get_ics`,
`free_busy`, `connection_details`; `create_event`, `update_event`, `delete_event`, `move_event`, `create_calendar`,
`import_ics`; and for admins `diagnostics`, `sync_birthdays`, `set_holidays`, `holiday_regions`, `list_accounts`.

## Tests

```sh
pip install -e '.[all,test]'          # in the program folder, once
python -m pytest iocalendar/tests     # on a test MariaDB of its own: a Docker container it starts, or IOSUITE_TEST_DB=host:port:user:password
```

Covered: calendars and roles, every event field round-tripping through JSON, iCalendar and jCal, all-day events,
repeating events with this / following / all changes and deletes, import and export, subscription links, free/busy,
app passwords, CalDAV discovery, PUT with preconditions, calendar-query with time ranges and expand, multiget,
sync-collection with deletions, MKCALENDAR, and the MCP server (switch, sign-in, the agenda, changing one occurrence, a
viewer's limits). CI runs them against MariaDB.

## Layout

The package `iocalendar/` of the repository:

```
main.py            the application: what is ioCalendar's own (its jobs, body limits, routes), handed to iosuite_shared.application
api.py             the REST API: calendars, events, occurrences, free/busy, import/export, subscriptions, Apple profile
caldav.py          CalDAV / WebDAV
ical.py            iCalendar and jCal: reading, indexing, expanding repeating events, editing, writing
model.py           calendars and events in MariaDB, sync tokens and tombstones for CalDAV
contacts.py        the ioContact client: people and the Birthdays calendar
tasks.py           the ioTask client: the tasks due on a day, ticked off from the calendar (asked as the viewer)
bills.py           the ioMoney client: the household's coming bills on their day (asked as the viewer)
papers.py          the ioDocs client: the documents that expire, on their day (asked as the viewer)
holiday.py         the Holidays calendars (one per country, with region and language; filled daily)
members.py         family members on events (kept as CATEGORIES), and the member filter
mcp/               the MCP server: base (the server, finding events; who is asking comes from iosuite_shared.mcp), read, write and admin tools
access.py          who may call a route (the markers come from iosuite_shared)
users.py           accounts, app passwords and subscription links (the suite's, through iosuite_shared)
static/            the web app (index.html, app.js, app.css, icons)
```

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later), see [LICENSE](../LICENSE).

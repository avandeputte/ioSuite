# ioHealth

Copies your Apple Health data, all of it or just the types you pick, into your own MariaDB database, and gives you a
fitness web app on top of it: dashboards, charts of any metric (stacked or overlaid), workouts with their GPS routes on
a map, sleep, training load and personal records. Nothing goes through a cloud service: an iPhone app uploads straight
to your own server, over HTTPS behind your reverse proxy (or plain HTTP on your own network).
The same app serves the web app. Accounts are the ioThing suite's shared ones (the same as
[ioPix](../iopix/), [ioNote](../ionote/) and
[ioContact](../iocontact/)): every person in the household signs in with their own name
and sees only their own health data.

The iPhone app that uploads the data is in its own repository,
[iohealth-apps](https://github.com/avandeputte/iosuite-apps/tree/main/iohealth) (Health data only exists on the iPhone), as ioNote and
ioPix keep theirs in [ionote-apps](https://github.com/avandeputte/iosuite-apps/tree/main/ionote) and iopix-apps.

```
┌──────────────┐   HTTPS (REST, gzip NDJSON)   ┌───────────────┐        ┌──────────┐
│   ioHealth   │ ────────────────────────────▶ │ reverse proxy │ ─────▶ │  server  │ ──▶ MariaDB (health + iosuite)
│  (iPhone)    │                               │ (TLS)         │  HTTP  │ (ioSuite)│
└──────────────┘                               └───────────────┘        └──────────┘
```

## What it does

The fitness web app is built into the server. Open the server's address in a browser (`https://home.example.com/health/`
or `http://192.168.1.10/health/`) and sign in: the sign-in screen is the suite's, with a tile per account (an account
without a password signs in with one click, on the home network only). It shows only the signed-in person's data, and
shows new data as soon as a sync finishes.

The menu is laid out as in ioPix: a sidebar with the pages in groups (Dashboard, Day, Metrics, Workouts; Analysis:
Correlations, Map, Records; Health: Sleep, Glucose), Settings at its foot. On a wide
screen it stays docked beside the page, or its button puts it away (remembered) and the menu button slides it over
the page when needed. On phones the same pages are a bottom bar (Dashboard, Day, Metrics, Workouts) with the rest
under More.

| page | what's on it |
|---|---|
| **Dashboard** | today's Move/Exercise/Stand rings and the last week's, last night's sleep, 14-day blood glucose summary (when there is glucose data), cards for steps, energy, distance, resting heart rate, HRV, VO₂ max, weight, respiratory rate, blood oxygen… (today, 7-day average against the 4 weeks before, 60-day sparkline), recent workouts and weekly training time by activity; a **Heads-up** list (glucose time in range and lows over the last week, resting heart rate up, HRV down or sleep down against your usual (the last 7 days next to the 4 weeks before; how far is yours to set), no sync for a day, goal streaks, misses and trends) |
| **Day** | one day on one page: totals, rings, last night's sleep, workouts, and a timeline of glucose (with carbs), heart rate, steps and energy with sleep and workouts shaded. Previous/next and a date picker; days link here from the workout calendar, the sleep page and correlations |
| **Metrics** | chart any synced type over any range (today, yesterday, 7 days to all time, or custom dates), **zoom and pan** (on every chart: click and drag to move along the timeline, Shift-drag across the chart to zoom in, the mouse wheel, Ctrl/⌘ + scroll or a pinch to zoom, double-click to reset; the detail reloads to fit the view), grouped per sample, hour, day, week, month or year; activity rings too (Move, Exercise and Stand per day, their goals and % of goal); several metrics at once, either **stacked** (one chart each, cursors linked) or **overlaid** (one chart, an axis per unit); min/max bands; **compare** with the previous period or a year earlier (a dashed line, and the change in the table); goal lines; average/min/max/total/trend table. The URL keeps the selection, so a view can be bookmarked |
| **Workouts** | filter by activity and period; totals, a year calendar, time per week or month, training load (fitness, fatigue and form from heart-rate TRIMP), and the list |
| **Workout** | the route on a map coloured by pace, heart rate or elevation; heart rate, pace/speed, elevation and power over time (hovering moves a marker along the route); splits per km or mile; heart rate zones; best 400 m … marathon inside the workout; laps, segments and every statistic |
| **Map** | every GPS route of a period on one map, coloured by activity |
| **Sleep** | stages per night (click one for its timeline), averages, bedtime and wake time, consistency |
| **Glucose** | blood glucose from a CGM or meter: average, GMI (estimated A1c), time in/below/above range, variability (CV), low episodes; readings with your target band and optional overlays (heart rate, steps, carbohydrates, insulin, workouts…); the daily pattern (ambulatory glucose profile) and time in range per day; **glucose around workouts and meals**: the average change from an hour before to three hours after, per activity or per meal size (from logged carbohydrates), and each event's numbers. A workout's own page shows its glucose curve too. mg/dL or mmol/L and the target range are set in Settings |
| **Correlations** | pick two metrics and a period: a scatter plot of the days (click a dot for that day), the correlation, how much one explains the other and the best-fit line, same day or "the day before" (sleep, workouts or carbs, then the next day's glucose). Includes glucose time in range and variability per day and workout minutes. A table ranks what else goes with the second metric |
| **Records** | fastest running efforts from the GPS routes, best days, health bests, ring streaks, and bests per activity |
| **Settings** | in tabs, as in ioContact and ioCalendar (`#/settings/<tab>`; each tab loads only what it shows). *Account*: your name, email and password (iosuite_shared's panel, the same in every io app). *Display*: theme (light, dark or system, kept with your account), units (automatic from your region, kilometres or miles), and which pages and metrics to show (turn off Sleep, Glucose or any metric you don't use and it disappears from the menu, the dashboard, Metrics and Records). *Health*: glucose unit and target range, maximum heart rate (default 220 − age from your date of birth). *Goals and alerts*: **goals** (any metric, at least or at most: 10,000 steps a day, weight at most 75 kg, 7.5 h of sleep…) and the thresholds for dashboard alerts. For admins: *Server*: iosuite_shared's panel, the same in every io app: the installed version, the database and time zone, the server log, Restart. For suite admins: *Security* (people and their role in every app, app passwords, sign-in at the proxy) and *Global settings* (the apps, keys and tokens), the suite's admin panel, the same as on the start page and in every io app (iosuite_shared's `/api/suite-admin/ui.js`) |
| **Notifications** | through the suite's web push (Settings › Account › Notifications, per person): *Health goals*, when a sync brings one of today's goals up to it; *Weekly health summary*, on Monday at your morning time, last week's steps a day, sleep a night and workouts next to the week before; *Outside your usual*, on the day your resting heart rate, heart rate variability or sleep leaves what is usual for you (the Heads-up list's own check, made on the server: at your morning time, and after each sync from then on, once) |

**Export.** The ⤓ CSV buttons download what a chart or table shows (Metrics, Day, glucose readings and responses,
workouts, sleep, correlations). ⤓ PDF in the header saves the current page through the print dialog, in light colours
without the menus.

**On your phone.** In Safari on the iPhone, Share → Add to Home Screen puts ioHealth on the home screen with its own
icon, opening full-screen like an app (Android: Chrome's menu → Install app). Sign in once there.

How the numbers are made: days and weeks (Monday to Sunday) follow the browser's time zone. Totals such as steps come
from the source that counted the most in each period, so an iPhone and a Watch counting the same steps aren't added
together. A night of sleep is everything from 18:00 to 18:00 the next day, taken from the app that recorded the most
sleep that night. Settings are stored in the database (`hlt_user_settings`, per account), so they follow you to every browser.

The web app's data comes from a JSON API under `/api/` (`types`, `series`, `workouts`, `workouts/{uuid}`, `routes`,
`sleep`, `glucose`, `activity`, `profile`, `records`, `records/efforts`, `usual`, `status`, and `settings`, which also takes `PUT`; for admins
`server`, which also takes `POST` with `{"action": "restart"}`), which also accepts an app password as a bearer token, for
scripts (`Authorization: Bearer iohealth-…`); it answers with that account's data. Map tiles load from OpenStreetMap in the browser; everything else (including the chart and map
libraries, [uPlot](https://github.com/leeoniya/uPlot) and [Leaflet](https://leafletjs.com)) is served by the
container.

## Run

ioHealth is one of the apps of [ioSuite](../README.md), one program that runs the apps it is told to. Install the suite
with ioHealth in it, alone or with the others, on any Linux machine:

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite2/main/install.sh | bash -s -- --apps iohealth
```

It asks for the MariaDB server, the first admin and the suite's address, then starts the service; leave `--apps` out
for the list of every app, to tick. On a server that already runs the suite:

```sh
iosuite install --add iohealth       # --remove iohealth stops running it; what it stored stays
```

In Docker, name it in `APPS` in the stack file ([docker-compose.yml](../docker-compose.yml); empty there: every app); on
Proxmox VE, tick it in the list the container's script shows. The guide has each way in full:
[any Linux or Mac](../docs/docs/start/linux-mac.md), [Docker](../docs/docs/start/docker.md), [Proxmox VE](../docs/docs/start/proxmox.md)
and [one app or all of them](../docs/docs/start/one-or-all.md).

| | |
| --- | --- |
| Address | `/health/` at the suite's address (`https://home.example.com/health/`), and a name of its own if you give it one |
| Devices | the ioHealthSync iPhone app's uploads at `/health/v1/…`, at the [address for devices](../docs/docs/reference/configuration.md#the-three-ports) |
| Database | `iohealth`, beside the Shared ioSuite database (the accounts and every setting), both under the suite's one login; the tables are made on the first start and brought up to date by later versions by themselves |

Accounts are the suite's: `iosuite admin NAME --app iohealth` makes someone an admin of ioHealth only (`iosuite admin NAME`: of
the whole suite), `iosuite password NAME` sets a password; see [Accounts and roles](../docs/docs/run/accounts.md).

## Configuration

ioHealth has no file of settings. The machine's one file (`config.env` in the program folder) says how to reach the Shared
ioSuite database and which apps run here; everything else is kept in that database. Suite admins change it under
**Settings › Global settings › Settings**, which has a section for the whole suite and one for ioHealth, or from a shell;
a change applies when the app starts again:

```sh
iosuite settings iohealth        # what may be set, with the value stored now
iosuite set iohealth PUBLIC_URL https://health.example.com    # no value: back to the default
```

| Setting | Meaning |
| --- | --- |
| `PUBLIC_URL`, `SYNC_URL`, `MCP_URL` | an address of its own for the pages, for devices and for MCP clients (`https://health.example.com`), beside its folder at the suite's address |
| `DATA_DIR` | where the app writes on its own (`iohealth/` in the machine's `DATA_DIR`) |
| `DB_NAME` | the name of its database (`iohealth`) |
| `MAP_TILE_URL` | map tiles (`https://tile.openstreetmap.org/{z}/{x}/{y}.png`). The address workout maps are drawn from |
| `MAP_TILE_ATTRIBUTION` | map tiles: credit line. Shown on the maps (HTML). Empty: OpenStreetMap's |

The suite's own settings (its address, the domain the sign-in is shared on, the time zone, how long deletions are kept), the
machine's file and the three ports are in the guide's [Configuration](../docs/docs/reference/configuration.md).

## Updates

The suite is one program with one version, so every app is updated together: **Settings › Global settings › Updates**
(suite admins, in any app) shows the installed version and the newest one, with one **Update** button; from a shell it is
`update.sh` in the program folder, and in Docker the image is pulled. See [Updates](../docs/docs/run/updates.md).

**Settings › Server** shows the version ioHealth runs and has **Restart**. The log is one for the whole copy of the program,
each line marked with its app: suite admins read it under **Settings › Global settings › Logs**.

## Reverse proxy and HTTPS

ioHealth is reached through the suite's three ports: the pages (80), devices (8443) and MCP (8444). A reverse proxy gives each
a name and HTTPS, for the whole suite at once, and can make people sign in first (Cloudflare Access, Authelia, oauth2-proxy):
[Reverse proxy and HTTPS](../docs/docs/run/reverse-proxy.md) and [Cloudflare Tunnel and Access](../docs/docs/run/cloudflare.md) in the
guide have the set-up, with Caddy and nginx examples, sign-in at the proxy and the optional check of app passwords at
Cloudflare's edge ([cloudflare/edge-auth](../cloudflare/edge-auth/README.md)).

The iPhone app allows plain `http://` only to addresses on the local network; anything else must be `https://`. Its uploads (`/health/v1/…`) go to the address for devices, which stays outside a sign-in at the proxy: the phone signs in there with the account's name and password, a script with an app password.

## Users and permissions

**Accounts** are the ioThing suite's shared accounts ([iosuite_shared](../iosuite_shared/): the
Shared ioSuite database in MariaDB, shared with ioPix, ioNote and ioContact), so one name, password and session serve every app, and
someone signed in at `photos.example.com` is signed in at `health.example.com` too when the apps share a domain
(`COOKIE_DOMAIN`). What is ioHealth's own is kept per app: the role an account holds here, its settings and
its health data. A *suite admin* is admin in every app.

| who | can |
|---|---|
| not signed in | nothing but the sign-in screen (there is no shared data to look at) |
| **viewer** | see their own data, and their own settings and goals |
| **member** (the default) | plus upload their own data: the iPhone app signs in as a member or more |
| **editor** | the same as a member: everyone's data is their own, so there is nothing shared to change |
| **admin** | plus Server in Settings; accounts, roles and the sign-in settings are for suite admins (Settings › Security) |

Settings › Account is where you change your name, email and password. Every setting saves as soon as you change it. The iPhone app signs in with this server's address, your user
name and your password; a script can use an **app password** instead (made by a suite admin under Settings › Security › App passwords). Sessions are random tokens in an HttpOnly cookie (`iothing_session`, shared
by the apps on the domain) valid for 30 days and renewed while in use; passwords are Argon2id-hashed; wrong passwords
cost a growing wait.

## API

The paths below are ioHealth's own: at the suite's address they are inside its folder (`https://home.example.com/health/api/…`), at a name of its own they are as written. Phones, native apps and scripts use the [address for devices](../docs/docs/reference/configuration.md#the-three-ports) (port 8443; `https://sync.example.com/health/api/…` behind a reverse proxy), which takes app passwords and tokens and nothing else; from inside the home network an app password also works at the pages' address. MCP clients use the address for MCP (port 8444).

Every `/v1` call except `/v1/health` needs the account's `Authorization: Basic <user:password>` (what the iPhone app
sends) or `Bearer <app password>`, of a member or more; what is sent becomes that account's. Errors
are JSON `{"detail": "…"}` with 400, 401, 403, 404 or 413.

| request | body | reply |
|---|---|---|
| `GET /v1/health` | | `{"ok":true,"schemaVersion":N}` |
| `POST /v1/sessions` | `{"deviceName","systemVersion","fullResync","timeZone"}` (timeZone: the phone's IANA zone, for goal notifications) | 201 `{"sessionId":N}` |
| `POST /v1/sessions/{id}/items` | NDJSON lines as in `Shared/SyncProtocol.swift` (in iohealth-apps), optionally `Content-Encoding: gzip`; header `X-Batch-Seq: n` | `{"applied":k}` |
| `POST /v1/sessions/{id}/finish` | `{"totalSent":N}` | `{"received":N}` (items the session applied) |

Each batch is committed in one transaction together with its sequence number, so a batch resent after a lost reply is
acknowledged (`"duplicate":true`) without being applied twice. Every write is an upsert keyed on HealthKit's UUIDs, so
resending anything is safe.

## The iPhone app

Build and install it from [iohealth-apps](https://github.com/avandeputte/iosuite-apps/tree/main/iohealth), whose README has the steps.
On the phone, enter the suite's address for devices with ioHealth's folder (`https://sync.example.com/health`, or `http://192.168.1.10:8443/health` at home) and your
user name and password, then **Sync now**. Later syncs only send what's new or changed; with "Sync automatically" on
the phone also syncs in the background when new Health data arrives. The server has to be reachable at that moment; a
missed or cut-short round costs nothing, because the phone only moves on for batches the server has acknowledged.

The account the phone signs in with must be a **member** (the default) or more in ioHealth; a viewer can look but not upload.
Everyone in the household gets their own account, and the phones upload side by side into the same database, each
row tagged with its owner.

## The database

Every table is `hlt_<name>` (the suite's naming convention, so the apps can share one database), InnoDB/utf8mb4 with timestamps in UTC as `DATETIME(3)`, and every data row has a `user_id`: the
account it belongs to (its id in the shared account database's `ios_users` table). `SELECT … WHERE user_id = 1` is one
person; the examples below are for everyone at once.

| table | contents |
|---|---|
| `hlt_samples` | every quantity and category sample: `type` (a short snake_case name: `heart_rate`, `step_count`, `sleep_analysis`, `vo2_max`…), `kind` (`quantity`/`category`/…), `value`, `unit`, `start_date`, `end_date`, `count` (more than 1 for samples some apps pre-aggregate), `text` (names for category values such as `asleep`, `deep`, `rem`, or audiogram points as JSON), `source_name` (the app or device that recorded it), `metadata_json` |
| `hlt_workouts`, `hlt_workout_statistics`, `hlt_workout_events`, `hlt_workout_activities` | workouts and their per-workout heart rate / distance / energy stats, laps and pauses, and multisport segments |
| `hlt_workout_route_points` | GPS traces (lat, lon, altitude, speed, course, accuracy) |
| `hlt_heartbeats` | beat-to-beat intervals behind HRV readings |
| `hlt_activity_summaries` | daily Move / Exercise / Stand rings and goals |
| `hlt_characteristics` | date of birth, biological sex, blood type, skin type, wheelchair use |
| `hlt_sample_hourly`, `hlt_sample_hourly_ready` | every type summed per UTC hour and source (sum, count, min, max), so charts and records over months or years read thousands of rows instead of millions; kept current by each sync |
| `hlt_user_settings` | ioHealth's settings, per account |
| `hlt_deleted_objects`, `hlt_sync_log`, `hlt_schema_version` | bookkeeping |

Every data table also has `created_at` (when the server first stored the row) and `updated_at` (when its values last
changed; equal to `created_at` until then), both UTC. Resending unchanged data touches neither. The lap, pause and
multisport rows of a workout are rewritten whenever the workout is resent, so theirs restart then. Rows written
before these columns existed (schema versions below 5) have `NULL`.

When the server first starts on schema 8 or later it fills `hlt_sample_hourly` for existing data in the background, one
type and one month per transaction (small enough for a Galera cluster to replicate comfortably); charts read `hlt_samples`
directly until each type is done, and the log says when it has finished. Schema 9 (ioHealth 2.0) adds `user_id`; schema 10 adds it to the views below; schema 11 (ioHealth 2.8) gives every table, view and index the `hlt_` prefix and renames `inserted_at` to `created_at`, in place.

Two views report how long samples take to arrive (`created_at` minus the sample's `end_date`, in minutes, which
includes the Watch-to-iPhone hop): `hlt_sample_delay_by_type` (per account and type: count, min/avg/max delay, latest sample, latest
arrival) and `hlt_sample_delay_by_day` (the same per type and per day of arrival, UTC).

Type names are the HealthKit identifier without its prefix, in snake_case (`HKQuantityTypeIdentifierHeartRateVariabilitySDNN`
→ `heart_rate_variability_sdnn`); the phone and the server share the rule (`HealthTypes.storageName`,
`iohealth/db.py`'s `storage_name`). Units are your Health app's preferred units (kg or lb, km or mi…) where Apple exposes them,
otherwise metric; the `unit` column always says which.

```sql
-- resting heart rate, last 30 days
SELECT DATE(start_date) d, ROUND(AVG(value)) bpm
FROM hlt_samples WHERE type = 'resting_heart_rate'
GROUP BY d ORDER BY d DESC LIMIT 30;

-- how long after a measurement it reaches the database, slowest types first
SELECT * FROM hlt_sample_delay_by_type ORDER BY avg_delay_min DESC;

-- the same, today only
SELECT * FROM hlt_sample_delay_by_day WHERE day = UTC_DATE() ORDER BY avg_delay_min DESC;

-- hours of sleep per night by stage
SELECT DATE(start_date - INTERVAL 12 HOUR) night, text stage,
       ROUND(SUM(TIMESTAMPDIFF(SECOND, start_date, end_date)) / 3600, 2) hours
FROM hlt_samples WHERE type = 'sleep_analysis'
GROUP BY night, stage ORDER BY night DESC;
```

## Not included

- **ECGs**: the iPhone app doesn't request or send them (the voltage traces are most of the data by volume).
- **Vision prescriptions**: HealthKit only allows reading them one prescription at a time, with a separate prompt.
- **Clinical (FHIR) health records** need the separate "Clinical Health Records" entitlement, which Apple grants
  per app.
- Data the Watch has purged (very old raw samples that the phone never received).

## Tests

```sh
pip install -e '.[all,test]'          # in the program folder, once
python -m pytest iohealth/tests     # on a test MariaDB of its own: a Docker container it starts, or IOSUITE_TEST_DB=host:port:user:password
```

The tests run against a real MariaDB
(`IOSUITE_TEST_DB=host:port:user:password`, as in every app of the suite; it makes and drops
databases of its own, `health_test`, `iosuite_test_iohealth` and `health_mig_test`, so the user needs `CREATE` and `DROP`). The checks on GitHub run the same.

## Layout

The package `iohealth/` of the repository:

| path | what |
|---|---|
| `*.py` | the FastAPI service: the upload API (`/v1`), the web app's API (`/api`), the database and its migrations; accounts through the suite's [iosuite_shared](../iosuite_shared/) |
| `static/` | the web app (one page, `app.js`, `app.css`, the chart and map libraries, icons) |
| `tests/` | the tests, on a real MariaDB |

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later), see [LICENSE](../LICENSE).

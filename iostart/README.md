# ioStart

*The start page of the ioThing suite: one place with every io app ([ioPix](../iopix/),
[ioHealth](../iohealth/), [ioCalendar](../iocalendar/), [ioTask](../iotask/), [ioRecipe](../iorecipe/), [ioThings](../iothings/), [ioMoney](../iomoney/),
[ioContact](../iocontact/), [ioNote](../ionote/)).*

A self-hosted home page for the family: a tile per app, signed in with the suite's shared accounts ([`iosuite_shared`](../iosuite_shared/)), so
one sign-in here is a sign-in everywhere the page links to. FastAPI and a single-page vanilla JS app, built the same
way as the other io apps, with its few settings in MariaDB / MySQL. For now the tiles are links; each one keeps room for
what the app will show on the start page later (today's events, the newest photos, last night's sleep…).

## What it does

- **A tile per app**, with the app's own icon and colours, that opens it. Each app registers itself, with its address,
  in the suite's list of apps in the Shared ioSuite database (`ios_apps`), and the page
  reads it there and only there: nothing to type, nothing to override. ioStart registers itself the same way. An app
  that has not registered (not installed, or not started yet) has no tile; one the page has no widgets for gets a plain
  tile. Each person can hide tiles in Customize. What the tiles and cards show is asked of each app by this server
  with the viewer's own sign-in (so each person sees only what they may see there), on localhost when the app runs on
  the same machine, else at its LAN address, else its public one, with the suite's Cloudflare Access service token
  (Settings › Global settings › Keys and tokens) when one is set.
- **A search box** at the top (⌘K / Ctrl-K): as you type it lists the bookmarks that match, what the apps find
  for you (ioContact's people, ioCalendar's coming events, ioTask's open tasks, ioRecipe's recipes, ioThings' things, ioDocs' documents, your ioNote notes,
  ioMoney's payees and transactions ("plumber", or an amount: "$280"), ioPix's people, albums, folders and places; each asked
  with your own sign-in, so you see what you may see there), and a row per app that searches itself (each opens on
  its own results). Arrows
  pick a row, Enter opens it. When nothing of the suite matches, Enter searches the web (DuckDuckGo, or the engine
  picked in Customize the page); a prefix picks a site (`g` Google, `w` Wikipedia, `yt` YouTube, `m` Maps, `gh`
  GitHub…, also as `!g`), and an address typed in full (`github.com`) opens.
- **Quick add**: type an event in the search box ("dinner fri 19:00", "dentist tomorrow 9am", "trip 24 dec",
  "call mum 14:30-15:00") and pick "Add to the calendar": a dialog shows the title, day and times it understood, and
  the calendar, then makes the event in ioCalendar with the viewer's own sign-in. A line that starts with `t` (or
  `todo`, `task`) is a task for ioTask ("t call the plumber fri 9am": the day it names is its due date, none named is
  no due date, and the dialog asks which list); one that starts with `n` (or `note`) is a note for ioNote ("n the gate
  code is 4411"). Both are made with the viewer's own sign-in, like the event.
- **Calculator**: a sum or a conversion typed in the search box shows its answer as the first row, and Enter copies
  it: "15% of 84", "84 + 15%", "(12+8)*1.21", "2^10", "350f in c", "3 cups in ml", "5 km to mi", "10 lb in kg",
  "120 usd in eur" (the European Central Bank's rates of the day, fetched by the server from Frankfurter and kept six
  hours). A phone number or a date typed without spaces ("555-1234", "24/12") is not taken for a sum; "=24/12" is.
- **Kitchen timers**: "timer 10m pasta", "egg timer 6 min", "timer 1h30 roast" starts a timer for the whole family. The
  running ones count down under the greeting on every start page and on the wall display, with who started them;
  anyone can add a minute or dismiss one. When one ends, the page that started it and the wall display beep, and the
  person who started it gets a notification ("Kitchen timers" in Settings › Account › Notifications).
- **Feeds** (the gear › Feeds, or `#/news`): a reader for the sites you follow. Give it a site's address and it finds
  the feed (RSS, Atom or JSON Feed; a blog, a news site, a YouTube channel, a podcast). Feeds go in folders; articles
  are read in the page, starred to keep, searched, and marked read one by one or all at once (j and k step through
  them, s stars, m marks, o opens the page itself). Each person's feeds, and what they read and starred, are their own.
  The server reads every feed about every half hour, so the browser never asks the sites for the feeds; the pictures
  inside an article do load from their site when the article is opened. Import and export as OPML, the file every
  reader exchanges. The **Headlines** card on the start page lists the newest unread articles of the feeds you keep
  on it (a switch on each feed); it is there once you follow one.
- **Live**: every five minutes, and when the tab is shown again, the page brings the tiles, the cards, the weather
  and the dots up to date in place; at midnight it is drawn anew for the new day.
- **A wall display** (the gear › Wall display, or `#/wall` as a tablet's home address): full screen, ioPix photos one
  after another (drifting slowly, a new one every minute by default) behind a big clock, the date, the weather and its
  next hours, and today's and the coming days' events with the birthdays, each with its place ("6:00 PM Dinner @ Nan
  Xiang Dumpling", the part before the first comma). Behind the photos, and instead of them without ioPix, a sky in
  the colours of the hour and the weather. Customize picks the background (photos, the sky or black), which photos
  (as the photo strip, Rediscover, On this day, your ioPix favorites or one ioPix album) and how often the photo changes; the picture button on the wall goes to the next background. It keeps the screen on where the
  browser allows it; Escape or the ✕ (shown on a touch) goes back.
- **TRMNL e-ink screens** (Settings › TRMNL): Today (the date, the weather, and the list of the start page's Today card:
  today's events, tasks and birthdays by the hour, then the coming six days, as many lines as the screen holds), Calendar (seven days), Tasks, Documents to renew, Health, Money and Weather
  (the start page's own, once Settings › Home page has it: now, the next eight hours, five days, with the start
  page's weather pictures), each a TRMNL private plugin in its four sizes (full, the two halves and the quadrant, for TRMNL's mashups), downloaded as the zip
  TRMNL's Import new takes. TRMNL reads `GET /api/trmnl/<screen>?tz=&clock=12|24` with an ioStart app password of
  yours (a TRMNL server of your own inside the network, or TRMNL's cloud through Cloudflare Access with a service
  token); or, when TRMNL's cloud cannot reach the start page, the start page sends each screen to the plugin's webhook
  every 15 minutes when it changed (the webhook addresses and the app password it reads with are kept with the suite's
  keys and tokens). The markup is in iostart/trmnl_markup/, on TRMNL's own design framework. Health shows the day's
  rings (Move, Exercise, Stand, in black alone) and the week's steps as bars, Money what falls due on each of the
  week's days, Weather the hours' temperatures as a curve: pictures the markup writes itself, as SVG. On a TRMNL X
  (the framework's `lg:` classes) the text is larger and the halves and quadrants list more, so the larger screen
  is filled; a plugin imported before this needs importing again to look so. On a screen of coloured inks (the
  framework's `screen--color-6a`, such as the reTerminal E1004) the screens have colour: the rings in red, green and
  blue, the bars blue, what is late, expired or low red, the events and tasks marked in their calendar's or list's
  colour, the weather pictures in colour; a screen of grays shows them as before (the markup's `1bit:` `2bit:` `4bit:`
  classes).
- **A TRMNL server of its own** (Settings › TRMNL › Straight from the start page): the start page answers a TRMNL
  device itself, so a TRMNL needs no TRMNL account, plugin or webhook, and nothing leaves the network. In the device's
  Wi-Fi setup, give the start page's address inside the network as its server; it then shows a six-letter code, which
  a signed-in person types in Settings › TRMNL to make it theirs. From then on it shows that person's screens, read as
  them with their "TRMNL" app password, one playlist entry at each wake: a screen filling the display, or one of
  TRMNL's mashup layouts (two, three or four screens sharing it). Per device: its name, how often it looks (5 minutes
  to once a day), its shades (black and white or 4 grays on a TRMNL, up to 16 grays on a TRMNL X, in color or black
  and white on a reTerminal E1002 or E1004, which run TRMNL's firmware; the E1004's panel stands, and gets its picture
  lying down as the firmware turns it), a picture of each
  entry as it is now, its battery, signal, firmware and last log lines; quiet hours (it sleeps from one time of the
  day to another, showing a sleep screen with until when, or keeping its last picture; a press of its button still
  wakes it); what two
  presses of its button do (sleep until the morning, show which screen it is, start over, go back one, stay on what
  it shows, send what it shows to your phone as a notification, open its Wi-Fi setup); stay on one entry; a full
  redraw every time; the device's detailed log; a reset (it forgets its Wi-Fi and key and sets up again). A battery
  at 15% tells its owner once (Account › Notifications › TRMNL screens). Firmware updates are not offered from here.
  The pictures are drawn in Python
  (iostart/trmnldraw.py, no browser), from the same markup, laid out as TRMNL's framework does and held against its own
  renders in the tests (tests/trmnl_ref); an unchanged picture keeps its name, so the device does not fetch it again.
  The device signs its requests (`/api/setup`, `/api/display`, `/api/current_screen`, `/api/log`,
  `/api/trmnl/image/…`, open without a
  sign-in) with a key of its own, kept with the suite's keys and tokens; a reset device gets a new key only while its
  owner has Pair again open. Fonts: TRMNL's own and Inter (iostart/trmnl_fonts, SIL Open Font License).
- **A dot by each app's name**: green when the app answers its `/api/status`, red when it does not. Bookmarks the
  server cannot reach get a red dot too. The server asks each app once a minute and pings each bookmark every five (HEAD, redirects not followed; never its own address or a link-local one).
- **Two layouts** (Customize the page › Layout, per person or per device). *A card for each app*: each app with something to show
  gets a card, as many across as fit at 300px or more (three on a wide screen, one on a phone), so its lines are not
  cut short; the apps without a card are low tiles that share the free cell after the last card (or a row of their
  own). A card with nothing to show today (nothing planned, nothing due) becomes a low tile with that one line, and a
  card again when it has something. *One Today card, the apps in a row*: every app as an icon in one row to open it,
  and under it a Today card (ioCalendar's events, ioTask's tasks and ioContact's birthdays in one list by the hour, then
  the coming days' as far as the card has room, so a light day shows what is ahead; ioMoney's week of bills beside
  them) with ioHealth and ioPix's On this day in a narrow column next to it.
- **Your own page** (the gear next to the date › Customize the page, or › Arrange the page to do it where things
  stand: drag a tile or a card to its place, the eye takes it off, Done keeps it). Untick the tiles, the cards and the
  parts of the top row (greeting, search box, weather) you do not need, put the tiles and the cards (Birthdays, This
  week, the photo strip, the bookmarks) in your order, and pick your own photo strip ("Default" is the admin's
  choice). Also yours: each app as a full card or a low tile with one line (or by itself), what the Today card holds
  (events, tasks, birthdays, bills, Health and On this day beside it, how many days ahead), the weather in °C or °F
  (the wall and the TRMNL weather follow), the page's colour and the size of its type (the start page only), and the
  bookmarks as the full list, icons only, or folders shut until tapped.
- **A setup per device**: Customize the page › "This device only" gives the phone or the kitchen tablet a page of
  its own, with a name; the other devices keep the account's. Three places a setup comes from, the nearest first:
  the device's own, the account's, the family's. Admins set the family's starting point in Customize the page ›
  Family (for whoever has no setup of their own), or give one person the setup on screen (on all their devices).
  The wall display's firmware follows the account's setup.
- **The week ahead** under the tiles: a Birthdays card from ioContact (birthdays and anniversaries in the next 30
  days, with the contact's photo; a row opens the contact) and a This week card from ioCalendar (the coming seven
  days' events, day by day; a day opens in ioCalendar). Each stands no taller than the row of tiles, with "Show all"
  when there is more. With the Birthdays card on the page, the calendar's own "X's birthday" and anniversary events
  are left to it (the tile's Today and This week skip them). A card that its app cannot fill is left out.
- **A strip of photos** the width of the page under the tiles: ioPix's Rediscover (photos at random), or
  On this day; an admin picks which, or turns it off, in Settings › Home page.
- **A glimpse of each app on its tile**: ioPix shows photos taken on this day in earlier years (one per year, "3 years
  ago"), or a few picked at random (Rediscover) on a day without any; ioCalendar the rest of today (else the next event
  in the coming 60 days), in each calendar's colour; ioTask what is due today, the overdue tasks first, in each list's colour; ioHealth today's steps with the last seven days as bars, the
  move, exercise and stand rings, and last night's sleep; ioMoney the bills and subscriptions due in the coming
  seven days that are not paid yet (the soonest first, with what they come to), a warning when its forecast sees a cash
  account go under its lowest balance in the next 30 days, and one when a bank link is behind; ioDocs the passports,
  licenses and policies to renew (expired, or within their reminder), the soonest first. The
  server asks each app over its own API with the viewer's sign-in (the suite's session cookie, or the Basic / bearer
  credentials they came with), so everyone sees only what that app shows them; ioPix's thumbnails come through the
  start page too. An app that is down, or not open to that account, leaves its tile as it was. Nothing is kept.
- **The weather**, from AccuWeather: the conditions now, "Rain from 15:00" when the next hours bring some, and the
  five days ahead, at the top of the page; a click on the conditions opens the next 12 hours. Settings ›
  Weather (admins) takes a free API key from developer.accuweather.com and finds the place by its name. The server
  keeps a copy and asks AccuWeather at most every hour (conditions), 90 minutes (the next 12 hours) and 6 hours
  (forecast), and only while someone opens the page: 44 calls on a day the page stays open from morning to night, so
  a free key's 50 a day are enough; browsers never talk to AccuWeather.
- **Home Assistant**: a Home card with the entities an admin picks (lights, switches, locks, covers, scenes, sensors,
  people), each with its state; a tap toggles the ones the admin ticked "control", for editors and admins (a viewer sees the
  states and switches nothing, so a wall tablet that should switch lights signs in as an editor). Sensors ticked "wall" show on the
  wall display; the search box finds any entity by name and toggles the controllable ones; a line at the top of the Home card
  points out what needs attention (an entity in the state the admin named, and built in: a leak, smoke, gas or CO
  sensor that is on, a problem or safety sensor, a battery at 15% or under). Settings › Home Assistant (admins) takes
  the address and a long-lived access token; the server makes every call with it, and browsers never see the token
  nor talk to Home Assistant. The server holds one websocket to Home Assistant for state changes and streams the card
  to every open page (server-sent events) when something on the card or one of the alerts changes, so a light switched
  at the wall shows within a second; without the
  websocket (HA_FEED=0, or an old install) the states come in one call kept five seconds.
- **Bookmarks**: one tree of folders and links, as a browser keeps them, on a page of its own
  (`#/bookmarks`, from the start page and the gear menu). Each person's bookmarks are their own (members, editors and
  admins keep some; nobody else sees them), and the start page's admins share folders and links with everyone (the
  people icon beside the house); only they change the shared ones. Others can add their own links in a shared folder
  and take a shared one off their own start page; their browsers put back what they change of the shared ones. The start page shows the part picked for it, as
  [homepage](https://gethomepage.dev/configs/bookmarks/) lays bookmarks out: the house on a folder shows it as a group
  with its links, the house on a link shows or hides just that one; each link has an icon, the name and the site. The icon is the site's
  own, as a browser finds it: the server asks the bookmarked page for its icon (`<link rel="icon">`, else
  `/favicon.ico`), keeps it in the database per site and serves it itself, so your browser asks the bookmarked sites
  nothing; a site without one shows a two-letter badge. An icon you give a link wins: an image address, a file name
  from the dashboard-icons collection (`github.png`), or a file of your own uploaded for the link (an SVG, which stays sharp at any size, or a PNG). The groups pack into columns (as many 250 px columns as
  fit). Editors and admins add, change, reorder and move folders and links (drag by the handle, with a mouse or a
  finger), import a bookmarks file a browser exported (HTML) or an XBEL file, and export either. A folder's "Open all"
  (on the Bookmarks page, and on a group's name on the start page) opens its links, each in a tab of its own.
- **Tidy up** (the Bookmarks page): the links that no longer work and the same address kept more than once, for your
  own bookmarks and the shared ones. The server asks every web address once, in the background (a HEAD request, a GET
  where the site dislikes HEAD; never this server itself, never following a redirect), and lists the ones where nothing
  answered or the server failed, the ones whose page is gone (404, 410) and the ones that moved for good (301, 308),
  whose new address is one click away. A page behind a sign-in, a temporary redirect or a certificate the server
  cannot vouch for is fine. When most addresses give no answer the page says the server probably cannot reach the
  internet, and does not offer to delete them all. Nothing is deleted or changed without a click; the answers are
  kept in memory until the next check.
- **The Bookmarks app** at `<address>/bookmarks`: the Bookmarks page as an app of its own, with its own name, icon
  and manifest (`static/bookmarks.webmanifest`), opening straight on the bookmarks. On an iPhone or iPad open that
  address (Safari, or Vivaldi, Chrome, Edge, Firefox) and choose Share › Add to Home Screen; on Android or a desktop,
  the browser's Install. It runs without the browser around it and fetches the tree each time it comes back to the
  front (no offline copy). On a phone it has a search box, rows to tap, a ⋯ menu per link and folder, and a short
  link form (the address; the name is the site's address when left empty). Sign-in is the page's own: behind
  Cloudflare Access a home-screen app signs in once by itself (it keeps its own cookies, apart from the browser's).
- **ioStart, the iPhone and iPad app** ([avandeputte/iosuite-apps](https://github.com/avandeputte/iosuite-apps), folder
  `iostart/`): the tree with search and editing, a share sheet entry that bookmarks the page open in any browser, and a
  built-in browser (WebKit) for opening bookmarks inside the app, plus home screen widgets (today, the next event,
  favourite bookmarks) and Siri / Shortcuts actions to add a task or an event. It speaks the extension's API
  (`/dav/ext`) and signs in with the same one-tap flow, asking for a full app password (`?scope=full`) because its
  widgets and Siri read and add in ioCalendar and ioTask as the person (`/dav/ext/today`, `/dav/ext/calendars`,
  `/dav/ext/tasks`, `/dav/ext/events`); a sync-only password is told to sign in again for those.
- **Bookmark sync with browsers**: everything in the tree syncs, on the start page or not.
  - *The ioStart Bookmarks extension* (`static/extension`, Chrome, Edge and Firefox; its own README there): keeps the
    browser's own bookmarks the same as the tree, both ways, with nothing to configure but the address. The bookmarks
    bar is the top-level folder "Bookmarks bar", Firefox's bookmarks menu the folder "Bookmarks menu", Other bookmarks
    everything else at the top, so every browser shows the same. It sends what changed in the browser in one request
    (`/dav/ext`, `iostart/bookmarkext.py`) and makes the browser the tree that comes back, so a delete here or in another
    browser goes everywhere. One-click sign-in (the same flow as below: an app password of its own, for sync only).
    Install it from the [Chrome Web Store](https://chromewebstore.google.com/detail/iosuite-bookmarks/nldealkpbjiholobfadimblcmdlphkoe) (Chrome, Edge, Vivaldi, Brave, Opera); Firefox and builds of your own
    from Settings › Bookmarks or a release. `.github/workflows/extension.yml` packages each version as a release and,
    with an addons.mozilla.org API key in the repository's secrets, has Mozilla sign the Firefox file.
  - *Nextcloud Bookmarks API* at `<address>/dav/nextcloud` (REST v2: folders, bookmarks, tags, order, hashes, bulk
    import, the lock, and Nextcloud's sign-in flow for apps). [Floccus](https://floccus.org) (Firefox, Chrome, Edge,
    Android, iOS): add a *Nextcloud Bookmarks* account with that address and say yes on the page it opens; it gets an
    app password of its own, for sync only. Other clients written for Nextcloud Bookmarks sign in with the account's
    name and an app password.
  - *A bookmarks file over WebDAV* at `<address>/dav/bookmarks/`: `bookmarks.xbel` (XBEL) or `bookmarks.html`
    (the bookmarks HTML of browsers), for Floccus's WebDAV kind of account and anything else that syncs such a file.
    Name and app password; no passphrase (an encrypted file cannot be read, so it is refused).
  - App passwords live in the Shared ioSuite database like all others (Settings › Account, Settings › Security). A
    viewer's sync app can read; changing takes an editor or admin. Behind Cloudflare Access, `/dav/*` needs the same
    bypass as the other apps' CalDAV / CardDAV paths. A bookmark is in one folder (the same address in two folders is
    two bookmarks); bookmarklets and other non-web addresses sync but never show on the start page.
- **The suite's accounts**: the same sign-in as every io app (the account tiles, one click for an account without a password),
  Settings › Account (display name, email, password) and Settings › Display (the theme, kept with the account), both
  iosuite_shared's panels, the same in every io app; every setting saves as soon as you change it. Accounts and roles
  are managed under Settings › Security (below). Sign-in at a reverse proxy (Cloudflare Access…) works as in the other apps.
- **Suite administration** (Settings › Security and Settings › Global settings, suite admins only): everything in the Shared ioSuite database for the
  whole suite. **People**: add, rename and delete accounts, email, sign-in list, suite admin, set or remove a password,
  their role in every app, their sessions (end one or all) and app passwords. **Roles**: a grid of everyone against
  every app (or "default", the app's default role). **App passwords**: everyone's, in every app, with their scope
  (everything, sync only, or read only), revoke one or make one for someone. **Keys and tokens**: every app's keys for
  services outside the suite (this page's Home Assistant token and AccuWeather key, ioPix's Google keys, the suite's
  Cloudflare Access service token), replace or clear, never shown back. The apps' own **service accounts**
  (`iocalendar-app`…, under People), with which apps read from each other without any setup. **Apps**: each app's default role (none makes it
  invitation-only) and sign-in requirement; forget an uninstalled app. **Sign-in at the proxy** for the whole suite. The
  panel is iosuite_shared's (`/api/suite-admin/ui.js` on `/api/suite-admin`), so every io app shows the same one.
- **Updates**: the suite has one version, the same for every app. When a newer one is out, suite admins see one note on the start page with **Update now**; Settings › Global settings › Updates shows the installed version against GitHub with one **Update** button and every app's own line under Details. The version and Restart are under Settings › Server, the log under Settings › Global settings › Logs, as in every app of the suite.
- **One MCP server for the whole suite** (`/mcp`, off until switched on at Settings › Server): connect an AI assistant here once, with your user name and an ioStart app password (Settings › Account), and it gets every app's tools, named after the app (`iocalendar_…`, `iotask_…`, `iorecipe_…`), so one request can span apps ("put Friday's dinner ingredients on the shopping list"). Each call is passed on to that app's own MCP server as you, so each app still decides what you may see and change there; an app whose own MCP server is off (its Settings › Server), or where you have no role, offers nothing. `suite_apps` lists the apps with their status and their own instructions. An ioStart app password (one without a limit) also signs in at any app's `/mcp` directly. ioStart's own tools: `suite_version` and `update_suite` update every app at once (suite admins).
- Light and dark, a phone layout, installable as a web app (manifest and icons).

## Run

ioStart is one of the apps of [ioSuite](../README.md), one program that runs the apps it is told to. Install the suite
with ioStart in it, alone or with the others, on any Linux machine:

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite2/main/install.sh | bash -s -- --apps iostart
```

It asks for the MariaDB server, the first admin and the suite's address, then starts the service; leave `--apps` out
for the list of every app, to tick. On a server that already runs the suite:

```sh
iosuite install --add iostart       # --remove iostart stops running it; what it stored stays
```

In Docker, name it in `APPS` in the stack file ([docker-compose.yml](../docker-compose.yml); empty there: every app); on
Proxmox VE, tick it in the list the container's script shows. The guide has each way in full:
[any Linux or Mac](../docs/docs/start/linux-mac.md), [Docker](../docs/docs/start/docker.md), [Proxmox VE](../docs/docs/start/proxmox.md)
and [one app or all of them](../docs/docs/start/one-or-all.md).

| | |
| --- | --- |
| Address | the suite's address itself (`https://home.example.com/`) |
| Devices | bookmark sync at `/dav/…` (the browser extension, the iPhone app), widgets, e-ink screens and the wall display at `/api/…`, at the [address for devices](../docs/docs/reference/configuration.md#the-three-ports) |
| MCP | `/mcp` at the address for MCP ([AI assistants](../docs/docs/run/assistants.md)) |
| Database | `iostart`, beside the Shared ioSuite database (the accounts and every setting), both under the suite's one login; the tables are made on the first start and brought up to date by later versions by themselves |

From a shell, in the program folder (`/opt/iosuite` when installed as root):

```sh
.venv/bin/python -m iostart.cli check   # connect to the databases and say what is there
```

Accounts are the suite's: `iosuite admin NAME --app iostart` makes someone an admin of ioStart only (`iosuite admin NAME`: of
the whole suite), `iosuite password NAME` sets a password; see [Accounts and roles](../docs/docs/run/accounts.md).

## Configuration

ioStart has no file of settings. The machine's one file (`config.env` in the program folder) says how to reach the Shared
ioSuite database and which apps run here; everything else is kept in that database. Suite admins change it under
**Settings › Global settings › Settings**, which has a section for the whole suite and one for ioStart, or from a shell;
a change applies when the app starts again:

```sh
iosuite settings iostart        # what may be set, with the value stored now
iosuite set iostart HA_FEED 0    # no value: back to the default
```

| Setting | Meaning |
| --- | --- |
| `PUBLIC_URL`, `SYNC_URL`, `MCP_URL` | an address of its own for the pages, for devices and for MCP clients, when it is not the suite's |
| `DATA_DIR` | where the app writes on its own (`iostart/` in the machine's `DATA_DIR`) |
| `DB_NAME` | the name of its database (`iostart`) |
| `HA_FEED` | follow Home Assistant live (`1` or `0`; on by default). Off: no standing connection to Home Assistant; the page asks every few seconds instead |
| `SITE_ICONS` | fetch the bookmarked sites' icons (`1` or `0`; on by default) |
| `TIMERS_LOOP` | send “timer done” notifications (`1` or `0`; on by default) |
| `NEWS_LOOP` | fetch followed feeds in the background (`1` or `0`; on by default) |
| `TRMNL_PUSH` | push TRMNL screens (`1` or `0`; on by default) |

The suite's own settings (its address, the domain the sign-in is shared on, the time zone, how long deletions are kept), the
machine's file and the three ports are in the guide's [Configuration](../docs/docs/reference/configuration.md).

## Updates

The suite is one program with one version, so every app is updated together: **Settings › Global settings › Updates**
(suite admins, in any app) shows the installed version and the newest one, with one **Update** button; from a shell it is
`update.sh` in the program folder, and in Docker the image is pulled. See [Updates](../docs/docs/run/updates.md).

**Settings › Server** shows the version ioStart runs and has **Restart**. The log is one for the whole copy of the program,
each line marked with its app: suite admins read it under **Settings › Global settings › Logs**.

## Reverse proxy and HTTPS

ioStart is reached through the suite's three ports: the pages (80), devices (8443) and MCP (8444). A reverse proxy gives each
a name and HTTPS, for the whole suite at once, and can make people sign in first (Cloudflare Access, Authelia, oauth2-proxy):
[Reverse proxy and HTTPS](../docs/docs/run/reverse-proxy.md) and [Cloudflare Tunnel and Access](../docs/docs/run/cloudflare.md) in the
guide have the set-up, with Caddy and nginx examples, sign-in at the proxy and the optional check of app passwords at
Cloudflare's edge ([cloudflare/edge-auth](../cloudflare/edge-auth/README.md)).

The browser extension, the iPhone app, the widgets, the e-ink screens and the wall display use the address for devices, which stays outside a sign-in at the proxy.

## Tests

```sh
pip install -e '.[all,test]'          # in the program folder, once
python -m pytest iostart/tests     # on a test MariaDB of its own: a Docker container it starts, or IOSUITE_TEST_DB=host:port:user:password
```

Covered: status and sign-in, the tiles and where they point (this host, the forwarded host behind a proxy, Settings,
the environment), hiding an app, the weather (AccuWeather mocked: set-up, the place search, the server's copy and its
age, a stale reading when AccuWeather is down), Home Assistant (its API mocked: set-up, the card's entities and
their wording, the allowlist for switching, the search, the alerts), the tiles' glimpses (the apps' answers mocked: On this day and
Rediscover, the rest of today and what's next, steps and rings, the week's bills, an app that refuses or is down), the search box's finds in ioMoney, ioDocs and ioPix, the ioDocs tile, a task and a note from the search box, the bookmarks (groups, links, order, moves, the homepage import; Tidy up's check against a server made in the test, and its duplicates) and
what a viewer may not change. CI runs them against MariaDB.

## Layout

The package `iostart/` of the repository:

```
main.py            the application: start-up (tables, first admin, the update check), the suite's middleware, status and routes
mcp.py             the suite's one MCP server (/mcp): every app's tools passed on as the person asking, suite_apps, suite_version and update_suite
access.py          who may call a route: the markers every /api route carries (public, signed_in, editor, admin)
api.py             the REST API: the apps and their settings (sign-in, accounts, status, the server, updates and the log: iosuite_shared's routers)
apps.py            the suite's apps as they registered (iosuite_shared.suite) and the order of their tiles
status.py          is each app up (its /api/status) and does it have an update; is each bookmark reachable
layout.py          each account's own layout: hidden tiles and cards, the tiles' order, the photo strip
widgets.py         what the tiles and cards show, what the search box finds and adds: ioPix, ioCalendar, ioTask, ioHealth, ioMoney, ioDocs, ioNote and ioContact asked over their APIs with the viewer's sign-in
bookmarkcheck.py      Tidy up: the bookmarks whose address no longer answers, is gone or moved, and the same address kept twice
weather.py         AccuWeather: the settings, the place search, the cached conditions and forecast
homeassistant.py      Home Assistant: the settings, the chosen entities and their state, switching them, the search, the alerts
ha_feed.py         Home Assistant's websocket: state changes folded into the copy, streamed to the pages
bookmarks.py       the bookmark groups and links
news.py            the reader: feeds fetched once for everybody, each person's own subscriptions, read and starred; the loop
newsapi.py         its routes (/api/news)
feedread.py        RSS, Atom and JSON Feed as one shape, a site's feed found from its page, an article's HTML made safe, OPML
timers.py          kitchen timers: the family's, from the search box; the "timer done" notification loop
rates.py           the exchange rates for the search box's currency conversions (ECB, through Frankfurter)
auth.py            the shared accounts and the updater (iosuite_shared), as ioStart uses them
db.py              MariaDB access and the schema (the meta settings table, the bookmarks)
config.py          the settings: the suite's standard names (iosuite_shared.config) and ioStart's own
cli.py             python -m iostart.cli: migrate, check
__main__.py        python -m iostart: the server (HOST, PORT)
static/            the web app: index.html, app.js (one module, no build step), app.css, the icons (each app's tile shows the icon it registered, served by that app)
tests/             pytest, against a MariaDB of its own
```

### Growing the page

A tile is drawn from `/api/apps` (`iostart/apps.py`, `showHome` in `static/app.js`) and keeps a `.more` block under its
name, filled from `GET /api/widgets/<app>?tz=<IANA zone>` (`iostart/widgets.py`, `drawWidgets` in `static/app.js`). To give
another app a glimpse: a function in `iostart/widgets.py` that asks the app with `fetch()` (the viewer's credentials go
along) and returns what the tile needs, and a drawing function in `WIDGETS` in `static/app.js`. Images go through the
start page (its Content-Security-Policy allows only its own origin), as `/api/widgets/iopix/thumb/<id>` does.

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later), see [LICENSE](../LICENSE).

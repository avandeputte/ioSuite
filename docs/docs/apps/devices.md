---
description: Connect phones, Macs, calendar, reminders and contacts apps to ioSuite, and the address they use.
---

# Phones, Macs and other apps

## Every app, in the browser

Every web app has a phone layout and installs like an app: in Safari on the iPhone, Share › Add to Home Screen; in
Chrome on Android, the menu › Install app. Light, dark or the device's theme, kept with your account. Installing needs
HTTPS (or `localhost`).

## The address for devices

People open the suite's pages at one address, and what syncs in the background uses another: the **address for
devices** (port 8443 of the server, or the name your reverse proxy gives it: `SYNC_URL`). That goes for calendar,
reminders and contacts accounts, the ioPix, ioNote, ioStart and ioHealthSync apps, the iPhone widgets and the browser
extension. They sign in there with an app password; a browser's sign-in is not read on that port. An app that asks
for your name and password (the browser extension; a native app) sends them there once, with the code of two-step
sign-in when your account has it, and gets an app password of its own, which it keeps in place of what you typed:
Settings › Account lists it under the app's name, and signing out in the app removes it. AI assistants have a third
address, for MCP (port 8444).

That port is the one to open to the internet for phones, and it serves what they use and nothing else: calendar,
reminders and contacts sync, bookmark sync, ioHealth's uploads, and of each app's API only the calls its native apps
make, each one named in the app's manifest (`devices` in its `app.json`). No page, no script of the pages, no
reference of the API, no suite settings, and nothing at all of an app that has no native app (ioMoney, ioDocs,
ioThings, ioRecipe, ioDNS, ioBackup). Everything else is answered "not served at this port".

**Settings › Apps and devices** in each app shows the exact addresses to type. A calendar or contacts account set up
with the pages' address is answered there too. An e-ink screen, the wall display or a script is given the pages'
address: an app password or the device's own key is taken for an app's `/api/` there. See
[The three ports](../reference/configuration.md#the-three-ports).

## Native apps

| App | Device | What it does | Source |
| --- | --- | --- | --- |
| **ioPix** | iPhone, iPad, Mac, Apple TV | your photos, people and places in a native app; Send to ioPix from the share sheet, the camera roll or a Mac menu bar uploader | [iosuite-apps/iopix](https://github.com/avandeputte/iosuite-apps/tree/main/iopix) |
| **ioNote** | Mac, iPhone, iPad | the clipboard Inbox and screenshots on the Mac, notes everywhere, synced with the ioNote server and usable offline | [iosuite-apps/ionote](https://github.com/avandeputte/iosuite-apps/tree/main/ionote) |
| **ioHealthSync** | iPhone | copies Apple Health data to the ioHealth server: everything or the types you pick, incremental, in the background | [iosuite-apps/iohealth](https://github.com/avandeputte/iosuite-apps/tree/main/iohealth) |
| **ioStart** | iPhone, iPad | the start page's bookmarks: browse, search and edit them, and bookmark a page from any browser's share sheet | [iosuite-apps/iostart](https://github.com/avandeputte/iosuite-apps/tree/main/iostart) |

They are built from source with Xcode and XcodeGen (`brew install xcodegen`, then `xcodegen generate`) from the
[iosuite-apps](https://github.com/avandeputte/iosuite-apps) repository; each app's README has the steps. They sign in with your suite account. Behind Cloudflare, the address for devices stays outside Access (see
[Cloudflare](../run/cloudflare.md)).

## Calendars, tasks and contacts on every device

ioCalendar, ioTask and ioContact speak the standards phones and desktop apps already use. Settings › Apps and devices in each
app shows the exact addresses to type.

| On | ioCalendar | ioTask | ioContact |
| --- | --- | --- | --- |
| iPhone, iPad, Mac | CalDAV, or the **configuration profile** from Settings › Apps and devices (one tap, with a device-only app password inside) | Apple Reminders over CalDAV, or its configuration profile | CardDAV, or its configuration profile |
| Android | CalDAV with DAVx⁵ | CalDAV with DAVx⁵ and Tasks.org or jtx Board | CardDAV with DAVx⁵ |
| Thunderbird, Evolution, GNOME, KDE | CalDAV | CalDAV (to-dos) | CardDAV, LDAP |
| Google Calendar, Outlook | a private `webcal://` subscription link (read-only) | | vCard export |
| Mail apps, desk phones, printers | | | the LDAP directory (read-only) |

Sign these in with your user name and an **app password** (Settings › Account › App passwords), one per device, so
losing a phone means revoking one password. An app password can be limited to the sync protocols only; the ones in the
Apple profiles always are. Away from home, phones need HTTPS: see [Reverse proxy and HTTPS](../run/reverse-proxy.md).

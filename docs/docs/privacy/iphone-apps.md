# Privacy policy: the iPhone and iPad apps

*Last updated 27 November 2026.*

This policy covers the ioSuite apps for iPhone and iPad: **ioStart**, **ioNote** and **ioHealthSync** (ioPix has
[its own](https://iopix.net/privacy/)). Each one is an app for an ioSuite server: a self-hosted program that you, or
someone in your household, runs on your own computer or server. The apps' author does not run a server for them.

## In short

The apps send what you keep in them to one place only: the ioSuite server whose address you type when you sign in.
Nothing is sent to the apps' author or to anyone else. Nothing is sold, shared, or used for advertising. The author
collects no data at all.

## Signing in

You type your server's address for apps, your account name and your password (and, when your account has two-step
sign-in, the code from your code app). They are sent once to that server, which checks them and answers with an
app password made for this device. The app keeps only that app password, in the iPhone's Keychain, and sends it
with every request to your server. Your password and code are not kept. You can see and remove the app password on
the start page under *Settings › Account*; *Sign out* in the app removes it too.

## What each app handles

- **ioStart**: your bookmarks, the start page's Today list (events, tasks, birthdays and bills from the other apps on
  your server), your news feeds and their articles. Pages you open from a bookmark or an article are loaded directly
  from that website, which sees your visit as it would in Safari. A copy of what the start page said last is kept on
  the device so the app and its widgets work offline.
- **ioNote**: your notes, folders, tags and the images and files in them. A full copy is kept on the device, so
  reading, searching and writing work offline; changes are sent to your server when it can be reached. Text in
  images is read on the device with Apple's Vision framework.
- **ioHealthSync**: the Apple Health data you allow it to read, all of it or only the types you pick. It reads that
  data and copies it to your own server; it never writes to Health. Health data is used only for that copy: it is
  not used for advertising or marketing, not shared with anyone other than your own server, and not stored
  anywhere in iCloud by the app.

## Where it goes

- **To your server only**, at the address you typed, over the connection that address uses (HTTPS when it starts
  with `https://`).
- **Nobody else.** No analytics, no telemetry, no crash reports, no advertising, no tracking and no third-party
  services. The apps' author receives nothing.

What happens to your data on the server is up to whoever runs that server; it stays in its database.

## Deleting your data

Signing out removes the app password and what the app keeps on the device; deleting the app removes everything it
kept on the device. Your data on the server is deleted from the server's web pages, or by its administrator, who can
also delete your whole account (*Settings › People*).

## Changes

If an app ever handles other data or sends it anywhere else, this page will say so first, with a new date at the
top.

## Contact

Questions about this policy: open an issue at
[github.com/avandeputte/iosuite/issues](https://github.com/avandeputte/iosuite/issues). The apps' source is at
[github.com/avandeputte/iosuite-apps](https://github.com/avandeputte/iosuite-apps).

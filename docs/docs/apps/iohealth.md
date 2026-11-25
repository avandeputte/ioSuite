---
description: ioHealth, Apple Health data on your own server, with the ioHealthSync iPhone app.
---

# ioHealth <small>health</small>

Copies your Apple Health data, all of it or just the types you pick, into your own MariaDB database, and gives you a
fitness web app on top of it. Nothing goes through a cloud service: the **ioHealthSync** iPhone app uploads straight to
your server.

[The ioHealth page on the website, with more screenshots →](https://iosuite.iothing.net/ioHealth/)
{ .md-button }

![The ioHealth dashboard: activity rings, last night's sleep and the trend of every metric](../img/iohealth.jpg)

## What it does

- **Dashboard**: today's rings and the last week's, last night's sleep, every metric against your usual, recent
  workouts, and a heads-up list (resting heart rate up, HRV or sleep down against your usual, glucose lows, goal
  streaks). What leaves your usual also comes as a notification, on the day it begins.
- **Metrics**: chart any synced type over any range, zoom and pan, stack or overlay several, compare with a year
  earlier, goal lines.
- **Workouts** with their GPS routes on a map, splits, heart rate zones, training load; **Sleep** stages per night;
  **Glucose** from a CGM or meter; **Correlations** between any two metrics; **Records**.
- **Medicines and allergies**: each medicine with its dose and times, a reminder at each time (with a Taken button
  where the phone shows one), today's doses to tick taken or skipped, and the last 30 days at a glance.
- **Emergency card**: a wallet-size card to print, cut out and fold, with your allergies, conditions, blood type,
  medicines, doctor, the people to call and your health insurance.
- **Per person**: everyone in the household syncs into their own account and sees only their own data.
- CSV export of any chart, PDF of any page, and a JSON API with app passwords for scripts.

![ioHealth's sleep page](../img/iohealth-sleep.jpg)

## On its own

ioHealth is a complete fitness web app. It needs its database, the Shared ioSuite database, and the ioHealthSync app
on each iPhone. Health data only exists on the iPhone, so the app is iPhone only. The phone allows plain `http://` only
to addresses on your own network; anything else must be HTTPS.

## With the other apps

- **ioStart**: today's steps with the last seven days as bars, the move, exercise and stand rings, and last night's
  sleep on the ioHealth tile.
- **ioContact** and **ioDocs**: the emergency card takes your doctor and the people to call from your contacts, and
  your health insurance from your papers; it shows only what you see in those apps.
- The same accounts as every other app: each person signs in to ioHealthSync with their suite account.

## Install

ioHealth is one of the suite's apps: tick it in the [installer](../start/linux-mac.md), the [Docker Compose builder](../start/docker.md) or the [Proxmox script](../start/proxmox.md), or add it later to a server that runs the suite:

```sh
iosuite install --add iohealth
```

| | |
| --- | --- |
| Address | `/health/` at the suite's address (`https://home.example.com/health/`), and a name of its own if you give it one |
| Devices | the ioHealthSync iPhone app's sign-in and its uploads at `/health/v1/…`, at the [address for devices](../reference/configuration.md#the-three-ports); nothing else of ioHealth is served there |
| Source | [iohealth](https://github.com/avandeputte/iosuite/tree/main/iohealth) (server), [iohealth-apps](https://github.com/avandeputte/iosuite-apps/tree/main/iohealth) (the ioHealthSync iPhone app) |

The iPhone app is built from [iosuite-apps/iohealth](https://github.com/avandeputte/iosuite-apps/tree/main/iohealth) with Xcode. See
[Phones, Macs and other apps](devices.md).

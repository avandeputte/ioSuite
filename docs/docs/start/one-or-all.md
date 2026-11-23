---
description: Run one ioSuite app or all of them, what the apps add to each other, and how to add or remove one later.
---

# One app or all of them

ioSuite is **one program that runs the apps you tell it to**. Every app's code comes with it; a line in the machine's
file says which of them this machine runs. No app needs another: pick one, or all thirteen.

## Just one app

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash -s -- --apps iopix
```

A photo app alone is a perfectly good install. It needs somewhere to run (a Proxmox VE container, a Docker host, or any
Linux machine) and a MariaDB or MySQL server; the installer can create its databases for you. The app does not look
for the others, does not show empty spaces for them, and does not need the [ioStart start page](../apps/iostart.md).
Its Settings show People, Apps, Servers and Keys to suite admins all the same: those manage the accounts and the
settings in the Shared ioSuite database, whether one app uses them or all of them.

| You want | Run |
| --- | --- |
| A web app for your photos (with digiKam, or without) | [ioPix](../apps/iopix.md) |
| Notes and clipboard snippets on your Mac and iPhone | [ioNote](../apps/ionote.md) and the Mac / iPhone app |
| A family calendar on every phone | [ioCalendar](../apps/iocalendar.md) |
| Shared task lists, in Apple Reminders too | [ioTask](../apps/iotask.md) |
| The family's recipes, typed in or imported from the web | [ioRecipe](../apps/iorecipe.md) |
| Everything you own, its manuals, warranties and upkeep (instead of Homebox) | [ioThings](../apps/iothings.md) |
| The household's net worth, transactions from Monarch Money, a portfolio, the house and the cars | [ioMoney](../apps/iomoney.md) |
| Passports, licenses, policies and certificates, read off their scans, with a reminder before they expire | [ioDocs](../apps/iodocs.md) |
| A family address book on every phone and in every mail app | [ioContact](../apps/iocontact.md) |
| Your Apple Health data, kept and charted at home | [ioHealth](../apps/iohealth.md) and the ioHealthSync iPhone app |

## Adding another app later

```sh
iosuite install --add iocalendar
```

Or run `iosuite install` and tick it in the list. Its database is made, its packages are installed and the service
starts again with it. From then on:

- **Everyone already has an account.** The accounts, passwords and app passwords are the Shared ioSuite database's, so
  the new app knows everybody. Each person gets the app's default role there (member, unless an admin changes it in
  Settings › Apps › The apps).
- **One sign-in covers all of them**: they are at one address, each in its folder.
- **They find each other.** Every app writes its name, address and version in the suite's list of apps when it starts,
  so nobody types an address into another app.

Nothing about the first app changes, and neither app needs the other to keep running.

## What some apps add to each other

These are extras, switched on by having both apps; neither app needs the other:

| Together | You get |
| --- | --- |
| ioContact + ioCalendar | a read-only **Birthdays** calendar with the birthdays and anniversaries from ioContact; the people on an event are picked from your contacts |
| ioPix + ioContact | link a contact to a person named in ioPix: that face becomes the contact's photo, on phones (CardDAV) and in the LDAP directory too |
| ioStart + any app | a tile per app on the start page with what matters today: the next events, the tasks due, photos from this day, today's steps and last night's sleep |
| ioStart + ioCalendar | "Quick add": type "dinner fri 19:00" in the start page's search box to make the event |
| ioStart + ioTask or ioNote | "t buy milk sat" in the search box adds a task, "n the gate code is 4411" a note |
| ioStart + ioMoney | the bills due this week on the tile, and payees and transactions in the search box |
| ioDocs + ioCalendar or ioStart | the day each passport, license or policy expires on the calendar; the ones to renew on the start page's tile |
| any two | the same accounts and roles, one admin panel, the same Settings, one sign-in, one log |

## On more than one server

The apps do not have to be on one machine. Install the program on a second server, give it the **same Shared ioSuite
database**, and tell it which apps it runs: ioPix on a machine with the photos and a strong processor, the rest on a
small one. It is still one suite: the same accounts, one sign-in, every app in the start page and in the others'
menus, one log screen. See [Several copies and several servers](several-apps.md).

## Removing an app

```sh
iosuite install --remove iohealth
```

The service starts again without it, and it leaves the start page and the other apps' menus. The other apps don't
notice. **Its database and its data stay**, and so do its roles and settings in the Shared ioSuite database, so adding
it again brings everything back. Drop its database yourself to be rid of the data.

In Docker, take it out of `APPS` in the stack file and start the stack again (`docker compose up -d`): the same
happens.

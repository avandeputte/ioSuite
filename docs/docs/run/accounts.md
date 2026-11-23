---
description: One account for every app of ioSuite, a role per app, suite admins and app passwords.
---

# Accounts and roles

The accounts live in the **Shared ioSuite database**, not in the apps: everyone has **one name and one password for
all of them**, and one sign-in at the suite's address (and across the apps' own names when they share a domain).

## What is shared and what is per app

| Shared (one per person) | Per app |
| --- | --- |
| name, display name, email, password | the role: `none`, `viewer`, `member`, `editor` or `admin` |
| sessions (the `iothing_session` cookie) | settings and other per-person data |
| suite admin, shown on the sign-in screen or not | app passwords (each made in, and for, one app) |
| sign-in at the proxy (Cloudflare Access...) | sign-in required, default role |

- A **suite admin** is admin in every app and manages the accounts. The first account is one.
- An app's **admin** manages that app's own settings. The suite's settings, the updates, the log and the accounts are
  the suite admins'.
- An **editor** changes shared things (the Family calendar, the Family address book) as well as their own.
- A **member** keeps private things of their own (a Personal calendar, their own lists and recipes) and sees the
  family's read-only.
- A **viewer** only reads: nothing is changed with that role.
- What is private stays private: notes and health data belong to one account, admins included. (A note an editor
  puts in ioNote's Family space is the one exception: everyone reads those.)
- An account without a role in an app holds that app's **default role** (`member` unless changed). Set the default to
  `none` and the app is by invitation only.
- A **passwordless** account signs in with one click, on the home network only, and is a member at most everywhere:
  for a child, or a tablet on the kitchen wall.

## Where to manage them

In any app, as a suite admin: **Settings › People** (People, Family, Roles, App passwords, Sign-in at the proxy),
**Settings › Apps** (the apps and all their settings), **Settings › Servers** (updates, the certificate, the jobs, the log) and
**Settings › Keys**. It is the same panel in every app.
Everyone has **Settings › Account** (name, email, password, two-step sign-in and passkeys, their app passwords) and
**Settings › Display** (the theme, kept with the account).

From a shell on the server:

```sh
iosuite list
iosuite create emma --email emma@example.com
iosuite role emma iocalendar editor
iosuite password emma
iosuite sign-in-reset emma        # a lost phone: two-step sign-in off, passkeys removed
```

## Deleting someone

Delete an account under **Settings › People › People**: open the person and press Delete. Before anything happens,
the panel asks every app what is only that person's and lists it: their private calendars, lists, address book,
recipes and cookbooks, private money accounts, notes, health data, favourites, private albums, own bookmarks and home page layout, and their
sessions, app passwords and notification devices. To go ahead you type their user name. Each app then removes its
part, the account goes, and the panel shows what was removed.

What they added to something everyone shares stays for the others: events on the Family calendar, tasks on a shared
list, family recipes, shared bookmarks and albums. An app that cannot be reached at that moment removes the person's
data the next time it starts.

## Estate planning PDF

If someone in the family dies, the people settling the estate need their details in one place. Open the person under
**Settings › People › People** and press **Make the estate PDF**; anyone can make their own under **Settings ›
Account**. Every app adds what it knows about that person:

- **ioContact**: their own card and their closest family (spouse or partner, parents, siblings, children, emergency
  contacts) with each one's phone, email and address. Link their card under Settings › People › Family.
- **ioDocs**: their documents and the household's (wills first, then insurance, deeds, tax papers…), with numbers,
  dates and the scans.
- **ioMoney**: their accounts and the household's, with the bank, the last digits of the number and the balance; the
  house and the cars with the loan against them.
- **ioThings**: what is theirs, with where it is, its serial number and what it cost.

A suite admin's PDF includes the person's private documents and accounts. If an app cannot be reached, the first page
says so: make the PDF again once it is back. The PDF holds private information; keep it somewhere safe.

## App passwords

Phones, sync apps, scripts and AI assistants sign in with an **app password** instead of your password: one per device
or tool, made under Settings › Account › App passwords, revocable on its own. Each has a scope:

| Scope | Reaches |
| --- | --- |
| everything | what the account may do: the REST API, MCP, sync |
| sync only | the app's sync protocols (CalDAV, CardDAV, LDAP) and nothing else |
| read only | GET requests, outside MCP and sync |

An app password belongs to the app it was made in; one made in ioStart for everything also signs in at every app's
MCP address. From outside your network an app password is taken at the suite's addresses for devices and for MCP,
not with the pages: see [The three ports](../reference/configuration.md#the-three-ports).

## Sessions and passwords

Sessions are random tokens in an HttpOnly cookie, valid for 30 days and renewed while in use; each records where it
began and was last seen. Passwords are hashed with Argon2id, and wrong passwords cost a growing wait. Sign out ends this
browser's session; an admin can end any session under Security › People.

## Who added and changed what

Every event, task, contact, note, recipe, thing, document, transaction, house or car, and photo keeps a short record:
who added it and who changed it last, with what, and when. Under an item, below **Linked**, one quiet line says it
("Added by Alex with the web page (Safari on Mac) · changed by Sam with CalDAV (iPhone calendar) yesterday, 8:02 AM"),
and **History** opens its last 20 changes, kept 90 days, each with a few words on what changed (time, place, title) but
never what the item says. The MCP tools that read one item answer it too, under `changes`.

"With what" is told from how the change came in: the web page (and the browser), a native app, CalDAV or CardDAV, MCP,
another app password, an import (a file, Homebox), a sync (Monarch Money, a subscribed calendar) or the app itself (a
rule, public holidays, the demo data). When an app password signed the change in, its name is shown, so name them after
the device ("iPhone calendar", "Claude"). A change the start page made for someone (quick add, the wall display, the
suite's MCP server) names the start page as well as what the person used.

The record is shown only to people who may see the item, admins included in that rule: a private event's record is
as private as the event. The address a change came from is shown to the person who made it and to suite admins;
everyone else sees "at home" or "away from home".

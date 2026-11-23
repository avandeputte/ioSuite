---
description: ioContact, contacts for the family in the ioThing suite.
---

# ioContact <small>contacts</small>

A contact manager for the whole family: a web app, and the standard protocols every mail, contacts and calendar app
already speaks, so the same contacts show up on phones, in Apple Contacts, Outlook, Thunderbird and anywhere else.

[The ioContact page on the website, with more screenshots →](https://iosuite.iothing.net/ioContact/)
{ .md-button }

![ioContact's family tree, drawn from the relations in the address book](../img/iocontact.jpg)

## What it does

- **Contacts** with every field a phone has: names, any number of phones, emails and addresses, birthdays,
  anniversaries, company, social profiles, websites, labels, notes.
- **Relations** between contacts, kept on both sides (make Tim Mary's son and Mary becomes Tim's mother), and a
  **family tree** laid out by generation.
- **Address books**: the shared Family book, a private Personal one for each account, and more as you like.
- **Clean up**: likely duplicates with the reasons, compare and merge (and undo), data quality checks with one-click
  fixes, and suggestions from public profiles that wait for you to accept them.
- **Everywhere**: CardDAV for Apple Contacts, DAVx⁵ on Android and Thunderbird; vCard 3.0 and 4.0; an LDAP directory
  for mail apps and printers; a family birthday calendar to subscribe to; a REST API.

## On its own

ioContact is a complete family address book. It needs its database and the Shared ioSuite database, and HTTPS if
phones should sync away from home. The LDAP directory speaks plain LDAP: keep it on the home network.

## With the other apps

- **ioCalendar** shows the birthdays and anniversaries as a Birthdays calendar, and picks the people on an event
  from your contacts.
- **ioPix**: link a contact to a person named in ioPix and that face is the contact's photo, everywhere.
- **ioStart**: a Birthdays card on the start page, and the search box finds people.

## Install

ioContact is one of the suite's apps: tick it in the [installer](../start/linux-mac.md), the [Docker Compose builder](../start/docker.md) or the [Proxmox script](../start/proxmox.md), or add it later to a server that runs the suite:

```sh
iosuite install --add iocontact
```

| | |
| --- | --- |
| Address | `/contacts/` at the suite's address (`https://home.example.com/contacts/`), and a name of its own if you give it one |
| Devices | CardDAV at `/contacts/dav/`, the birthdays feed at `/contacts/cal/…`; LDAP on its own port (3890), at the [address for devices](../reference/configuration.md#the-three-ports) |
| MCP | `/contacts/mcp` at the address for MCP ([AI assistants](../run/assistants.md)) |
| Source | [iosuite2/iocontact](https://github.com/avandeputte/iosuite2/tree/main/iocontact) |

---
description: ioNote, notes, clipboard snippets and screenshots in the ioThing suite.
---

# ioNote <small>notes</small>

Your notes, clipboard snippets and screenshots, searchable everywhere. The server keeps them in its database, pictures
included, and gives you a web app; the **ioNote apps for Mac, iPhone and iPad** keep a full copy and sync with it.

[The ioNote page on the website, with more screenshots →](https://iosuite.iothing.net/ioNote/)
{ .md-button }

![ioNote with folders, tags and a note open](../img/ionote.jpg)

## What it does

- **Notes** with a title, text, tags, a folder, a pin and optionally a picture (a screenshot, a photo) with the text read
  from it.
- **Search** every word you type, in titles, text, tags and the text inside pictures, through MariaDB's full-text index.
- **Web app**: folders and tags in the sidebar, editing that saves as you type, pictures pasted or dropped anywhere
  become notes, a change log, trash, import and export.
- **On the Mac**: everything you copy and every screenshot lands in an Inbox on that Mac; keep what is worth keeping
  as a note. Right-click › Save to ioNote in any app. On the **iPhone and iPad**: the same notes, paste and photos.
- **Offline**: the apps work without the server and send their changes when it is back.
- **Private**: every note belongs to the account that made it; nobody else sees it, admins included.
- **Family notes**: the exception you choose. A note put in the **Family** space (the wifi password, the bin days, the
  packing list) is read by everyone with a role in ioNote; editors and admins write and change those notes, and can
  take one back, which makes it their own again. Family notes sit in no folder; tags group them.

## On its own

ioNote is a complete notes app. It needs its database (MariaDB or MySQL) and the
Shared ioSuite database for its accounts. Text recognition for pictures added in the web app is optional (RapidOCR,
about 60 MB); the Mac and iPhone read the text on the device.

## With the other apps

- **ioStart**: the start page's search box searches your notes, and "n the gate code is 4411" there adds one.
- The same accounts and sign-in as every other app.

## Install

ioNote is one of the suite's apps: tick it in the [installer](../start/linux-mac.md), the [Docker Compose builder](../start/docker.md) or the [Proxmox script](../start/proxmox.md), or add it later to a server that runs the suite:

```sh
iosuite install --add ionote
```

| | |
| --- | --- |
| Address | `/notes/` at the suite's address (`https://home.example.com/notes/`), and a name of its own if you give it one |
| Devices | the Mac and iPhone apps, at the [address for devices](../reference/configuration.md#the-three-ports): of `/notes/api/…` it serves the calls they make (sign-in, sync, pictures and attachments) and nothing else |
| MCP | `/notes/mcp` at the address for MCP ([AI assistants](../run/assistants.md)) |
| Source | [ionote](https://github.com/avandeputte/iosuite/tree/main/ionote) (server), [ionote-apps](https://github.com/avandeputte/iosuite-apps/tree/main/ionote) (Mac, iPhone, iPad) |

The Mac and iPhone apps are built from [iosuite-apps/ionote](https://github.com/avandeputte/iosuite-apps/tree/main/ionote) with Xcode. See
[Phones, Macs and other apps](devices.md).

---
description: ioPix, the photo app of the ioThing suite.
---

# ioPix <small>photos</small>

A web app for a photo library, for browsing, searching and managing photos from any browser. It started as a web
companion for a [digiKam](https://www.digikam.org) library, and works just as well without digiKam: point it at a
folder of photos and it keeps the library itself.

[The ioPix page on the website, with more screenshots →](https://iosuite.iothing.net/ioPix/)
{ .md-button }

![ioPix Explore: library totals, photos from this day in past years and a shuffle of older ones](../img/iopix-explore.jpg)

**The full ioPix guide is at [iopix.net](https://iopix.net/docs/)**; this page is the short version.

## What it does

- **Browse** by date, folder, album, person, place and tag; a viewer with an info panel (rating, caption, faces,
  tags, location); a map of every geotagged photo; places worked out offline from GPS positions.
- **Search** by what is in the photos (content search), by text in them, by objects and faces, with models that run on
  your own server. Each feature is optional and downloads its model when you turn it on.
- **Edit** ratings, titles, captions, tags, dates, locations and faces, written to sidecars or into the files, the way
  digiKam writes them, with an edit log and undo for every change.
- **People**: name the faces in your photos; with ioContact, a person can be a contact's photo.

![The ioPix viewer with its info panel](../img/iopix-viewer.jpg)

## On its own

ioPix is a complete photo app. It needs the photos (a folder, read-only unless you turn on editing), a MariaDB or MySQL
database for what it builds, and the Shared ioSuite database for its accounts. digiKam is optional.

## With the other apps

- **ioContact** can link a contact to a person named in ioPix; the face becomes the contact's photo.
- **ioStart** shows photos taken on this day in earlier years on the ioPix tile, and a strip of photos under the
  tiles.
- The start page's search box finds the people, albums, folders and places of your photos, and searches ioPix too.

## Install

ioPix is one of the suite's apps: tick it in the [installer](../start/linux-mac.md), the [Docker Compose builder](../start/docker.md) or the [Proxmox script](../start/proxmox.md), or add it later to a server that runs the suite:

```sh
iosuite install --add iopix
```

| | |
| --- | --- |
| Address | `/pix/` at the suite's address (`https://home.example.com/pix/`), and a name of its own if you give it one |
| Devices | scripts with an app password at `/pix/api/…`, at the [address for devices](../reference/configuration.md#the-three-ports); the iPhone, iPad, Mac and Apple TV apps show ioPix's own pages, so they take the pages' address |
| MCP | `/pix/mcp` at the address for MCP ([AI assistants](../run/assistants.md)) |
| Source | [iosuite/iopix](https://github.com/avandeputte/iosuite/tree/main/iopix) |

The installer asks for the photos folder and, when you use digiKam, the folder of its database; the Proxmox script bind-mounts both into the container. ioPix can run in a [copy of its own](../start/several-apps.md), so that a scan of a large library never slows the other apps. See [iopix.net › Install](https://iopix.net/docs/) for digiKam on SQLite or MariaDB, the AI models and the album roots.

---
description: One version for the whole suite, and one button that updates it.
---

# Updates

The suite is one program with one version: every app is updated together.

## In the web app

Once a day the suite asks GitHub whether the main branch has a newer version (only the public list of branches is
read; nothing about your server is sent). When there is one, suite admins see a note on the start page, and
**Settings › Global settings › Updates** (in any app) has:

- the installed version and the newest one, with **Update** and **Check now**;
- the daily check, on or off for the whole suite;
- **Details**: every app's line, with the copy it runs in, its version and how its last update went. It opens by itself
  when something failed or was left behind.

**Update** runs `update.sh` in the program folder: the new version's Python packages first, then the code (a failed
step leaves the running version as it was), and the service starts again; the apps add what a new version needs to
their tables as they start. The page follows along and reloads when the suite is back. When the suite runs on several
servers, each of them sees the request and updates itself.

**Settings › Server** in each app shows the version, where the log is, and **Restart**.

## From a shell

```sh
sh /opt/iosuite/update.sh            # the latest code, the same settings, the service restarted
sh /opt/iosuite/update.sh --check    # only look
```

In a Proxmox container, `update` does the same.

## In Docker

Pull the image instead: `docker compose pull && docker compose up -d`.

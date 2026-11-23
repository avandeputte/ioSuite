---
description: The app databases and the Shared ioSuite database, the one login they share, and how their tables are named.
---

# Databases

## Two kinds, one login

**An app's own database** holds everything the app keeps: events, contacts, notes (pictures included), health
samples, the photo library's index. One per app.

**The Shared ioSuite database** (`iosuite` by default) holds what is the same for every app:

- the accounts, their passwords (Argon2id), sessions and app passwords;
- each account's role in each app, and each app's default role and sign-in requirement;
- **every setting**: the whole suite's and each app's (see [Configuration](configuration.md));
- the list of apps: every app writes its name, version, address and the copy of the program it runs in there when it
  starts, which is how the start page and the other apps find it without anyone typing an address;
- keys and tokens for services outside the suite, and sign-in at the proxy.

All of them are on **one MariaDB or MySQL server**, reached with **one login**: the one in the machine's `config.env`
(`IOSUITE_DB_USER`, `iosuite` by default). It has every right on the Shared ioSuite database and on each app's
database, and nothing else on the server.

## Default names

| App | Database | Table prefix |
| --- | --- | --- |
| Shared ioSuite database | `iosuite` | `ios_` |
| ioPix | `iopix` | `pix_` |
| ioNote | `ionote` | `nts_` |
| ioCalendar | `iocalendar` | `cal_` |
| ioStart (start page) | `iostart` | `prt_` |
| ioContact | `iocontact` | `con_` |
| ioHealth | `iohealth` | `hlt_` |
| ioDNS | `iodns` | `dns_` |
| ioTask | `iotask` | `tsk_` |
| ioBackup | `iobackup` | `bkp_` |
| ioRecipe | `iorecipe` | `rcp_` |
| ioThings | `iothings` | `thg_` |
| ioMoney | `iomoney` | `mny_` |
| ioDocs | `iodocs` | `doc_` |

An app's database can have another name: its `DB_NAME` setting (Settings › Apps › All settings). Every table
carries its app's prefix. The tables are created on the first start; a later version adds the columns and indexes it
needs by itself when it starts.

## Creating them

The installer does it when you give it a MariaDB administrator once (`--db-admin root`, or the question it asks): the
databases of the apps you chose, the Shared ioSuite database and the login, with a password it makes up and writes in
`config.env`. Nothing is dropped, and the administrator's password is used once and not written anywhere. Adding an app
later creates its database the same way.

To make them yourself instead:

```sql
CREATE USER 'iosuite'@'app-host' IDENTIFIED BY 'a-good-password';
CREATE DATABASE iosuite CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL ON iosuite.* TO 'iosuite'@'app-host';
CREATE DATABASE iocalendar CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL ON iocalendar.* TO 'iosuite'@'app-host';
-- and so on, a database per app
```

`app-host` is the machine the program runs on (`localhost` when MariaDB is on the same machine); a login for any host
(`'%'`) with a password someone could guess is what to avoid. When the suite runs on two servers, the login exists for
each of them.

## Backups

Back up the databases with ioBackup, the suite's admin tool for database backups (see
[ioBackup](../apps/iobackup.md)): it backs up the database server on a schedule to a folder or Google Drive, keeps the
newest few, and restores whole databases or single tables. Your usual MariaDB tools (`mariadb-dump`) work too. The
Shared ioSuite database belongs in every backup: it has the accounts and the settings of all the apps. ioPix keeps a
data folder too (thumbnails, models, the edit log's backups), and ioNote can export every note to a file under Import
and export.

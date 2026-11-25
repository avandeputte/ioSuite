# ioDocs

*The family's papers, in ioSuite (with [ioPix](../iopix/), [ioNote](../ionote/), [ioContact](../iocontact/), [ioCalendar](../iocalendar/), [ioTask](../iotask/), [ioRecipe](../iorecipe/), [ioThings](../iothings/), [ioMoney](../iomoney/), [ioHealth](../iohealth/) and the [ioStart](../iostart/) start page).*

A self-hosted home for the family's papers: passports, ID cards, driver's licenses, visas, insurance policies, the car's
registration, birth and marriage certificates, wills, health cards. Each one with its scans, who it belongs to, its
number and dates, and a reminder before it expires, early enough to renew it (a passport nine months ahead, a policy a
month). Drop a scan or a photo and it is **read**: the text off the page, the machine-readable lines of a passport or
an ID card, the barcode on the back of a US or Canadian driver's license, which fill the document in. FastAPI and a
single-page vanilla JS app, everything stored in MariaDB / MySQL (the scans too), Tesseract for the reading, and the
suite's shared library ([`iosuite_shared/`](../iosuite_shared/)).

## What it does

- **Documents** of a kind (passport, passport card, ID card, driver's license, visa, residence permit, insurance
  policy, vehicle registration, health and vaccination, birth, marriage, property, will and legal papers, tax,
  diplomas, memberships and cards, other), each with its title, number, issuer, country, the day it was issued and the
  day it expires, notes, fields of your own (a policy's deductible, the agent's phone) and its scans and files.
- **Whose it is**: the family members it is for (the suite's one family list), or none for the household's own papers
  (the home insurance). By person, by kind, and a search over everything, the text read off the scans included.
- **Who sees it**, per document: *the family* (everyone with a role here), *its people and the grown-ups* (the people
  it is for, whoever added it, and the editors and admins; the usual), or *private* (only its people and whoever added
  it: a will). New accounts have no role here (as in ioMoney): an admin gives one in Settings › People.
- **Reading scans** (Tesseract on the server, `iodocs/ocr.py`): a passport's or ID card's machine-readable zone (TD1, TD2
  and TD3, with their check digits) gives the kind, number, country, name, birth date, sex and the expiry. The zone is
  found by reading each band of the picture (turned too, for a photo taken sideways or upside down) with a Tesseract
  model trained on its font, `iodocs/tessdata/mrz.traineddata` (from DoubangoTelecom/tesseractMRZ, BSD licence, see
  `iodocs/tessdata/NOTICE`), until one gives a zone whose check digits hold. The issue date is only in the printed words:
  it is filled in when every reading of the page gives the same day that fits the expiry (10, 7, 5, 6 or 3 years), else
  left empty and the person is told to type it in; the PDF417
  barcode on the back of a North American license (AAMVA) gives the number, the state, the dates, the address and the
  class; anything else is read as text, for its dates (the policy period, "EXP", "4b"), its number and its kind. A PDF's
  own text is used when it has some, else its pages are read. What is read fills in the fields still empty, never
  over what you wrote: what differs is offered, to take or leave. **Read again** on any file.
- **To renew**: what has expired or is within its reminder (the kind's usual, or its own number of days, or none), on
  a page of its own and in the morning notification (web push, *Papers to renew*: on the reminder's first day, a week
  before, the day itself and the day after), to the document's people, or to the editors and admins for the
  household's papers.
- **Renew**: the new passport in place of the old one, which is archived and linked to it.
- **Number shown on demand**: a document's number is masked until **Show**, with **Copy**.
- **Who may do what**: viewers look; members add documents and change the ones they added or that are theirs; editors
  change everything they see; admins too, and the settings.
- **Linked items**: link a document to an event, a contact, a note, a thing or a transaction elsewhere in the suite.
- **AI assistants**: an MCP server ("when does Ava's passport expire?", "what's our car insurance policy number?").
- **With the other apps**: ioCalendar shows the day each document expires; the start page has a *To renew* tile and
  finds documents in its search box.
- **Settings › People, Apps, Servers and Keys** (suite admins): the suite's people, their role in every app, app
  passwords and sign-in at the proxy; the apps, keys and tokens (iosuite_shared's panel, the same in every app).
- Light and dark, phone-sized screens (a photo straight from the phone's camera), installable as an app.

## Run

ioDocs is one of the apps of [ioSuite](../README.md), one program that runs the apps it is told to. Install the suite
with ioDocs in it, alone or with the others, on any Linux machine:

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash -s -- --apps iodocs
```

It asks for the MariaDB server, the first admin and the suite's address, then starts the service; leave `--apps` out
for the list of every app, to tick. On a server that already runs the suite:

```sh
iosuite install --add iodocs       # --remove iodocs stops running it; what it stored stays
```

In Docker, name it in `APPS` in the stack file ([docker-compose.yml](../docker-compose.yml); empty there: every app); on
Proxmox VE, tick it in the list the container's script shows. The guide has each way in full:
[any Linux or Mac](../docs/docs/start/linux-mac.md), [Docker](../docs/docs/start/docker.md), [Proxmox VE](../docs/docs/start/proxmox.md)
and [one app or all of them](../docs/docs/start/one-or-all.md).

| | |
| --- | --- |
| Address | `/docs/` at the suite's address (`https://home.example.com/docs/`), and a name of its own if you give it one |
| MCP | `/docs/mcp` at the address for MCP ([AI assistants](../docs/docs/run/assistants.md)) |
| Database | `iodocs`, beside the Shared ioSuite database (the accounts and every setting), both under the suite's one login; the tables are made on the first start and brought up to date by later versions by themselves |
| On the server | Tesseract and Poppler, for reading scans (`tesseract-ocr`, `tesseract-ocr-eng`, `poppler-utils`); the installer, the Proxmox script and the container image have them |

From a shell, in the program folder (`/opt/iosuite` when installed as root):

```sh
iosuite iodocs check       # connect to the databases and say what is there, and what this server can read off a scan
iosuite iodocs read FILE   # what ioDocs reads off a scan or a PDF (nothing is kept): a test of OCR on this server
```

Accounts are the suite's: `iosuite admin NAME --app iodocs` makes someone an admin of ioDocs only (`iosuite admin NAME`: of
the whole suite), `iosuite password NAME` sets a password; see [Accounts and roles](../docs/docs/run/accounts.md).

## Configuration

ioDocs has no file of settings. The machine's one file (`config.env` in the program folder) says how to reach the Shared
ioSuite database and which apps run here; everything else is kept in that database. Suite admins change it under
**Settings › Apps › All settings**, which has a section for the whole suite and one for ioDocs, or from a shell;
a change applies when the app starts again:

```sh
iosuite settings iodocs        # what may be set, with the value stored now
iosuite set iodocs PUBLIC_URL https://docs.example.com    # no value: back to the default
```

| Setting | Meaning |
| --- | --- |
| `PUBLIC_URL`, `SYNC_URL`, `MCP_URL` | an address of its own for the pages, for devices and for MCP clients (`https://docs.example.com`), beside its folder at the suite's address |
| `DATA_DIR` | where the app writes on its own (`iodocs/` in the machine's `DATA_DIR`) |
| `DB_NAME` | the name of its database (`iodocs`) |
| `MAX_FILE_MB` | largest file (MB) (`100`). One scan, photo or PDF as uploaded |
| `TESSERACT` | OCR program (`tesseract`). The program that reads the scans; off: never read them |
| `OCR_LANGS` | OCR languages (`eng`). Tesseract's languages (eng+fra+deu); each needs its tesseract-ocr-<lang> package |

The suite's own settings (its address, the domain the sign-in is shared on, the time zone, how long deletions are kept), the
machine's file and the three ports are in the guide's [Configuration](../docs/docs/reference/configuration.md).

## Updates

The suite is one program with one version, so every app is updated together: **Settings › Servers › Updates**
(suite admins, in any app) shows the installed version and the newest one, with one **Update** button; from a shell it is
`update.sh` in the program folder, and in Docker the image is pulled. See [Updates](../docs/docs/run/updates.md).

The suite runs one version, so **Settings › Servers › Updates** shows it with a line and a **Restart** button for each server the suite runs on. The log is one for the whole copy of the program,
each line marked with its app: suite admins read it under **Settings › Servers › Logs**.

## API

The paths below are ioDocs' own: at the suite's address they are inside its folder (`https://home.example.com/docs/api/…`), at a name of its own they are as written. A script signs in with an app password at the pages' address. The [address for devices](../docs/docs/reference/configuration.md#the-three-ports) (port 8443), the one to open to the internet for phones and native apps, serves nothing of ioDocs. MCP clients use the address for MCP (port 8444).

| For | Standard | Where |
| --- | --- | --- |
| Web and JSON clients | **REST/JSON**: documents (list, search, by kind, person or status), one document, add, change, renew, delete; its files (add, read, put first, remove; each gets a name of its own, such as iodocs-000123.pdf, never the one it was uploaded under) | `/api/`, OpenAPI docs at `/api/docs` |
| ioCalendar and the start page | the documents that expire between two days | `GET /api/expiring?start=&end=` |
| AI assistants | **Model Context Protocol** (streamable HTTP, and stdio) | `/mcp` (switched on in Settings › Apps), or every app's tools at ioStart's `/mcp` |

Settings › Account makes **app passwords**, for the REST API (HTTP Basic, or `Authorization: Bearer <app password>`)
and for MCP.

```sh
curl -u alex:APP-PASSWORD "https://sync.example.com/docs/api/documents?status=expiring"
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: application/json' \
  -d '{"kind": "passport", "people": ["Ava"], "number": "C70224518", "expiresOn": "2031-12-28"}' \
  https://sync.example.com/docs/api/documents
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: image/jpeg' --data-binary @passport.jpg \
  "https://sync.example.com/docs/api/documents/12/files?name=passport.jpg"     # read at once: {file, found, filled, differs}
```

The MCP tools: `overview`, `expiring`, `search_documents`, `get_document`, `scan_text`, `add_document`,
`update_document`, `renew_document`, `delete_document`, and for admins `diagnostics` and `list_accounts`.

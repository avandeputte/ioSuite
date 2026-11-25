# ioRecipe

*The family's recipes, in ioSuite (with [ioPix](../iopix/), [ioNote](../ionote/), [ioContact](../iocontact/), [ioCalendar](../iocalendar/), [ioTask](../iotask/), [ioHealth](../iohealth/) and the [ioStart](../iostart/) start page).*

A self-hosted recipe book: a web app for the whole family to keep recipes with their ingredients, steps and photos, to import a recipe from the web by its address, from pasted text, from a photo or from a file, and to cook, shop and print from it. FastAPI and a single-page vanilla JS app, with everything stored in MariaDB / MySQL (the photos too), and the suite's shared library (`iosuite_shared`, in [iosuite_shared/](../iosuite_shared/)).

## What it does

- **Recipes** with a title, a description, what they make (4, or 24 cookies), preparation and cooking time, **ingredients**, **steps**, notes, tags, and where they come from. In the ingredients and the steps, a line that ends with a colon ("For the icing:") is a heading.
- **Photos**: as many as you like for a recipe (the first is the one on its card) and one for any step, uploaded from the computer or taken with the phone. Each is turned upright, made smaller and kept as a JPEG in the database, with a small copy for the cards.
- **Import from the web**: paste the address of a recipe page and ioRecipe fetches it, the way a browser asks for a page, and keeps the recipe on it (title, ingredients, steps, times, servings, tags) with its picture and a link back. It reads the schema.org Recipe data that most recipe sites publish for search engines; where a page has none, it reads the page as a person would: the lists a recipe plugin marks as ingredients and instructions, or the text under an "Ingredients" heading. A page that still gives no complete recipe is read by a small AI model that runs inside the app, on your own server (see [Reading a page with AI](#reading-a-page-with-ai)).
- **Import from pasted text or a photo**: paste a recipe from a message or a document, or give a photo of one (a page of a cookbook, a card, a screenshot): the text is made into a draft that opens in the recipe form, to be looked over before it is saved. A photo is read on the server itself, by Tesseract (see [Reading a photo of a recipe](#reading-a-photo-of-a-recipe)); it goes nowhere else.
- **Export and import as a file**: one recipe, a cookbook or everything you see as a `.zip` (the recipes, their photos, your favourites and ratings, their cookbooks), to keep safe or to import into another ioRecipe. The same import takes **Mealie**'s recipes: a recipe's JSON, a `.zip` of them with their pictures, or a Mealie backup.
- **The recipes as cards**, with their photo, how long they take and what they make: all of them, the family's, your own, your favourites, the ones with a tag or in a cookbook, by title, the newest or the best rated first; **search** finds words in the title, the ingredients, the steps, the notes and the tags.
- **Favourites and ratings**: the heart makes a recipe one of your favourites, the stars are your rating (1 to 5). Both are yours alone; everyone sees the average of the ratings.
- **Cookbooks**: recipes grouped under a name (Baking, Weeknights, To try). A family cookbook is everyone's and holds family recipes; a cookbook of your own may hold the family's recipes and yours. A recipe can be in several.
- **Cooking from it**: the amounts follow the servings you want (half, double, ten times: `1 1/2 cups` becomes `3 cups`, `2-3 tbsp` becomes `4-6 tbsp`), the ingredients have boxes to tick off as they go in, a step is struck out with a click, and **Print** gives the recipe alone on paper, with the amounts as they are shown.
- **The shopping list**, when [ioTask](../iotask/) is part of the suite: a recipe's ingredients (for the servings shown, without the ones ticked off) become tasks in one of your lists there. Nothing to set up; ioTask is asked as you.
- **Family and private recipes**: a family recipe is seen by everyone; a private one only by its owner. A recipe can be moved from one to the other.
- **Roles as in the other io apps**: viewers only read the family's recipes, members (the default) also keep private recipes of their own, editors change the family's recipes too, admins also manage users and settings. The same accounts, passwords and app passwords as the other io apps; one sign-in for all of them with a shared cookie domain.
- **Settings › People, Apps, Servers and Keys** (suite admins): the whole suite's people and their role in every app, app passwords and sign-in at the proxy; the apps, keys and tokens; the same panel as on the start page and in every io app (iosuite_shared's `/api/suite-admin/ui.js`).
- Light and dark, phone-sized screens, installable as an app.

## Run

ioRecipe is one of the apps of [ioSuite](../README.md), one program that runs the apps it is told to. Install the suite
with ioRecipe in it, alone or with the others, on any Linux machine:

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash -s -- --apps iorecipe
```

It asks for the MariaDB server, the first admin and the suite's address, then starts the service; leave `--apps` out
for the list of every app, to tick. On a server that already runs the suite:

```sh
iosuite install --add iorecipe       # --remove iorecipe stops running it; what it stored stays
```

In Docker, name it in `APPS` in the stack file ([docker-compose.yml](../docker-compose.yml); empty there: every app); on
Proxmox VE, tick it in the list the container's script shows. The guide has each way in full:
[any Linux or Mac](../docs/docs/start/linux-mac.md), [Docker](../docs/docs/start/docker.md), [Proxmox VE](../docs/docs/start/proxmox.md)
and [one app or all of them](../docs/docs/start/one-or-all.md).

| | |
| --- | --- |
| Address | `/recipes/` at the suite's address (`https://home.example.com/recipes/`), and a name of its own if you give it one |
| MCP | `/recipes/mcp` at the address for MCP ([AI assistants](../docs/docs/run/assistants.md)) |
| Database | `iorecipe`, beside the Shared ioSuite database (the accounts and every setting), both under the suite's one login; the tables are made on the first start and brought up to date by later versions by themselves |
| On the server | Tesseract, for reading a photo of a recipe (`tesseract-ocr`); the installer, the Proxmox script and the container image have them |

From a shell, in the program folder (`/opt/iosuite` when installed as root):

```sh
iosuite iorecipe check   # connect to the databases and say what is there
```

Accounts are the suite's: `iosuite admin NAME --app iorecipe` makes someone an admin of ioRecipe only (`iosuite admin NAME`: of
the whole suite), `iosuite password NAME` sets a password; see [Accounts and roles](../docs/docs/run/accounts.md).

## Configuration

ioRecipe has no file of settings. The machine's one file (`config.env` in the program folder) says how to reach the Shared
ioSuite database and which apps run here; everything else is kept in that database. Its admins change its own settings under
**Settings › This app**, suite admins every app's under
**Settings › Apps › All settings**, which has a section for the whole suite and one for ioRecipe, or from a shell;
a change takes hold at once, except for the few the screen marks, which apply when the app starts again:

```sh
iosuite settings iorecipe        # what may be set, with the value stored now
iosuite set iorecipe PUBLIC_URL https://recipes.example.com    # no value: back to the default
```

| Setting | Meaning |
| --- | --- |
| `PUBLIC_URL`, `SYNC_URL`, `MCP_URL` | an address of its own for the pages, for devices and for MCP clients (`https://recipes.example.com`), beside its folder at the suite's address |
| `DATA_DIR` | where the app writes on its own (`iorecipe/` in the machine's `DATA_DIR`) |
| `DB_NAME` | the name of its database (`iorecipe`) |
| `AI` | read web pages without recipe data with AI (`1` or `0`; on by default). A small model that runs on this server, inside the app |
| `AI_MODEL` | AI model. Another model than the one the app fetches: a GGUF file on the server, or the address of one |
| `AI_TIMEOUT` | AI: seconds one page may take (`300`) |

The suite's own settings (its address, the domain the sign-in is shared on, the time zone, how long deletions are
kept, and `OCR_PROGRAM` and `OCR_LANGUAGES`: the program that reads the text on a photo of a recipe and the languages
it reads in, shared with ioDocs and ioNote), the machine's file and the three ports are in the guide's
[Configuration](../docs/docs/reference/configuration.md).

### Reading a page with AI

Most recipe pages are imported without it. For the ones that are not (a recipe told as a story, a layout ioRecipe
cannot make out), ioRecipe has a small language model **inside the app, on your own server**: when a page has no
recipe data and its own lists and headings give no complete recipe, the model reads the page's text and returns
the recipe as the page words it. Nothing is sent to an AI service; there is none behind this.

- The runtime is [llama.cpp](https://github.com/ggml-org/llama.cpp) (through `llama-cpp-python`). It is an optional set of
  packages, compiled on the server, which takes a few minutes and needs a C++ compiler and `cmake`:
  `iosuite install --extras iorecipe-ai`. The published container image is without it.
- The model is Qwen2.5 1.5B Instruct (Apache 2.0), one file of about 1 GB, fetched once from Hugging Face into
  ioRecipe's data folder (`iorecipe/models` in the machine's `DATA_DIR`) when the app first starts with the runtime.
- A page takes a minute or so of the server's processor, in a process of its own, and about 2 GB of memory while it
  is read. Lines the model gives that are not on the page are dropped.
- The setting `AI` turns it off (`iosuite set iorecipe AI 0`). `AI_MODEL` names another GGUF model (a file on the server, or its web
  address): a larger one reads better and slower. `AI_TIMEOUT` is the seconds a page may take (300).

Some sites test for a person's browser and refuse a server whatever it sends. The import says so; copy the page's
text and use Import › Pasted text for those.

### Reading a photo of a recipe

Import › Photo reads the text on a picture with [Tesseract](https://github.com/tesseract-ocr/tesseract), a program
of its own that runs on the server: the photo is not sent anywhere. The installer, the Proxmox script and the
container image come with it, in English. Without it, everything else works
and the Photo tab says what is missing. To add it, or another language, by hand:

```sh
sudo apt-get install tesseract-ocr tesseract-ocr-nld tesseract-ocr-fra    # Debian, Ubuntu (tesseract-ocr-<code> per language)
brew install tesseract tesseract-lang                                      # macOS
```

Print reads well; handwriting mostly does not. What comes out is a draft in the recipe form, never a saved recipe.

## Updates

The suite is one program with one version, so every app is updated together: **Settings › Servers › Updates**
(suite admins, in any app) shows the installed version and the newest one, with one **Update** button; from a shell it is
`update.sh` in the program folder, and in Docker the image is pulled. See [Updates](../docs/docs/run/updates.md).

The suite runs one version, so **Settings › Servers › Updates** shows it with a line and a **Restart** button for each server the suite runs on. The log is one for the whole copy of the program,
each line marked with its app: suite admins read it under **Settings › Servers › Logs**.

Everything is under one Settings page (the sidebar and the avatar menu); a change is saved the moment it is made: your own tabs (account, display), then for admins server, and for suite admins security and global settings. Import from the web is a page of its own in the sidebar.

## Reverse proxy and HTTPS

ioRecipe is reached through the suite's three ports: the pages (80), devices (8443) and MCP (8444). A reverse proxy gives each
a name and HTTPS, for the whole suite at once, and can make people sign in first (Cloudflare Access, Authelia, oauth2-proxy):
[Reverse proxy and HTTPS](../docs/docs/run/reverse-proxy.md) and [Cloudflare Tunnel and Access](../docs/docs/run/cloudflare.md) in the
guide have the set-up, with Caddy and nginx examples, sign-in at the proxy and the optional check of app passwords at
Cloudflare's edge ([cloudflare/edge-auth](../cloudflare/edge-auth/README.md)).

## API

The paths below are ioRecipe's own: at the suite's address they are inside its folder (`https://home.example.com/recipes/api/…`), at a name of its own they are as written. A script signs in with an app password at the pages' address. The [address for devices](../docs/docs/reference/configuration.md#the-three-ports) (port 8443), the one to open to the internet for phones and native apps, serves nothing of ioRecipe. MCP clients use the address for MCP (port 8444).

| For | Standard | Where |
| --- | --- | --- |
| Web and JSON clients | **REST/JSON**: recipes (list, search, by tag, cookbook, the family's, your own or your favourites), one recipe, add, change, delete, its photos, your favourite and rating, cookbooks, import and export | `/api/`, OpenAPI docs at `/api/docs` |
| Recipes from other sites | **schema.org Recipe** (JSON-LD and microdata) read from the page at the address given; without it, the page's own lists and text, or the AI model on the server | `POST /api/import` |
| Recipes as files | a `.zip` with `recipes.json` and `photos/`; in: that, a Mealie export or backup, a recipe as JSON | `GET /api/export`, `POST /api/import/file` |
| The shopping list | ioTask's REST API, asked as the person signed in | `POST /api/recipes/{id}/shopping` |
| AI assistants: Claude and anything else that speaks MCP | **Model Context Protocol** (streamable HTTP, and stdio) | `/mcp` (switched on in Settings › Apps) |

Settings › Account makes **app passwords**: one per program, revocable on its own, used with your user name for the
REST API (HTTP Basic, or `Authorization: Bearer <app password>`) and for MCP.

```sh
curl -u alex:APP-PASSWORD "https://sync.example.com/recipes/api/recipes?q=chocolate&tag=cookies"
curl -u alex:APP-PASSWORD https://sync.example.com/recipes/api/recipes/12
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: application/json' \
  -d '{"title": "Oat cookies", "servings": "24 cookies", "prepMinutes": 15, "cookMinutes": 12,
       "ingredients": ["200 g oats", "100 g butter", "1 egg"], "steps": ["Mix.", "Bake 12 minutes at 180 °C."],
       "tags": ["cookies"], "family": true}' https://sync.example.com/recipes/api/recipes
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: image/jpeg' --data-binary @cookies.jpg https://sync.example.com/recipes/api/recipes/12/photos
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: image/jpeg' --data-binary @dough.jpg "https://sync.example.com/recipes/api/recipes/12/photos?step=1"
curl -u alex:APP-PASSWORD -X PUT -H 'Content-Type: application/json' -d '{"favourite": true, "rating": 5}' https://sync.example.com/recipes/api/recipes/12/mark
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: application/json' \
  -d '{"url": "https://www.example.com/recipes/oat-cookies"}' https://sync.example.com/recipes/api/import
curl -u alex:APP-PASSWORD -o recipes.zip https://sync.example.com/recipes/api/export
curl -u alex:APP-PASSWORD -X POST --data-binary @mealie-export.zip "https://sync.example.com/recipes/api/import/file?family=true"
```

`ingredients` and `steps` are lists of lines (or one text with a line each). `family` says where a new recipe goes:
`true` for the family's (editors and admins), `false` for a private one; left out, it is the family's for those who
may add there. A recipe's `photos` are its own, in their order, then its steps' (`step`: the step's place in `steps`,
from 0); `photo` is the one its card shows, and `?size=small` gives a picture's small copy. `POST /api/import/text`
(`{text}`) and `POST /api/import/photo` (the picture as the body) save nothing: they answer with a `draft`, the
fields `POST /api/recipes` takes.

## MCP server

ioRecipe is also an MCP server, as the other io apps are, so an assistant such as Claude can work with the recipes:
look them up by words, tag or cookbook, read one in full, add and change them, import one from a web address, mark
favourites and rate them, keep cookbooks, delete them, and,
for admins, check the server's health, look for a new version and install it.

It is off until a suite admin turns it on in **Settings › Apps**; off, `/mcp` does not answer
at all. Every assistant signs in with an **app password** (Settings › Account › App passwords), as HTTP Basic or
`Authorization: Bearer <app password>`, and acts as that account, with its rights.

```sh
claude mcp add --transport http iorecipe https://mcp.example.com/recipes/mcp --header "Authorization: Bearer APP-PASSWORD"
```

On the server itself, `iosuite mcp iorecipe --user NAME` serves the same tools over stdio.

The tools: `overview`, `list_recipes`, `search_recipes`, `get_recipe`; `create_recipe`, `update_recipe`,
`delete_recipe`, `import_recipe`, `mark_recipe`; `list_cookbooks`, `create_cookbook`, `add_to_cookbook`,
`remove_from_cookbook`, `delete_cookbook`; and for admins `diagnostics`, `list_accounts`.

## Tests

```sh
pip install -e '.[all,test]'          # in the program folder, once
python -m pytest iorecipe/tests     # on a test MariaDB of its own: a Docker container it starts, or IOSUITE_TEST_DB=host:port:user:password
```

Covered: a recipe's fields round-tripping, the search, tags and counts, who sees and changes what in each role, the
photos (resized, in their order, a step's following its step, refused when not a picture), favourites and ratings,
cookbooks, reading recipes from web pages
(JSON-LD on its own and in a graph, with sections and HTML in the values; microdata; pages without a recipe;
addresses the server will not fetch), the import with its picture, a recipe out of plain text and off a photo (where
Tesseract is installed), an export coming back whole, Mealie's recipes and backup, the shopping list, and the MCP
server (switch, sign-in, the tools).
CI runs them against MariaDB.

## Layout

The package `iorecipe/` of the repository:

```
main.py            the application: what is ioRecipe's own (its body limits, routes), handed to iosuite_shared.application
api.py             the REST API: recipes, photos, favourites and ratings, cookbooks, import, export, the shopping list
model.py           recipes in MariaDB: the fields, who sees and changes what, the search and the tags, photos, marks, cookbooks
scrape.py          import from the web: fetching a page and reading its schema.org Recipe (JSON-LD, microdata), else its lists and text
ai.py              a page's text read by a small AI model on this server (llama.cpp), where nothing else found the recipe
textimport.py      a recipe out of plain text (pasted, or read off a photo)
ocr.py             the text on a photo, read by Tesseract on this server
portable.py        recipes as files: the export, and imports of it and of Mealie's
shopping.py        the ingredients as tasks in ioTask, asked as the person signed in
images.py          a photo: checked, turned upright, kept as two JPEGs
mcp/               the MCP server: base (the server, finding a recipe; who is asking comes from iosuite_shared.mcp), recipes and admin tools
access.py          who may call a route (the markers come from iosuite_shared)
users.py           accounts and app passwords (the suite's, through iosuite_shared)
static/            the web app (index.html, app.js, app.css, icons)
```

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later), see [LICENSE](../LICENSE).

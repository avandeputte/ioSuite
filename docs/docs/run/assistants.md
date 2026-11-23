---
description: Connect Claude or another AI assistant to ioSuite over MCP.
---

# AI assistants (MCP)

ioPix, ioNote, ioCalendar, ioTask, ioRecipe, ioThings, ioMoney, ioDocs and ioContact are also
[Model Context Protocol](https://modelcontextprotocol.io) servers, so an assistant such as Claude can work with them
as you: explore and search the photo library, search and write notes, read the agenda and add events, add tasks and
tick them off, look recipes up and import them from the web, ask about the net worth, the spending and the portfolio,
find contacts and file suggestions for them, and, for admins, check the server's health. ioHealth has no MCP server.

MCP has **a port of its own (8444)**, apart from the pages and from the devices, so you decide separately who may
reach it. Each app answers there at `/mcp` in its folder:

| | Address |
| --- | --- |
| the whole suite (the start page) | `http://server:8444/mcp` |
| one app | `http://server:8444/calendar/mcp`, `…/notes/mcp`, `…/pix/mcp` |

The start page's is **one MCP server for the whole suite**: connect an assistant there once and it gets every app's
tools, named after the app (`iocalendar_add_event`, `iotask_add_task`...), so one request can span apps ("put Friday's
dinner ingredients on the shopping list"). Each call is carried out as you, so each app still decides what you may
see and change there; an app whose own MCP switch is off, or where you have no role, offers nothing. `suite_apps`
lists the apps it reaches, and suite admins also get `suite_version` and `update_suite`.

## Turn it on

MCP is **off on a fresh install**. A suite admin turns it on per app under **Settings › Apps**; while off, `/mcp` doesn't
answer at all. The port can also stay closed altogether: `MCP_PORT=off` in the machine's file.

## Connect an assistant

Every assistant signs in with an **app password** (Settings › Account › App passwords, scope "everything") and acts as
that account, with its rights:

```sh
claude mcp add --transport http iosuite https://mcp.example.com/mcp \
  --header "Authorization: Bearer APP-PASSWORD"
```

That address is whatever reaches port 8444: a name of its own at your reverse proxy (told to the suite as `MCP_URL`
under Settings › Apps › All settings), or `http://<server>:8444/mcp` on a home network without HTTPS. Settings ›
Server shows the address to use.

For **Claude Desktop** on a computer in your network, use the `mcp-remote` bridge in `claude_desktop_config.json`
(it needs Node.js):

```json
{
  "mcpServers": {
    "iosuite": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.example.com/mcp",
               "--header", "Authorization: Bearer APP-PASSWORD"]
    }
  }
}
```

On the server itself, `.venv/bin/python -m iocalendar.mcp --user NAME` in the program folder serves one app's tools
over stdio. It reads the account and its role once, when it starts: after changing someone's role, restart any stdio
server running as them. Starting one needs the machine's `config.env` (with the database password), so it is only for
whoever runs the server.

## Be careful with admin app passwords

The tools for operating the suite (diagnostics, the log, updating) need an admin. An admin's app password can install
code on the server: treat it like a root password, and revoke it when in doubt. For an assistant that only needs to
read and write your own data, use an app password of a non-admin account.

Behind a reverse proxy, the MCP port must not be buffered; see [Reverse proxy and HTTPS](reverse-proxy.md) and
[Cloudflare](cloudflare.md).

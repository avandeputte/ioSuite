---
description: The first sign-in, the first accounts, and what to set next.
---

# First run

## Open the suite

Open `http://<server>/`. That is the start page, with a tile per app; each app is also at its folder
(`http://<server>/calendar/`, `/tasks/`, `/notes/`, `/pix/` and so on). On a machine that does not run the start
page, the address shows the first app it does run.

The sign-in screen is the same in every app: a tile per account (a click and a password), or *Other* to type a name.

- **The installer made an admin** (you answered the admin question, or gave `--admin`): sign in with it. The first
  account in a Shared ioSuite database is a **suite admin**: admin in every app, and the one who manages the accounts
  and the settings.
- **No account yet**: the suite offers to create the first one, right there in the browser. That works only from
  inside your network (or on the server itself), never through a reverse proxy from outside. Open it at the server's
  own address for it (`http://192.168.1.10/`), not at its public name: until an account exists, a visitor from the
  internet, through a Cloudflare Tunnel, or through a reverse proxy the suite has not been told about gets the sign-in
  screen saying "No account exists here yet" and nothing else. A reverse proxy on another machine is told to the suite
  afterwards, under [Reverse proxy addresses](../run/reverse-proxy.md#tell-the-suite-where-the-proxy-is).

## Make the accounts

As a suite admin, open **Settings › People › People** in any app:

- add an account for each person (name, display name, email, password), or a **passwordless** account for a child or a
  kitchen tablet: one click to sign in, on the home network only, and a member at most everywhere;
- set each person's role per app under **Roles** (viewer, member, editor, admin, or none), or leave the app's default;
- decide under **Settings › Apps › The apps** whether an app is open to everyone with an account (its default
  role) or by invitation only (default role `none`), and whether it requires a sign-in at all.

See [Accounts and roles](../run/accounts.md).

## Next

- Look through **Settings › Apps › All settings**: the time zone, the suite's address, and each app's own
  settings (the photos folder for ioPix, the public holidays for ioCalendar). See [Configuration](../reference/configuration.md).
- Put the suite behind HTTPS: [Reverse proxy and HTTPS](../run/reverse-proxy.md),
  [Cloudflare Tunnel and Access](../run/cloudflare.md), or let the suite
  [ask for its own certificate](../run/https.md) and answer HTTPS itself.
- Connect your devices: [Phones, Macs and other apps](../apps/devices.md). They use the devices' port (8443).
- Settings › Servers › Updates shows the suite's version and updates it: [Updates](../run/updates.md).
- Optionally, let an AI assistant in: [AI assistants (MCP)](../run/assistants.md).

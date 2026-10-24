# Engram 3.7 development features

Each feature has its own version and commit. The current source version is
`3.7.0-dev-beta.9`. Stable production remains unchanged; these are draft previews.

| Version | Feature | Edition | Where |
| --- | --- | --- | --- |
| 3.7.0-dev-beta.2 | Team workspaces | Commercial | Team workspace |
| 3.7.0-dev-beta.3 | Company branding | Commercial | Company branding |
| 3.7.0-dev-beta.4 | Licence renewal | Commercial / owner service | Licence and owner dashboard |
| 3.7.0-dev-beta.5 | Project handover packs | Commercial | Project handover |
| 3.7.0-dev-beta.6 | Guided first-run setup | Commercial | `/setup` |
| 3.7.0-dev-beta.7 | Memory reminders | Personal and Commercial | Reminders and each memory's detail page |
| 3.7.0-dev-beta.8 | Host deployment installer | Personal and Commercial | Terminal setup wizard |
| 3.7.0-dev-beta.9 | Dream Lab | Personal and Commercial | `/dreams`: offline prototypes, inspiration, checks, keep/evolve/destroy and nightly generation |

See [Dream Lab](DREAM-LAB.md) for its building blocks, sandbox, limits and migration 019.

## One-command host deployment

On a fresh Ubuntu or Debian host:

```sh
curl -fsSL https://engram-beta.hindley.tech/install.sh | sudo bash
```

This development command currently selects draft PR #85's branch. Inspect the script
before running it as root. It installs prerequisite tools and Docker from Docker's
official apt repository if needed, then opens an interactive deployment wizard.
It preserves an existing Docker installation and refuses conflicting container runtimes.

The wizard selects the edition and a new install directory, generates service secrets,
builds and starts the stack, creates the administrator, and can activate a Commercial
key and download the AI models. Commercial setup can fetch the issuer's **public** key
over HTTPS or read a local public-key file. The development default is the disposable
beta licence service. The private issuer and owner SMTP service are never installed
on customer hosts.

For direct HTTPS, point the hostname's DNS to the host and allow incoming TCP ports
80/443 before starting. Caddy obtains and stores the certificate automatically.
Alternatively choose an existing proxy/tunnel; the gateway binds to localhost only.
The installer verifies local health and reports public HTTPS verification separately.
It does not create DNS records or change an external provider's account.

An existing install directory, configuration, or matching Docker resources causes
setup to stop. Failed installations retain their directory and data for diagnosis.
Use the upgrade guide for existing deployments. Downloaded customer ZIPs also include
the wizard: run `sudo python3 install.py` on the host.

## Team workspaces

Instance administrators create projects. A project owner can invite a new account
using a private link, or add/update an existing username. Links last 48 hours and
can be accepted once. Share them privately; invitations are not automatically emailed.
The invited account sets its own password and only sees projects it belongs to.
Owners manage memberships, editors can edit memories, and viewers can read/search.
Existing non-team accounts retain their Personal-project access. Instance admins
retain access to all projects. Role changes also apply to credentials owned by members.
Activity shows recent actions within the selected project.

## Branding and handovers

Instance administrators can set a company name, tagline, bright accent colour and
a PNG logo up to 100 KB. Branding appears in the web workspace and sign-in screen.
Handovers export current project memories, decisions, open questions/tasks and
checked saved briefs as JSON or Markdown. They do not invent summaries with an AI
model. Limits and omitted counts are included. Stale briefs are flagged and their
conclusions are withheld from the Markdown handover. Exports contain project data.

## Setup wizard

Open `/setup`. Existing installations sign in as an administrator. New empty
installations can opt into browser account creation by creating a one-time token:

```sh
mkdir -p secrets
openssl rand -hex 32 > secrets/setup-token
sudo chgrp 10001 secrets/setup-token
chmod 640 secrets/setup-token
```

Keep the directory traversable by container UID 10001. The token remains readable
only by its operator owner and container group 10001. Keep the token out of chat and source control.
Use it only over your normal HTTPS origin. The account endpoint closes once any
account exists; remove the file after setup. Alternatively use the existing local
`scripts/create_admin.py` command without enabling bootstrap.

The wizard activates the licence, checks the configured Ollama server, lets an
administrator choose an already-installed chat model, and creates the first project.
The chosen chat model is persisted and used by API and worker generation calls.
Embedding settings are preserved. Missing models must be installed on the Ollama
server; the wizard does not silently download models or change the server URL.

## Memory reminders

Schedule a future reminder from a memory, or select one in Reminders. Local times
are converted to UTC for storage. Reminders are private to the signed-in user and
the selected project, including when the viewer is an instance administrator.
Due reminders appear in the web app on opening/focus and refresh every minute.
Mark them done, dismiss them, or snooze until tomorrow. This is an in-app reminder
system; background operating-system push and reminder emails are not configured.

## Upgrade an existing development installation

Back up the database, environment, owner SQLite database and existing images first.
Apply migrations in order before restarting API, worker and scheduler:

```sh
for migration in db/migrations/0{15..18}_*.sql; do
  docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$migration"
done
```

This assumes migrations through 014 have already been applied. New empty databases
apply the full sequence at first boot. Use the appropriate Personal or Commercial
Compose override when rebuilding. Owner renewals upgrade their SQLite schema on start.
Existing native builds retain their recorded qualification status. The new source
runtime/channel is separate; no APK, iOS build or OTA publication is implied.

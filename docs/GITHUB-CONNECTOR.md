# GitHub Connector

Engram v2.1 uses a GitHub App rather than a personal access token.

## Recommended GitHub App permissions

Repository permissions:

- Metadata: Read-only
- Contents: Read-only
- Issues: Read-only
- Pull requests: Read-only

No write permission is required.

Scheduled sync does not require a webhook.

## Create the GitHub App

Create a GitHub App under your GitHub account or organization settings.

Set the permissions above and install it only on the repositories you want Engram to see.

Generate a private key (`.pem`).

## Configure Engram

Place the generated private key at:

```text
/opt/memorybank/memorybank/secrets/github-app.pem
```

Protect it:

```bash
chmod 600 secrets/github-app.pem
```

Set in `.env`:

```dotenv
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=/run/secrets/github-app.pem
```

Recreate the application services after changing `.env`:

```bash
sudo docker compose up -d --force-recreate api worker connector-scheduler
```

## Installation ID

The connector UI asks for the GitHub App **installation ID**.

The App ID and installation ID are different values.

## What is synced

Configurable per connector:

- repository metadata
- README
- documentation files
- issues
- pull requests
- source code (off by default)

Each source is hashed. Unchanged items are skipped on later syncs.

Changed items become new source documents and automatically enter the document → candidate-memory pipeline.

## Scheduling

Connectors have a schedule between 5 minutes and 7 days.

The `connector-scheduler` container checks for due connectors and queues work into the existing RQ worker.

## Private repositories

Engram can only read repositories granted to the GitHub App installation.

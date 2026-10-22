# Commercial licensing and email delivery (v3 development beta)

## Customer builds

Use the Commercial Compose override to build the API, worker and scheduler with a baked edition marker:

```sh
docker compose -f docker-compose.yml -f docker-compose.commercial.yml build
docker compose -f docker-compose.yml -f docker-compose.commercial.yml up -d
```

Deploy only the issuer's **public** Ed25519 key in `secrets/commercial-license-public.pem`.
Set `COMMERCIAL_LICENSE_PURCHASE_URL` to the owner's request page, for example
`https://engram-beta.hindley.tech/licence-store/`.
Open `/licence`, copy the installation ID, request a key, sign in as an administrator,
and paste the emailed key. A missing, forged, expired or differently scoped key keeps
product API and MCP access locked with HTTP 402. Health, login and licence activation
remain reachable. There is no Personal toggle in Commercial.

Community is MIT licensed and requires no key. Its final image omits commercial
implementation code. Customer images omit the issuer CLI, owner service and signing secrets.

## Owner service

This is separate owner infrastructure, not part of customer installations.
Payment processing is **not configured**. Arrange payment separately; the owner
manually confirms receipt in the dashboard. Confirmation creates one signed key
and queues its email automatically. Unpaid requests never issue or email keys.

Create a private directory outside the checkout containing:

- `issuer-private.pem`: Ed25519 signing key, matching the customer public key.
- `admin-password`: strong owner dashboard password.
- `smtp-password`: mailbox SMTP password.

Make the directory accessible only to the owner service UID 10001 (directory 0700,
files 0600). Mount it read-only using `ENGRAM_OWNER_SECRETS_DIR`. Never include it in
customer images, source control or customer backup exports. Back up the owner signing
key and `licence_orders` volume securely; they contain customer licence material.

```sh
export ENGRAM_OWNER_SECRETS_DIR=/protected/engram-owner
docker compose -f docker-compose.yml -f docker-compose.commercial.yml \
  -f docker-compose.licence-owner.yml up -d --build licence-owner
```

The service listens on 8091 on the internal edge network, with no published host port.
Add a TLS gateway route `handle_path /licence-store/* { reverse_proxy licence-owner:8091 }`
before its frontend catch-all. Use a trailing slash on the public request URL.
The owner dashboard is `/licence-store/admin`; HTTP Basic username is `owner`, password
is the protected `admin-password` file. Only owner-authenticated requests carrying the
CSRF header can approve or resend. Do not expose this service over plaintext HTTP.

SMTP defaults: `box.hindley.tech:465`, verified TLS, username/sender `jayden@hindley.tech`.
Override the owner service SMTP environment for another mailbox. The sender is fixed,
not taken from public request input. A private deployment can resolve the mail hostname
to its LAN address while retaining the hostname for certificate verification.

## Operation and delivery guarantees

1. Customer submits name, email and installation ID.
2. Owner arranges payment separately and opens the dashboard.
3. Owner selects the last licensed day (UTC) and clicks **Mark paid & email key**.
4. The background outbox sends the key from Jayden's mailbox. Refresh shows sent/error.

Approval is transactional and idempotent: repeat confirmation never mints another key.
SMTP failures retain the key and retry with backoff up to hourly. Resend uses the same key.
Delivery is at least once: a crash after SMTP acceptance may produce a duplicate email,
with the same key and Message-ID. A `sent` status means SMTP accepted it, not proof of inbox arrival.
The owner process must run as one instance; SQLite is intended for this small owner deployment.
No Stripe integration, card collection, automatic payment verification or pricing is included.

For local offline issuance, the owner-only `scripts/commercial_license.py` CLI remains
available in source. Keep the private key in owner infrastructure; never customer builds.

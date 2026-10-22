# Commercial keys — v3.0.0-dev-beta.1

Personal, noncommercial self-hosting remains free under [LICENSE](../LICENSE).
Commercial keys activate a separately agreed paid commercial licence. The owner
collects payment and agrees terms outside Engram, then issues a key. This beta
does not offer checkout, payment verification, automatic billing or refunds.

## Server setup

1. Back up the database and environment. Existing installations must apply
   `db/migrations/014_commercial_license.sql` after migrations 009–013, then
   rebuild the API, workers and web. Fresh Compose databases apply 014 automatically.
2. Put the issuer's **public** key in `secrets/commercial-license-public.pem`.
   It must be readable by the container's UID 10001 (a public key can be mode 644).
   The existing Compose secrets mount exposes it at the default verification path.
   `COMMERCIAL_LICENSE_PUBLIC_KEY_PATH` can select another mounted public-key file.
3. Sign in as an administrator. Open **Settings → Licence** and copy the installation ID.
4. Request a commercial licence with that ID. After payment and agreement,
   select **Commercial**, paste the issued key and save. The status shows the
   licensed customer, licence ID and expiry. Leave the key blank when saving an
   already valid commercial activation; a replacement key renews the entitlement.

Status and activation require an administrator session; API keys cannot manage
licensing. Responses and audit events never return the full commercial key.
Activation is installation-wide and persists across project switches/restarts.
Selecting Personal removes the stored key and is only appropriate for actual
personal/noncommercial use. It does not grant commercial permission.

## Owner-only issuance

Run these commands from `backend` on the owner's offline workstation with
backend dependencies installed. Use an existing protected directory **outside
the repository** for issuer files. The CLI refuses to overwrite existing files.

```sh
python -m scripts.commercial_license keygen \
  --private-key /secure/offline/engram-issuer-private.pem \
  --public-key /secure/offline/engram-issuer-public.pem

python -m scripts.commercial_license issue \
  --private-key /secure/offline/engram-issuer-private.pem \
  --installation-id INSTALLATION_UUID_FROM_SETTINGS \
  --customer "Example Ltd" --expires 2027-10-22 \
  --output /secure/offline/example-ltd.license
```

The private PEM is unencrypted: protect it with filesystem permissions/Windows
ACLs and encrypted offline storage. Never commit it, mount it in a customer
installation, or send it to customers. Only distribute the public PEM and the
customer's `.license` file. Key generation and issuance print no secret material.
No real issuer key is generated or shipped by this PR.

Keys use Ed25519 signatures, an explicit issuer/audience, a unique licence ID,
customer name, installation UUID and expiry. Expiry dates include the stated
day in UTC. Keep the server clock accurate. Renew by issuing a replacement for
the same installation. Back up the database: its installation UUID is required
to reuse the key after recovery. A new installation UUID needs a reissued key.

## Enforcement and first-beta limits

Personal mode needs no key. Commercial mode can only be activated with a valid
key signed by the configured issuer and bound to this installation. Invalid
renewals leave the existing activation intact. If a key later expires or its
public verifier becomes unavailable, interactive product writes return HTTP 402;
MCP write tools reject changes too. Existing reads, search/Ask/Reflect previews,
sign-in/logout, licence renewal and disaster-recovery routes remain available.
Data is not deleted or encrypted as a licensing action.

Already queued work and automatic schedules continue in this first beta; the
gate applies to interactive API/MCP mutations. There is no online revocation,
seat metering or payment provider integration. Signed keys remain valid until
expiry unless the installation's verifier changes. A server owner can modify
source/configuration: these checks are not tamper-proof DRM or a substitute for
the commercial agreement. Operational hardening and billing can be added later.

Existing mobile releases remain on their 2.7 preview channels. CI required an
Expo patch alignment to 57.0.31; future v3 builds use Android build 9 / iOS build 7,
runtime `3.0.0-dev-beta.1-native1` and the `v3-beta1` EAS profile with channel
`v3-dev-beta-1`. No native build or OTA update is published by this change.
The web Settings licence form is the activation interface in this first beta.

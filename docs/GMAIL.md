# Gmail connector (v2.4 preview)

The connector imports message body text from one Gmail account as source
documents, then uses the existing document processing and Memory Inbox review
flow. It requests only `gmail.readonly`. It does not send, modify, archive,
label, or delete mail and does not import attachments. The default sync selects
the Inbox and `newer_than:30d`, with a limit of 100 messages per run. Change the
search, label, and limit before connecting. Gmail messages not matching that
selection are not synced.

## Configure Google OAuth

1. Create/select a Google Cloud project and enable the Gmail API.
2. Configure the OAuth consent screen for your personal use and add your Gmail
   address as a test user if the app is in Testing mode.
3. Create an OAuth client with application type **Web application**.
4. Add this exact authorized redirect URI, shown on MemoryBank's Connectors
   page once credentials are configured:

   ```text
   https://YOUR_MEMORYBANK_HOST/api/v1/connectors/gmail/callback
   ```

5. Add the client ID and client secret to the server-side `.env`; never put
   them in the web application:

   ```dotenv
   GOOGLE_OAUTH_CLIENT_ID=your-web-client-id
   GOOGLE_OAUTH_CLIENT_SECRET=your-web-client-secret
   GOOGLE_TOKEN_ENCRYPTION_KEY=base64-encoded-32-byte-key
   ```

   Generate the encryption key with `openssl rand -base64 32`. Keep it backed
   up in your normal secrets store. Losing it disconnects Gmail connectors; it
   does not affect memories or source documents already stored.

6. Apply `db/migrations/008_gmail_connector_credentials.sql`, then rebuild and
   recreate `api`, `worker`, `connector-scheduler`, and `web`.
7. Open Connectors, choose the query and label, and select **Connect Gmail**.
   Google displays the requested access before the user grants it.

Refresh tokens are encrypted using AES-256-GCM with the connector UUID as
associated data. They are never returned by the API. Deleting a Gmail connector
attempts to revoke its Google token; imported source documents and accepted
memories remain, following the existing connector deletion behavior.

## Google testing and verification

`gmail.readonly` is a restricted Google OAuth scope. Google allows qualifying
personal-use apps with fewer than 100 users to remain unverified, with an
unverified-app warning that the user must accept. A project left in Testing
mode expires each test user's authorization after seven days, including its
offline refresh token. A long-running deployment therefore needs the OAuth
project setup and publishing status that Google permits for its use case.
Publishing an app for broader use can require restricted-scope verification
and a security assessment. See Google's [Gmail scope classifications](https://developers.google.com/workspace/gmail/api/auth/scopes),
[personal-use verification exception](https://support.google.com/cloud/answer/13464323),
and [testing-mode token expiry](https://support.google.com/cloud/answer/15549945).

## Sync behavior and limits

- Gmail API polling runs on the connector schedule and fetches at most 500
  messages per run; the UI defaults to 100. Gmail results are paginated within
  that limit. Each message is a separate Markdown source document.
- Content hashes prevent duplicate documents on repeat sync. Changed messages
  update their connector item and queue document reprocessing. Search labels,
  sender, subject, date, thread ID and the Gmail web link are retained as
  provenance.
- The first release is bounded polling, not Gmail push notifications. Each run
  selects up to the 500 newest matching messages; there is no historical cursor,
  so increasing the limit will not page through mail beyond those 500 messages.
- Removing a message or label in Gmail does not delete its imported document or
  accepted memories. Remove those in MemoryBank explicitly.
- Gmail search terms are passed to Gmail's API as a query. Avoid queries that
  include mail you do not want copied into MemoryBank.

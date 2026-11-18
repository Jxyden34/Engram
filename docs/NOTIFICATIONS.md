# Notifications

Open **Capture & review → Notifications** on the web, or **Workspace →
Notifications** in the native companion. Administrator browser and mobile sessions
can use the inbox. Each project has its own notifications. API keys and OAuth
clients do not receive administrator notifications.

The connector scheduler checks conditions on its existing interval. **Check now**
performs a manual refresh, limited to six requests per minute. Opening a source,
marking a notification read, and dismissing it affect your own receipts.
Dismissing a notice leaves its underlying source issue available for review.
When an issue clears it leaves the active inbox. If it returns, a new generation
becomes unread for every administrator. Resolved history is retained for 90 days.
At most 100 sources per detector and 200 inbox items are returned per refresh.

| Condition | Trigger | Review destination |
| --- | --- | --- |
| Connector failure | An enabled connector's last status is failed | Connectors |
| Important conflict | An unresolved imported candidate conflicts with a current memory of importance 8–10 | Memory Inbox |
| Backup failure | PostgreSQL or object backup health is unhealthy, including missing or stale verified backups | Disaster Recovery |
| Important update | A current memory of importance 8–10 changes title/content, or supersedes a prior fact, within 30 days | Memory and version history |
| Stale credential documentation | A current credential memory or credential-tagged memory has not changed for 180 days | Memory |
| Unresolved candidates | Candidates remain pending for seven days | Memory Inbox |

Backup health applies to the whole server and appears only in the Personal project.
Credential tags include credential, credentials, password, api-key, and access-token.
Notifications include generic descriptions and source links. Memory content,
credential text, connector errors, and provider tokens are omitted.

Notifications appear in the application inbox. Optional Telegram delivery uses
a dedicated bot and a saved chat destination for each project. Mobile source links
open the authenticated web interface on the configured server.

## Upgrade

Apply migration 021 before starting the v3.2 application and scheduler. Fresh
installations apply it automatically through Compose. The scheduler logs
per-project refresh failures and continues with the next project.

## Telegram

Create a dedicated bot through Telegram's @BotFather and set its token as
`TELEGRAM_BOT_TOKEN` in the server's private environment file. Restart the API
and connector scheduler to load it. Start a private conversation with the bot
or add it to a group where it can send messages. Obtain the numeric chat ID
using your bot's Bot API updates and enter it in **Notifications → Telegram
delivery**. Save, enable delivery, and use **Send test message**.

The token stays in the server environment. Notification messages include a
generic description and a link to the configured public Engram origin.
Telegram receives those messages and the chat destination. Use a private
chat if the notification categories reveal sensitive context.

Each notification generation has one delivery record. Successful deliveries
are skipped on subsequent scans. Failures retry up to five times with
exponential delays starting at one minute. A network timeout or crash after
Telegram accepts a message can cause a duplicate because Telegram sendMessage
has no idempotency key. Disable delivery in the project's settings to stop
future sends. Changing destinations does not resend already delivered events.

[Telegram Bot API](https://core.telegram.org/bots/api#sendmessage)

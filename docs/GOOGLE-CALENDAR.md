# Google Calendar connector

Enable the Calendar API in a separate Google Cloud project from Gmail so that
revoking Calendar consent does not affect Gmail. Add
`https://YOUR-HOST/api/v1/connectors/google-calendar/callback` to the Calendar
OAuth web client and set `GOOGLE_CALENDAR_CLIENT_ID` and
`GOOGLE_CALENDAR_CLIENT_SECRET` in the server environment. Engram uses the same
encryption key setting as the [Gmail connector](GMAIL.md). Calendar consent
requests only owned-event read access.
[Google Calendar scopes](https://developers.google.com/workspace/calendar/api/auth)

In Engram, select the destination project and open **Connectors**. Enter an
owned calendar ID or leave `primary`, then approve access in Google. The
connector polls every six hours by default and indexes up to 500 event
occurrences from 30 days ago through 90 days ahead. The source documents include
event dates, locations, attendees, notes, and the original event link. The
existing Memory Inbox handles candidate review.
[Google Events API](https://developers.google.com/workspace/calendar/api/v3/reference/events/list)

Deleting the connector attempts to revoke its token. Imported documents and
reviewed memories are retained when the connector is deleted or events leave
the sync window. Cancelled events are skipped. Provider setup and a live sync
with an authorized test calendar still need verification.

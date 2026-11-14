# Google Calendar connector

Enable the Calendar API and add `https://YOUR-HOST/api/v1/connectors/google-calendar/callback`
to your Google OAuth web client. Engram uses the same server-side Google client
settings and token encryption key as the [Gmail connector](GMAIL.md). The
Calendar consent flow requests only owned-event read access.
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

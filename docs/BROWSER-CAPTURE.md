# Browser Capture

MemoryBank v2.1 includes a Manifest V3 extension under:

```text
extensions/memorybank-capture/
```

The extension uses a dedicated `capture:write` API key.

Captured pages are not promoted directly into permanent memory.

```text
Browser
  -> /api/v1/capture
  -> source document
  -> extraction + embedding
  -> local candidate analysis
  -> unified Memory Inbox
  -> accept / edit / reject
```

This preserves the same human-review boundary as documents, ChatGPT imports and connectors.

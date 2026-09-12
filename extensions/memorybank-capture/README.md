# MemoryBank Capture Extension

Chrome / Edge Manifest V3 extension for sending pages, selections, links and notes to MemoryBank.

## Install

1. In MemoryBank, open **AI & API**.
2. Generate a **Browser Capture** key. It has only `capture:write`.
3. Open `chrome://extensions` or `edge://extensions`.
4. Enable **Developer mode**.
5. Choose **Load unpacked**.
6. Select this `memorybank-capture` directory.
7. Open the extension popup.
8. Enter your public MemoryBank origin, for example `https://memory.example.com`.
9. Paste the capture key and click **Save connection**.

## Capture methods

- toolbar popup → Capture page
- toolbar popup → Selection
- toolbar popup → Quick note
- right click page → Save page to MemoryBank
- right click selection → Save selection to MemoryBank
- right click link → Save link to MemoryBank

Captured content becomes a source document, is extracted/embedded, and is automatically sent to the normal candidate Memory Inbox.

## Security

The API key is stored in `chrome.storage.local` for this browser profile.

Use a dedicated `capture:write` key, never a full AI/admin key. Revoke the key immediately if the device or browser profile is lost.

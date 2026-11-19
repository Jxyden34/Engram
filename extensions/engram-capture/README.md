# Engram Capture Extension

Manifest V3 extension for sending pages, selections, links and notes to Engram.

## Install

1. Select the target project in Engram and open **Personal API Gateway**.
2. Generate a **Browser Capture** key. It has only `capture:write`.
3. Open `chrome://extensions` or `edge://extensions`.
4. Enable **Developer mode**.
5. Choose **Load unpacked**.
6. Select this `engram-capture` directory.
7. Open the extension popup.
8. Enter your public Engram origin, for example `https://engram.example.com`.
9. Paste the capture key and click **Save connection**.

For temporary Firefox testing, open `about:debugging#/runtime/this-firefox`,
choose **Load Temporary Add-on**, and select `manifest.json`. The shared
manifest requires Chrome/Edge 121 or Firefox 121 and later.
[Browser support](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/background#browser_support)

Use **Project ID** to check that the key belongs to the intended project.
Leave it blank to capture into the key's own project. Saved tags are attached
to captures from the popup and context menu.

## Capture methods

- toolbar popup → Capture page
- toolbar popup → Reader view
- toolbar popup → Capture visible screenshot (PNG with local English OCR)
- toolbar popup → Selection
- toolbar popup → Quick note
- right click page → Save page to Engram
- right click selection → Save selection to Engram
- right click link → Save link to Engram

Captured content becomes a source document, is extracted/embedded, and is automatically sent to the normal candidate Memory Inbox.

## Security

The API key is stored in `chrome.storage.local` for this browser profile.

Use a dedicated `capture:write` key, never a full AI/admin key. Revoke the key immediately if the device or browser profile is lost.

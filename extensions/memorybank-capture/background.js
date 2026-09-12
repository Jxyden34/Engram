const MENU_PAGE = "memorybank-page";
const MENU_SELECTION = "memorybank-selection";
const MENU_LINK = "memorybank-link";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_PAGE,
      title: "Save page to MemoryBank",
      contexts: ["page"],
    });
    chrome.contextMenus.create({
      id: MENU_SELECTION,
      title: "Save selection to MemoryBank",
      contexts: ["selection"],
    });
    chrome.contextMenus.create({
      id: MENU_LINK,
      title: "Save link to MemoryBank",
      contexts: ["link"],
    });
  });
});

async function settings() {
  return chrome.storage.local.get(["memorybankUrl", "memorybankKey"]);
}

async function captureFromTab(tabId, mode) {
  const result = await chrome.scripting.executeScript({
    target: { tabId },
    func: (captureMode) => {
      const selected = window.getSelection()?.toString()?.trim() || "";
      const text = document.body?.innerText?.trim() || "";
      return {
        title: document.title || location.hostname,
        url: location.href,
        text: captureMode === "selection" && selected ? selected : text,
      };
    },
    args: [mode],
  });
  return result?.[0]?.result;
}

async function sendCapture(payload) {
  const cfg = await settings();
  const base = String(cfg.memorybankUrl || "").replace(/\/+$/, "");
  const key = String(cfg.memorybankKey || "").trim();

  if (!base || !key) {
    throw new Error("Configure the MemoryBank URL and capture key in the extension popup.");
  }

  const response = await fetch(`${base}/api/v1/capture`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${key}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || `MemoryBank returned ${response.status}`);
  }
  return body;
}

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  try {
    if (!tab?.id) return;

    if (info.menuItemId === MENU_LINK) {
      await sendCapture({
        capture_type: "link",
        title: info.linkUrl || "Saved link",
        url: info.linkUrl,
        text: info.linkUrl || "",
        metadata: { page_url: info.pageUrl || null },
      });
      return;
    }

    const mode = info.menuItemId === MENU_SELECTION ? "selection" : "page";
    const data = await captureFromTab(tab.id, mode);
    if (!data?.text) throw new Error("No readable text found on this page.");

    await sendCapture({
      capture_type: mode,
      title: data.title,
      url: data.url,
      text: data.text,
      metadata: {},
    });
  } catch (error) {
    console.error("MemoryBank capture failed:", error);
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "capture") return;

  (async () => {
    try {
      let payload = message.payload;
      if (message.mode === "page" || message.mode === "selection") {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tab?.id) throw new Error("No active browser tab.");
        const data = await captureFromTab(tab.id, message.mode);
        if (!data?.text) throw new Error("No readable text found.");
        payload = {
          capture_type: message.mode,
          title: data.title,
          url: data.url,
          text: data.text,
          metadata: {},
        };
      }

      const result = await sendCapture(payload);
      sendResponse({ ok: true, result });
    } catch (error) {
      sendResponse({ ok: false, error: String(error.message || error) });
    }
  })();

  return true;
});

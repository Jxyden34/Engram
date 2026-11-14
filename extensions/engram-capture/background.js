const MENU_PAGE = "engram-page";
const MENU_SELECTION = "engram-selection";
const MENU_LINK = "engram-link";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_PAGE,
      title: "Save page to Engram",
      contexts: ["page"],
    });
    chrome.contextMenus.create({
      id: MENU_SELECTION,
      title: "Save selection to Engram",
      contexts: ["selection"],
    });
    chrome.contextMenus.create({
      id: MENU_LINK,
      title: "Save link to Engram",
      contexts: ["link"],
    });
  });
});

async function settings() {
  const cfg = await chrome.storage.local.get(["engramUrl", "engramKey", "memorybankUrl", "memorybankKey", "engramTags", "engramProject"]);
  return {
    url: cfg.engramUrl || cfg.memorybankUrl,
    key: cfg.engramKey || cfg.memorybankKey,
    tags: cfg.engramTags || [],
    project: cfg.engramProject,
  };
}

async function captureFromTab(tabId, mode) {
  const result = await chrome.scripting.executeScript({
    target: { tabId },
    func: (captureMode) => {
      const selected = window.getSelection()?.toString()?.trim() || "";
      const text = document.body?.innerText?.trim() || "";
      const mainContent = document.querySelector("article, main, [role=main]");
      const content = captureMode === "reader" ? mainContent?.innerText?.trim() || text : text;
      return {
        title: document.title || location.hostname,
        url: location.href,
        text: captureMode === "selection" && selected ? selected : content,
      };
    },
    args: [mode],
  });
  return result?.[0]?.result;
}

async function sendCapture(payload) {
  const cfg = await settings();
  const base = String(cfg.url || "").replace(/\/+$/, "");
  const key = String(cfg.key || "").trim();

  if (!base || !key) {
    throw new Error("Configure the Engram URL and capture key in the extension popup.");
  }

  const headers = { Authorization: `Bearer ${key}`, "Content-Type": "application/json" };
  if (cfg.project) headers["X-Engram-Project"] = cfg.project;
  const response = await fetch(`${base}/api/v1/capture`, {
    method: "POST",
    headers,
    body: JSON.stringify({ ...payload, tags: payload.tags ?? cfg.tags }),
  });

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || `Engram returned ${response.status}`);
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
    console.error("Engram capture failed:", error);
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "capture") return;

  (async () => {
    try {
      let payload = message.payload;
      if (["page", "selection", "reader"].includes(message.mode)) {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tab?.id) throw new Error("No active browser tab.");
        const data = await captureFromTab(tab.id, message.mode);
        if (!data?.text) throw new Error("No readable text found.");
        payload = {
          capture_type: message.mode === "reader" ? "page" : message.mode,
          title: data.title,
          url: data.url,
          text: data.text,
          metadata: message.mode === "reader" ? { extraction: "reader" } : {},
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

const url = document.getElementById("url");
const key = document.getElementById("key");
const status = document.getElementById("status");
const note = document.getElementById("note");

async function load() {
  const cfg = await chrome.storage.local.get(["engramUrl", "engramKey", "memorybankUrl", "memorybankKey"]);
  url.value = cfg.engramUrl || cfg.memorybankUrl || "";
  key.value = cfg.engramKey || cfg.memorybankKey || "";
}

async function save() {
  await chrome.storage.local.set({
    engramUrl: url.value.trim().replace(/\/+$/, ""),
    engramKey: key.value.trim(),
  });
  status.textContent = "Connection saved.";
}

function send(message) {
  status.textContent = "Sending…";
  chrome.runtime.sendMessage(message, (response) => {
    if (chrome.runtime.lastError) {
      status.textContent = chrome.runtime.lastError.message;
      return;
    }
    status.textContent = response?.ok ? "Saved to Engram ✓" : (response?.error || "Capture failed");
  });
}

document.getElementById("save").addEventListener("click", save);
document.getElementById("page").addEventListener("click", () => send({ type: "capture", mode: "page" }));
document.getElementById("selection").addEventListener("click", () => send({ type: "capture", mode: "selection" }));
document.getElementById("noteButton").addEventListener("click", () => {
  const text = note.value.trim();
  if (!text) {
    status.textContent = "Write a note first.";
    return;
  }
  send({
    type: "capture",
    mode: "note",
    payload: {
      capture_type: "note",
      title: `Browser note ${new Date().toLocaleString()}`,
      text,
      metadata: {},
    },
  });
  note.value = "";
});

load();

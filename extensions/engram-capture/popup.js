const url = document.getElementById("url");
const key = document.getElementById("key");
const status = document.getElementById("status");
const note = document.getElementById("note");
const tags = document.getElementById("tags");

function captureTags() {
  return [...new Set(tags.value.split(",").map(tag => tag.trim()).filter(Boolean))];
}

async function load() {
  const cfg = await chrome.storage.local.get(["engramUrl", "engramKey", "memorybankUrl", "memorybankKey", "engramTags"]);
  url.value = cfg.engramUrl || cfg.memorybankUrl || "";
  key.value = cfg.engramKey || cfg.memorybankKey || "";
  tags.value = (cfg.engramTags || []).join(", ");
}

async function save() {
  const values = captureTags();
  if (values.length > 20 || values.some(tag => Array.from(tag).length > 64)) {
    status.textContent = "Use up to 20 tags, each 64 characters or fewer.";
    return;
  }
  await chrome.storage.local.set({
    engramUrl: url.value.trim().replace(/\/+$/, ""),
    engramKey: key.value.trim(),
    engramTags: values,
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
document.getElementById("reader").addEventListener("click", () => send({ type: "capture", mode: "reader" }));
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

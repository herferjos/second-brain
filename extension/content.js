const MAX_CHARS = 20000;

function normalizeText(s) {
  return (s || "").replace(/\s+/g, " ").trim();
}

function extractSnapshot() {
  const url = location.href;
  const title = document.title || "";
  const raw = document.body ? document.body.innerText : "";
  const text = normalizeText(raw);
  const truncated = text.length > MAX_CHARS;
  return {
    url,
    title,
    text: truncated ? text.slice(0, MAX_CHARS) : text,
    truncated,
    text_len: text.length
  };
}

function sendSnapshot(reason) {
  try {
    chrome.runtime.sendMessage({
      kind: "page_text",
      reason,
      payload: extractSnapshot()
    });
  } catch (e) {}
}

sendSnapshot("load");

let lastUrl = location.href;
setInterval(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    sendSnapshot("url_change");
  }
}, 1000);

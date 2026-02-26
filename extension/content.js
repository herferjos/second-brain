function normalizeText(s) {
  return (s || "").replace(/\s+/g, " ").trim();
}

function getBodyText() {
  return document.body ? document.body.innerText : "";
}

let lastSentText = null;

function extractSnapshot() {
  const url = location.href;
  const title = document.title || "";
  const text = normalizeText(getBodyText());
  
  return {
    url,
    title,
    text,
    text_len: text.length
  };
}

function sendSnapshot(reason) {
  try {
    const payload = extractSnapshot();
    
    // Don't send empty text
    if (!payload.text) return;

    // Avoid duplicating events if text hasn't changed
    if (payload.text === lastSentText) return;

    lastSentText = payload.text;

    chrome.runtime.sendMessage({
      kind: "page_text",
      reason,
      payload
    });
  } catch (e) {
    // Fail silently (e.g. extension context invalidated)
  }
}

// Initial load
setTimeout(() => sendSnapshot("load"), 1000);

// Watch for URL changes
let lastUrl = location.href;
setInterval(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    // Reset lastSentText on URL change to ensure we capture the new page even if text is similar (unlikely but safer)
    // Actually, if text is exactly the same on new URL, maybe we DO want to track it?
    // User said "hazlo sin duplicar eventos". If content is identical, maybe not needed. 
    // But usually URL change means different context. 
    // Let's reset lastSentText to allow re-sending if URL changed.
    lastSentText = null; 
    sendSnapshot("url_change");
  }
}, 1000);

// Watch for dynamic content changes (SPAs, lazy loading, etc)
// Debounce to avoid spamming while page renders
let debounceTimer;
const observer = new MutationObserver(() => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    sendSnapshot("dom_mutation");
  }, 2000); // Wait for 2s of silence before sending
});

if (document.body) {
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });
}

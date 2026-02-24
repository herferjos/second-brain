const COLLECTOR_URL = "http://127.0.0.1:8787/events";
const QUEUE_KEY = "event_queue_v1";

function baseEvent(type, meta) {
  return {
    id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
    ts: new Date().toISOString(),
    source: "browser",
    type,
    meta
  };
}

async function sha256Hex(s) {
  const data = new TextEncoder().encode(s || "");
  const hashBuf = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hashBuf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function getQueue() {
  const obj = await chrome.storage.local.get([QUEUE_KEY]);
  return Array.isArray(obj[QUEUE_KEY]) ? obj[QUEUE_KEY] : [];
}

async function setQueue(queue) {
  await chrome.storage.local.set({ [QUEUE_KEY]: queue });
}

async function enqueue(event) {
  const q = await getQueue();
  q.push(event);
  await setQueue(q);
}

async function flushQueue(max = 50) {
  const q = await getQueue();
  if (q.length === 0) return;
  const batch = q.slice(0, max);
  try {
    const resp = await fetch(COLLECTOR_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: batch })
    });
    if (!resp.ok) throw new Error("collector_rejected");
    await setQueue(q.slice(batch.length));
  } catch (e) {}
}

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (!msg || msg.kind !== "page_text") return;
  (async () => {
    const tabId = sender && sender.tab ? sender.tab.id : null;
    const p = msg.payload || {};
    const text = typeof p.text === "string" ? p.text : "";
    const textSha = await sha256Hex(text);

    await enqueue(
      baseEvent("browser.page_text", {
        tab_id: tabId,
        url: p.url,
        title: p.title,
        text,
        text_len: p.text_len,
        text_sha256: textSha,
        truncated: !!p.truncated,
        content_method: "innerText",
        reason: msg.reason
      })
    );
    await flushQueue();
  })();
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete") return;
  enqueue(
    baseEvent("browser.page_view", {
      tab_id: tabId,
      url: tab.url || "",
      title: tab.title || ""
    })
  ).then(() => flushQueue());
});

setInterval(() => flushQueue(), 3000);

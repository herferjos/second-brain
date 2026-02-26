const COLLECTOR_URL = "http://127.0.0.1:8787/events";
const QUEUE_KEY = "event_queue_v1";
const REC_BADGE_TEXT = "REC";

let recordingTabId = null;
let isFlushing = false;

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
  if (isFlushing) return;
  isFlushing = true;
  try {
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
  } finally {
    isFlushing = false;
  }
}

async function ensureOffscreenDocument() {
  if (!chrome.offscreen) return;

  try {
    const has = await chrome.offscreen.hasDocument();
    if (has) return;
  } catch (e) {}

  try {
    await chrome.offscreen.createDocument({
      url: "offscreen.html",
      reasons: ["USER_MEDIA"],
      justification: "Record the current tab audio and upload to the local collector"
    });
  } catch (e) {}
}

async function setRecordingBadge(isRecording) {
  try {
    await chrome.action.setBadgeBackgroundColor({ color: "#d93025" });
    await chrome.action.setBadgeText({ text: isRecording ? REC_BADGE_TEXT : "" });
  } catch (e) {}
}

async function stopTabRecording() {
  if (!recordingTabId) return;
  recordingTabId = null;
  await setRecordingBadge(false);
  try {
    chrome.runtime.sendMessage({ target: "offscreen", kind: "audio_stop" });
  } catch (e) {}
}

async function startTabRecording(tab) {
  if (!tab || !tab.id) return;

  await ensureOffscreenDocument();

  let streamId = null;
  try {
    streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id });
  } catch (e) {
    streamId = null;
  }
  if (!streamId) return;

  recordingTabId = tab.id;
  await setRecordingBadge(true);
  try {
    chrome.runtime.sendMessage({
      target: "offscreen",
      kind: "audio_start",
      streamId,
      tabId: tab.id,
      meta: { page_url: tab.url || "", page_title: tab.title || "" }
    });
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

const lastPageView = new Map(); // tabId -> { url, ts }

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete") return;

  const now = Date.now();
  const last = lastPageView.get(tabId);
  const currentUrl = tab.url || "";
  
  // Debounce duplicates: if same URL and < 2s, skip
  if (last && last.url === currentUrl && (now - last.ts) < 2000) {
    return;
  }

  lastPageView.set(tabId, { url: currentUrl, ts: now });

  enqueue(
    baseEvent("browser.page_view", {
      tab_id: tabId,
      url: currentUrl,
      title: tab.title || ""
    })
  ).then(() => flushQueue());
});

chrome.tabs.onRemoved.addListener((tabId) => {
  if (recordingTabId && tabId === recordingTabId) stopTabRecording();
  lastPageView.delete(tabId);
});

chrome.action.onClicked.addListener((tab) => {
  (async () => {
    if (recordingTabId && tab && tab.id === recordingTabId) {
      await stopTabRecording();
      return;
    }

    // Only one tab at a time.
    if (recordingTabId) await stopTabRecording();
    await startTabRecording(tab);
  })();
});

setInterval(() => flushQueue(), 3000);

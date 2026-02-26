const statusLineEl = document.getElementById("status-line");
const captureLineEl = document.getElementById("capture-line");
const tabLineEl = document.getElementById("tab-line");
const errorLineEl = document.getElementById("error-line");

const startBtn = document.getElementById("start-btn");
const stopBtn = document.getElementById("stop-btn");

let activeTabId = null;
let activeTabLabel = "";
let state = null;

function sendMessage(message) {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage(message, (response) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, reason: chrome.runtime.lastError.message || "runtime_error" });
          return;
        }
        resolve(response || { ok: false, reason: "empty_response" });
      });
    } catch (e) {
      resolve({ ok: false, reason: String(e && e.message ? e.message : e) });
    }
  });
}

function getTabCaptureStreamId(tabId) {
  return new Promise((resolve) => {
    if (!chrome.tabCapture || typeof chrome.tabCapture.getMediaStreamId !== "function") {
      resolve({ ok: false, reason: "tab_capture_api_unavailable" });
      return;
    }

    try {
      chrome.tabCapture.getMediaStreamId({ targetTabId: tabId }, (streamId) => {
        if (chrome.runtime.lastError) {
          resolve({
            ok: false,
            reason: chrome.runtime.lastError.message || "stream_id_failed"
          });
          return;
        }
        if (!streamId) {
          resolve({ ok: false, reason: "empty_stream_id" });
          return;
        }
        resolve({ ok: true, streamId });
      });
    } catch (e) {
      resolve({ ok: false, reason: String(e && e.message ? e.message : e) });
    }
  });
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tabs || tabs.length === 0) return null;
  return tabs[0];
}

function setError(message) {
  errorLineEl.textContent = message || "";
}

function humanizeError(reason) {
  const text = String(reason || "");
  if (!text) return "Unknown error";
  if (/invoked for the current page/i.test(text)) {
    return "Chrome blocked tabCapture without explicit action invocation.";
  }
  if (/permission/i.test(text)) {
    return `Permission error: ${text}`;
  }
  return text;
}

function render() {
  if (!activeTabId || !state) {
    statusLineEl.textContent = "No active tab available.";
    captureLineEl.textContent = "Status: idle";
    tabLineEl.textContent = "";
    startBtn.disabled = true;
    stopBtn.disabled = true;
    return;
  }

  if (state.audioDetected) {
    statusLineEl.textContent = "Audio detected in this tab.";
  } else {
    statusLineEl.textContent = "No live audio detected right now.";
  }

  captureLineEl.textContent = state.recording ? "Status: recording" : "Status: idle";
  tabLineEl.textContent = activeTabLabel;

  startBtn.disabled = !!state.recording;
  stopBtn.disabled = !state.recording;
}

async function refreshState() {
  if (!activeTabId) return;

  const response = await sendMessage({ kind: "popup_get_audio_state", tabId: activeTabId });
  if (!response.ok) {
    setError(response.reason || "Could not load tab status");
    return;
  }

  state = response.state || null;
  const tab = response.tab || null;
  activeTabLabel = (tab && tab.title) || "Untitled tab";
  setError("");
  render();
}

async function init() {
  const tab = await getActiveTab();
  if (!tab || !tab.id) {
    setError("No active tab found");
    render();
    return;
  }

  activeTabId = tab.id;
  activeTabLabel = tab.title || "Untitled tab";
  await refreshState();
}

startBtn.addEventListener("click", async () => {
  if (!activeTabId) return;

  const tabStream = await getTabCaptureStreamId(activeTabId);
  const response = tabStream.ok
    ? await sendMessage({
        kind: "popup_start_audio",
        tabId: activeTabId,
        streamId: tabStream.streamId,
        sourceType: "tab_capture"
      })
    : await sendMessage({
        kind: "popup_start_audio",
        tabId: activeTabId,
        sourceType: "tab_capture"
      });

  if (!response.ok) {
    const tabCaptureHint = !tabStream.ok ? ` (tabCapture: ${humanizeError(tabStream.reason)})` : "";
    setError(`${humanizeError(response.reason || "Could not start recording")}${tabCaptureHint}`);
  } else {
    setError("");
  }
  await refreshState();
});

stopBtn.addEventListener("click", async () => {
  if (!activeTabId) return;

  const response = await sendMessage({ kind: "popup_stop_audio", tabId: activeTabId });
  if (!response.ok) {
    setError(humanizeError(response.reason || "Could not stop recording"));
  } else {
    setError("");
  }
  await refreshState();
});

chrome.runtime.onMessage.addListener((message) => {
  if (!message || message.kind !== "audio_state_changed") return;
  if (!activeTabId || message.tabId !== activeTabId) return;

  if (message.state) {
    state = message.state;
    render();
  }
});

setInterval(() => {
  refreshState();
}, 2000);

init();

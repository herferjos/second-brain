const COLLECTOR_URL = "http://127.0.0.1:8787/events";
const QUEUE_KEY = "event_queue_v1";
const REC_BADGE_TEXT = "REC";

let recordingTabId = null;
let isFlushing = false;

const tabAudioState = new Map();
const lastPageText = new Map();
const lastPageView = new Map();

function getOrCreateAudioState(tabId) {
  if (!tabAudioState.has(tabId)) {
    tabAudioState.set(tabId, {
      audible: false,
      micActive: false,
      approved: false,
      rejected: false
    });
  }
  return tabAudioState.get(tabId);
}

function isAudioDetected(state) {
  return !!(state && (state.audible || state.micActive));
}

function supportsTabPrompt(tab) {
  const url = (tab && tab.url) || "";
  return /^https?:\/\//.test(url);
}

function getAudioUiState(tabId) {
  const state = getOrCreateAudioState(tabId);
  return {
    tabId,
    audible: !!state.audible,
    micActive: !!state.micActive,
    audioDetected: isAudioDetected(state),
    approved: !!state.approved,
    rejected: !!state.rejected,
    recording: recordingTabId === tabId,
    recordingTabId
  };
}

function notifyAudioStateChanged(tabId) {
  if (!tabId) return;
  const state = getAudioUiState(tabId);

  try {
    chrome.runtime.sendMessage(
      {
        kind: "audio_state_changed",
        tabId,
        state
      },
      () => {
        void chrome.runtime.lastError;
      }
    );
  } catch (e) {}

  try {
    chrome.tabs.sendMessage(
      tabId,
      {
        kind: "audio_overlay_state",
        tabId,
        state
      },
      () => {
        void chrome.runtime.lastError;
      }
    );
  } catch (e) {}
}

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

async function stopTabRecording(options = {}) {
  const { clearApproval = false, markRejected = false } = options;
  if (!recordingTabId) return;

  const previousTabId = recordingTabId;
  recordingTabId = null;

  await setRecordingBadge(false);

  try {
    chrome.runtime.sendMessage({ target: "offscreen", kind: "audio_stop" });
  } catch (e) {}

  const state = getOrCreateAudioState(previousTabId);
  if (clearApproval) {
    state.approved = false;
  }
  if (markRejected) {
    state.rejected = true;
  }

  notifyAudioStateChanged(previousTabId);
}

async function startTabRecording(tab, providedStreamId = null, sourceType = "tab_capture") {
  if (!tab || !tab.id) return { ok: false, reason: "invalid_tab" };

  await ensureOffscreenDocument();

  let streamId = providedStreamId || null;
  let resolvedSourceType = sourceType;
  let streamIdError = null;
  if (!streamId) {
    try {
      streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id });
      resolvedSourceType = "tab_capture";
    } catch (e) {
      streamIdError = String(e && e.message ? e.message : e);
      streamId = null;
    }
  }
  if (!streamId) {
    return { ok: false, reason: streamIdError || "stream_id_unavailable" };
  }

  recordingTabId = tab.id;
  await setRecordingBadge(true);

  try {
    chrome.runtime.sendMessage({
      target: "offscreen",
      kind: "audio_start",
      streamId,
      tabId: tab.id,
      sourceType: resolvedSourceType,
      meta: {
        page_url: tab.url || "",
        page_title: tab.title || ""
      }
    });
  } catch (e) {
    recordingTabId = null;
    await setRecordingBadge(false);
    return {
      ok: false,
      reason: String(e && e.message ? e.message : e) || "offscreen_start_failed"
    };
  }

  notifyAudioStateChanged(tab.id);
  return { ok: true };
}

async function startRecordingForTab(
  tabId,
  providedStreamId = null,
  sourceType = "tab_capture"
) {
  if (!tabId) return { ok: false, reason: "invalid_tab" };

  let tab = null;
  try {
    tab = await chrome.tabs.get(tabId);
  } catch (e) {
    return { ok: false, reason: "missing_tab" };
  }

  if (!tab || !supportsTabPrompt(tab)) {
    return { ok: false, reason: "unsupported_tab" };
  }

  const state = getOrCreateAudioState(tabId);
  state.approved = true;
  state.rejected = false;

  if (recordingTabId && recordingTabId !== tabId) {
    await stopTabRecording();
  }

  if (recordingTabId === tabId) {
    notifyAudioStateChanged(tabId);
    return { ok: true, state: getAudioUiState(tabId) };
  }

  const startResult = await startTabRecording(tab, providedStreamId, sourceType);
  if (!startResult.ok) {
    state.approved = false;
    notifyAudioStateChanged(tabId);
    return {
      ok: false,
      reason: startResult.reason || "capture_failed",
      state: getAudioUiState(tabId)
    };
  }

  return { ok: true, state: getAudioUiState(tabId) };
}

async function stopRecordingForTab(tabId, options = {}) {
  const { reject = false } = options;
  if (!tabId) return { ok: false, reason: "invalid_tab" };

  const state = getOrCreateAudioState(tabId);

  if (recordingTabId === tabId) {
    await stopTabRecording({ clearApproval: reject, markRejected: reject });
  }

  if (reject) {
    state.approved = false;
    state.rejected = true;
  } else {
    state.rejected = false;
  }

  notifyAudioStateChanged(tabId);
  return { ok: true, state: getAudioUiState(tabId) };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg) return;

  if (msg.kind === "tab_audio_activity") {
    (async () => {
      const tabId = sender && sender.tab ? sender.tab.id : null;
      if (!tabId) return;

      const state = getOrCreateAudioState(tabId);
      if (msg.direction === "user_input") {
        state.micActive = !!msg.active;
      }

      notifyAudioStateChanged(tabId);
    })();
    return;
  }

  if (msg.kind === "overlay_get_audio_state") {
    (async () => {
      const tabId = sender && sender.tab ? sender.tab.id : null;
      if (!tabId) {
        sendResponse({ ok: false, reason: "invalid_tab" });
        return;
      }

      let tab = null;
      try {
        tab = await chrome.tabs.get(tabId);
      } catch (e) {
        sendResponse({ ok: false, reason: "missing_tab" });
        return;
      }

      sendResponse({
        ok: true,
        tab: {
          id: tab.id,
          url: tab.url || "",
          title: tab.title || ""
        },
        state: getAudioUiState(tabId)
      });
    })();
    return true;
  }

  if (msg.kind === "overlay_start_audio") {
    (async () => {
      const tabId = sender && sender.tab ? sender.tab.id : null;
      const result = await startRecordingForTab(tabId);
      sendResponse(result);
    })();
    return true;
  }

  if (msg.kind === "overlay_stop_audio") {
    (async () => {
      const tabId = sender && sender.tab ? sender.tab.id : null;
      const result = await stopRecordingForTab(tabId, { reject: false });
      sendResponse(result);
    })();
    return true;
  }

  if (msg.kind === "popup_get_audio_state") {
    (async () => {
      const tabId = Number(msg.tabId) || null;
      if (!tabId) {
        sendResponse({ ok: false, reason: "invalid_tab" });
        return;
      }

      let tab = null;
      try {
        tab = await chrome.tabs.get(tabId);
      } catch (e) {
        sendResponse({ ok: false, reason: "missing_tab" });
        return;
      }

      sendResponse({
        ok: true,
        tab: {
          id: tab.id,
          url: tab.url || "",
          title: tab.title || ""
        },
        state: getAudioUiState(tabId)
      });
    })();
    return true;
  }

  if (msg.kind === "popup_start_audio") {
    (async () => {
      const tabId = Number(msg.tabId) || null;
      const streamId =
        typeof msg.streamId === "string" && msg.streamId.trim()
          ? msg.streamId.trim()
          : null;
      const sourceType =
        msg.sourceType === "desktop_capture" ? "desktop_capture" : "tab_capture";
      const result = await startRecordingForTab(tabId, streamId, sourceType);
      sendResponse(result);
    })();
    return true;
  }

  if (msg.kind === "popup_stop_audio") {
    (async () => {
      const tabId = Number(msg.tabId) || null;
      const result = await stopRecordingForTab(tabId, { reject: false });
      sendResponse(result);
    })();
    return true;
  }

  if (msg.kind === "popup_reject_audio") {
    (async () => {
      const tabId = Number(msg.tabId) || null;
      const result = await stopRecordingForTab(tabId, { reject: true });
      sendResponse(result);
    })();
    return true;
  }

  if (msg.kind === "popup_allow_audio") {
    (async () => {
      const tabId = Number(msg.tabId) || null;
      if (!tabId) {
        sendResponse({ ok: false, reason: "invalid_tab" });
        return;
      }

      const state = getOrCreateAudioState(tabId);
      state.rejected = false;
      notifyAudioStateChanged(tabId);
      sendResponse({ ok: true, state: getAudioUiState(tabId) });
    })();
    return true;
  }

  if (msg.kind !== "page_text") return;

  (async () => {
    const tabId = sender && sender.tab ? sender.tab.id : null;
    const p = msg.payload || {};
    const text = typeof p.text === "string" ? p.text : "";

    if (!text || text.length < 50) return;

    const textSha = await sha256Hex(text);

    if (tabId && lastPageText.get(tabId) === textSha) {
      return;
    }

    if (tabId) {
      lastPageText.set(tabId, textSha);
    }

    await enqueue(
      baseEvent("browser.page_text", {
        tab_id: tabId,
        url: p.url,
        title: p.title,
        text,
        text_len: text.length,
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
  (async () => {
    if (typeof changeInfo.audible === "boolean") {
      const state = getOrCreateAudioState(tabId);
      state.audible = changeInfo.audible;
      notifyAudioStateChanged(tabId);
    }

    if (changeInfo.status !== "complete") return;

    const now = Date.now();
    const last = lastPageView.get(tabId);
    const currentUrl = tab.url || "";

    if (last && last.url === currentUrl && now - last.ts < 2000) {
      return;
    }

    if (last && last.url !== currentUrl) {
      lastPageText.delete(tabId);
    }

    lastPageView.set(tabId, { url: currentUrl, ts: now });

    if (tab.audible) {
      const state = getOrCreateAudioState(tabId);
      state.audible = true;
      notifyAudioStateChanged(tabId);
    }

    await enqueue(
      baseEvent("browser.page_view", {
        tab_id: tabId,
        url: currentUrl,
        title: tab.title || ""
      })
    );
    await flushQueue();
  })();
});

chrome.tabs.onActivated.addListener(({ tabId }) => {
  (async () => {
    notifyAudioStateChanged(tabId);
  })();
});

chrome.tabs.onRemoved.addListener((tabId) => {
  (async () => {
    if (recordingTabId && tabId === recordingTabId) {
      await stopTabRecording({ clearApproval: true, markRejected: false });
    }

    lastPageView.delete(tabId);
    lastPageText.delete(tabId);
    tabAudioState.delete(tabId);
  })();
});

setInterval(() => flushQueue(), 3000);

const COLLECTOR_AUDIO_URL = "http://127.0.0.1:8787/audio";

let mediaStream = null;
let mediaRecorder = null;
let recordingTabId = null;
let recordingMeta = null;

function pickMimeType() {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg"
  ];
  for (const t of candidates) {
    try {
      if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t)) {
        return t;
      }
    } catch (e) {}
  }
  return "";
}

async function uploadChunk(blob, meta) {
  if (!blob || blob.size === 0) return;

  const mime = (blob.type || "").trim() || "application/octet-stream";
  const ext =
    mime.includes("webm") ? "webm" : mime.includes("ogg") ? "ogg" : "bin";
  const segId =
    (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())) +
    "_" +
    String(Date.now());

  const form = new FormData();
  form.append("file", blob, `${segId}.${ext}`);
  form.append("segment_id", segId);
  form.append("client_source", "browser_extension_tab_capture");
  if (meta && meta.page_url) form.append("page_url", meta.page_url);
  if (meta && meta.page_title) form.append("page_title", meta.page_title);

  try {
    const resp = await fetch(COLLECTOR_AUDIO_URL, { method: "POST", body: form });
    // Ignore errors; we don't want to kill the recorder mid-meeting.
    if (!resp.ok) throw new Error("collector_rejected");
  } catch (e) {}
}

async function startRecording(streamId, tabId, meta) {
  if (!streamId) return;

  // Stop any previous session first (best effort).
  await stopRecording();

  recordingTabId = tabId || null;
  recordingMeta = meta || null;

  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      mandatory: {
        chromeMediaSource: "tab",
        chromeMediaSourceId: streamId
      }
    },
    video: false
  });

  const mimeType = pickMimeType();
  mediaRecorder = mimeType
    ? new MediaRecorder(mediaStream, { mimeType })
    : new MediaRecorder(mediaStream);

  mediaRecorder.addEventListener("dataavailable", (evt) => {
    const blob = evt && evt.data ? evt.data : null;
    uploadChunk(blob, recordingMeta);
  });

  mediaRecorder.addEventListener("stop", () => {
    try {
      if (mediaStream) {
        for (const track of mediaStream.getTracks()) track.stop();
      }
    } catch (e) {}
    mediaStream = null;
    mediaRecorder = null;
    recordingTabId = null;
    recordingMeta = null;
  });

  // Chunk every 15s to keep uploads small.
  mediaRecorder.start(15000);
}

async function stopRecording() {
  try {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
      return;
    }
  } catch (e) {}

  try {
    if (mediaStream) {
      for (const track of mediaStream.getTracks()) track.stop();
    }
  } catch (e) {}

  mediaStream = null;
  mediaRecorder = null;
  recordingTabId = null;
  recordingMeta = null;
}

chrome.runtime.onMessage.addListener((msg) => {
  if (!msg || msg.target !== "offscreen") return;

  if (msg.kind === "audio_start") {
    startRecording(msg.streamId, msg.tabId, msg.meta || null);
  } else if (msg.kind === "audio_stop") {
    stopRecording();
  }
});

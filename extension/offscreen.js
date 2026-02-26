const COLLECTOR_AUDIO_URL = "http://127.0.0.1:8787/audio";

let tabAudioStream = null;
let micAudioStream = null;
let mixedAudioStream = null;
let mixAudioContext = null;
let playbackAudioContext = null;
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
  if (meta && meta.capture_scope) form.append("capture_scope", meta.capture_scope);

  try {
    const resp = await fetch(COLLECTOR_AUDIO_URL, { method: "POST", body: form });
    // Ignore errors; we don't want to kill the recorder mid-meeting.
    if (!resp.ok) throw new Error("collector_rejected");
  } catch (e) {}
}

async function getCapturedTabStream(streamId, sourceType) {
  const captureSource =
    sourceType === "desktop_capture" ? "desktop" : "tab";

  return navigator.mediaDevices.getUserMedia({
    audio: {
      mandatory: {
        chromeMediaSource: captureSource,
        chromeMediaSourceId: streamId
      }
    },
    video: false
  });
}

async function startRecording(streamId, tabId, meta, sourceType) {
  if (!streamId) return;

  // Stop any previous session first (best effort).
  await stopRecording();

  recordingTabId = tabId || null;
  recordingMeta = {
    ...(meta || {}),
    capture_scope: "tab_output_plus_user_microphone"
  };

  tabAudioStream = await getCapturedTabStream(streamId, sourceType);

  try {
    micAudioStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      },
      video: false
    });
  } catch (e) {
    micAudioStream = null;
  }

  mixAudioContext = new AudioContext();
  const destination = mixAudioContext.createMediaStreamDestination();
  try {
    if (tabAudioStream) {
      // Keep local tab audio audible while also sending it to recorder mix.
      const tabSource = mixAudioContext.createMediaStreamSource(tabAudioStream);
      tabSource.connect(destination);
    }
    if (micAudioStream) {
      mixAudioContext.createMediaStreamSource(micAudioStream).connect(destination);
    }
  } catch (e) {}
  mixedAudioStream = destination.stream;

  // Re-route captured tab output back to local speakers.
  // Without this, Chrome tab capture can suppress playback.
  try {
    playbackAudioContext = new AudioContext();
    const playbackSource = playbackAudioContext.createMediaStreamSource(tabAudioStream);
    playbackSource.connect(playbackAudioContext.destination);
    if (playbackAudioContext.state === "suspended") {
      playbackAudioContext.resume();
    }
  } catch (e) {}

  const mimeType = pickMimeType();
  mediaRecorder = mimeType
    ? new MediaRecorder(mixedAudioStream, { mimeType })
    : new MediaRecorder(mixedAudioStream);

  mediaRecorder.addEventListener("dataavailable", (evt) => {
    const blob = evt && evt.data ? evt.data : null;
    uploadChunk(blob, recordingMeta);
  });

  mediaRecorder.addEventListener("stop", () => {
    stopRecording();
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
    if (tabAudioStream) {
      for (const track of tabAudioStream.getTracks()) track.stop();
    }
  } catch (e) {}

  try {
    if (micAudioStream) {
      for (const track of micAudioStream.getTracks()) track.stop();
    }
  } catch (e) {}

  try {
    if (mixedAudioStream) {
      for (const track of mixedAudioStream.getTracks()) track.stop();
    }
  } catch (e) {}

  try {
    if (mixAudioContext) {
      mixAudioContext.close();
    }
  } catch (e) {}

  try {
    if (playbackAudioContext) {
      playbackAudioContext.close();
    }
  } catch (e) {}

  tabAudioStream = null;
  micAudioStream = null;
  mixedAudioStream = null;
  mixAudioContext = null;
  playbackAudioContext = null;
  mediaRecorder = null;
  recordingTabId = null;
  recordingMeta = null;
}

chrome.runtime.onMessage.addListener((msg) => {
  if (!msg || msg.target !== "offscreen") return;

  if (msg.kind === "audio_start") {
    startRecording(
      msg.streamId,
      msg.tabId,
      msg.meta || null,
      msg.sourceType || "tab_capture"
    );
  } else if (msg.kind === "audio_stop") {
    stopRecording();
  }
});

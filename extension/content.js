// Extract structured text (Markdown-like) from the DOM

const PAGE_AUDIO_MONITOR_SOURCE = "second_brain_page_audio_monitor";

function injectPageAudioMonitor() {
  try {
    if (window.__secondBrainPageAudioMonitorInjected) return;
    window.__secondBrainPageAudioMonitorInjected = true;

    const script = document.createElement("script");
    script.src = chrome.runtime.getURL("page_audio_monitor.js");
    script.async = false;
    (document.head || document.documentElement).appendChild(script);
    script.onload = () => script.remove();
  } catch (e) {}
}

window.addEventListener("message", (event) => {
  try {
    if (event.source !== window) return;
    const data = event.data || {};
    if (data.source !== PAGE_AUDIO_MONITOR_SOURCE) return;
    if (data.kind !== "mic_activity") return;

    chrome.runtime.sendMessage({
      kind: "tab_audio_activity",
      direction: "user_input",
      active: !!data.active,
      reason: data.reason || "page_monitor"
    });
  } catch (e) {}
});

const overlayUiState = {
  audioDetected: false,
  recording: false,
  busy: false,
  error: ""
};

let overlayHost = null;
let overlayStatusEl = null;
let overlayStartBtn = null;
let overlayStopBtn = null;
let overlayErrorEl = null;
let overlayErrorTimer = null;

function sendRuntimeMessage(message) {
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

function humanizeOverlayError(reason) {
  const text = String(reason || "");
  if (!text) return "Could not start capture.";
  if (/invoked/i.test(text) || /activeTab/i.test(text) || /permission/i.test(text)) {
    return "Chrome blocked capture in this context. Click the extension icon once, then use Start.";
  }
  return text;
}

function ensureAudioOverlay() {
  if (overlayHost) return;
  if (!document.documentElement) return;

  overlayHost = document.createElement("div");
  overlayHost.id = "second-brain-audio-overlay-host";
  overlayHost.style.position = "fixed";
  overlayHost.style.right = "14px";
  overlayHost.style.bottom = "14px";
  overlayHost.style.zIndex = "2147483647";
  overlayHost.style.display = "none";

  const shadow = overlayHost.attachShadow({ mode: "open" });
  shadow.innerHTML = `
    <style>
      .panel {
        background: rgba(15, 18, 23, 0.95);
        border: 1px solid rgba(255, 255, 255, 0.18);
        border-radius: 12px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
        color: #f8f9fa;
        font-family: "Segoe UI", Tahoma, sans-serif;
        min-width: 220px;
        padding: 10px;
      }
      .status {
        font-size: 12px;
        font-weight: 600;
        line-height: 1.35;
      }
      .actions {
        display: grid;
        gap: 8px;
        grid-template-columns: 1fr 1fr;
        margin-top: 8px;
      }
      button {
        border: 1px solid transparent;
        border-radius: 8px;
        cursor: pointer;
        font-size: 12px;
        font-weight: 700;
        padding: 8px 10px;
      }
      button:disabled {
        cursor: default;
        opacity: 0.45;
      }
      .start-btn {
        background: #1a73e8;
        color: #ffffff;
      }
      .stop-btn {
        background: #ffffff;
        color: #202124;
      }
      .error {
        color: #f28b82;
        font-size: 11px;
        line-height: 1.3;
        margin-top: 8px;
        min-height: 14px;
      }
    </style>
    <div class="panel" role="region" aria-label="Audio capture controls">
      <div id="sb-audio-status" class="status">Audio detected in this tab.</div>
      <div class="actions">
        <button id="sb-audio-start" class="start-btn" type="button">Start</button>
        <button id="sb-audio-stop" class="stop-btn" type="button">Stop</button>
      </div>
      <div id="sb-audio-error" class="error"></div>
    </div>
  `;

  overlayStatusEl = shadow.getElementById("sb-audio-status");
  overlayStartBtn = shadow.getElementById("sb-audio-start");
  overlayStopBtn = shadow.getElementById("sb-audio-stop");
  overlayErrorEl = shadow.getElementById("sb-audio-error");

  overlayStartBtn.addEventListener("click", () => {
    void startOverlayRecording();
  });
  overlayStopBtn.addEventListener("click", () => {
    void stopOverlayRecording();
  });

  document.documentElement.appendChild(overlayHost);
}

function shouldShowOverlay() {
  return overlayUiState.audioDetected || overlayUiState.recording || !!overlayUiState.error;
}

function renderOverlay() {
  ensureAudioOverlay();
  if (!overlayHost) return;

  overlayHost.style.display = shouldShowOverlay() ? "block" : "none";
  if (!overlayStatusEl || !overlayStartBtn || !overlayStopBtn || !overlayErrorEl) return;

  if (overlayUiState.recording) {
    overlayStatusEl.textContent = "Recording audio for this tab.";
  } else if (overlayUiState.audioDetected) {
    overlayStatusEl.textContent = "Audio detected in this tab.";
  } else {
    overlayStatusEl.textContent = "No audio detected.";
  }

  overlayStartBtn.disabled = overlayUiState.recording || overlayUiState.busy;
  overlayStopBtn.disabled = !overlayUiState.recording || overlayUiState.busy;
  overlayErrorEl.textContent = overlayUiState.error || "";
}

function setOverlayError(message) {
  overlayUiState.error = message || "";
  if (overlayErrorTimer) {
    clearTimeout(overlayErrorTimer);
    overlayErrorTimer = null;
  }

  if (overlayUiState.error) {
    overlayErrorTimer = setTimeout(() => {
      overlayUiState.error = "";
      renderOverlay();
    }, 5000);
  }

  renderOverlay();
}

function applyOverlayState(state) {
  overlayUiState.audioDetected = !!(state && state.audioDetected);
  overlayUiState.recording = !!(state && state.recording);
  renderOverlay();
}

async function startOverlayRecording() {
  overlayUiState.busy = true;
  setOverlayError("");
  renderOverlay();

  const response = await sendRuntimeMessage({ kind: "overlay_start_audio" });
  overlayUiState.busy = false;

  if (!response.ok) {
    setOverlayError(humanizeOverlayError(response.reason));
  } else if (response.state) {
    applyOverlayState(response.state);
  } else {
    renderOverlay();
  }
}

async function stopOverlayRecording() {
  overlayUiState.busy = true;
  setOverlayError("");
  renderOverlay();

  const response = await sendRuntimeMessage({ kind: "overlay_stop_audio" });
  overlayUiState.busy = false;

  if (!response.ok) {
    setOverlayError(String(response.reason || "Could not stop capture"));
  } else if (response.state) {
    applyOverlayState(response.state);
  } else {
    renderOverlay();
  }
}

async function requestOverlayState() {
  const response = await sendRuntimeMessage({ kind: "overlay_get_audio_state" });
  if (response && response.ok && response.state) {
    applyOverlayState(response.state);
  }
}

chrome.runtime.onMessage.addListener((msg) => {
  if (!msg || msg.kind !== "audio_overlay_state") return;
  applyOverlayState(msg.state || null);
});

function getStructuredText(node, preserveWhitespace = false) {
  if (!node) return "";
  
  // Handle text nodes
  if (node.nodeType === Node.TEXT_NODE) {
    const text = node.textContent || "";
    if (preserveWhitespace) return text;
    // Collapse whitespace but keep single spaces
    return text.replace(/\s+/g, " ");
  }
  
  // Only traverse Element nodes
  if (node.nodeType !== Node.ELEMENT_NODE) return "";
  
  const tag = node.tagName;
  
  // Skip technical/hidden tags
  const ignoredTags = [
    'SCRIPT', 'STYLE', 'NOSCRIPT', 'IFRAME', 'SVG', 
    'HEAD', 'METADATA', 'LINK', 'OBJECT', 'FANCYBOX'
  ];
  if (ignoredTags.includes(tag)) return "";
  
  // Only respect the standard hidden attribute. 
  if (node.hasAttribute('hidden')) return "";
  
  const isPre = tag === 'PRE' || tag === 'TEXTAREA' || tag === 'CODE';
  const shouldPreserve = preserveWhitespace || isPre;

  let content = "";
  
  // 1. Try Shadow Root (open mode only)
  if (node.shadowRoot) {
    for (let i = 0; i < node.shadowRoot.childNodes.length; i++) {
      content += getStructuredText(node.shadowRoot.childNodes[i], shouldPreserve);
    }
  } 
  
  // 2. Traverse Light DOM children
  if (!node.shadowRoot && node.childNodes.length > 0) {
     for (let i = 0; i < node.childNodes.length; i++) {
      content += getStructuredText(node.childNodes[i], shouldPreserve);
    }
  }
  
  // Formatting
  switch (tag) {
    case 'SLOT': {
      if (node.assignedNodes) {
        const nodes = node.assignedNodes();
        for (let i = 0; i < nodes.length; i++) {
          content += getStructuredText(nodes[i], shouldPreserve);
        }
      }
      return content;
    }
    case 'H1': return `\n\n# ${content.trim()}\n\n`;
    case 'H2': return `\n\n## ${content.trim()}\n\n`;
    case 'H3': return `\n\n### ${content.trim()}\n\n`;
    case 'H4': 
    case 'H5': 
    case 'H6': return `\n\n#### ${content.trim()}\n\n`;
    
    case 'P': return `\n\n${content.trim()}\n\n`;
    case 'BR': return `\n`;
    case 'HR': return `\n---\n`;
    
    case 'LI': return `\n- ${content.trim()}`;
    case 'UL': 
    case 'OL': return `\n\n${content.trim()}\n\n`;
    
    case 'A': {
      const href = node.href || node.getAttribute('href');
      const text = content.trim();
      if (!text) return ""; 
      if (!href || href.startsWith('javascript:') || href.startsWith('#')) return ` ${text} `;
      return ` [${text}](${href}) `;
    }
    
    case 'IMG': {
      const alt = node.getAttribute('alt');
      // Only show images if they have alt text, to reduce noise
      return alt ? ` ![${alt}] ` : "";
    }
    
    case 'INPUT': {
      const type = node.getAttribute('type');
      const val = node.value || node.getAttribute('value') || "";
      if (type === 'hidden' || type === 'password') return "";
      return ` [Input: ${val}] `;
    }

    case 'TEXTAREA': {
      return `\n${node.value || ""}\n`;
    }
    
    case 'B':
    case 'STRONG': return ` **${content.trim()}** `;
    case 'I':
    case 'EM': return ` *${content.trim()}* `;
    
    case 'CODE': {
      // If already inside PRE, don't wrap in backticks
      if (preserveWhitespace && node.parentNode && node.parentNode.tagName === 'PRE') return content;
      return ` \`${content.trim()}\` `;
    }
    
    case 'PRE': return `\n\`\`\`\n${content}\n\`\`\`\n`;
    case 'BLOCKQUOTE': return `\n> ${content.trim()}\n`;
    
    case 'TR': return `\n| ${content.trim()} |`;
    case 'TH':
    case 'TD': return ` ${content.trim()} |`;
    
    case 'DIV':
    case 'SECTION':
    case 'ARTICLE':
    case 'MAIN':
    case 'HEADER':
    case 'FOOTER':
    case 'ASIDE':
    case 'NAV':
    case 'FORM':
      return `\n${content}`;
      
    default: return content;
  }
}

function getPageContent() {
  if (!document.body) return "";
  
  let structured = getStructuredText(document.body);
  
  // Clean up excessive newlines
  structured = structured.replace(/(\n\s*){3,}/g, "\n\n");
  structured = structured.trim();
  
  // Fallback if structured failed significantly
  if (structured.length < 50 && document.body.innerText.length > 50) {
    return document.body.innerText.trim();
  }
  
  return structured;
}

let lastSentText = null;

function extractSnapshot() {
  const url = location.href;
  const title = document.title || "";
  const text = getPageContent();
  
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
    
    if (!payload.text) return;

    // Deduplication check
    if (payload.text === lastSentText) return;
    if (payload.text.length < 50) return; 

    lastSentText = payload.text;

    chrome.runtime.sendMessage({
      kind: "page_text",
      reason,
      payload
    });
  } catch (e) {
    // Extension context might be invalidated
  }
}

// Initial load
setTimeout(() => sendSnapshot("load"), 3000);

// Watch for URL changes
let lastUrl = location.href;
setInterval(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    lastSentText = null; // Force resend on URL change
    setTimeout(() => sendSnapshot("url_change"), 3000); 
  }
}, 1000);

// --- INTELLIGENT OBSERVER ---

let debounceTimer;
let maxWaitTimer;

// This triggers when DOM changes
const observer = new MutationObserver((mutations) => {
  // 1. Reset the "Silence Timer" (Debounce)
  // Will fire only if page stops changing for 2 seconds
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    sendSnapshot("dom_settled");
    
    // Clear the maxWait because we successfully sent a snapshot
    clearTimeout(maxWaitTimer);
    maxWaitTimer = null;
  }, 2000);

  // 2. Start "Max Wait Timer" (Throttle) if not running
  // Will fire if page keeps changing for 10 seconds without stopping (e.g. ChatGPT streaming)
  if (!maxWaitTimer) {
    maxWaitTimer = setTimeout(() => {
      sendSnapshot("dom_active_update");
      maxWaitTimer = null; 
      // Note: we don't clear debounceTimer; it will just reset again on next mutation
    }, 10000);
  }
});

if (document.body) {
  observer.observe(document.body, { 
    childList: true, 
    subtree: true, 
    characterData: true,
    attributes: true 
  });
}

injectPageAudioMonitor();
setTimeout(() => {
  void requestOverlayState();
}, 800);

// --- USER INTERACTION TRIGGERS ---

// Capture explicit user actions that imply content change/creation
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    // User submitted something. Wait a bit for UI to update (e.g. user message bubbles)
    // and take a snapshot. 
    setTimeout(() => sendSnapshot("user_enter_key"), 500);
  }
}, true);

document.addEventListener("click", (e) => {
  // General click (buttons, navigation) - often triggers UI changes
  // Debounce slightly to not spam on double clicks
  setTimeout(() => sendSnapshot("user_click"), 1000);
}, true);

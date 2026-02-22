const API_URL = "http://localhost:8000/session";
const IDLE_THRESHOLD = 300; // 5 minutes (in seconds)

let sessionData = [];
let tabTimers = {}; // { tabId: startTime }

// Configure idle detection
chrome.idle.setDetectionInterval(IDLE_THRESHOLD);

chrome.idle.onStateChanged.addListener((state) => {
  console.log(`Idle state changed: ${state}`);
  if ((state === "idle" || state === "locked") && sessionData.length > 0) {
    flushSession();
  }
});

// Capture when a tab finishes loading
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url && tab.url.startsWith('http')) {
    // Start timer for this tab
    tabTimers[tabId] = Date.now();

    // Try to capture content
    setTimeout(() => captureTabContent(tabId), 1000); // Small delay to ensure script loading
  }
});

// Capture when a tab is closed (to calculate time spent, optional)
chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabTimers[tabId]) {
    delete tabTimers[tabId];
  }
});

async function captureTabContent(tabId) {
  try {
    const response = await chrome.tabs.sendMessage(tabId, { action: "CAPTURE_STATE" });

    if (response) {
      console.log(`Capturado: ${response.title}`);

      // Avoid consecutive duplicates of the same URL
      const lastEntry = sessionData[sessionData.length - 1];
      if (lastEntry && lastEntry.url === response.url) {
        return;
      }

      sessionData.push(response);
    }
  } catch (err) {
    // It is normal that it fails on pages where the script cannot be injected (e.g. chrome store)
    console.log(`Could not capture tab ${tabId}: ${err.message}`);
  }
}

async function flushSession() {
  console.log(`Sending session with ${sessionData.length} activities...`);

  try {
    const payload = {
      activities: sessionData,
      session_end: new Date().toISOString()
    };

    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);

    console.log("Session sent successfully.");
    sessionData = []; // Clean buffer

  } catch (err) {
    console.error("Error sending session:", err.message);
    // We do not clean sessionData to try again later
  }
}

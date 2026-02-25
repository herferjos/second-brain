# SecondBrain LifeLog Extension

Chrome MV3 extension that logs page views, visible text snapshots, and (optionally) tab audio to the LifeLog collector.

## Setup

1. Start the collector (see `collector/README.md`).

2. Load the extension in Chrome:
   - Open `chrome://extensions/`
   - Enable "Developer mode"
   - Click "Load unpacked"
   - Select the `extension/` folder

## Behavior

- On each page load and URL change: extracts visible text via `innerText`, truncates to 20k chars, and sends `browser.page_text` events.
- On tab navigation complete: sends `browser.page_view` events.
- Events are queued in `chrome.storage.local` when the collector is down and retried every 3 seconds.

## Tab Audio Recording (Browser Output -> Collector)

This extension can record the active tab audio (e.g. meetings in the browser) and upload chunks to the collector `/audio` endpoint.

- Click the extension icon to toggle recording for the current tab.
- While recording, the toolbar badge shows `REC`.
- Audio is uploaded in small chunks (every ~15 seconds).

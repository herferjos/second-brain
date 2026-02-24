# SecondBrain LifeLog Extension

Chrome MV3 extension that logs page views and visible text snapshots to the LifeLog collector.

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

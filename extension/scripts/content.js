// Listen for requests from the background script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "CAPTURE_STATE") {
    const data = {
      url: window.location.href,
      title: document.title,
      content: window.Scraper.getContent(),
      events: window.Monitor.getEvents(),
      timestamp: new Date().toISOString()
    };
    sendResponse(data);
  }
  return true; // Keep the channel open for asynchronous response
});

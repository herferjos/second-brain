const Scraper = {
  /**
   * Extract the main content of the current page.
   */
  getContent() {
    if (window.location.hostname.includes("docs.google.com")) {
      return this.scrapeGoogleDocs();
    }
    
    // For normal websites, we use a combination of common selectors
    // and try to avoid menus, footers, etc.
    const bodyClone = document.body.cloneNode(true);
    
    // Remove unwanted elements from the clone before extracting text
    const toRemove = bodyClone.querySelectorAll('nav, footer, script, style, aside, header, .ads, .menu');
    toRemove.forEach(el => el.remove());

    return bodyClone.innerText.replace(/\s+/g, ' ').trim().substring(0, 15000);
  },

  /**
   * Specific logic for Google Docs (tries to read the text layers).
   */ 
  scrapeGoogleDocs() {
    // Google Docs uses a 'kix-line' system to render text
    const lines = document.querySelectorAll('.kix-line');
    if (lines.length > 0) {
      return Array.from(lines).map(line => line.innerText).join('\n');
    }
    
    // Fallback: find the main container
    const editor = document.querySelector('.docs-editor-container') || document.body;
    return editor.innerText;
  }
};

window.Scraper = Scraper;

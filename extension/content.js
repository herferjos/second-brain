// Extract structured text (Markdown-like) from the DOM

function getStructuredText(node, preserveWhitespace = false) {
  if (!node) return "";
  
  if (node.nodeType === Node.TEXT_NODE) {
    if (preserveWhitespace) return node.textContent || "";
    return (node.textContent || "").replace(/\s+/g, " ");
  }
  
  if (node.nodeType !== Node.ELEMENT_NODE) return "";
  
  const tag = node.tagName;
  
  const ignoredTags = [
    'SCRIPT', 'STYLE', 'NOSCRIPT', 'IFRAME', 'SVG', 
    'HEAD', 'METADATA', 'LINK', 'OBJECT', 'FANCYBOX'
  ];
  if (ignoredTags.includes(tag)) return "";
  
  if (node.hasAttribute('hidden') || node.getAttribute('aria-hidden') === 'true') return "";
  
  const isPre = tag === 'PRE' || tag === 'TEXTAREA';
  const shouldPreserve = preserveWhitespace || isPre;

  let content = "";
  for (let i = 0; i < node.childNodes.length; i++) {
    content += getStructuredText(node.childNodes[i], shouldPreserve);
  }
  
  switch (tag) {
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
      if (!href || href.startsWith('javascript:')) return content;
      return ` [${text}](${href}) `;
    }
    
    case 'IMG': {
      const alt = node.getAttribute('alt');
      return alt ? ` ![${alt}] ` : "";
    }
    
    case 'B':
    case 'STRONG': return ` **${content.trim()}** `;
    case 'I':
    case 'EM': return ` *${content.trim()}* `;
    
    case 'CODE': {
      if (node.parentNode && node.parentNode.tagName === 'PRE') return content;
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
      return `\n${content}\n`;
      
    default: return content;
  }
}

function getPageContent() {
  if (!document.body) return "";
  const raw = getStructuredText(document.body);
  return raw.replace(/\n{3,}/g, "\n\n").trim();
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

    if (payload.text === lastSentText) return;
    lastSentText = payload.text;

    chrome.runtime.sendMessage({
      kind: "page_text",
      reason,
      payload
    });
  } catch (e) {
  }
}

// Initial load
setTimeout(() => sendSnapshot("load"), 1000);

// Watch for URL changes
let lastUrl = location.href;
setInterval(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    lastSentText = null; 
    sendSnapshot("url_change");
  }
}, 1000);

// Watch for dynamic content changes
let debounceTimer;
const observer = new MutationObserver(() => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    sendSnapshot("dom_mutation");
  }, 2000);
});

if (document.body) {
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });
}

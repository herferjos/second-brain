const Monitor = {
  events: [],
  maxEvents: 50,

  init() {
    this.setupListeners();
  },

  setupListeners() {
    // Monitor clicks
    document.addEventListener('click', (e) => {
      const target = e.target;
      const info = `Click en ${target.tagName} (${target.innerText?.substring(0, 20) || target.id || 'sin texto'})`;
      this.addEvent(info);
    }, true);

    // Monitor significant changes in inputs (debounced)
    let inputTimeout;
    document.addEventListener('input', (e) => {
      clearTimeout(inputTimeout);
      inputTimeout = setTimeout(() => {
        const info = `Escritura en ${e.target.tagName} (ID: ${e.target.id || 'N/A'})`;
        this.addEvent(info);
      }, 2000);
    }, true);
  },

  addEvent(msg) {
    const timestamp = new Date().toLocaleTimeString();
    this.events.push(`[${timestamp}] ${msg}`);
    
    // Keep a limit of events to avoid saturating
    if (this.events.length > this.maxEvents) {
      this.events.shift();
    }
  },

  getEvents() {
    const currentEvents = [...this.events];
    this.events = []; // Clean after delivering
    return currentEvents;
  }
};

window.Monitor = Monitor;
Monitor.init();

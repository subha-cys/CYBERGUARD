(() => {
  if (globalThis.cyberguardPageInspectorInstalled) {
    sendPageSummary();
    return;
  }
  globalThis.cyberguardPageInspectorInstalled = true;

  function escapeAttribute(value) {
    return String(value || '').slice(0, 300).replace(/[&"<>]/g, character => ({
      '&': '&amp;', '"': '&quot;', '<': '&lt;', '>': '&gt;'
    })[character]);
  }

  function sendPageSummary() {
    if (globalThis.cyberguardPageLastReportedUrl === location.href) return;
    globalThis.cyberguardPageLastReportedUrl = location.href;
    const forms = [...document.forms].slice(0, 20).map(form => {
      const action = escapeAttribute(form.action);
      const controls = [...form.querySelectorAll('input, select, textarea')].slice(0, 50).map(control => {
        const type = escapeAttribute(control.type || control.tagName.toLowerCase());
        const name = escapeAttribute(control.name || control.id || '');
        const autocomplete = escapeAttribute(control.autocomplete || '');
        return `<input type="${type}" name="${name}" autocomplete="${autocomplete}">`;
      }).join('');
      return `<form action="${action}">${controls}</form>`;
    }).join('');

    chrome.runtime.sendMessage({
      type: 'CYBERGUARD_PAGE_SUMMARY',
      url: location.href,
      title: document.title || '',
      html_content: `<html><head><title>${escapeAttribute(document.title)}</title></head><body>${forms}</body></html>`.slice(0, 16000)
    }).catch(() => {});
  }

  chrome.runtime.onMessage.addListener(message => {
    if (message.type === 'CYBERGUARD_SCAN_PAGE') sendPageSummary();
  });

  chrome.storage.local.get('monitoringEnabled').then(({ monitoringEnabled }) => {
    if (monitoringEnabled) sendPageSummary();
  });
})();
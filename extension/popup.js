const serviceState = document.getElementById('serviceState');
const toggle = document.getElementById('monitorToggle');
const description = document.getElementById('monitorDescription');
const errorBox = document.getElementById('error');

async function refresh() {
  const state = await chrome.runtime.sendMessage({ type: 'CYBERGUARD_GET_STATE' });
  toggle.setAttribute('aria-checked', String(Boolean(state.monitoringEnabled)));
  toggle.setAttribute('aria-label', state.monitoringEnabled ? 'Disable website monitoring' : 'Enable website monitoring');
  description.textContent = state.monitoringEnabled
    ? (state.monitorStatus?.startsWith('Monitoring could not resume:') ? state.monitorStatus : 'Active for HTTP and HTTPS pages')
    : 'Off until you enable it';
  if (state.lastScan) {
    const scan = state.lastScan;
    const time = new Date(scan.checkedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    document.getElementById('lastScan').hidden = false;
    document.getElementById('lastScan').innerHTML = `<b>Last page:</b> ${escapeHtml(scan.title || scan.url)}<br><b>Risk:</b> <span class="risk">${scan.riskScore}/100 - ${escapeHtml(scan.riskLevel)}</span> - ${time}`;
  }

  try {
    const response = await fetch(`${state.serviceUrl}/api/health`);
    if (!response.ok) throw new Error('Service did not respond');
    serviceState.className = 'service-state ready';
    serviceState.querySelector('span').textContent = 'Local analysis service connected';
  } catch {
    serviceState.className = 'service-state offline';
    serviceState.querySelector('span').textContent = 'Local service offline; start run.bat';
  }
}

function escapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[character]);
}

toggle.addEventListener('click', async () => {
  errorBox.hidden = true;
  const enabled = toggle.getAttribute('aria-checked') !== 'true';
  try {
    if (enabled && !await chrome.permissions.request({ origins: ['<all_urls>'] })) {
      throw new Error('Website access was not granted. Monitoring remains off.');
    }
    const result = await chrome.runtime.sendMessage({ type: 'CYBERGUARD_SET_MONITORING', enabled });
    if (!result.ok) throw new Error(result.error);
    await refresh();
  } catch (error) {
    errorBox.textContent = error.message || 'Could not change monitoring state.';
    errorBox.hidden = false;
  }
});

document.getElementById('openDashboard').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.windowId !== undefined) await chrome.sidePanel.open({ windowId: tab.windowId });
  window.close();
});

refresh();
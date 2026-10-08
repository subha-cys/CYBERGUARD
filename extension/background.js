const CONTENT_SCRIPT_ID = 'cyberguard-page-inspector';
const API_BASE = 'http://127.0.0.1:8765';
const RISK_THRESHOLD = 50;

async function setStatus(status) {
  await chrome.storage.local.set({ monitorStatus: status, statusUpdatedAt: Date.now() });
}

async function registerInspector() {
  const registered = await chrome.scripting.getRegisteredContentScripts({ ids: [CONTENT_SCRIPT_ID] });
  if (!registered.length) {
    await chrome.scripting.registerContentScripts([{
      id: CONTENT_SCRIPT_ID,
      matches: ['http://*/*', 'https://*/*'],
      js: ['content.js'],
      runAt: 'document_idle',
      persistAcrossSessions: true
    }]);
  }
}

async function enableMonitoring() {
  if (!await chrome.permissions.contains({ origins: ['<all_urls>'] })) {
    throw new Error('Website access permission is required to monitor navigation.');
  }
  await registerInspector();
  await chrome.storage.local.set({ monitoringEnabled: true });
  await setStatus('Monitoring is on');

  const tabs = await chrome.tabs.query({});
  for (const tab of tabs) {
    if (tab.id && /^https?:/.test(tab.url || '')) {
      chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] }).catch(() => {});
    }
  }
}

async function disableMonitoring() {
  await chrome.storage.local.set({ monitoringEnabled: false });
  await chrome.scripting.unregisterContentScripts({ ids: [CONTENT_SCRIPT_ID] }).catch(() => {});
  await chrome.permissions.remove({ origins: ['<all_urls>'] });
  await chrome.action.setBadgeText({ text: '' });
  await setStatus('Monitoring is off');
}

async function inspectPage(message, sender) {
  const { monitoringEnabled } = await chrome.storage.local.get('monitoringEnabled');
  const senderUrl = sender.tab?.url || '';
  if (!monitoringEnabled || !sender.tab?.id || !/^https?:/.test(senderUrl)) return;
  if (message.url !== senderUrl || typeof message.html_content !== 'string' || message.html_content.length > 16000) return;

  try {
    const response = await fetch(`${API_BASE}/api/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: 'url',
        url: message.url,
        html_content: message.html_content,
        asset_sensitivity: 'medium'
      })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `Local service returned ${response.status}`);

    const riskScore = Number(result.risk_score) || 0;
    await chrome.storage.local.set({
      monitorStatus: riskScore >= RISK_THRESHOLD ? 'Threat indicators found' : 'Last page checked',
      lastScan: {
        url: message.url,
        title: String(message.title || '').slice(0, 160),
        riskScore,
        riskLevel: result.risk_level || result.risk?.severity || 'low',
        threat: result.threat_category || result.fusion?.threat || 'undetermined',
        checkedAt: Date.now()
      }
    });
    await chrome.action.setBadgeBackgroundColor({ color: '#bd343d' });
    await chrome.action.setBadgeText({ text: riskScore >= RISK_THRESHOLD ? '!' : '' });
    await chrome.action.setTitle({ title: riskScore >= RISK_THRESHOLD
      ? `CYBERGUARD: elevated risk (${riskScore}/100)`
      : 'CYBERGUARD: page checked' });
  } catch (error) {
    await setStatus(`Local service unavailable: ${error.message}`);
  }
}

chrome.runtime.onInstalled.addListener(async () => {
  const current = await chrome.storage.local.get('monitoringEnabled');
  if (current.monitoringEnabled !== true) {
    await chrome.storage.local.set({ monitoringEnabled: false });
  } else {
    await enableMonitoring().catch(error => setStatus(`Monitoring could not resume: ${error.message}`));
  }
});

chrome.runtime.onStartup.addListener(async () => {
  const { monitoringEnabled } = await chrome.storage.local.get('monitoringEnabled');
  if (monitoringEnabled) {
    await enableMonitoring().catch(error => setStatus(`Monitoring could not resume: ${error.message}`));
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'CYBERGUARD_PAGE_SUMMARY') {
    inspectPage(message, sender).then(() => sendResponse({ ok: true }));
    return true;
  }
  if (message.type === 'CYBERGUARD_SET_MONITORING') {
    const operation = message.enabled ? enableMonitoring() : disableMonitoring();
    operation.then(() => sendResponse({ ok: true })).catch(error => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message.type === 'CYBERGUARD_GET_STATE') {
    chrome.storage.local.get(['monitoringEnabled', 'monitorStatus', 'lastScan']).then(state => {
      sendResponse({ ...state, serviceUrl: API_BASE });
    });
    return true;
  }
});
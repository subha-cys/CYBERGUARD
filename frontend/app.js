const state={view:'analysis',analysis:null,analysisKind:'email',busy:false,demoMode:null};
const liveVoice={stream:null,context:null,processor:null,mute:null,interval:null,chunks:[],samples:0,busy:false,windows:0,session:0};
const awarenessTips=[
  {category:'VERIFY OUTSIDE THE MESSAGE',text:'If a request asks for money or credentials, contact the person through a number or app you already trust—not the details in the message.',sticker:'CHECK TWICE'},
  {category:'ONE-TIME CODES ARE FOR YOU',text:'Never read a sign-in code to someone who contacted you. Enter it only in the service’s app or site that you opened yourself.',sticker:'KEEP IT PRIVATE'},
  {category:'QR CODES HIDE THE DESTINATION',text:'Preview the full web address before opening a QR link, then check the domain for misspellings or lookalikes.',sticker:'LOOK BEFORE YOU TAP'},
  {category:'CALLER ID CAN BE FAKED',text:'A familiar name or number on your screen is not proof of identity. Hang up and call back using a trusted contact.',sticker:'CALL BACK SAFELY'},
  {category:'URGENCY IS A SIGNAL, NOT PROOF',text:'Pressure to act immediately is a reason to pause and verify. Urgency by itself does not prove a message is fraudulent.',sticker:'PAUSE FIRST'},
  {category:'READ THE ACTUAL DOMAIN',text:'A brand name elsewhere in a URL can mislead. Check the hostname immediately before the first slash after “://”.',sticker:'SPOT THE DOMAIN'},
  {category:'CHOOSE STRONGER SIGN-IN',text:'Where available, use a passkey or security key. Never approve a sign-in prompt you did not initiate.',sticker:'LOCK IT DOWN'},
  {category:'AI VOICES CAN SOUND REAL',text:'A familiar-sounding voice is not proof. Verify unexpected requests for money or secrets through a separate trusted channel.',sticker:'TRUST, THEN VERIFY'}
];
let awarenessIndex=-1;
const root=document.getElementById('viewRoot');
function setTheme(theme){
  const selected=theme==='light'?'light':'vampire';
  document.documentElement.dataset.theme=selected;
  const button=document.getElementById('themeToggle');
  if(button){
    const light=selected==='light';
    button.innerHTML=`${light?'☾':'☼'} <span>${light?'Dark':'Light'} theme</span>`;
    button.setAttribute('aria-label',`Switch to ${light?'dark vampire red':'light'} theme`);
    button.setAttribute('aria-pressed',String(light));
  }
  try{localStorage.setItem('cyberguard-theme',selected)}catch{}
}
try{setTheme(localStorage.getItem('cyberguard-theme')||'vampire')}catch{setTheme('vampire')}
const revealObserver='IntersectionObserver'in window?new IntersectionObserver(entries=>entries.forEach(entry=>{
  if(entry.isIntersecting){entry.target.classList.add('is-visible');revealObserver.unobserve(entry.target)}
}),{threshold:.08}):null;
function observeScrollReveal(){
  if((root.querySelector('.analysis-layout')||root.querySelector('#analysisForm'))&&!root.querySelector('.awareness-dock'))root.insertAdjacentHTML('beforeend',awarenessWidgetMarkup());
  const resultRoot=document.getElementById('analysisResult');
  const learning=state.analysis?.learning;
  if(resultRoot&&learning?.sample_id&&!resultRoot.querySelector('.learning-panel')){
    resultRoot.insertAdjacentHTML('beforeend',learningPanelMarkup(learning));
    refreshLearningSummary();
  }
  if(!revealObserver)return;
  root.querySelectorAll(':scope > *:not(.scroll-reveal)').forEach(element=>{
    element.classList.add('scroll-reveal');
    revealObserver.observe(element);
  });
}
if('MutationObserver'in window)new MutationObserver(observeScrollReveal).observe(root,{childList:true,subtree:true});
observeScrollReveal();
const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const human=value=>String(value??'—').replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
const shortId=value=>value?String(value).slice(0,8).toUpperCase():'—';
const fmtTime=value=>{if(!value)return'—';const d=new Date(value);return Number.isNaN(+d)?escapeHtml(value):d.toLocaleString([], {month:'short',day:'2-digit',hour:'2-digit',minute:'2-digit'})};
const severityColor={critical:'#fa777d',high:'#f17b78',medium:'#e9b85f',low:'#56dfae'};
const endpoint=async(path,options={})=>{const response=await fetch(`${window.CYBERGUARD_API_BASE||''}${path}`,{headers:{'Content-Type':'application/json',...(options.headers||{})},...options});let data;try{data=await response.json()}catch{throw new Error('The analysis service returned an unreadable response.')}if(!response.ok)throw new Error(data.error||`Request failed (${response.status})`);return data};
function chooseAwarenessTip(){let previous=awarenessIndex;if(previous<0){try{previous=Number(localStorage.getItem('cyberguard-awareness-tip'))}catch{previous=-1}}let index=Math.floor(Math.random()*awarenessTips.length);if(awarenessTips.length>1&&index===previous)index=(index+1)%awarenessTips.length;awarenessIndex=index;try{localStorage.setItem('cyberguard-awareness-tip',String(index))}catch{}return awarenessTips[index]}
function awarenessWidgetMarkup(){const tip=chooseAwarenessTip();return `<aside class="awareness-dock" aria-label="Cyber safety awareness tip"><div class="awareness-sticker" id="awarenessSticker" aria-hidden="true">${tip.sticker}</div><div class="awareness-doodle awareness-doodle-shield" aria-hidden="true"><svg viewBox="0 0 64 72" fill="none"><path d="M32 4 55 13v19c0 16-9 27-23 36C18 59 9 48 9 32V13L32 4Z" stroke="currentColor" stroke-width="2.5"/><path d="m21 34 7 7 15-17" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="53" cy="8" r="2" fill="currentColor"/></svg></div><div class="awareness-kicker"><span class="awareness-spark" aria-hidden="true">✳</span> FIELD NOTE <span class="awareness-count" id="awarenessCount">${String(awarenessIndex+1).padStart(2,'0')} / ${String(awarenessTips.length).padStart(2,'0')}</span></div><h2 class="awareness-title" id="awarenessTitle">${tip.category}</h2><p class="awareness-copy" id="awarenessCopy">${tip.text}</p><button class="awareness-next" type="button" data-action="next-awareness" aria-label="Show another cyber safety tip">Another tip <span aria-hidden="true">↗</span></button><span class="awareness-doodle awareness-doodle-star" aria-hidden="true">✦</span></aside>`}
function rotateAwarenessTip(){const tip=chooseAwarenessTip();const title=document.getElementById('awarenessTitle');const copy=document.getElementById('awarenessCopy');const count=document.getElementById('awarenessCount');const sticker=document.getElementById('awarenessSticker');if(!title||!copy||!count||!sticker)return;title.textContent=tip.category;copy.textContent=tip.text;sticker.textContent=tip.sticker;count.textContent=`${String(awarenessIndex+1).padStart(2,'0')} / ${String(awarenessTips.length).padStart(2,'0')}`}
function learningPanelMarkup(learning){const modality=learning.modality;const authenticLabel=modality==='audio'?'Human voice':'Authentic';const syntheticLabel=modality==='audio'?'AI-generated voice':'Synthetic';return `<section class="panel learning-panel" aria-label="Review this example for local model learning"><div class="panel-head"><div><div class="panel-title">Local learning memory</div><div class="panel-subtitle">FEATURES ONLY · AWAITING YOUR VERIFIED LABEL</div></div><span class="tag medium">NOT YET LEARNED</span></div><div class="panel-body"><p class="learning-copy">This analysis saved numeric ${escapeHtml(modality)} features on this device only—not the original file or its contents. The model will not learn from its own prediction; confirm the real-world label to include this example.</p><label class="field-label" for="learningGroup">SOURCE GROUP · REUSE FOR RELATED EXAMPLES</label><input id="learningGroup" class="field learning-group" maxlength="200" placeholder="e.g. speaker-04 or source-set-02" autocomplete="off"><div class="learning-actions"><button class="button ghost small" type="button" data-learning-label="authentic">${escapeHtml(authenticLabel)}</button><button class="button ghost small" type="button" data-learning-label="synthetic">${escapeHtml(syntheticLabel)}</button></div><div class="learning-status" id="learningStatus" role="status">Use a consistent pseudonymous group for samples from the same speaker, source, or series. Training needs at least 20 confirmed examples per label across 8 distinct groups.</div><div class="learning-counts" id="learningCounts">Loading local memory totals…</div><button class="learning-clear" type="button" data-learning-clear>Clear saved examples</button><span class="learning-clear-note">Clearing removes saved examples; any already-promoted model remains active.</span></div></section>`}
async function refreshLearningSummary(){const target=document.getElementById('learningCounts');if(!target)return;try{const data=await endpoint('/api/learning');const counts=data.examples?.[state.analysis?.learning?.modality]||{};target.textContent=`${counts.authentic||0} authentic · ${counts.synthetic||0} synthetic · ${counts.groups||0} source groups · ${counts.pending||0} awaiting review`}catch(error){target.textContent=`Could not load local memory totals: ${error.message}`}}
document.addEventListener('click',async event=>{
  const labelButton=event.target.closest('[data-learning-label]');
  if(labelButton){
    const learning=state.analysis?.learning;
    const group=document.getElementById('learningGroup')?.value.trim();
    const status=document.getElementById('learningStatus');
    if(!learning?.sample_id||!status)return;
    if(!group){status.textContent='Enter a pseudonymous source group before confirming the label.';document.getElementById('learningGroup')?.focus();return}
    const buttons=document.querySelectorAll('[data-learning-label]');
    buttons.forEach(button=>button.disabled=true);
    status.textContent='Saving verified label and checking whether the reviewed set can safely improve the model…';
    try{
      const response=await endpoint(`/api/learning/${encodeURIComponent(learning.sample_id)}/label`,{method:'PATCH',body:JSON.stringify({label:labelButton.dataset.learningLabel,group_id:group})});
      const training=response.training||{};
      state.analysis.learning.status='reviewed';
      status.textContent=training.message||'Label saved to local reviewed memory.';
      const panel=labelButton.closest('.learning-panel');
      panel?.querySelectorAll('[data-learning-label]').forEach(button=>button.remove());
      const badge=panel?.querySelector('.tag');
      if(badge){badge.className='tag low';badge.textContent='REVIEWED'}
      if(training.promoted)toast('Reviewed examples improved the held-out score; the local model was updated.');
      else if(training.status==='not_improved')toast('Feedback saved. The active model was kept because the candidate did not pass the improvement check.');
      await refreshLearningSummary();
    }catch(error){
      status.textContent=`Could not save this review: ${error.message}`;
      buttons.forEach(button=>button.disabled=false);
    }
    return;
  }
  if(event.target.closest('[data-learning-clear]')){
    if(!window.confirm('Clear all locally saved learning examples? Any promoted model will remain active.'))return;
    const status=document.getElementById('learningStatus');
    try{
      await endpoint('/api/learning',{method:'DELETE'});
      if(status)status.textContent='Saved examples cleared from local memory. The active model was not removed.';
      document.querySelectorAll('.learning-panel [data-learning-label]').forEach(button=>button.disabled=true);
      await refreshLearningSummary();
    }catch(error){if(status)status.textContent=`Could not clear local memory: ${error.message}`}
  }
});
document.addEventListener('click',event=>{if(event.target.closest('[data-action="next-awareness"]'))rotateAwarenessTip()});
function toast(message){const el=document.getElementById('toast');el.textContent=message;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2600)}
function setView(view){stopLiveVoice();state.view=view;state.analysis=null;state.demoMode=null;document.querySelectorAll('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.view===view));document.getElementById('pageLabel').textContent={dashboard:'Overview',analysis:'New analysis',incidents:'Incident queue'}[view]||'Overview';render()}
function heading(eyebrow,title,description,action=''){return `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${description}</p></div>${action}</div>`}
function severityTag(value){const key=String(value||'low').toLowerCase();return `<span class="tag ${escapeHtml(key)}">${escapeHtml(key.toUpperCase())}</span>`}
function incidentContext(incident){const input=incident.input_summary||{};return [human(input.type||'Analysis'),input.sender,input.subject,input.target,input.filename].filter(Boolean).join(' · ')}
function incidentRows(items){if(!items?.length)return `<tr><td colspan="8"><div class="empty-state">No live analysis incidents yet. Qualifying findings from real scans will be saved here.</div></td></tr>`;return items.map(x=>`<tr><td class="mono incident-id">CG-${shortId(x.incident_id)}</td><td>${escapeHtml(incidentContext(x))}</td><td>${escapeHtml(human(x.threat))}</td><td>${severityTag(x.severity)}</td><td class="mono">${x.risk_score}<span style="color:#64737e">/100</span></td><td>${fmtTime(x.timestamp)}</td><td><span class="tag ${escapeHtml(x.status)}">${escapeHtml(human(x.status))}</span></td><td>${escapeHtml(x.recommended_response?.[0]?.action?human(x.recommended_response[0].action):'Review indicators')}</td></tr>`).join('')}
async function renderDashboard(){root.innerHTML=`<div class="loading"><span class="spinner"></span>Loading operational metrics…</div>`;try{const d=await endpoint('/api/dashboard');document.getElementById('navIncidentCount').textContent=d.active_incidents;const severity=d.severity_distribution,total=Math.max(1,...Object.values(severity));const threatRows=Object.entries(d.threat_categories).sort((a,b)=>b[1]-a[1]);root.innerHTML=`${heading('LIVE OPERATIONS','Threat intelligence overview','Live counts and incidents generated by the CYBERGUARD analysis pipeline.',`<div class="page-heading-actions"><a class="button complaint-shortcut" href="https://cybercrime.gov.in/Webform/Crime_AuthoLogin.aspx" target="_blank" rel="noopener noreferrer">Register complaint ↗</a><button class="button" data-action="go-analysis">＋ &nbsp;Run analysis</button></div>`)}
  <div class="metrics-grid"><div class="metric-card"><div class="metric-label">Total analyses</div><div class="metric-value">${d.total_analyses.toLocaleString()}</div><div class="metric-foot">actual backend runs</div></div><div class="metric-card"><div class="metric-label">Active incidents</div><div class="metric-value ${d.active_incidents?'metric-accent':''}">${d.active_incidents.toString().padStart(2,'0')}</div><div class="metric-foot">open · acknowledged · investigating</div></div><div class="metric-card"><div class="metric-label">Mean processing time</div><div class="metric-value">${Number(d.average_processing_ms).toFixed(1)}<small style="font:11px var(--mono);color:#84919b"> ms</small></div><div class="metric-foot">measured end-to-end</div></div><div class="metric-card"><div class="metric-label">Detectors ready</div><div class="metric-value metric-accent">${d.detector_status.filter(x=>x.status==='ready').length}<small style="font:11px var(--mono);color:#84919b"> / ${d.detector_status.length}</small></div><div class="metric-foot">including available models</div></div><div class="metric-card"><div class="metric-label">Incident threshold</div><div class="metric-value">50<span style="font:11px var(--mono);color:#84919b"> /100</span></div><div class="metric-foot">configured risk policy</div></div></div>
  <div class="dashboard-grid"><section class="panel"><div class="panel-head"><div class="panel-title">Risk severity distribution</div><div class="panel-subtitle">ANALYSES · ALL TIME</div></div><div class="panel-body"><div class="severity-bars">${['critical','high','medium','low'].map(k=>`<div class="severity-row"><div class="severity-name"><i class="severity-dot" style="background:${severityColor[k]}"></i>${k}</div><div class="bar-track"><div class="bar-fill" style="width:${severity[k]===0?0:Math.max(4,severity[k]/total*100)}%;background:${severityColor[k]}"></div></div><div class="severity-count">${severity[k]}</div></div>`).join('')}</div></div></section>
  <section class="panel"><div class="panel-head"><div class="panel-title">Threat categories</div><div class="panel-subtitle">FUSED CLASSIFICATIONS</div></div><div class="panel-body"><div class="threat-list">${threatRows.length?threatRows.map(([k,v])=>`<div class="threat-row"><span>${escapeHtml(human(k))}</span><b>${v}</b></div>`).join(''):`<div class="threat-empty">No analyses recorded yet.</div>`}</div></div></section></div>
  <div class="dashboard-grid"><section class="panel table-panel"><div class="panel-head"><div><div class="panel-title">Recent live incidents</div><div class="panel-subtitle" style="margin-top:4px">Real analyses · newest first · demos excluded</div></div><button class="button ghost small" data-action="go-incidents">Open queue&nbsp; ↗</button></div><div class="table-scroll"><table class="data-table"><thead><tr><th>Incident ID</th><th>Input</th><th>Threat</th><th>Severity</th><th>Risk</th><th>Timestamp</th><th>Status</th><th>Recommended action</th></tr></thead><tbody>${incidentRows(d.recent_incidents)}</tbody></table></div></section>
  <section class="panel"><div class="panel-head"><div class="panel-title">Detector status</div><div class="panel-subtitle">RUNTIME REGISTRY</div></div><div class="panel-body"><div class="model-list">${d.detector_status.map(x=>`<div class="model-item"><b><i class="ready-dot ${x.status==='ready'?'':'unavailable-dot'}"></i>${escapeHtml(x.name)}</b><span>${escapeHtml(x.version)} · ${escapeHtml(x.status)}</span></div>`).join('')}</div><div class="explain-label">Model versions</div><div class="model-list">${Object.entries(d.model_versions).map(([k,v])=>`<div class="model-item"><b>${escapeHtml(human(k))}</b><span>${escapeHtml(v)}</span></div>`).join('')}</div></div></section></div>
  <div class="panel-subtitle" style="text-align:right">METRICS UPDATED ${fmtTime(d.updated_at)} · SCORES AND EVIDENCE ARE BACKEND RESULTS</div>`}catch(e){root.innerHTML=`${heading('SERVICE STATUS','Dashboard unavailable','Could not retrieve live metrics.')}<div class="error-box">${escapeHtml(e.message)}</div>`}}
function analysisForm(){const kind=state.analysisKind;const tabs=[['email','Email'],['sms','SMS / Smishing'],['social_media','Social Media'],['qr_code','QR Code / Quishing'],['url','URL inspection'],['website','Website / HTML'],['login','Login event'],['image','Image'],['audio','Audio'],['video','Video']];let fields='';if(kind==='email')fields=`<div class="field-wrap"><label class="field-label" for="text">MESSAGE BODY</label><textarea class="field" id="text" required placeholder="Paste email content (URLs within text will be automatically extracted and scanned)…"></textarea></div><div class="field-row"><div class="field-wrap"><label class="field-label" for="sender">SENDER (OPTIONAL)</label><input class="field" id="sender" placeholder="Display Name &lt;alert@bank-security.com&gt;"></div><div class="field-wrap"><label class="field-label" for="emailUrl">TARGET / LINK URL (OPTIONAL)</label><input class="field" id="emailUrl" placeholder="https://example.org/verify"></div></div><div class="form-note">URLs in the message body are automatically extracted and scanned by the unified URL engine.</div>`;else if(kind==='sms'||kind==='social_media')fields=`<div class="field-wrap"><label class="field-label" for="text">${kind==='sms'?'SMS / TEXT MESSAGE':'SOCIAL MEDIA MESSAGE'}</label><textarea class="field" id="text" required placeholder="Paste message body (e.g., USPS Notice: Delivery on hold. Reschedule at https://…)..."></textarea></div><div class="field-row"><div class="field-wrap"><label class="field-label" for="sender">SENDER PHONE / HANDLE (OPTIONAL)</label><input class="field" id="sender" placeholder="${kind==='sms'?'+1-800-555-0199':'@support_desk'}"></div><div class="field-wrap"><label class="field-label" for="emailUrl">EXTRACTED URL (OPTIONAL)</label><input class="field" id="emailUrl" placeholder="https://…"></div></div><div class="form-note">Analyzes urgency language, credential/OTP requests, financial lures, and suspicious links.</div>`;else if(kind==='qr_code')fields=`<div class="field-wrap"><label class="field-label" for="qrUrl">DECODED QR-CODE DESTINATION URL</label><input class="field" id="qrUrl" required placeholder="https://micros0ft-authenticator.xyz/mfa"></div><div class="field-wrap"><label class="field-label" for="qrText">QR-CODE CONTEXT / INSTRUCTIONS (OPTIONAL)</label><textarea class="field" id="qrText" style="min-height:90px" placeholder="e.g. Scan this QR code with your mobile camera to verify MFA settings immediately…"></textarea></div><div class="form-note">Evaluates destination URL, homoglyphs, brand spoofing, and quishing social-engineering lures.</div>`;else if(kind==='url')fields=`<div class="field-wrap"><label class="field-label" for="url">URL TO INSPECT</label><input class="field" id="url" required placeholder="https://example.org/path"></div><div class="field-wrap"><label class="field-label" for="displayedUrl">DISPLAYED / ANCHOR TEXT URL (OPTIONAL)</label><input class="field" id="displayedUrl" placeholder="e.g. https://paypal.com/signin"></div><div class="form-note">Evaluates typosquatting, brand similarity, homoglyphs, entropy, suspicious TLDs, and path depth. Safe offline inspection.</div>`;else if(kind==='website')fields=`<div class="field-wrap"><label class="field-label" for="webUrl">WEBSITE URL</label><input class="field" id="webUrl" required placeholder="https://login.example-portal.com/auth"></div><div class="field-wrap"><label class="field-label" for="webDisplayedUrl">DISPLAYED BRAND / URL (OPTIONAL)</label><input class="field" id="webDisplayedUrl" placeholder="e.g. https://microsoft.com"></div><div class="field-wrap"><label class="field-label" for="htmlContent">HTML SOURCE / DOM CONTENT</label><textarea class="field" id="htmlContent" style="min-height:160px;font-family:var(--mono);font-size:11px" placeholder="Paste HTML markup to inspect for fake login forms, credential fields, external form actions, and brand impersonation…"></textarea></div><div class="form-note">Safe structural DOM analysis. No scripts or external requests are executed.</div>`;else if(kind==='login')fields=`<div class="field-wrap"><label class="field-label" for="loginJson">LOGIN EVENT · JSON</label><textarea class="field" id="loginJson" required style="min-height:228px;font-family:var(--mono);font-size:11px">{
  "user_id": "synthetic-user-01",
  "timestamp": "2026-01-01T03:00:00Z",
  "ip": "192.0.2.30",
  "country": "ZZ",
  "device_id": "new-device",
  "failed_attempts": 7,
  "successful_login": true
}</textarea></div><div class="form-note">Use authorized events only. User identifiers and history are not enriched.</div>`;else fields=`<div class="field-wrap"><label class="field-label">${kind.toUpperCase()} MEDIA</label><div class="upload-zone"><div style="margin-bottom:10px">Choose a file for actual local metadata assessment</div><input id="mediaFile" type="file" required accept="${kind==='image'?'image/*':kind==='audio'?'audio/*':'video/*'}"><div id="uploadName" class="upload-name">${kind.toUpperCase()} · MAX 100 MiB</div></div></div><div class="limitation">Media metadata is not proof of a deepfake. Inconclusive results will explicitly state that manipulation cannot be determined from available evidence.</div>`;
  if(['image','audio','video'].includes(kind))fields+=`<div class="learning-disclosure">After analysis, numeric media features are stored locally for optional review-based learning. Original files are not retained; demos and live microphone windows are not added to memory.</div>`;
  return `<section class="panel form-panel"><div class="tabs">${tabs.map(([key,label])=>`<button type="button" class="tab ${kind===key?'active':''}" data-kind="${key}">${label}</button>`).join('')}</div><form id="analysisForm">${fields}<div class="form-note">Asset sensitivity is automatically inferred from inspectable content. Media that cannot be inspected for sensitive contents defaults to medium.</div><button class="button" id="submitAnalysis" type="submit">Analyze with CYBERGUARD&nbsp; →</button></form></section>`}
function demoPrefillNotice(){return state.demoMode?`<div class="demo-prefill-notice" role="status">SYNTHETIC DEMO INPUT · ${escapeHtml(state.demoMode.label)} · NOT A REAL INCIDENT</div>`:''}
function renderAnalysis(){stopLiveVoice();root.innerHTML=`${heading('DETECTOR WORKSPACE','New analysis','Submit an authorized artifact or event. Every result is produced by the live backend.',`<button class="button ghost" type="button" data-action="toggle-demos" aria-expanded="false">▷ &nbsp;Demo scenarios</button>`)}
  ${demoPickerMarkup()}${demoPrefillNotice()}<div class="analysis-layout"><div>${liveVoiceMarkup()}${analysisForm()}<div class="demo-disclaimer" style="margin-top:12px"><b style="color:#c9d7de">DATA HANDLING</b><br>Media uploads are held in a temporary local file for analysis and deleted afterward. Demo inputs are synthetic and excluded from the incident queue and dashboard totals.</div></div><div><div class="pipeline-caption">END-TO-END ANALYSIS CHAIN</div>${pipelineMarkup()}<div id="analysisResult">${state.analysis?resultMarkup(state.analysis):`<div class="result-placeholder"><strong>Awaiting an analysis</strong>Choose an input type and submit it to see real detector output, evidence, fusion, risk, explanation, and advisory response.</div>`}</div></div></div>`}
function pipelineMarkup(){const steps=['INPUT','AI/ML DETECTORS','SECURITY RULES','EVIDENCE','THREAT FUSION','RISK SCORE','EXPLANATION','RESPONSE'];return `<div class="pipeline">${steps.map((s,i)=>`${i?'<span class="pipe-arrow"></span>':''}<div class="pipe-step ${state.analysis?'done':''}"><span class="pipe-num">${state.analysis?'✓':String(i+1).padStart(2,'0')}</span>${s}</div>`).join('')}</div>`}
function riskLabel(item){const name=item.factor;const names={credential_request:'Credential request',suspicious_url:'Suspicious URL',detector_agreement:'Independent detector agreement',domain_anomaly:'Sender domain anomaly',urgency:'Urgency language',url_presence:'URL present',financial_request:'Financial request',impersonation_language:'Impersonation language',attachment_indicator:'Attachment indicator',repeated_failures:'Repeated login failures',successful_login_after_failures:'Success after repeated failures',unusual_hour_indicator:'Unusual login hour',isolation_forest_outlier:'Isolation Forest outlier',identity_claim_inconsistent:'Identity claim inconsistent',high_risk_request:'High-risk request',abnormal_context:'Abnormal context',independent_verification_absent:'Independent verification absent',manipulation_model_indicator:'Manipulation model indicator',asset_sensitivity:'Asset sensitivity',threat_base:'Threat category baseline'};return names[name]||human(name)}
function evidenceMarkup(items){if(!items?.length)return '<div class="empty-state" style="padding:12px">No evidence items were reported by the detectors.</div>';return items.map(e=>`<div class="evidence-card"><div class="evidence-indicator">${escapeHtml(human(e.indicator||e.type||'Evidence item'))}</div><div class="evidence-detail">${escapeHtml(e.detector||'')} · ${escapeHtml(typeof e.value==='object'?JSON.stringify(e.value):e.value??e.type??'Indicator observed')}</div></div>`).join('')}
function detectorMarkup(items){if(!items?.length)return '<div class="empty-state">No detector results.</div>';return items.map(d=>`<div class="detector-card"><div class="detector-top"><span class="detector-name">${escapeHtml(d.detector)}</span><span class="detector-class">${escapeHtml(human(d.classification))}</span></div><div class="detector-meta"><span>METHOD · ${escapeHtml(d.method||'—')}</span><span>VERSION · ${escapeHtml(d.detector_version||'—')}</span><span>MODEL · ${escapeHtml(d.model_version||'N/A')}</span><span class="confidence">CONFIDENCE · ${d.confidence==null?'Unavailable':`${(Number(d.confidence)*100).toFixed(1)}% (${escapeHtml(d.confidence_status||'reported')})`}</span></div><div class="detector-evidence"><b>Evidence:</b> ${d.evidence?.length?escapeHtml(d.evidence.map(e=>`${e.indicator||e.type}: ${typeof e.value==='object'?JSON.stringify(e.value):e.value??'observed'}`).join(' · ')):'No detector evidence reported.'}</div>${d.limitations?.length?`<div class="limitation"><b>Limitations</b><br>${d.limitations.map(x=>escapeHtml(x)).join('<br>')}</div>`:''}</div>`).join('')}
function resultMarkup(r){const f=r.fusion||{},risk=r.risk||{},exp=r.explanation||{},actions=r.response||[];const label=human(f.threat||'undetermined');const evidence=f.evidence||[];const contributors=risk.contributors||[];const voiceOrigin=r.voice_origin||f.voice_origin;const voiceLabel=voiceOrigin?({likely_ai_generated:'Likely AI-generated',likely_human:'Likely human',inconclusive:'Inconclusive'}[voiceOrigin.classification]||human(voiceOrigin.classification)):'';
  const pPhish=r.phishing_model_score_uncalibrated==null?null:Number(r.phishing_model_score_uncalibrated);const pUrl=r.malicious_url_indicator_score==null?null:Number(r.malicious_url_indicator_score);
  const pPhishDisplay=pPhish??0;const pUrlDisplay=pUrl??0;
  const pPhishColor=pPhishDisplay>=0.7?'#fa777d':pPhishDisplay>=0.35?'#e9b85f':'#56dfae';
  const pUrlColor=pUrlDisplay>=0.7?'#fa777d':pUrlDisplay>=0.35?'#e9b85f':'#56dfae';
  const reasons=exp.reasons?.length?exp.reasons:(exp.why||[]);
  return `<div class="threat-banner"><div><strong>${escapeHtml(label)}</strong><small>FUSION · ${escapeHtml(f.agreement||'no signal')} · ${f.supporting_detectors?.length||0} supporting detector(s)</small></div><div class="risk-number" style="color:${severityColor[risk.severity]||'#e8eef3'}">${risk.risk_score??0}<span> / 100</span></div></div>
  ${risk.asset_sensitivity_assessment?`<section class="panel result-section"><div class="panel-head"><div class="panel-title">Automatically inferred asset sensitivity</div><div class="panel-subtitle">${escapeHtml(human(risk.asset_sensitivity_assessment.level))}</div></div><div class="panel-body"><div class="limitation">${escapeHtml(risk.asset_sensitivity_assessment.reason)}</div>${risk.asset_sensitivity_assessment.indicators?.length?`<div class="panel-subtitle">DETECTED CATEGORIES · ${risk.asset_sensitivity_assessment.indicators.map(x=>escapeHtml(human(x))).join(' · ')}</div>`:''}</div></section>`:''}
  <div class="prob-grid">
    <div class="prob-card">
      <div class="prob-head"><span class="prob-label">Phishing model score · uncalibrated</span><span class="badge-prob" style="background:${pPhishColor}22;color:${pPhishColor};border:1px solid ${pPhishColor}55">${pPhish==null?'Unavailable':pPhish.toFixed(3)}</span></div>
      <div class="prob-val" style="color:${pPhishColor}">${pPhish==null?'—':pPhish.toFixed(3)}</div>
      <div class="prob-bar-track"><div class="prob-bar-fill" style="width:${Math.max(4,pPhishDisplay*100)}%;background:${pPhishColor}"></div></div>
    </div>
    <div class="prob-card">
      <div class="prob-head"><span class="prob-label">URL indicator score · uncalibrated</span><span class="badge-prob" style="background:${pUrlColor}22;color:${pUrlColor};border:1px solid ${pUrlColor}55">${pUrl==null?'Unavailable':pUrl.toFixed(3)}</span></div>
      <div class="prob-val" style="color:${pUrlColor}">${pUrl==null?'—':pUrl.toFixed(3)}</div>
      <div class="prob-bar-track"><div class="prob-bar-fill" style="width:${Math.max(4,pUrlDisplay*100)}%;background:${pUrlColor}"></div></div>
    </div>
  </div>
  ${voiceOrigin?`<section class="panel result-section"><div class="panel-head"><div class="panel-title">Voice origin assessment</div><div class="panel-subtitle">${voiceOrigin.method==='unvalidated_acoustic_heuristic'?'HEURISTIC':'LOCAL MODEL'} · NO CONFIDENCE SCORE</div></div><div class="panel-body"><strong>${escapeHtml(voiceLabel)}</strong><p class="limitation">${(voiceOrigin.limitations||[]).map(x=>escapeHtml(x)).join('<br>')}</p>${voiceOrigin.evidence?.length?`<div class="panel-subtitle">OBSERVED CUES · ${voiceOrigin.evidence.map(x=>escapeHtml(human(x))).join(' · ')}</div>`:''}</div></section>`:''}
  <section class="panel result-section"><div class="panel-head"><div class="panel-title">Risk assessment</div>${severityTag(risk.severity)}</div><div class="panel-body"><div class="panel-subtitle" style="margin-bottom:8px">TRANSPARENT CONTRIBUTORS · ${risk.policy_version||''}</div>${contributors.length?contributors.map(x=>`<div class="contributor"><span>${escapeHtml(riskLabel(x))}<small style="display:block;color:#71808a;margin-top:3px">${escapeHtml(x.reason||'')}</small></span><b>+${x.points}</b></div>`).join(''):'<div class="empty-state" style="padding:12px">No risk contributors. Score is 0.</div>'}<div style="height:8px"></div><div class="bar-track" style="height:8px"><div class="bar-fill" style="width:${Math.max(0,Math.min(100,risk.risk_score||0))}%;background:${severityColor[risk.severity]||'#56dfae'}"></div></div><div class="panel-subtitle" style="margin-top:8px">INCIDENT THRESHOLD · ${risk.incident_threshold??50}/100 · ${risk.incident_required?'INCIDENT CREATED':'NO INCIDENT REQUIRED'}</div></div></section>
  <section class="panel result-section"><div class="panel-head"><div class="panel-title">Evidence</div><div class="panel-subtitle">${evidence.length} ITEM(S) · FUSION OUTPUT</div></div><div class="panel-body">${evidenceMarkup(evidence)}</div></section>
  <section class="panel result-section"><div class="panel-head"><div class="panel-title">Detector transparency</div><div class="panel-subtitle">PER-DETECTOR OUTPUT</div></div><div class="panel-body">${detectorMarkup(f.detector_results||[])}</div></section>
  <section class="panel result-section"><div class="panel-head"><div class="panel-title">Explanation &amp; reasons</div><div class="panel-subtitle">STRUCTURED EVIDENCE GROUNDED</div></div><div class="panel-body"><div class="explainer"><b>${escapeHtml(exp.what||'')}</b><div class="explain-label">Observed indicators &amp; reasons</div><div class="reasons-list">${reasons.length?reasons.map(x=>`<div class="reason-bullet"><span>${escapeHtml(x)}</span></div>`).join(''):'<div class="reasons-empty">No suspicious indicators triggered.</div>'}</div>${exp.why?.length&&exp.why!==reasons?`<div class="explain-label">Detector findings</div>${exp.why.map(x=>`<div>• ${escapeHtml(x)}</div>`).join('')}`:''}<div class="explain-label">Limitations</div>${(exp.limitations||[]).map(x=>`<div>• ${escapeHtml(x)}</div>`).join('')||'None returned'}</div></div></section>
  <section class="panel result-section"><div class="panel-head"><div class="panel-title">Response recommendations</div><div class="panel-subtitle">ADVISORY ONLY · NO AUTOMATION</div></div><div class="panel-body">${actions.length?actions.map((x,i)=>`<div class="action-row"><span class="action-index">0${i+1}</span><div><strong>${escapeHtml(human(x.action))}</strong><p>${escapeHtml(x.rationale)}</p><span class="action-badges">${x.approval_required?'APPROVAL REQUIRED':'REVIEW'} · ${x.automatic_execution?'AUTOMATIC':'MANUAL'}</span></div></div>`).join(''):'<div class="empty-state" style="padding:12px">No response action recommended.</div>'}</div></section>
  ${r.incident?`<div class="demo-disclaimer" style="border-color:#684044;color:#ffc1c1">Incident created · CG-${shortId(r.incident.incident_id)} · ${escapeHtml(human(r.incident.status))} · persisted in the incident queue.</div>`:''}<details style="margin:8px 0;color:#8c9aa4;font-size:10px"><summary style="cursor:pointer">View submitted input</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere;color:#a9b7c0;background:#0c141c;padding:10px">${escapeHtml(JSON.stringify(r.input||{},null,2))}</pre></details><div class="panel-subtitle" style="text-align:right">END-TO-END PROCESSING · ${Number(r.processing_time_ms||0).toFixed(2)} ms</div>`}
function renderIncidents(){root.innerHTML=`${heading('CASE MANAGEMENT','Live incident queue','Real CyberGuard analyses are saved when risk reaches the incident threshold. Synthetic demo runs and older unverified records are excluded.')}
  <div class="metrics-grid" id="incidentMetrics"></div><section class="panel table-panel"><div class="panel-head"><div><div class="panel-title">Live analysis incidents</div><div class="panel-subtitle" style="margin-top:4px">Local SQLite records · source and input summary included</div></div><button class="button ghost small" data-action="refresh-incidents">↻ &nbsp;Refresh</button></div><div class="table-scroll"><table class="data-table"><thead><tr><th>Incident ID</th><th>Input</th><th>Threat</th><th>Severity</th><th>Risk</th><th>Timestamp</th><th>Status</th><th>Recommended action</th><th>Update</th></tr></thead><tbody id="incidentBody"><tr><td colspan="9"><div class="loading"><span class="spinner"></span>Loading incidents…</div></td></tr></tbody></table></div></section><div class="demo-disclaimer">Only actual analysis requests create incidents. Demo scenarios do not write to the incident queue. Raw message bodies are not copied into incident input summaries.</div>`;loadIncidents()}
async function loadIncidents(){try{const [d,queue]=await Promise.all([endpoint('/api/dashboard'),endpoint('/api/incidents')]),items=queue.incidents;document.getElementById('navIncidentCount').textContent=d.active_incidents;document.getElementById('incidentMetrics').innerHTML=`<div class="metric-card"><div class="metric-label">Live incidents</div><div class="metric-value">${items.length}</div><div class="metric-foot">qualifying real analyses</div></div><div class="metric-card"><div class="metric-label">Active</div><div class="metric-value">${d.active_incidents}</div><div class="metric-foot">not resolved</div></div><div class="metric-card"><div class="metric-label">Critical / high</div><div class="metric-value" style="color:var(--red)">${items.filter(x=>['critical','high'].includes(x.severity)).length}</div><div class="metric-foot">live incident queue</div></div>`;document.getElementById('incidentBody').innerHTML=items.length?items.map(x=>`<tr><td class="mono incident-id" title="${escapeHtml(x.incident_id)}">CG-${shortId(x.incident_id)}</td><td>${escapeHtml(incidentContext(x))}</td><td>${escapeHtml(human(x.threat))}</td><td>${severityTag(x.severity)}</td><td class="mono">${x.risk_score}/100</td><td>${fmtTime(x.timestamp)}</td><td><span class="tag ${escapeHtml(x.status)}">${escapeHtml(human(x.status))}</span></td><td>${escapeHtml(x.recommended_response?.[0]?.action?human(x.recommended_response[0].action):'Review indicators')}</td><td><select class="mini-select status-select" data-incident="${escapeHtml(x.incident_id)}"><option value="${escapeHtml(x.status)}">${escapeHtml(human(x.status))}</option>${['open','acknowledged','investigating','resolved'].filter(s=>s!==x.status).map(s=>`<option value="${s}">${human(s)}</option>`).join('')}</select></td></tr>`).join(''):`<tr><td colspan="9"><div class="empty-state">No qualifying live incidents yet. Submit a real email, link, login, or media analysis; findings at or above the configured threshold will be saved here.</div></td></tr>`}catch(e){document.getElementById('incidentBody').innerHTML=`<tr><td colspan="9"><div class="error-box">${escapeHtml(e.message)}</div></td></tr>`}}
const demos=[
  ['legitimate_url','DEMO 01','Legitimate URL & Website','Safe standard HTTPS domain with clean benign HTML content.','URL + WEBPAGE'],
  ['lookalike_domain','DEMO 02','Lookalike / Typosquatting Domain','Brand spoofing (paypa1-security.com) with displayed anchor mismatch.','URL LEXICAL'],
  ['suspicious_long_url','DEMO 03','Suspicious URL Structure','High entropy, path depth, IP address host, and nested URL redirect parameters.','URL LEXICAL'],
  ['fake_login_page','DEMO 04','Fake Login Page / Credential Theft','Cloned Microsoft login with external form action and OTP harvester fields.','WEBPAGE ANALYSIS'],
  ['phishing_email','DEMO 05','Urgent Credential Phishing Email','Synthetic urgent account suspension warning containing malicious link.','EMAIL · NLP + RULES'],
  ['sms_phishing','DEMO 06','SMS Smishing with Short Link','Delivery parcel fee urgency text with suspicious top-level domain link.','SMS · SMISHING RULES'],
  ['qr_code_phishing','DEMO 07','QR Code / Quishing MFA Lure','Lure directing mobile camera scan to typosquatted MFA login domain.','QR CODE · QUISHING RULES'],
  ['account_takeover','DEMO 08','Anomalous Account Login','Synthetic event with repeated failures, unusual hour, and success.','LOGIN · RULES + IFOREST'],
  ['multimedia_impersonation','DEMO 09','Multimedia Context Checks','Synthetic image metadata plus inconsistent contextual risk indicators.','IMAGE + CONTEXT']
];
const demoInputs={
  legitimate_url:{type:'url',url:'https://example.org/about'},
  lookalike_domain:{type:'url',url:'https://paypa1-security.com/signin',displayedUrl:'https://paypal.com/signin'},
  suspicious_long_url:{type:'url',url:'http://192.0.2.14/login/update/account/verify?token=3f89a2&session=%2F%3F%26auth%3Dtrue&redirect=http%3A%2F%2Fupdate-now.xyz%2Fauth#login-credentials-secure-token-id-99887766554433221100'},
  fake_login_page:{type:'website',url:'http://192.0.2.55/microsoft/login',htmlContent:'<!DOCTYPE html><html><head><title>Sign in to your Microsoft account</title></head><body><h2>Sign in</h2><form action="http://198.51.100.88/collect" method="POST"><label>Email, phone, or Skype</label><input type="text" name="loginfmt"><label>Password</label><input type="password" name="passwd"><label>Security PIN / OTP</label><input type="text" name="mfa_otp"><button type="submit">Sign in</button></form></body></html>'},
  phishing_email:{type:'email',rawMessage:'From: IT Support <alert@example.org>\nSubject: URGENT: Mailbox locked\n\nURGENT: Your mailbox is locked due to policy violations. Verify your account password now within 24 hours at http://192.0.2.44/verify to avoid suspension.'},
  sms_phishing:{type:'sms',text:'USPS Notice: Your package delivery is on hold due to an unpaid customs fee of $2.30. Reschedule delivery immediately at https://usps-parcel-redelivery.top/claim or reply STOP to cancel.',sender:'+1-800-555-0199'},
  qr_code_phishing:{type:'qr_code',text:'Security Warning: Scan the QR code below with your mobile camera to verify your MFA authenticator settings immediately: https://micros0ft-authenticator.xyz/mfa',url:'https://micros0ft-authenticator.xyz/mfa'},
  account_takeover:{type:'login',event:{user_id:'synthetic-user-demo',timestamp:'2026-01-01T03:00:00Z',ip:'192.0.2.30',country:'ZZ',device_id:'synthetic-new-device',failed_attempts:7,successful_login:true}},
  multimedia_impersonation:{type:'image',fixture:'synthetic_manipulated_image'},
  normal_image:{type:'image',fixture:'normal_image'},
  synthetic_manipulated_image:{type:'image',fixture:'synthetic_manipulated_image'},
  normal_audio:{type:'audio',fixture:'normal_audio'},
  synthetic_audio:{type:'audio',fixture:'synthetic_audio'},
  normal_video:{type:'video',fixture:'normal_video'},
  manipulated_video:{type:'video',fixture:'manipulated_video'}
};
const expandedDemoCards=[
  ...demos.map(([id,num,title,description,type])=>({id,num,title,description,type})),
  {id:'normal_image',num:'DEMO 10',title:'Synthetic Reference Image',description:'Local image fixture for the image authenticity detector.',type:'IMAGE · LOCAL FIXTURE'},
  {id:'synthetic_manipulated_image',num:'DEMO 11',title:'Synthetic Edited Image',description:'Safe generated image fixture with artificial editing indicators.',type:'IMAGE · LOCAL FIXTURE'},
  {id:'normal_audio',num:'DEMO 12',title:'Synthetic Reference Audio',description:'Generated WAV sample routed to the audio authenticity form.',type:'AUDIO · LOCAL FIXTURE'},
  {id:'synthetic_audio',num:'DEMO 13',title:'Synthetic Audio Anomalies',description:'Generated WAV sample routed to the audio authenticity form.',type:'AUDIO · LOCAL FIXTURE'},
  {id:'normal_video',num:'DEMO 14',title:'Synthetic Reference Video',description:'Generated AVI sample routed to the video authenticity form.',type:'VIDEO · LOCAL FIXTURE'},
  {id:'manipulated_video',num:'DEMO 15',title:'Synthetic Video Anomalies',description:'Generated AVI sample routed to the video authenticity form.',type:'VIDEO · LOCAL FIXTURE'}
];
function demoPickerMarkup(){return `<section id="demoPicker" class="panel demo-picker" hidden aria-label="Select a synthetic demo"><div class="panel-head"><div><div class="panel-title">Choose a demo input</div><div class="panel-subtitle">PREFILLS THE FORM ONLY · ANALYZE WHEN YOU ARE READY</div></div><button class="button ghost small" type="button" data-action="close-demos" aria-label="Close demo scenarios">Close</button></div><div class="demo-picker-grid">${expandedDemoCards.map(item=>`<button type="button" class="demo-picker-card" data-demo-select="${escapeHtml(item.id)}"><span class="demo-number">${item.num} / SYNTHETIC</span><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.description)}</span><small>${escapeHtml(item.type)}</small></button>`).join('')}</div><p class="demo-picker-note">Samples are synthetic. They are analyzed locally only after you press Analyze, and are not saved to incidents or dashboard totals.</p></section>`}
async function prefillDemo(demoId,button){
  const spec=demoInputs[demoId];
  const card=expandedDemoCards.find(item=>item.id===demoId);
  if(!spec||!card)return;
  if(button)button.disabled=true;
  state.view='analysis';
  state.analysis=null;
  state.analysisKind=spec.type;
  state.demoMode={id:demoId,label:card.title};
  document.querySelectorAll('.nav-item').forEach(item=>item.classList.toggle('active',item.dataset.view==='analysis'));
  document.getElementById('pageLabel').textContent='New analysis';
  renderAnalysis();
  document.getElementById('demoPicker').hidden=true;
  const fill=(id,value)=>{const field=document.getElementById(id);if(field)field.value=value};
  if(spec.rawMessage)fill('rawMessage',spec.rawMessage);
  if(spec.text)fill('text',spec.text);
  if(spec.sender)fill('sender',spec.sender);
  if(spec.url){
    fill(spec.type==='url'?'url':spec.type==='website'?'webUrl':spec.type==='qr_code'?'qrUrl':'emailUrl',spec.url);
  }
  if(spec.displayedUrl)fill('displayedUrl',spec.displayedUrl);
  if(spec.htmlContent)fill('htmlContent',spec.htmlContent);
  if(spec.type==='login')fill('loginJson',JSON.stringify(spec.event,null,2));
  if(spec.type==='qr_code')fill('qrText',spec.text);
  if(spec.fixture){
    try{
      const fixture=await endpoint(`/api/demo-fixture/${encodeURIComponent(spec.fixture)}`);
      if(typeof DataTransfer==='undefined')throw new Error('This browser cannot prefill a sample file. Select a local file to continue.');
      const bytes=Uint8Array.from(atob(fixture.content_base64),character=>character.charCodeAt(0));
      const file=new File([bytes],fixture.filename,{type:fixture.content_type||'application/octet-stream'});
      const transfer=new DataTransfer();
      transfer.items.add(file);
      const input=document.getElementById('mediaFile');
      input.files=transfer.files;
      input.dispatchEvent(new Event('change',{bubbles:true}));
    }catch(error){
      state.demoMode=null;
      toast(`Could not load synthetic media fixture: ${error.message}`);
      if(button)button.disabled=false;
      return;
    }
  }
  document.getElementById('analysisForm').scrollIntoView({behavior:'smooth',block:'center'});
  toast(`${card.title} loaded. Review it and press Analyze to run the pipeline.`);
}
function render(){if(state.view==='dashboard')renderDashboard();else if(state.view==='incidents')renderIncidents();else renderAnalysis()}
document.addEventListener('click',async event=>{
  const action=event.target.closest('[data-action]')?.dataset.action;
  if(action==='toggle-demos'||action==='close-demos'){
    event.preventDefault();event.stopImmediatePropagation();
    const picker=document.getElementById('demoPicker');
    const button=document.querySelector('[data-action="toggle-demos"]');
    if(picker){picker.hidden=action==='close-demos'?true:!picker.hidden;button?.setAttribute('aria-expanded',String(!picker.hidden));if(!picker.hidden)picker.scrollIntoView({behavior:'smooth',block:'start'})}
    return;
  }
  const selection=event.target.closest('[data-demo-select]');
  if(selection){event.preventDefault();event.stopImmediatePropagation();await prefillDemo(selection.dataset.demoSelect,selection)}
},true);
document.addEventListener('click',async e=>{const nav=e.target.closest('[data-view]');if(nav){setView(nav.dataset.view);return}const kind=e.target.closest('[data-kind]');if(kind){state.analysisKind=kind.dataset.kind;state.analysis=null;state.demoMode=null;renderAnalysis();return}const action=e.target.closest('[data-action]')?.dataset.action;if(action==='go-analysis')setView('analysis');if(action==='go-incidents')setView('incidents');if(action==='refresh-incidents')loadIncidents()});
document.addEventListener('click',async event=>{
  const action=event.target.closest('[data-action]')?.dataset.action;
  if(action==='copy-complaint'){
    const draft=document.getElementById('complaintDraft');
    if(!draft)return;
    try{await navigator.clipboard.writeText(draft.value);toast('Complaint draft copied.')}
    catch{draft.focus();draft.select();toast('Clipboard access unavailable. Select the draft and copy it manually.')}
  }else if(action==='download-complaint'){
    const draft=document.getElementById('complaintDraft');
    if(!draft)return;
    const blob=new Blob([draft.value],{type:'text/plain;charset=utf-8'});
    const url=URL.createObjectURL(blob);
    const link=document.createElement('a');
    link.href=url;
    link.download='cyberguard-cybercrime-complaint-draft.txt';
    link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    toast('Complaint draft downloaded.');
  }
});
document.getElementById('themeToggle').addEventListener('click',()=>{
  setTheme(document.documentElement.dataset.theme==='light'?'vampire':'light');
});
document.addEventListener('change',async e=>{if(e.target.matches('[data-incident]')){const select=e.target;const previous=select.querySelector('option')?.value;select.disabled=true;try{await endpoint(`/api/incidents/${encodeURIComponent(select.dataset.incident)}/status`,{method:'PATCH',body:JSON.stringify({status:select.value})});toast(`Incident ${human(select.value).toLowerCase()}.`);loadIncidents()}catch(err){toast(err.message);select.value=previous;select.disabled=false}}if(e.target.id==='mediaFile'){const label=document.getElementById('uploadName');if(label&&e.target.files[0])label.textContent=`${e.target.files[0].name} · ${(e.target.files[0].size/1024/1024).toFixed(2)} MiB`}});
document.addEventListener('submit',async e=>{if(e.target.id!=='analysisForm')return;e.preventDefault();if(state.busy)return;const kind=state.analysisKind;const payload={type:kind};if(state.demoMode){payload.synthetic_demo=true;payload.demo_id=state.demoMode.id}if(kind==='email'||kind==='sms'||kind==='social_media'){payload.text=document.getElementById('text').value;const s=document.getElementById('sender')?.value;if(s)payload.sender=s;const u=document.getElementById('emailUrl')?.value;if(u)payload.url=u}else if(kind==='qr_code'){payload.url=document.getElementById('qrUrl').value;const t=document.getElementById('qrText')?.value;if(t)payload.text=t}else if(kind==='url'){payload.url=document.getElementById('url').value;const d=document.getElementById('displayedUrl')?.value;if(d)payload.displayed_url=d}else if(kind==='website'){payload.url=document.getElementById('webUrl').value;const h=document.getElementById('htmlContent')?.value;if(h)payload.html_content=h;const d=document.getElementById('webDisplayedUrl')?.value;if(d)payload.displayed_url=d}else if(kind==='login'){try{payload.event=JSON.parse(document.getElementById('loginJson').value)}catch{toast('Login event must be valid JSON.');return}}else{const file=document.getElementById('mediaFile').files[0];if(!file)return;if(file.size>100*1024*1024){toast('Maximum media size is 100 MiB.');return}payload.filename=file.name;payload.content_base64=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('Could not read selected file.'));reader.readAsDataURL(file)})}state.busy=true;const btn=document.getElementById('submitAnalysis');btn.disabled=true;btn.innerHTML='<span class="spinner"></span> Running actual detectors…';try{const result=await endpoint(state.demoMode?'/api/analyze-demo':'/api/analyze',{method:'POST',body:JSON.stringify(payload)});state.analysis=result;document.getElementById('analysisResult').innerHTML=resultMarkup(result);document.querySelectorAll('.pipe-step').forEach(x=>x.classList.add('done'));if(!state.demoMode)document.getElementById('navIncidentCount').textContent=(await endpoint('/api/dashboard')).active_incidents;toast(state.demoMode?'Synthetic scenario analyzed; it was not saved to incidents.':'Analysis completed by the actual backend pipeline.')}catch(err){document.getElementById('analysisResult').innerHTML=`<div class="error-box">${escapeHtml(err.message)}</div>`}finally{state.busy=false;const b=document.getElementById('submitAnalysis');if(b){b.disabled=false;b.textContent='Analyze with CYBERGUARD →'}}});
function tick(){document.getElementById('clock').textContent=new Date().toLocaleString([], {hour:'2-digit',minute:'2-digit',timeZoneName:'short'})}setInterval(tick,30000);tick();

const standardAnalysisForm=analysisForm;
analysisForm=function(){
  if(state.analysisKind==='impersonation')return `<section class="panel form-panel"><div class="tabs">${[['message','Email scan'],['email','Email'],['sms','SMS / Smishing'],['social_media','Social Media'],['qr_code','QR Code / Quishing'],['url','URL inspection'],['website','Website / HTML'],['login','Login event'],['impersonation','Impersonation'],['image','Image'],['audio','Audio'],['video','Video']].map(([key,label])=>`<button type="button" class="tab ${key===state.analysisKind?'active':''}" data-kind="${key}">${label}</button>`).join('')}</div><form id="analysisForm"><div class="field-row"><div class="field-wrap"><label class="field-label" for="impSender">SENDER EMAIL</label><input class="field" id="impSender" type="email" required placeholder="notice@example.org"></div><div class="field-wrap"><label class="field-label" for="impDisplay">DISPLAY NAME (OPTIONAL)</label><input class="field" id="impDisplay" placeholder="Name shown by sender"></div></div><div class="field-row"><div class="field-wrap"><label class="field-label" for="impRole">CLAIMED ROLE (OPTIONAL)</label><input class="field" id="impRole" placeholder="e.g. manager, government, bank"></div><div class="field-wrap"><label class="field-label" for="impChannel">CHANNEL</label><select class="field" id="impChannel"><option value="email">Email</option><option value="whatsapp">WhatsApp</option><option value="sms">SMS</option><option value="telegram">Telegram</option><option value="social">Social media</option><option value="voice_call">Voice call</option></select></div></div><div class="field-wrap"><label class="field-label" for="impOrganization">CLAIMED ORGANIZATION (OPTIONAL)</label><input class="field" id="impOrganization" placeholder="Organization name"></div><div class="field-wrap"><label class="field-label" for="impText">MESSAGE BODY</label><textarea class="field" id="impText" required placeholder="Paste the message to assess sender identity and context…"></textarea></div><div class="field-row"><div class="field-wrap"><label class="field-label" for="impTrustedDomains">TRUSTED DOMAINS (OPTIONAL · COMMA SEPARATED)</label><input class="field" id="impTrustedDomains" placeholder="example.org, example.net"></div><div class="field-wrap"><label class="field-label" for="impOrgDomain">CLAIMED ORGANIZATION DOMAIN (OPTIONAL)</label><input class="field" id="impOrgDomain" placeholder="example.org"></div></div><div class="field-row"><div class="field-wrap"><label class="field-label" for="impAuth">EMAIL SPF / DKIM / DMARC RESULT (OPTIONAL)</label><select class="field" id="impAuth"><option value="">Not available</option><option value="pass">Pass</option><option value="fail">Fail</option><option value="softfail">Soft fail</option></select></div><div class="field-wrap"><label class="field-label" for="impPrior">PRIOR INTERACTIONS (OPTIONAL)</label><input class="field" id="impPrior" type="number" min="0" step="1" placeholder="Leave blank if unknown"></div></div><div class="form-note">Uses the existing identity rules and risk pipeline. Missing information is not treated as suspicious. Use only communications and contact data you are authorized to analyze.</div><button class="button" id="submitAnalysis" type="submit">Analyze with CYBERGUARD&nbsp; →</button></form></section>`;
  const markup=standardAnalysisForm();
  return markup;
};

const standardEmailResultMarkup=resultMarkup;
const emailAnalysisOptions=[
  ['email','Email'],['sms','SMS / Smishing'],['social_media','Social Media'],
  ['qr_code','QR Code / Quishing'],['url','URL inspection'],['website','Website / HTML'],
  ['login','Login event'],['image','Image'],
  ['audio','Audio'],['video','Video'],
];
const emailObjectives=values=>(values||[]).map(human).join(', ')||'No specific action detected';
function complaintMarkup(result){
  const risk=result.risk||{};
  const score=Number(result.risk_score??risk.risk_score??0);
  const threshold=Number(risk.incident_threshold??50);
  const severity=String(risk.severity||result.severity||'low').toLowerCase();
  const threat=String(result.threat_category||result.fusion?.threat||'').toLowerCase().replace(/[\s-]+/g,'_');
  const benignLabels=['','benign','legitimate','safe','normal','clean','undetermined','unknown','none','not_applicable','no_threat','not_threat','no_threat_detected','not_malicious','legitimate_url','safe_url','benign_url'];
  if(result.input?.synthetic_demo)return '';
  const flagged=Boolean(risk.incident_required)||score>=threshold||
    ['medium','high','critical'].includes(severity)||!benignLabels.includes(threat);
  if(!flagged)return '';

  const input=result.input||{};
  const detected=input.auto_detected||{};
  const incident=result.incident||{};
  const evidence=result.fusion?.evidence||[];
  const reasons=result.explanation?.reasons||result.explanation?.why||[];
  const urls=[...(detected.urls||[])];
  for(const value of [input.url,input.target_url,input.displayed_url]){
    if(value&&!urls.includes(value))urls.push(value);
  }
  const incidentId=incident.incident_id?`CG-${shortId(incident.incident_id)}`:'Not assigned';
  const observedAt=incident.timestamp||result.timestamp||'Please provide the approximate date and time.';
  const narrative=`I received a suspicious ${human(input.type||'digital communication')} on [enter the incident date and time]. The sender or account was reported as ${detected.sender||input.sender||'not identified'}. CyberGuard reported a possible ${human(result.threat_category||result.fusion?.threat||'suspicious activity')} and a risk score of ${score} out of 100. Indicators reported by the tool include ${(reasons.length?reasons:['suspicious activity requiring review']).join(', ')}. I have preserved the original communication and available supporting evidence. I request that this activity be reviewed and investigated. [Add what happened, any action you took, and any financial or account impact using verified facts.]`;
  const portalNarrative=narrative.replace(/[#$@^*`’'~|!]/g,'').replace(/\s+/g,' ').trim();
  const lines=[
    'FORMAL CYBERCRIME COMPLAINT — DRAFT FOR REVIEW',
    '',
    'To: The National Cyber Crime Reporting Portal, Government of India',
    'Subject: Request to investigate a suspected cybercrime incident',
    '',
    '1. COMPLAINANT DETAILS (complete before filing)',
    'Full name: [Enter your name]',
    'Mobile number and email: [Enter your contact details]',
    'State/Union Territory and city: [Enter location]',
    'Preferred language: [Enter language]',
    'Complainant identity document image: [Prepare separately for upload on the official portal; do not add ID numbers to this draft]',
    '',
    '2. INCIDENT DETAILS',
    `CyberGuard incident reference: ${incidentId}`,
    `Approximate incident date/time: ${observedAt}`,
    `Communication or event type: ${human(input.type||'Not detected')}`,
    `Sender/account identifier: ${detected.sender||input.sender||input.username||'Not detected in submitted material'}`,
    `Message subject: ${detected.subject||input.subject||'Not detected'}`,
    `Claimed organization: ${detected.claimed_organization||'Not detected'}`,
    `Claimed role: ${detected.claimed_role||'Not detected'}`,
    `Observed links or destinations: ${urls.length?urls.join(', '):'None detected'}`,
    `Attachment names: ${(detected.attachments||[]).join(', ')||'None detected'}`,
    `Suspected incident category: ${human(result.threat_category||result.fusion?.threat||'Suspicious activity')}`,
    `Automated risk assessment: ${score}/100 (${severity.toUpperCase()}) — advisory, not a verified finding`,
    '',
    'PORTAL INCIDENT DETAILS (the official portal checklist requests at least 200 characters; verify the current character restrictions before pasting):',
    portalNarrative,
    '',
    '3. INCIDENT DESCRIPTION',
    'I request that the authorities review the following suspicious communication or event. The details below were extracted from material I submitted to CyberGuard and should be checked against the original evidence:',
    `- Likely objective inferred by the tool: ${emailObjectives(detected.objectives)}`,
    ...(reasons.length?reasons.map(reason=>`- Reported indicator: ${String(reason)}`):[]),
    ...evidence.slice(0,12).map(item=>`- Evidence (${item.detector||'detector'}): ${String(item.indicator||item.type||'indicator')} — ${typeof item.value==='object'?JSON.stringify(item.value):String(item.value??'observed')}`),
    'Please describe what happened in your own words, including any interaction, money lost, account access, or threats: [Complete this section]',
    '',
    '4. FINANCIAL / ACCOUNT IMPACT',
    'Financial loss (amount and currency): [Enter amount, or state none/unknown]',
    'Bank, wallet, or merchant name (if applicable): [Enter details]',
    '12-digit transaction ID/UTR number (if applicable): [Enter details]',
    'Transaction date (if applicable): [Enter details]',
    'Affected account, service, or device: [Enter details]',
    'Any immediate safety or financial risk: [Enter details]',
    '',
    '5. EVIDENCE AVAILABLE',
    'Preserve the original email/message with full headers, screenshots, URLs, call/SMS logs, payment receipts, and relevant account notifications. Do not delete or alter original evidence. The portal checklist currently requests relevant evidence files (up to 10 MB each) and a complainant identity document image (up to 5 MB). Attach only evidence you are comfortable sharing with the authorities.',
    'Optional suspect details if known: phone number, email, social media handle, bank account, address, photograph, and other identifying documents. Do not guess missing details.',
    '',
    '6. REQUEST',
    'I request that this complaint be reviewed, the reported activity investigated, and appropriate action taken. I confirm that I will verify and correct this draft and provide supporting evidence before submission.',
    '',
    'IMPORTANT: This draft was generated from an automated advisory analysis. It is not proof of a crime, does not verify the sender or claims, and has not been submitted. Review every field, remove inaccurate information, and submit only through the official portal.'
  ];
  return `<section class="panel complaint-panel" aria-labelledby="complaintHeading"><div class="panel-head"><div><div class="panel-title" id="complaintHeading">Threat detected — prepare a complaint</div><div class="panel-subtitle">REVIEW THE DRAFT · NO INFORMATION IS SUBMITTED AUTOMATICALLY</div></div><span class="tag high">USER ACTION REQUIRED</span></div><div class="panel-body"><p class="complaint-intro">A formal draft has been prepared from this analysis. Fill in missing personal and impact details, verify all claims against the original evidence, then open the official Indian Cyber Crime Reporting Portal to file it.</p><label class="field-label" for="complaintDraft">EDITABLE COMPLAINT DRAFT</label><textarea id="complaintDraft" class="field complaint-draft" spellcheck="true">${escapeHtml(lines.join('\n'))}</textarea><div class="complaint-actions"><button class="button ghost small" type="button" data-action="copy-complaint">Copy draft</button><button class="button ghost small" type="button" data-action="download-complaint">Download .txt</button><a class="button complaint-portal" href="https://cybercrime.gov.in/Webform/Crime_AuthoLogin.aspx" target="_blank" rel="noopener noreferrer">Open complaint registration ↗</a></div><p class="complaint-note">The official portal requires you to verify the report, provide personal details, and sign in. CyberGuard does not send your email, ID, or complaint automatically.</p></div></section>`;
}
const detectedEmailFields=detected=>[
  ['Sender',detected.display_name&&detected.display_name!=='Not present in message'
    ?`${detected.display_name} <${detected.sender}>`:detected.sender],
  ['Organization from sender domain',detected.sender_organization],
  ['Sender domain',detected.sender_domain],
  ['Organization claim',detected.claimed_organization],
  ['Claimed role',detected.claimed_role],
  ['Likely objective',emailObjectives(detected.objectives)],
  ['Subject',detected.subject],
  ['Links',detected.urls?.length?detected.urls.join(', '):'None detected'],
  ['Attachments',detected.attachments?.length?detected.attachments.join(', '):'None detected'],
  ['Authentication results (as pasted)',Object.entries(detected.authentication_as_pasted||{}).map(([key,value])=>`${key.toUpperCase()}: ${value}`).join(' · ')||'Not present'],
  ['Message parsing warnings',[...(detected.parser_warnings||[]),...(detected.decoding_warnings||[])].join(' ')||'None'],
];
const emailTabs=()=>`<div class="tabs">${emailAnalysisOptions.map(([kind,label])=>`<button type="button" class="tab ${state.analysisKind===kind?'active':''}" data-kind="${kind}">${label}</button>`).join('')}</div>`;
const standardAnalysisFormWithIdentity=standardAnalysisForm;
analysisForm=function(){
  if(state.analysisKind!=='email')return standardAnalysisFormWithIdentity();
  return `<section class="panel form-panel email-workflow">${emailTabs()}<form id="analysisForm"><label class="field-label" for="rawMessage">PASTE FULL EMAIL</label><textarea class="field email-paste" id="rawMessage" required maxlength="100000" placeholder="Paste the email, including its From and Subject headers if available. CyberGuard will extract sender, organization and role clues, likely objective, and links automatically."></textarea><p class="email-hint">No sender, organization, role, or explanation fields needed. Missing details are shown as not detected.</p><button class="button" id="submitAnalysis" type="submit">Analyze with CYBERGUARD&nbsp; →</button></form></section>`;
};
const standardRenderAnalysis=renderAnalysis;
renderAnalysis=function(){
  stopLiveVoice();
  if(state.analysisKind!=='email'){
    standardRenderAnalysis();
    root.querySelector('.tabs [data-kind="message"]')?.remove();
    return;
  }
  root.innerHTML=`${heading('EMAIL SECURITY','Analyze an email','Paste it once. Sender, organization and role clues, likely objective, and links are extracted automatically.',`<button class="button ghost" type="button" data-action="toggle-demos" aria-expanded="false">▷ &nbsp;Demo scenarios</button>`)}${demoPickerMarkup()}${demoPrefillNotice()}${liveVoiceMarkup()}${analysisForm()}<div id="analysisResult">${state.analysis?resultMarkup(state.analysis):'<div class="email-empty">Your analysis summary will appear here.</div>'}</div>`;
};
resultMarkup=function(result){
  const detected=result.input&&result.input.auto_detected;
  if(!detected)return standardEmailResultMarkup(result);
  const score=Number(result.risk_score||0);
  const severity=result.risk?.severity||'low';
  const reasons=(result.explanation?.reasons||[]).slice(0,2);
  const sensitivity=result.asset_sensitivity;
  return `<section class="panel email-summary">${result.input?.synthetic_demo?'<div class="demo-result-label">SYNTHETIC DEMO · NOT A REAL INCIDENT</div>':''}<div class="email-summary-head"><div><span class="eyebrow">ANALYSIS RESULT</span><h2>${escapeHtml(human(result.threat_category||result.fusion?.threat||'undetermined'))}</h2></div><div class="email-score" style="color:${severityColor[severity]||'#e8eef3'}">${score}<small>/100</small><span>${escapeHtml(severity.toUpperCase())}</span></div></div>${sensitivity?`<div class="email-reasons"><b>Automatically inferred sensitivity: ${escapeHtml(human(sensitivity.level))}</b><div>${escapeHtml(sensitivity.reason)}</div></div>`:''}<div class="email-fields">${detectedEmailFields(detected).map(([label,value])=>`<div class="email-field"><span>${escapeHtml(label)}</span><b>${escapeHtml(value||'Not detected')}</b></div>`).join('')}</div>${reasons.length?`<div class="email-reasons">${reasons.map(reason=>`<div>${escapeHtml(reason)}</div>`).join('')}</div>`:''}<p class="email-caveat">Organization and role are clues inferred from the sender domain or message wording. Authentication results are copied from the pasted headers and are not independently verified. Attachments are listed but their contents are not scanned. Sensitivity checks inspect text only; media without OCR or transcription defaults to medium. This offline analysis cannot guarantee detection of every malicious email.</p></section><details class="email-details"><summary>Show evidence, explanation, and recommended actions</summary>${standardEmailResultMarkup(result)}</details>`;
};
const resultMarkupWithEmailSummary=resultMarkup;
resultMarkup=function(result){
  const markup=resultMarkupWithEmailSummary(result);
  const complaint=complaintMarkup(result);
  if(result.input?.synthetic_demo)return `<div class="demo-result-label">SYNTHETIC DEMO · NOT A REAL INCIDENT · EXCLUDED FROM QUEUE</div>${markup}`;
  if(!complaint)return markup;
  if(result.input?.auto_detected){
    return markup.replace('</section><details class="email-details">',
      `${complaint}</section><details class="email-details">`);
  }
  return `${markup}${complaint}`;
};
document.addEventListener('submit',async event=>{
  if(event.target.id!=='analysisForm'||state.analysisKind!=='email')return;
  event.preventDefault();
  event.stopImmediatePropagation();
  if(state.busy)return;
  state.busy=true;
  const button=document.getElementById('submitAnalysis');
  button.disabled=true;
  button.textContent='Analyzing email…';
  try{
    const result=await endpoint(state.demoMode?'/api/analyze-demo':'/api/analyze',{method:'POST',body:JSON.stringify({
      type:'email',raw_message:document.getElementById('rawMessage').value,
      ...(state.demoMode?{synthetic_demo:true,demo_id:state.demoMode.id}:{}),
    })});
    state.analysis=result;
    document.getElementById('analysisResult').innerHTML=resultMarkup(result);
    if(!state.demoMode)document.getElementById('navIncidentCount').textContent=(await endpoint('/api/dashboard')).active_incidents;
    toast(state.demoMode?'Synthetic scenario analyzed; it was not saved to incidents.':'Email analysis completed.');
  }catch(error){
    const message=error.message.includes('email text or URL must contain')
      ?'The dashboard service is still running an older version. Restart it and refresh to enable automatic email extraction.'
      :error.message;
    document.getElementById('analysisResult').innerHTML=`<div class="error-box">${escapeHtml(message)}</div>`;
  }finally{
    state.busy=false;
    button.disabled=false;
    button.textContent='Analyze with CYBERGUARD →';
  }
},true);
function liveVoiceMarkup(){
  return `<section class="panel live-voice-panel"><div class="panel-head"><div><div class="panel-title">Live microphone voice check</div><div class="panel-subtitle">LOCAL · FIVE-SECOND WINDOWS · NO INCIDENTS SAVED</div></div><span class="live-voice-indicator" aria-hidden="true"></span></div><div class="panel-body"><label class="field-label" for="liveVoiceDevice">MICROPHONE INPUT</label><div class="live-voice-device"><select class="field" id="liveVoiceDevice"><option value="">Default microphone</option></select><button class="button ghost small" type="button" data-action="refresh-live-voice-devices">Find microphones</button></div><div class="live-voice-actions"><button class="button" type="button" data-action="start-live-voice">🎙 Start live check</button><button class="button ghost" type="button" data-action="stop-live-voice" disabled>Stop</button><span id="liveVoiceStatus" role="status">Microphone is off.</span></div><div id="liveVoiceResult" class="live-voice-result"><strong>Ready when you are</strong><span>Select a laptop or connected microphone, then start. The latest result updates after each speech window.</span></div><p class="live-voice-note">Uses browser echo cancellation, noise suppression, and automatic gain control when supported. Background noise, codecs, and speaking style can still cause mistakes; low-quality audio is reported as inconclusive. This detector is not validated for call-grade or noisy-environment accuracy. Audio is analyzed locally and discarded after each window.</p></div></section>`;
}
function setLiveVoiceStatus(message){
  const status=document.getElementById('liveVoiceStatus');
  if(status)status.textContent=message;
}
function liveVoiceLabel(value){
  return ({likely_human:'Likely human',likely_ai_generated:'Likely AI-generated',inconclusive:'Inconclusive'})[value]||'Inconclusive';
}
function stopLiveVoice(){
  liveVoice.session+=1;
  if(liveVoice.interval){clearInterval(liveVoice.interval);liveVoice.interval=null}
  if(liveVoice.processor){liveVoice.processor.onaudioprocess=null;liveVoice.processor.disconnect();liveVoice.processor=null}
  if(liveVoice.mute){liveVoice.mute.disconnect();liveVoice.mute=null}
  if(liveVoice.stream){liveVoice.stream.getTracks().forEach(track=>track.stop());liveVoice.stream=null}
  if(liveVoice.context){const context=liveVoice.context;liveVoice.context=null;if(context.state!=='closed')context.close().catch(()=>{})}
  liveVoice.chunks=[];
  liveVoice.samples=0;
  liveVoice.busy=false;
  const start=document.querySelector('[data-action="start-live-voice"]');
  const stop=document.querySelector('[data-action="stop-live-voice"]');
  const device=document.getElementById('liveVoiceDevice');
  if(start)start.disabled=false;
  if(stop)stop.disabled=true;
  if(device)device.disabled=false;
  if(document.getElementById('liveVoiceStatus'))setLiveVoiceStatus('Microphone is off.');
}
function encodeLiveVoiceWav(chunks,sampleCount,sourceRate){
  const source=new Float32Array(sampleCount);
  let offset=0;
  for(const chunk of chunks){source.set(chunk,offset);offset+=chunk.length}
  const targetRate=16000;
  const targetCount=Math.floor(source.length*targetRate/sourceRate);
  if(targetCount<targetRate*3)throw new Error('Wait for at least three seconds of speech before analyzing.');
  const pcm=new ArrayBuffer(44+targetCount*2);
  const view=new DataView(pcm);
  const write=(position,text)=>{for(let i=0;i<text.length;i++)view.setUint8(position+i,text.charCodeAt(i))};
  write(0,'RIFF');view.setUint32(4,36+targetCount*2,true);write(8,'WAVE');write(12,'fmt ');
  view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);
  view.setUint32(24,targetRate,true);view.setUint32(28,targetRate*2,true);
  view.setUint16(32,2,true);view.setUint16(34,16,true);write(36,'data');view.setUint32(40,targetCount*2,true);
  for(let i=0;i<targetCount;i++){
    const position=i*sourceRate/targetRate;
    const left=Math.floor(position),right=Math.min(left+1,source.length-1),fraction=position-left;
    const sample=Math.max(-1,Math.min(1,source[left]*(1-fraction)+source[right]*fraction));
    view.setInt16(44+i*2,sample<0?sample*32768:sample*32767,true);
  }
  let binary='';
  const bytes=new Uint8Array(pcm);
  for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,Math.min(i+8192,bytes.length)));
  return btoa(binary);
}
function appendLiveVoiceResult(result){
  const output=document.getElementById('liveVoiceResult');
  if(!output)return;
  const origin=result.voice_origin||{};
  const quality=result.audio_quality||{};
  const label=liveVoiceLabel(result.classification);
  const method=result.detector_method==='ml'?'LOCAL TRAINED MODEL':'ACOUSTIC HEURISTIC';
  const warnings=quality.warnings?.length?quality.warnings.map(escapeHtml).join('<br>'):'Audio level and speech activity were sufficient for this window.';
  output.innerHTML=`<div class="live-voice-result-head"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(method)} · NO CONFIDENCE SCORE</span></div><div>${escapeHtml(warnings)}</div><small>Window ${liveVoice.windows} · ${quality.duration_seconds??'—'} s · ${quality.signal_level_dbfs??'—'} dBFS · ${quality.usable?'usable capture':'quality check failed'}</small>${origin.limitations?.length?`<small>${origin.limitations.map(escapeHtml).join(' ')}</small>`:''}`;
}
async function analyzeLiveVoiceWindow(){
  if(liveVoice.busy||!liveVoice.context||liveVoice.samples<liveVoice.context.sampleRate*5)return;
  const session=liveVoice.session;
  liveVoice.busy=true;
  const sourceRate=liveVoice.context.sampleRate;
  const chunks=liveVoice.chunks;
  const sampleCount=liveVoice.samples;
  liveVoice.chunks=[];
  liveVoice.samples=0;
  try{
    const content_base64=encodeLiveVoiceWav(chunks,sampleCount,sourceRate);
    setLiveVoiceStatus('Analyzing the latest microphone window…');
    const result=await endpoint('/api/live-voice',{method:'POST',body:JSON.stringify({content_base64})});
    if(session!==liveVoice.session)return;
    liveVoice.windows+=1;
    appendLiveVoiceResult(result);
    setLiveVoiceStatus('Listening · next result in about five seconds');
  }catch(error){
    if(session===liveVoice.session)setLiveVoiceStatus(error.message);
  }finally{
    if(session===liveVoice.session)liveVoice.busy=false;
  }
}
async function refreshLiveVoiceDevices(){
  let temporaryStream;
  try{
    temporaryStream=await navigator.mediaDevices.getUserMedia({audio:true});
    const devices=await navigator.mediaDevices.enumerateDevices();
    const select=document.getElementById('liveVoiceDevice');
    if(!select)return;
    const selected=select.value;
    const microphones=devices.filter(device=>device.kind==='audioinput');
    select.innerHTML='<option value="">Default microphone</option>'+microphones.map((device,index)=>`<option value="${escapeHtml(device.deviceId)}">${escapeHtml(device.label||`Microphone ${index+1}`)}</option>`).join('');
    if(microphones.some(device=>device.deviceId===selected))select.value=selected;
    setLiveVoiceStatus(`${microphones.length} microphone input(s) found.`);
  }catch(error){
    setLiveVoiceStatus(`Could not list microphones: ${error.message}`);
  }finally{
    temporaryStream?.getTracks().forEach(track=>track.stop());
  }
}
async function startLiveVoice(){
  if(!navigator.mediaDevices?.getUserMedia){setLiveVoiceStatus('This browser does not provide microphone capture. Use a current browser on localhost or HTTPS.');return}
  const session=liveVoice.session+1;
  liveVoice.session=session;
  const start=document.querySelector('[data-action="start-live-voice"]');
  const stop=document.querySelector('[data-action="stop-live-voice"]');
  const device=document.getElementById('liveVoiceDevice');
  if(start)start.disabled=true;
  if(device)device.disabled=true;
  try{
    const deviceId=device?.value;
    const audio={channelCount:{ideal:1},echoCancellation:true,noiseSuppression:true,autoGainControl:true};
    if(deviceId)audio.deviceId={exact:deviceId};
    liveVoice.stream=await navigator.mediaDevices.getUserMedia({audio});
    if(session!==liveVoice.session){liveVoice.stream.getTracks().forEach(track=>track.stop());liveVoice.stream=null;return}
    const devices=await navigator.mediaDevices.enumerateDevices();
    if(device){
      const selected=liveVoice.stream.getAudioTracks()[0]?.getSettings?.().deviceId||deviceId||'';
      const microphones=devices.filter(item=>item.kind==='audioinput');
      device.innerHTML='<option value="">Default microphone</option>'+microphones.map((item,index)=>`<option value="${escapeHtml(item.deviceId)}">${escapeHtml(item.label||`Microphone ${index+1}`)}</option>`).join('');
      if(microphones.some(item=>item.deviceId===selected))device.value=selected;
      device.disabled=true;
    }
    try{liveVoice.context=new AudioContext({sampleRate:16000})}
    catch{liveVoice.context=new AudioContext()}
    await liveVoice.context.resume();
    const source=liveVoice.context.createMediaStreamSource(liveVoice.stream);
    liveVoice.processor=liveVoice.context.createScriptProcessor(4096,1,1);
    liveVoice.mute=liveVoice.context.createGain();
    liveVoice.mute.gain.value=0;
    liveVoice.processor.onaudioprocess=event=>{
      if(!liveVoice.stream)return;
      const input=event.inputBuffer.getChannelData(0);
      const copy=new Float32Array(input);
      liveVoice.chunks.push(copy);
      liveVoice.samples+=copy.length;
      while(liveVoice.samples>liveVoice.context.sampleRate*10&&liveVoice.chunks.length){
        liveVoice.samples-=liveVoice.chunks.shift().length;
      }
    };
    source.connect(liveVoice.processor);
    liveVoice.processor.connect(liveVoice.mute);
    liveVoice.mute.connect(liveVoice.context.destination);
    liveVoice.windows=0;
    liveVoice.interval=setInterval(analyzeLiveVoiceWindow,400);
    if(start)start.disabled=true;
    if(stop)stop.disabled=false;
    setLiveVoiceStatus(`Listening through ${liveVoice.stream.getAudioTracks()[0]?.label||'selected microphone'}; analysis updates every ~5 seconds.`);
    liveVoice.stream.getTracks().forEach(track=>track.addEventListener('ended',()=>{stopLiveVoice();setLiveVoiceStatus('Microphone disconnected.')} ,{once:true}));
  }catch(error){
    if(session!==liveVoice.session)return;
    stopLiveVoice();
    const message=error.message.includes('Request failed (404)')
      ?'The dashboard server needs a restart to enable live microphone analysis. Restart it, reload this page, and try again.'
      :`Could not start microphone: ${error.message}`;
    setLiveVoiceStatus(message);
  }
}
document.addEventListener('click',event=>{
  const action=event.target.closest('[data-action]')?.dataset.action;
  if(action==='start-live-voice')startLiveVoice();
  if(action==='stop-live-voice')stopLiveVoice();
  if(action==='refresh-live-voice-devices')refreshLiveVoiceDevices();
});
window.addEventListener('pagehide',stopLiveVoice);
render();

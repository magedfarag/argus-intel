// ─── State ──────────────────────────────────────────────────────────────────
const HISTORY_KEY = 'analysis_history';
const MAX_HISTORY = 50;

const state = {
  config:           null,
  providers:        [],
  drawnLayer:       null,
  geometry:         null,
  areaKm2:          0,
  analysis:         null,
  filteredChanges:  [],
  pollTimer:        null,
  currentJobId:     null,
  historyOpen:      false,
};

// ─── Map ─────────────────────────────────────────────────────────────────────
const map = L.map('map').setView([24.7136, 46.6753], 11);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '© OpenStreetMap contributors',
}).addTo(map);

const drawnItems = new L.FeatureGroup();
map.addLayer(drawnItems);

const drawControl = new L.Control.Draw({
  edit: { featureGroup: drawnItems, remove: false },
  draw: {
    polyline: false, marker: false, circlemarker: false,
    polygon: { allowIntersection: false, showArea: true },
    rectangle: true, circle: true,
  },
});
map.addControl(drawControl);

// ─── UI Helpers ───────────────────────────────────────────────────────────────
function setMessage(msg, isError = false) {
  const el = document.getElementById('submitMessage');
  el.textContent = msg;
  el.style.color = isError ? '#fca5a5' : '#9ca3af';
}

function setJobProgress(visible, label = '', jobId = '') {
  const el = document.getElementById('jobProgress');
  el.classList.toggle('hidden', !visible);
  document.getElementById('jobProgressLabel').textContent = label;
  document.getElementById('jobProgressId').textContent = jobId ? `Job ID: ${jobId}` : '';
}

function showWarnings(warnings) {
  const banner = document.getElementById('warningBanner');
  if (!warnings || warnings.length === 0) {
    banner.classList.add('hidden');
    return;
  }
  banner.classList.remove('hidden');
  banner.innerHTML = '<strong>Notices:</strong><ul>' +
    warnings.map(w => `<li>${escHtml(w)}</li>`).join('') + '</ul>';
}

function escHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function updateSelectionUI() {
  document.getElementById('geometryType').textContent = state.geometry ? state.geometry.type : 'None';
  document.getElementById('areaDisplay').textContent = `${state.areaKm2.toFixed(4)} km²`;
  const valid = state.areaKm2 >= 0.01 && state.areaKm2 <= 100;
  document.getElementById('selectionStatus').textContent =
    state.geometry ? (valid ? 'Valid selection' : 'Outside allowed range') : 'No valid selection';
  document.getElementById('analyzeBtn').disabled = !(state.geometry && valid);
}

function setCurrentLayer(layer) {
  drawnItems.clearLayers();
  drawnItems.addLayer(layer);
  state.drawnLayer = layer;
  let feature = layer.toGeoJSON();
  if (layer instanceof L.Circle) {
    feature = turf.circle(
      [layer.getLatLng().lng, layer.getLatLng().lat],
      layer.getRadius() / 1000,
      { steps: 64, units: 'kilometers' },
    );
    feature.properties = { shape: 'Circle', radius_m: layer.getRadius() };
  }
  state.geometry = feature.geometry;
  state.areaKm2  = turf.area(feature) / 1_000_000;
  updateSelectionUI();
}

map.on(L.Draw.Event.CREATED, (e) => setCurrentLayer(e.layer));
map.on(L.Draw.Event.EDITED,  (e) => e.layers.eachLayer(setCurrentLayer));

function clearSelection() {
  drawnItems.clearLayers();
  state.drawnLayer = null;
  state.geometry   = null;
  state.areaKm2    = 0;
  updateSelectionUI();
  setMessage('Selection cleared.');
}
document.getElementById('clearBtn').addEventListener('click', clearSelection);

// Bounding box draw
document.getElementById('applyBboxBtn').addEventListener('click', () => {
  const minLat = parseFloat(document.getElementById('minLat').value);
  const minLng = parseFloat(document.getElementById('minLng').value);
  const maxLat = parseFloat(document.getElementById('maxLat').value);
  const maxLng = parseFloat(document.getElementById('maxLng').value);
  if ([minLat, minLng, maxLat, maxLng].some(Number.isNaN)) {
    setMessage('Enter all bounding box coordinates before drawing.', true); return;
  }
  if (!(minLat < maxLat && minLng < maxLng)) {
    setMessage('Min values must be less than max values.', true); return;
  }
  const layer = L.rectangle([[minLat, minLng], [maxLat, maxLng]], { color: '#0ea5e9', weight: 2 });
  setCurrentLayer(layer);
  map.fitBounds(layer.getBounds(), { padding: [20, 20] });
  setMessage('Bounding box applied.');
});

// Cloud slider
document.getElementById('cloudSlider').addEventListener('input', (e) => {
  document.getElementById('cloudDisplay').textContent = `${e.target.value}%`;
});

// ─── Data Loading ─────────────────────────────────────────────────────────────
function isoDate(d) { return d.toISOString().slice(0, 10); }

async function loadConfig() {
  const r = await fetch('/api/config');
  const cfg = await r.json();
  state.config = cfg;
  document.getElementById('todayBadge').textContent = `Dataset: ${cfg.today}`;
  const today = new Date(cfg.today);
  const start = new Date(today);
  start.setDate(today.getDate() - 30);
  document.getElementById('startDate').value = isoDate(start);
  document.getElementById('endDate').value   = isoDate(today);

  // Apply server-side defaults
  document.getElementById('cloudSlider').value = cfg.default_cloud_threshold ?? 20;
  document.getElementById('cloudDisplay').textContent = `${cfg.default_cloud_threshold ?? 20}%`;

  // Update mode badge
  const modeBadge = document.getElementById('modeBadge');
  const mode = cfg.app_mode || 'auto';
  modeBadge.textContent = mode.toUpperCase();
  modeBadge.className = `badge badge--mode badge--mode-${mode}`;
}

async function loadProviders() {
  try {
    const r = await fetch('/api/providers');
    const data = await r.json();
    state.providers = data.providers || [];
    renderProviderStrip();
  } catch (_) {
    document.getElementById('providerItems').textContent = 'unavailable';
  }
}

function renderProviderStrip() {
  const items = document.getElementById('providerItems');
  if (!state.providers.length) { items.textContent = 'none'; return; }
  items.innerHTML = state.providers.map(p => {
    const cls = p.available ? 'provider-chip provider-chip--ok' : 'provider-chip provider-chip--off';
    const tip = p.available ? (p.notes?.[0] ?? '') : (p.reason ?? 'unavailable');
    return `<span class="${cls}" title="${escHtml(tip)}">${escHtml(p.display_name)}</span>`;
  }).join('');
}

// ─── Analysis History ─────────────────────────────────────────────────────────
function fingerprint(payload) {
  // Deterministic key from the essential request parameters
  const coords = JSON.stringify(payload.geometry?.coordinates ?? '');
  return [coords, payload.start_date, payload.end_date, payload.provider, payload.cloud_threshold].join('|');
}

function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
  } catch (_) {
    return [];
  }
}

function saveToHistory(payload, result) {
  const history = loadHistory();
  const fp = fingerprint(payload);
  // Remove any existing entry with the same fingerprint (update with latest)
  const filtered = history.filter(h => h.fp !== fp);
  filtered.unshift({
    fp,
    timestamp: new Date().toISOString(),
    provider: result.provider || payload.provider,
    isDemo: result.is_demo || false,
    areaKm2: result.requested_area_km2 ?? payload.area_km2 ?? 0,
    totalChanges: result.stats?.total_changes ?? 0,
    startDate: payload.start_date,
    endDate: payload.end_date,
    payload,
    result,
  });
  // Cap history size
  if (filtered.length > MAX_HISTORY) filtered.length = MAX_HISTORY;
  localStorage.setItem(HISTORY_KEY, JSON.stringify(filtered));
  renderHistory();
}

function clearHistory() {
  localStorage.removeItem(HISTORY_KEY);
  renderHistory();
}

function deleteHistoryEntry(index) {
  const history = loadHistory();
  if (index < 0 || index >= history.length) return;
  history.splice(index, 1);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  renderHistory();
}

function findInHistory(payload) {
  const fp = fingerprint(payload);
  return loadHistory().find(h => h.fp === fp) || null;
}

function renderHistory() {
  const history = loadHistory();
  document.getElementById('historyCount').textContent = history.length;
  const list = document.getElementById('historyList');
  if (history.length === 0) {
    list.innerHTML = '<div class="history-empty">No previous analyses.</div>';
    return;
  }
  list.innerHTML = history.map((h, i) => {
    const ts = new Date(h.timestamp);
    const time = ts.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    const demoBadge = h.isDemo ? '<span class="history-item__badge history-item__badge--demo">DEMO</span>' : '';
    return `
    <div class="history-item" data-index="${i}" role="button" tabindex="0" title="Click to load this analysis">
      <div class="history-item__info">
        <div class="history-item__title">${escHtml(h.provider)} · ${h.areaKm2.toFixed(2)} km²</div>
        <div class="history-item__meta">${time} · ${escHtml(h.startDate)} → ${escHtml(h.endDate)}</div>
      </div>
      <div class="history-item__stats">
        ${demoBadge}
        <span class="history-item__badge history-item__badge--changes">${h.totalChanges} changes</span>
        <button class="history-item__delete" data-index="${i}" title="Remove from history" aria-label="Delete this entry">&times;</button>
      </div>
    </div>`;
  }).join('');
}

function showHistoryEntry(index) {
  const history = loadHistory();
  const entry = history[index];
  if (!entry) return;
  handleAnalysisResult(entry.result);
  setMessage('Loaded from history — no new request sent.');
}

// Toggle & event wiring
document.getElementById('historyToggle').addEventListener('click', () => {
  state.historyOpen = !state.historyOpen;
  document.getElementById('historyList').classList.toggle('hidden', !state.historyOpen);
  document.getElementById('historyChevron').classList.toggle('open', state.historyOpen);
});

document.getElementById('clearHistoryBtn').addEventListener('click', (e) => {
  e.stopPropagation();
  clearHistory();
});

document.getElementById('historyList').addEventListener('click', (e) => {
  const delBtn = e.target.closest('.history-item__delete');
  if (delBtn) {
    e.stopPropagation();
    deleteHistoryEntry(parseInt(delBtn.dataset.index, 10));
    return;
  }
  const item = e.target.closest('.history-item');
  if (!item) return;
  showHistoryEntry(parseInt(item.dataset.index, 10));
});

// ─── Analysis ─────────────────────────────────────────────────────────────────
document.getElementById('analyzeBtn').addEventListener('click', submitAnalysis);

async function submitAnalysis() {
  if (!state.geometry) { setMessage('No selection.', true); return; }
  cancelPoll();

  const btn = document.getElementById('analyzeBtn');
  btn.disabled = true;
  setMessage('Submitting…');
  showWarnings([]);

  const payload = {
    geometry:         state.geometry,
    start_date:       document.getElementById('startDate').value,
    end_date:         document.getElementById('endDate').value,
    provider:         document.getElementById('providerSelect').value,
    cloud_threshold:  parseFloat(document.getElementById('cloudSlider').value),
    processing_mode:  document.getElementById('processingMode').value,
    async_execution:  document.getElementById('asyncToggle').checked,
    area_km2:         state.areaKm2,
  };

  // Check history for identical request
  const cached = findInHistory(payload);
  if (cached) {
    handleAnalysisResult(cached.result);
    setMessage('Loaded from history — identical previous analysis found.');
    btn.disabled = false;
    return;
  }

  state.lastPayload = payload;

  try {
    const r = await fetch('/api/analyze', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });
    if (!r.ok) {
      const err = await r.json();
      setMessage(err.detail ?? `Error ${r.status}`, true);
      btn.disabled = false;
      return;
    }
    const body = await r.json();

    // Async job returned
    if (body.job_id && !body.analysis_id) {
      state.currentJobId = body.job_id;
      setJobProgress(true, 'Processing in background…', body.job_id);
      setMessage('Job submitted. Polling for results…');
      startPoll(body.job_id);
      btn.disabled = false;
      return;
    }

    // Synchronous result
    handleAnalysisResult(body);
  } catch (e) {
    setMessage(`Request failed: ${e.message}`, true);
  }
  btn.disabled = false;
}

function handleAnalysisResult(body) {
  state.analysis = body;
  state.currentJobId = null;
  cancelPoll();
  setJobProgress(false);
  showWarnings(body.warnings || []);
  filterChangesByTimeline();
  renderSummary();

  // Save to history (if we have the original payload)
  if (state.lastPayload) {
    saveToHistory(state.lastPayload, body);
    state.lastPayload = null;
  }

  const isDemo = body.is_demo;
  const modeBadge = document.getElementById('modeBadge');
  if (isDemo) {
    modeBadge.textContent = 'DEMO';
    modeBadge.className = 'badge badge--mode badge--mode-demo';
    setMessage('Demo mode — results are synthetic curated data.');
  } else {
    setMessage(`Live analysis: ${body.stats?.total_changes ?? 0} changes detected.`);
  }
}

// ─── Job Polling (WebSocket with HTTP fallback) ──────────────────────────────
const POLL_INTERVAL_MS = 3000;

function startPoll(jobId) {
  cancelPoll();
  // Try WebSocket first; fall back to HTTP polling on failure
  try {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${location.host}/api/jobs/${jobId}/stream`);
    state.ws = ws;

    ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.type === 'completed' && msg.result) {
        cancelPoll();
        setJobProgress(false);
        handleAnalysisResult(msg.result);
      } else if (msg.type === 'failed') {
        cancelPoll();
        setJobProgress(false);
        setMessage(`Job failed: ${msg.error ?? 'unknown error'}`, true);
      } else if (msg.type === 'error') {
        // Server cannot stream — fall back to HTTP polling
        cancelPoll();
        state.pollTimer = setInterval(() => pollJob(jobId), POLL_INTERVAL_MS);
      } else {
        document.getElementById('jobProgressLabel').textContent =
          `Processing\u2026 (${msg.state ?? msg.type})`;
      }
    };

    ws.onerror = () => {
      // WebSocket unavailable — fall back to HTTP polling
      cancelPoll();
      state.pollTimer = setInterval(() => pollJob(jobId), POLL_INTERVAL_MS);
    };

    ws.onclose = () => { state.ws = null; };
  } catch (_) {
    // WebSocket constructor failed — fall back to HTTP polling
    state.pollTimer = setInterval(() => pollJob(jobId), POLL_INTERVAL_MS);
  }
}

function cancelPoll() {
  if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
  if (state.ws) { try { state.ws.close(); } catch (_) {} state.ws = null; }
}

async function pollJob(jobId) {
  try {
    const r = await fetch(`/api/jobs/${jobId}`);
    if (!r.ok) { cancelPoll(); setJobProgress(false); setMessage(`Job lookup failed (${r.status}).`, true); return; }
    const job = await r.json();

    if (job.state === 'completed' && job.result) {
      cancelPoll();
      setJobProgress(false);
      handleAnalysisResult(job.result);
    } else if (job.state === 'failed') {
      cancelPoll();
      setJobProgress(false);
      setMessage(`Job failed: ${job.error ?? 'unknown error'}`, true);
    } else {
      document.getElementById('jobProgressLabel').textContent =
        `Processing\u2026 (${job.state})`;
    }
  } catch (_) {
    // Transient network error — keep polling
  }
}

// ─── Results rendering ────────────────────────────────────────────────────────
function renderSummary() {
  const el = document.getElementById('resultsSummary');
  if (!state.analysis) {
    el.className = 'summary-card empty-state';
    el.textContent = 'Run an analysis to populate the summary.';
    return;
  }
  const s = state.analysis;
  const isDemoTag = s.is_demo ? '<span class="pill pill--demo">DEMO DATA</span>' : '';
  el.className = 'summary-card';
  el.innerHTML = `
    <div class="summary-top">${isDemoTag}</div>
    <div class="meta-grid">
      <div><strong>Analysis ID</strong><br>${s.analysis_id}</div>
      <div><strong>Provider</strong><br>${s.provider}</div>
      <div><strong>Area</strong><br>${s.requested_area_km2.toFixed(4)} km²</div>
      <div><strong>Total changes</strong><br>${s.stats.total_changes}</div>
      <div><strong>Avg confidence</strong><br>${s.stats.avg_confidence}%</div>
      <div><strong>Window</strong><br>${s.imagery_window.start_date} → ${s.imagery_window.end_date}</div>
    </div>`;
}

function filterChangesByTimeline() {
  if (!state.analysis) return;
  const days   = parseInt(document.getElementById('timelineSlider').value, 10);
  const label  = days === 30 ? 'Showing all from last 30 days' : `Last ${days} day(s)`;
  document.getElementById('timelineLabel').textContent = label;
  const endDate = new Date(state.analysis.imagery_window.end_date);
  const cutoff  = new Date(endDate);
  cutoff.setDate(endDate.getDate() - days);
  state.filteredChanges = state.analysis.changes.filter(c => new Date(c.detected_at) >= cutoff);
  renderResultsList();
}

function renderResultsList() {
  const list = document.getElementById('resultsList');
  if (!state.analysis) { list.innerHTML = ''; return; }
  if (state.filteredChanges.length === 0) {
    list.innerHTML = '<div class="summary-card empty-state">No detections match the current timeline filter.</div>';
    return;
  }
  list.innerHTML = state.filteredChanges.map(ch => {
    const confClass = ch.confidence >= 80 ? 'pill pill--high' : ch.confidence >= 60 ? 'pill pill--mid' : 'pill pill--low';
    const resNote = ch.resolution_m ? `<span class="muted" style="font-size:0.8rem;"> · ${ch.resolution_m} m resolution</span>` : '';
    const chWarnings = ch.warnings?.length
      ? `<div class="change-warnings">${ch.warnings.map(w => `<span>${escHtml(w)}</span>`).join('')}</div>` : '';
    return `
    <article class="result-card">
      <div class="result-card-header">
        <div>
          <h3 style="margin:0 0 4px;">${escHtml(ch.change_type)}${resNote}</h3>
          <div class="muted">Detected: ${ch.detected_at.replace('T', ' ').slice(0, 16)}</div>
        </div>
        <div class="${confClass}">${ch.confidence}%</div>
      </div>
      <p style="margin:0;">${escHtml(ch.summary)}</p>
      ${chWarnings}
      ${(ch.before_image || ch.after_image) ? `
      <div class="result-images">
        <div><div class="muted" style="margin-bottom:4px;">Before</div>
          ${ch.before_image ? `<img src="${ch.before_image}" alt="Before" />` : '<div class="img-placeholder">No image</div>'}
        </div>
        <div><div class="muted" style="margin-bottom:4px;">After</div>
          ${ch.after_image ? `<img src="${ch.after_image}" alt="After" />` : '<div class="img-placeholder">No image</div>'}
        </div>
      </div>` : `
      <div class="result-images-note muted">Satellite NDVI analysis \u2014 imagery previews not available for pixel-level detections.</div>`}
      <div class="meta-grid">
        <div><strong>Center</strong><br>${ch.center.lat}, ${ch.center.lng}</div>
        <div><strong>BBox</strong><br>${ch.bbox.join(', ')}</div>
        <div><strong>Provider</strong><br>${ch.provider}</div>
        <div><strong>Change ID</strong><br>${ch.change_id}</div>
      </div>
      <div>
        <strong>Model rationale</strong>
        <ul class="rationale-list">${ch.rationale.map(r => `<li>${escHtml(r)}</li>`).join('')}</ul>
      </div>
    </article>`;
  }).join('');
}

document.getElementById('timelineSlider').addEventListener('input', filterChangesByTimeline);

// ─── Boot ─────────────────────────────────────────────────────────────────────
function seedHistoryIfEmpty() {
  if (loadHistory().length > 0) return;

  // Seed 1 — REAL Sentinel-2 NDVI change detection (rasterio COG streaming from AWS)
  // Before: S2A_38RPN_20250114 (0% cloud), After: S2C_38RPN_20250325 (0% cloud)
  // 8 changes detected via |ΔNDVI| > 0.12 threshold, morphological filtering, connected components
  const livePayload = {
    geometry: { type: 'Polygon', coordinates: [[[46.66,24.71],[46.69,24.71],[46.69,24.74],[46.66,24.74],[46.66,24.71]]] },
    start_date: '2025-01-14', end_date: '2025-03-25',
    provider: 'sentinel2', cloud_threshold: 15, processing_mode: 'balanced', async_execution: false, area_km2: 10.0,
  };
  const liveResult = {
    analysis_id: '1b6b2648-6879-41b9-910d-0a86d5e538c8',
    requested_area_km2: 10.0, provider: 'sentinel2', is_demo: false,
    request_bounds: [46.66, 24.71, 46.69, 24.74],
    imagery_window: { start_date: '2025-01-14', end_date: '2025-03-25' },
    warnings: [
      'Real satellite change detection: Sentinel-2 L2A COGs streamed from AWS Earth Search.',
      'Before scene: S2A_38RPN_20250114_0_L2A (0% cloud)',
      'After scene: S2C_38RPN_20250325_0_L2A (0% cloud)',
    ],
    changes: [
      {
        change_id: 'det-S2-38RPN-4', detected_at: '2025-03-25T07:43:16',
        change_type: 'Site clearing / earthwork', confidence: 75.0,
        center: { lng: 46.685812, lat: 24.731964 }, bbox: [46.685714, 24.731875, 46.685909, 24.732054],
        provider: 'sentinel2', summary: 'Site clearing / earthwork detected between 2025-01-14 and 2025-03-25 via Sentinel-2 10m NDVI change analysis.',
        rationale: ['NDVI decreased significantly - vegetation cover removed', 'Affected area ~500 m\u00b2 based on 5 pixels at 10m resolution', 'Pattern consistent with site clearing or excavation'],
        before_image: null, after_image: null, thumbnail: null,
        scene_id_before: 'S2A_38RPN_20250114_0_L2A', scene_id_after: 'S2C_38RPN_20250325_0_L2A', resolution_m: 10, warnings: [],
      },
      {
        change_id: 'det-S2-38RPN-5', detected_at: '2025-03-25T07:43:16',
        change_type: 'Site clearing / earthwork', confidence: 75.0,
        center: { lng: 46.685422, lat: 24.731786 }, bbox: [46.685325, 24.731696, 46.685519, 24.731875],
        provider: 'sentinel2', summary: 'Site clearing / earthwork detected between 2025-01-14 and 2025-03-25 via Sentinel-2 10m NDVI change analysis.',
        rationale: ['NDVI decreased significantly - vegetation cover removed', 'Affected area ~500 m\u00b2 based on 5 pixels at 10m resolution', 'Pattern consistent with site clearing or excavation'],
        before_image: null, after_image: null, thumbnail: null,
        scene_id_before: 'S2A_38RPN_20250114_0_L2A', scene_id_after: 'S2C_38RPN_20250325_0_L2A', resolution_m: 10, warnings: [],
      },
      {
        change_id: 'det-S2-38RPN-34', detected_at: '2025-03-25T07:43:16',
        change_type: 'Site clearing / earthwork', confidence: 75.0,
        center: { lng: 46.678799, lat: 24.717232 }, bbox: [46.678701, 24.717143, 46.678896, 24.717321],
        provider: 'sentinel2', summary: 'Site clearing / earthwork detected between 2025-01-14 and 2025-03-25 via Sentinel-2 10m NDVI change analysis.',
        rationale: ['NDVI decreased significantly - vegetation cover removed', 'Affected area ~500 m\u00b2 based on 5 pixels at 10m resolution', 'Pattern consistent with site clearing or excavation'],
        before_image: null, after_image: null, thumbnail: null,
        scene_id_before: 'S2A_38RPN_20250114_0_L2A', scene_id_after: 'S2C_38RPN_20250325_0_L2A', resolution_m: 10, warnings: [],
      },
      {
        change_id: 'det-S2-38RPN-1', detected_at: '2025-03-25T07:43:16',
        change_type: 'Roofing / enclosure', confidence: 70.0,
        center: { lng: 46.678604, lat: 24.737946 }, bbox: [46.678506, 24.737857, 46.678701, 24.738036],
        provider: 'sentinel2', summary: 'Roofing / enclosure detected between 2025-01-14 and 2025-03-25 via Sentinel-2 10m NDVI change analysis.',
        rationale: ['NDVI increase - higher reflectance surface detected', 'Pattern consistent with new roofing or impervious material', 'Affected area ~500 m\u00b2'],
        before_image: null, after_image: null, thumbnail: null,
        scene_id_before: 'S2A_38RPN_20250114_0_L2A', scene_id_after: 'S2C_38RPN_20250325_0_L2A', resolution_m: 10, warnings: [],
      },
      {
        change_id: 'det-S2-38RPN-2', detected_at: '2025-03-25T07:43:16',
        change_type: 'Roofing / enclosure', confidence: 70.0,
        center: { lng: 46.687175, lat: 24.736518 }, bbox: [46.687078, 24.736429, 46.687273, 24.736607],
        provider: 'sentinel2', summary: 'Roofing / enclosure detected between 2025-01-14 and 2025-03-25 via Sentinel-2 10m NDVI change analysis.',
        rationale: ['NDVI increase - higher reflectance surface detected', 'Pattern consistent with new roofing or impervious material', 'Affected area ~500 m\u00b2'],
        before_image: null, after_image: null, thumbnail: null,
        scene_id_before: 'S2A_38RPN_20250114_0_L2A', scene_id_after: 'S2C_38RPN_20250325_0_L2A', resolution_m: 10, warnings: [],
      },
      {
        change_id: 'det-S2-38RPN-3', detected_at: '2025-03-25T07:43:16',
        change_type: 'Roofing / enclosure', confidence: 70.0,
        center: { lng: 46.67461, lat: 24.733661 }, bbox: [46.674513, 24.733571, 46.674708, 24.73375],
        provider: 'sentinel2', summary: 'Roofing / enclosure detected between 2025-01-14 and 2025-03-25 via Sentinel-2 10m NDVI change analysis.',
        rationale: ['NDVI increase - higher reflectance surface detected', 'Pattern consistent with new roofing or impervious material', 'Affected area ~500 m\u00b2'],
        before_image: null, after_image: null, thumbnail: null,
        scene_id_before: 'S2A_38RPN_20250114_0_L2A', scene_id_after: 'S2C_38RPN_20250325_0_L2A', resolution_m: 10, warnings: [],
      },
      {
        change_id: 'det-S2-38RPN-6', detected_at: '2025-03-25T07:43:16',
        change_type: 'Roofing / enclosure', confidence: 70.0,
        center: { lng: 46.673344, lat: 24.731696 }, bbox: [46.673247, 24.731607, 46.673442, 24.731786],
        provider: 'sentinel2', summary: 'Roofing / enclosure detected between 2025-01-14 and 2025-03-25 via Sentinel-2 10m NDVI change analysis.',
        rationale: ['NDVI increase - higher reflectance surface detected', 'Pattern consistent with new roofing or impervious material', 'Affected area ~500 m\u00b2'],
        before_image: null, after_image: null, thumbnail: null,
        scene_id_before: 'S2A_38RPN_20250114_0_L2A', scene_id_after: 'S2C_38RPN_20250325_0_L2A', resolution_m: 10, warnings: [],
      },
      {
        change_id: 'det-S2-38RPN-7', detected_at: '2025-03-25T07:43:16',
        change_type: 'Roofing / enclosure', confidence: 70.0,
        center: { lng: 46.684594, lat: 24.731339 }, bbox: [46.684448, 24.73125, 46.68474, 24.731429],
        provider: 'sentinel2', summary: 'Roofing / enclosure detected between 2025-01-14 and 2025-03-25 via Sentinel-2 10m NDVI change analysis.',
        rationale: ['NDVI increase - higher reflectance surface detected', 'Pattern consistent with new roofing or impervious material', 'Affected area ~800 m\u00b2'],
        before_image: null, after_image: null, thumbnail: null,
        scene_id_before: 'S2A_38RPN_20250114_0_L2A', scene_id_after: 'S2C_38RPN_20250325_0_L2A', resolution_m: 10, warnings: [],
      },
    ],
    stats: { total_changes: 8, avg_confidence: 71.9, change_types: ['Roofing / enclosure', 'Site clearing / earthwork'], is_demo: false },
  };
  saveToHistory(livePayload, liveResult);
}

(async () => {
  seedHistoryIfEmpty();
  renderHistory();
  await loadConfig();
  await loadProviders();
})();

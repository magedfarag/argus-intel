// ─── State ──────────────────────────────────────────────────────────────────
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

// ─── Job Polling ──────────────────────────────────────────────────────────────
const POLL_INTERVAL_MS = 3000;

function startPoll(jobId) {
  cancelPoll();
  state.pollTimer = setInterval(() => pollJob(jobId), POLL_INTERVAL_MS);
}

function cancelPoll() {
  if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
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
        `Processing… (${job.state})`;
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
      <div class="result-images">
        <div><div class="muted" style="margin-bottom:4px;">Before</div>
          ${ch.before_image ? `<img src="${ch.before_image}" alt="Before" />` : '<div class="img-placeholder">No image</div>'}
        </div>
        <div><div class="muted" style="margin-bottom:4px;">After</div>
          ${ch.after_image ? `<img src="${ch.after_image}" alt="After" />` : '<div class="img-placeholder">No image</div>'}
        </div>
      </div>
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
(async () => {
  await loadConfig();
  await loadProviders();
})();

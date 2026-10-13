import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import { api, ApiError, API_BASE_URL } from './api';
import type { AuditRecord, ClinicalEvent, FeatureSnapshot, Prediction, TwinState, TwinSummary } from './types';

type ConnectionState = 'checking' | 'online' | 'offline';

const localDateTime = () => {
  const now = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000);
  return now.toISOString().slice(0, 19);
};

const nextEventId = () => `evt_${Date.now().toString(36)}`;
const readable = (value: string) => value.toLowerCase().replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase());
const displayValue = (value: unknown) => value === null ? 'Missing' : typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value);

const formatDateTime = (value: string) => {
  const d = new Date(value);
  const today = new Date();
  const isToday = d.toDateString() === today.toDateString();
  if (isToday) {
    return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', hour12: true }).format(d).toLowerCase();
  }
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true }).format(d);
};

function App() {
  const [connection, setConnection] = useState<ConnectionState>('checking');
  const [storageReady, setStorageReady] = useState<boolean | null>(null);
  const [twins, setTwins] = useState<TwinSummary[]>([]);
  const [selectedTwin, setSelectedTwin] = useState('');
  const [state, setState] = useState<TwinState | null>(null);
  const [events, setEvents] = useState<ClinicalEvent[]>([]);
  const [snapshots, setSnapshots] = useState<FeatureSnapshot[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [audits, setAudits] = useState<AuditRecord[]>([]);
  const [newTwinId, setNewTwinId] = useState('SYNTHETIC_TWIN_001');
  const [eventId, setEventId] = useState(nextEventId);
  const [eventType, setEventType] = useState<ClinicalEvent['event_type']>('PATHOLOGY_RESULT');
  const [effectiveTime, setEffectiveTime] = useState(localDateTime);
  const [qualityStatus, setQualityStatus] = useState<ClinicalEvent['quality_status']>('valid');
  const [payload, setPayload] = useState(JSON.stringify({ tumour_size_mm: 20, grade: 2, positive_nodes: 0 }, null, 2));

  // Selected prediction for detail view (default to latest)
  const [selectedPredictionId, setSelectedPredictionId] = useState<string | null>(null);

  // Expanded audit row
  const [expandedAuditId, setExpandedAuditId] = useState<string | null>(null);

  // Expanded snapshot row
  const [expandedSnapshotId, setExpandedSnapshotId] = useState<string | null>(null);

  // Loading state for twin detail refresh
  const [loadingDetails, setLoadingDetails] = useState(false);

  // Pagination offsets
  const [eventsOffset, setEventsOffset] = useState(0);
  const [eventsTotal, setEventsTotal] = useState(0);
  const PAGE_SIZE = 50;

  // Auto-populate JSON payload templates based on the event type selected
  const handleEventTypeChange = (type: ClinicalEvent['event_type']) => {
    setEventType(type);
    if (type === 'PATHOLOGY_RESULT') {
      setPayload(JSON.stringify({ tumour_size_mm: 20, grade: 2, positive_nodes: 0 }, null, 2));
    } else if (type === 'BIOMARKER_RESULT') {
      setPayload(JSON.stringify({ er_status: 'positive', pr_status: 'positive', her2_status: 'negative' }, null, 2));
    } else if (type === 'TREATMENT') {
      setPayload(JSON.stringify({ treatment_type: 'surgery', intent: 'curative' }, null, 2));
    } else {
      setPayload(JSON.stringify({}, null, 2));
    }
  };

  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const showError = (reason: unknown) => {
    setNotice('');
    setError(reason instanceof Error ? reason.message : 'Something went wrong.');
  };

  const refreshTwins = useCallback(async (preferredTwin?: string) => {
    const page = await api.listTwins();
    setTwins(page.items);
    setSelectedTwin((current) => preferredTwin || current || page.items[0]?.twin_id || '');
  }, []);

  const refreshDetails = useCallback(async (twinId: string, offset = 0) => {
    if (!twinId) return;
    setError('');
    setLoadingDetails(true);
    try {
      const [stateResult, eventsResult, snapshotsResult, predictionsResult, auditsResult] = await Promise.allSettled([
        api.getState(twinId),
        api.listEvents(twinId, PAGE_SIZE, offset),
        api.listSnapshots(twinId),
        api.listPredictions(twinId),
        api.listAudits(twinId),
      ]);
      if (stateResult.status === 'fulfilled') setState(stateResult.value);
      else if (stateResult.reason instanceof ApiError && stateResult.reason.status === 409) setState(null);
      else showError(stateResult.reason);
      if (eventsResult.status === 'fulfilled') {
        setEvents(eventsResult.value.items);
        setEventsTotal(eventsResult.value.total);
      }
      if (snapshotsResult.status === 'fulfilled') setSnapshots(snapshotsResult.value.items);
      if (predictionsResult.status === 'fulfilled') {
        const preds = predictionsResult.value.items;
        setPredictions(preds);
        // Default to latest prediction
        setSelectedPredictionId((cur) => cur && preds.find(p => p.prediction_id === cur) ? cur : preds[0]?.prediction_id ?? null);
      }
      if (auditsResult.status === 'fulfilled') setAudits(auditsResult.value.items);
    } finally {
      setLoadingDetails(false);
    }
  }, []);

  const checkStorage = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL.replace(/\/api\/v1$/, '')}/ready`, { headers: { Accept: 'application/json' } });
      setStorageReady(res.ok);
    } catch {
      setStorageReady(false);
    }
  }, []);

  const connect = useCallback(async () => {
    setConnection('checking');
    setError('');
    const online = await api.health();
    setConnection(online ? 'online' : 'offline');
    if (!online) return;
    await checkStorage();
    try {
      await refreshTwins();
    } catch (reason) {
      showError(reason);
    }
  }, [refreshTwins, checkStorage]);

  useEffect(() => {
    void connect();
  }, [connect]);

  useEffect(() => {
    if (selectedTwin) {
      setEventsOffset(0);
      void refreshDetails(selectedTwin, 0);
      // Update browser tab title
      document.title = `${selectedTwin} — OncoTwin BRCA`;
    } else {
      document.title = 'OncoTwin-BRCA Dashboard';
    }
  }, [selectedTwin, refreshDetails]);

  const currentTwin = twins.find((twin) => twin.twin_id === selectedTwin);
  const selectedPrediction = predictions.find(p => p.prediction_id === selectedPredictionId) ?? predictions[0] ?? null;
  const latestSnapshot = snapshots[0];
  const trajectory = useMemo(() => [...predictions].reverse(), [predictions]);

  // Normalize SHAP bar widths to max absolute value
  const maxAbsShap = useMemo(() => {
    if (!selectedPrediction?.shap_values?.length) return 1;
    return Math.max(...selectedPrediction.shap_values.map(sv => Math.abs(sv.value)), 0.001);
  }, [selectedPrediction]);

  const run = async (name: string, action: () => Promise<void>) => {
    setBusy(name);
    setError('');
    setNotice('');
    try {
      await action();
    } catch (reason) {
      showError(reason);
    } finally {
      setBusy('');
    }
  };

  const createTwin = (formEvent: FormEvent) => {
    formEvent.preventDefault();
    const twinId = newTwinId.trim();
    if (!twinId) return;
    void run('twin', async () => {
      await api.createTwin(twinId);
      await refreshTwins(twinId);
      setNotice(`Twin ${twinId} created.`);
    });
  };

  const appendEvent = (formEvent: FormEvent) => {
    formEvent.preventDefault();
    if (!selectedTwin) return;
    void run('event', async () => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(payload);
      } catch {
        throw new Error('Payload is not valid JSON.');
      }
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('Payload must be a JSON object.');
      }
      const now = new Date().toISOString();
      const newEventId = eventId.trim();
      const clinicalEvent: ClinicalEvent = {
        schema_version: '0.1.0',
        twin_id: selectedTwin,
        event_id: newEventId,
        event_type: eventType,
        effective_time: effectiveTime.includes('Z') ? effectiveTime : new Date(effectiveTime).toISOString(),
        received_time: now,
        source: 'synthetic-dashboard',
        quality_status: qualityStatus,
        provenance: {
          source_system: 'oncotwin-frontend',
          source_record_id: newEventId,
          data_version: 'synthetic-0.1.0',
        },
        payload: parsed as ClinicalEvent['payload'],
      };
      await api.appendEvent(selectedTwin, clinicalEvent, currentTwin?.state_version ?? 0);
      // Always reset event ID (including on retry after 409)
      setEventId(nextEventId());
      setEffectiveTime(localDateTime());
      await Promise.all([refreshTwins(selectedTwin), refreshDetails(selectedTwin)]);
      setNotice('Clinical event accepted and the twin state was rebuilt.');
    });
  };

  const createSnapshot = () => void run('snapshot', async () => {
    await api.createSnapshot(selectedTwin);
    await refreshDetails(selectedTwin);
    setNotice('Feature snapshot created from the current state.');
  });

  const createPrediction = () => void run('prediction', async () => {
    if (!latestSnapshot) throw new Error('Create a feature snapshot first.');
    const pred = await api.createPrediction(selectedTwin, latestSnapshot.snapshot_id);
    await refreshDetails(selectedTwin);
    setSelectedPredictionId(pred.prediction_id);
    setNotice('Mock prediction and linked audit record created.');
  });

  const handleRefresh = () => {
    void run('refresh', async () => {
      await refreshTwins(selectedTwin);
      if (selectedTwin) await refreshDetails(selectedTwin);
      setNotice('Data refreshed.');
    });
  };

  const loadMoreEvents = () => {
    const nextOffset = eventsOffset + PAGE_SIZE;
    setEventsOffset(nextOffset);
    void refreshDetails(selectedTwin, nextOffset);
  };

  const loadPrevEvents = () => {
    const prevOffset = Math.max(0, eventsOffset - PAGE_SIZE);
    setEventsOffset(prevOffset);
    void refreshDetails(selectedTwin, prevOffset);
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#main" aria-label="OncoTwin BRCA dashboard home">
          <span className="brand-mark" aria-hidden="true">OT</span>
          <span>OncoTwin <strong>BRCA</strong></span>
        </a>
        <div className="topbar-right">
          <button
            className="refresh-button"
            onClick={handleRefresh}
            disabled={busy === 'refresh' || connection !== 'online'}
            aria-label="Refresh all data"
            title="Refresh all data"
          >
            {busy === 'refresh' ? '↻' : '↻'} Refresh
          </button>
          <div className={`connection ${connection}`} role="status">
            <span aria-hidden="true" />
            {connection === 'checking' ? 'Checking API' : connection === 'online' ? 'Backend connected' : 'Backend offline'}
          </div>
        </div>
      </header>

      <div className="research-banner">
        <strong>Research prototype</strong>
        Synthetic data and mock model outputs only. No clinical use or treatment guidance.
      </div>

      {connection === 'online' && storageReady === false && (
        <div className="storage-warning" role="alert">
          <strong>⚠ Storage degraded</strong> — the backend storage layer is not ready. Data may not persist.
        </div>
      )}

      <div className="layout">
        <aside className="sidebar" aria-label="Twin navigation">
          <div className="sidebar-heading">
            <div><span className="kicker">Workspace</span><h2>Digital twins</h2></div>
            <span className="count">{twins.length}</span>
          </div>
          <div className="twin-list">
            {twins.length === 0 && <p className="empty-copy">No twins yet. Create the first synthetic twin below.</p>}
            {twins.map((twin) => (
              <button
                className={`twin-item ${selectedTwin === twin.twin_id ? 'active' : ''}`}
                key={twin.twin_id}
                onClick={() => setSelectedTwin(twin.twin_id)}
              >
                <span className="avatar" aria-hidden="true">{twin.twin_id.slice(0, 2).toUpperCase()}</span>
                <span><strong>{twin.twin_id}</strong><small>State v{twin.state_version}</small></span>
              </button>
            ))}
          </div>
          <form className="create-twin" onSubmit={createTwin}>
            <label htmlFor="new-twin">New synthetic twin ID</label>
            <div className="inline-input">
              <input id="new-twin" value={newTwinId} onChange={(e) => setNewTwinId(e.target.value)} />
              <button className="icon-button" disabled={busy === 'twin' || connection !== 'online'} aria-label="Create twin">+</button>
            </div>
          </form>
          <p className="lifecycle-hint">
            ℹ In-memory store resets on server restart. Use <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">/docs</a> for API access.
          </p>
          <p className="api-location">API <code>{API_BASE_URL}</code></p>
        </aside>

        <main id="main" className="content">
          <div aria-live="polite" className="messages">
            {error && <div className="message error" role="alert"><strong>Action needed</strong><span>{error}</span></div>}
            {notice && <div className="message success"><strong>Completed</strong><span>{notice}</span></div>}
          </div>

          {connection !== 'online' ? (
            <section className="welcome-card">
              <span className="welcome-icon" aria-hidden="true">{connection === 'checking' ? '…' : '!'}</span>
              <h1>{connection === 'checking' ? 'Connecting to backend' : 'Backend is offline'}</h1>
              <p>{connection === 'checking' ? 'Checking the research API before loading twins.' : 'Start the FastAPI service on port 8000, then try again.'}</p>
              {connection === 'offline' && <button className="primary-button" onClick={() => void connect()}>Retry connection</button>}
            </section>
          ) : !selectedTwin ? (
            <section className="welcome-card">
              <span className="welcome-icon" aria-hidden="true">◎</span>
              <h1>Create your first digital twin</h1>
              <p>Start with a synthetic identifier, then add a clinical event to build its state.</p>
            </section>
          ) : (
            <>
              <section className="page-heading">
                <div>
                  <span className="kicker">Synthetic patient workspace</span>
                  <h1>{selectedTwin}</h1>
                  <p>Versioned event history, features, mock predictions, and audit lineage.</p>
                </div>
                <span className="version-badge">State version {currentTwin?.state_version ?? 0}</span>
              </section>

              {loadingDetails && <div className="loading-bar" aria-label="Loading data…" role="status"><span /></div>}

              <section className="metric-grid" aria-label="Twin summary">
                <article className="metric-card accent">
                  <span className="metric-label">Mock risk output</span>
                  <strong>{selectedPrediction ? `${Math.round(selectedPrediction.risk_probability * 100)}%` : '—'}</strong>
                  <small>{selectedPrediction ? `${selectedPrediction.horizon_months}-month horizon` : 'No prediction created'}</small>
                </article>
                <article className="metric-card">
                  <span className="metric-label">Accepted events</span><strong>{eventsTotal || events.length}</strong>
                  <small>{state ? `As of ${formatDateTime(state.as_of)}` : 'Waiting for first event'}</small>
                </article>
                <article className="metric-card">
                  <span className="metric-label">Feature snapshots</span><strong>{snapshots.length}</strong>
                  <small>{latestSnapshot ? latestSnapshot.feature_set_version : 'None created'}</small>
                </article>
                <article className="metric-card">
                  <span className="metric-label">Missing fields</span><strong>{state?.missing_fields.length ?? 0}</strong>
                  <small>{state?.missing_fields.join(', ') || 'No missing values recorded'}</small>
                </article>
              </section>

              <div className="dashboard-grid">
                {/* ── Event input panel ── */}
                <section className="panel event-panel">
                  <div className="panel-heading"><div><span className="kicker">Input</span><h2>Add clinical event</h2></div></div>
                  <form onSubmit={appendEvent}>
                    <div className="form-grid">
                      <label>Event ID<input required value={eventId} onChange={(e) => setEventId(e.target.value)} /></label>
                      <label>Event type<select value={eventType} onChange={(e) => handleEventTypeChange(e.target.value as ClinicalEvent['event_type'])}>
                        {(['PATHOLOGY_RESULT', 'DIAGNOSIS', 'BIOMARKER_RESULT', 'TREATMENT', 'FOLLOW_UP'] as const).map((item) => <option key={item}>{item}</option>)}
                      </select></label>
                      <label>Effective time<input required type="datetime-local" step="1" value={effectiveTime} onChange={(e) => setEffectiveTime(e.target.value)} /></label>
                      <label>Quality<select value={qualityStatus} onChange={(e) => setQualityStatus(e.target.value as ClinicalEvent['quality_status'])}>
                        <option value="valid">Valid</option><option value="warning">Warning</option>
                      </select></label>
                    </div>
                    <label>Clinical payload (JSON)<textarea rows={7} value={payload} onChange={(e) => setPayload(e.target.value)} spellCheck="false" /></label>
                    <button className="primary-button" disabled={busy === 'event'}>{busy === 'event' ? 'Submitting…' : 'Accept event & rebuild state'}</button>
                  </form>
                </section>

                {/* ── Snapshot & inference pipeline ── */}
                <section className="panel workflow-panel">
                  <div className="panel-heading"><div><span className="kicker">Pipeline</span><h2>Snapshot and inference</h2></div></div>
                  <div className="workflow-step"><span>1</span><div><strong>Current state</strong><small>{state ? `Ready at version ${state.state_version}` : 'Add an accepted event'}</small></div><b className={state ? 'done' : ''}>{state ? '✓' : '○'}</b></div>
                  <div className="workflow-step"><span>2</span><div><strong>Feature snapshot</strong><small>{latestSnapshot ? latestSnapshot.snapshot_id : 'Capture immutable model inputs'}</small></div><b className={latestSnapshot ? 'done' : ''}>{latestSnapshot ? '✓' : '○'}</b></div>
                  <button className="secondary-button" onClick={createSnapshot} disabled={!state || busy === 'snapshot'}>{busy === 'snapshot' ? 'Creating…' : 'Create feature snapshot'}</button>
                  <div className="workflow-step"><span>3</span><div><strong>Mock prediction</strong><small>{selectedPrediction ? selectedPrediction.model_version : 'Run the connected mock adapter'}</small></div><b className={selectedPrediction ? 'done' : ''}>{selectedPrediction ? '✓' : '○'}</b></div>
                  <button className="primary-button" onClick={createPrediction} disabled={!latestSnapshot || busy === 'prediction'}>{busy === 'prediction' ? 'Generating…' : 'Generate mock prediction'}</button>
                </section>

                {/* ── Current twin state ── */}
                <section className="panel state-panel">
                  <div className="panel-heading"><div><span className="kicker">Digital twin</span><h2>Current state</h2></div><span>{state?.data_version}</span></div>
                  {!state ? <p className="empty-copy">The twin has no accepted events, so a state cannot be reconstructed yet.</p> : (
                    <div className="value-list">
                      {Object.entries(state.values).map(([key, value]) => <div className={value === null ? 'missing' : ''} key={key}><span>{readable(key)}</span><strong>{displayValue(value)}</strong></div>)}
                    </div>
                  )}
                  {!!state?.quality_warnings.length && <div className="warning-box"><strong>Quality notes</strong>{state.quality_warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>}
                </section>

                {/* ── Prediction detail panel ── */}
                <section className="panel prediction-panel">
                  <div className="panel-heading">
                    <div><span className="kicker">Model output</span><h2>Prediction detail</h2></div>
                    {selectedPrediction?.is_mock && <span className="mock-badge">Mock</span>}
                  </div>
                  {!selectedPrediction ? <p className="empty-copy">Create a snapshot and run mock inference to see a result.</p> : <>
                    <div className="risk-row">
                      <div
                        className="risk-ring"
                        style={{ '--risk': `${selectedPrediction.risk_probability * 100}%` } as React.CSSProperties}
                        aria-label={`${Math.round(selectedPrediction.risk_probability * 100)}% mock risk at ${selectedPrediction.horizon_months} months`}
                        role="img"
                      >
                        <span>{Math.round(selectedPrediction.risk_probability * 100)}<small>%</small></span>
                      </div>
                      <div>
                        <strong>{selectedPrediction.horizon_months}-month survival risk</strong>
                        <p>Confidence: {readable(selectedPrediction.confidence)}</p>
                        <p>Model: {selectedPrediction.model_name} {selectedPrediction.model_version}</p>
                        <p className="prediction-id-label">ID: <code>{selectedPrediction.prediction_id}</code></p>
                      </div>
                    </div>
                    {selectedPrediction.warnings?.map((warning) => <p className="model-warning" key={warning}>{warning}</p>)}

                    {selectedPrediction.shap_values && selectedPrediction.shap_values.length > 0 && (
                      <div className="shap-values">
                        <div className="shap-header">
                          <h3>Feature Contributions (SHAP)</h3>
                          <div className="shap-legend">
                            <span className="shap-legend-item positive">▌ Increases risk</span>
                            <span className="shap-legend-item negative">▌ Decreases risk</span>
                          </div>
                        </div>
                        <p className="shap-note">SHAP values explain model behaviour, not clinical causality.</p>
                        <div className="shap-bars">
                          {selectedPrediction.shap_values.map((sv) => (
                            <div key={sv.feature} className="shap-bar-row">
                              <span className="shap-feature" title={readable(sv.feature)}>{readable(sv.feature)}</span>
                              <div className="shap-bar-container" aria-label={`${readable(sv.feature)}: ${sv.value > 0 ? '+' : ''}${sv.value.toFixed(3)}`}>
                                <div
                                  className={`shap-bar ${sv.value > 0 ? 'positive' : 'negative'}`}
                                  style={{ width: `${Math.abs(sv.value) / maxAbsShap * 100}%` }}
                                />
                              </div>
                              <span className="shap-value">{sv.value > 0 ? '+' : ''}{sv.value.toFixed(3)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>}

                  {/* Prediction history — clickable bars */}
                  {trajectory.length >= 2 && (
                    <div className="trajectory">
                      <h3>Prediction history <small>(click to inspect)</small></h3>
                      <div className="bars" aria-label="Historical mock risk probabilities">
                        {trajectory.map((item) => (
                          <button
                            key={item.prediction_id}
                            className={`bar-btn ${item.prediction_id === selectedPredictionId ? 'selected' : ''}`}
                            onClick={() => setSelectedPredictionId(item.prediction_id)}
                            aria-pressed={item.prediction_id === selectedPredictionId}
                            title={`v${item.state_version}: ${Math.round(item.risk_probability * 100)}% risk`}
                            aria-label={`Select prediction at state version ${item.state_version}, ${Math.round(item.risk_probability * 100)}% risk`}
                          >
                            <span style={{ height: `${Math.max(item.risk_probability * 100, 4)}%` }} />
                            <small>v{item.state_version}</small>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </section>

                {/* ── Feature snapshots panel ── */}
                <section className="panel snapshots-panel">
                  <div className="panel-heading"><div><span className="kicker">Inputs</span><h2>Feature snapshots</h2></div><span>{snapshots.length} total</span></div>
                  {snapshots.length === 0 ? <p className="empty-copy">Snapshots capture immutable model inputs from the current state.</p> : (
                    <div className="snapshot-list">
                      {snapshots.map((snap) => (
                        <div key={snap.snapshot_id} className="snapshot-item">
                          <button
                            className="snapshot-header"
                            onClick={() => setExpandedSnapshotId(expandedSnapshotId === snap.snapshot_id ? null : snap.snapshot_id)}
                            aria-expanded={expandedSnapshotId === snap.snapshot_id}
                          >
                            <div>
                              <strong>{snap.snapshot_id}</strong>
                              <small>{snap.feature_set_version} · State v{snap.state_version} · {formatDateTime(snap.created_at)}</small>
                            </div>
                            <span className="expand-icon">{expandedSnapshotId === snap.snapshot_id ? '▲' : '▼'}</span>
                          </button>
                          {expandedSnapshotId === snap.snapshot_id && (
                            <div className="snapshot-detail">
                              {snap.missing_fields.length > 0 && (
                                <div className="warning-box"><strong>Missing fields</strong><p>{snap.missing_fields.join(', ')}</p></div>
                              )}
                              <div className="value-list">
                                {Object.entries(snap.features).map(([k, v]) => (
                                  <div className={v === null ? 'missing' : ''} key={k}>
                                    <span>{readable(k)}</span><strong>{displayValue(v)}</strong>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </section>

                {/* ── Clinical event timeline ── */}
                <section className="panel timeline-panel">
                  <div className="panel-heading"><div><span className="kicker">History</span><h2>Clinical events</h2></div><span>{eventsTotal || events.length} total</span></div>
                  {events.length === 0 ? <p className="empty-copy">Accepted events will appear here in replay order.</p> : (
                    <>
                      <ol className="timeline">
                        {events.map((item) => (
                          <li key={item.event_id}>
                            <span className={`quality-dot ${item.quality_status}`} />
                            <div>
                              <strong>{readable(item.event_type)}</strong>
                              <p>{item.event_id}</p>
                              <time dateTime={item.effective_time}>{formatDateTime(item.effective_time)}</time>
                            </div>
                            <span className="quality-label">{item.quality_status}</span>
                          </li>
                        ))}
                      </ol>
                      {eventsTotal > PAGE_SIZE && (
                        <div className="pagination">
                          <button className="secondary-button" disabled={eventsOffset === 0} onClick={loadPrevEvents}>← Prev</button>
                          <span>{eventsOffset + 1}–{Math.min(eventsOffset + PAGE_SIZE, eventsTotal)} of {eventsTotal}</span>
                          <button className="secondary-button" disabled={eventsOffset + PAGE_SIZE >= eventsTotal} onClick={loadMoreEvents}>Next →</button>
                        </div>
                      )}
                    </>
                  )}
                </section>

                {/* ── Audit records panel ── */}
                <section className="panel audit-panel">
                  <div className="panel-heading"><div><span className="kicker">Traceability</span><h2>Prediction audits</h2></div><span>{audits.length} records</span></div>
                  {audits.length === 0 ? <p className="empty-copy">A linked audit is saved atomically with every prediction.</p> : (
                    <div className="audit-list">
                      {audits.map((audit) => (
                        <article key={audit.audit_id}>
                          <span className="audit-icon" aria-hidden="true">✓</span>
                          <div>
                            <button
                              className="audit-header-btn"
                              onClick={() => setExpandedAuditId(expandedAuditId === audit.audit_id ? null : audit.audit_id)}
                              aria-expanded={expandedAuditId === audit.audit_id}
                            >
                              <strong>{readable(audit.action)}</strong>
                              <p>{audit.audit_id}</p>
                              <small>State v{audit.state_version} · {formatDateTime(audit.recorded_at)}</small>
                              <span className="expand-icon">{expandedAuditId === audit.audit_id ? '▲' : '▼'}</span>
                            </button>
                            {expandedAuditId === audit.audit_id && (
                              <div className="audit-detail">
                                <dl>
                                  <dt>Prediction ID</dt><dd><code>{audit.prediction_id || '—'}</code></dd>
                                  <dt>Snapshot ID</dt><dd><code>{audit.snapshot_id || '—'}</code></dd>
                                  <dt>Model version</dt><dd>{audit.model_version || '—'}</dd>
                                  <dt>Data version</dt><dd>{audit.data_version}</dd>
                                  <dt>Actor</dt><dd>{audit.actor}</dd>
                                  <dt>Event IDs ({audit.event_ids.length})</dt>
                                  <dd><code className="event-ids-list">{audit.event_ids.join(', ') || '—'}</code></dd>
                                </dl>
                              </div>
                            )}
                          </div>
                        </article>
                      ))}
                    </div>
                  )}
                </section>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;

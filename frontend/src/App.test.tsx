import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';
import { api, ApiError } from './api';

// Default timeout for all waitFor calls
const WAIT = { timeout: 3000 };

// Stub fetch globally to intercept /ready calls (api.* calls go through the vi.mock below).
// Default to a 200 ok so that any test that doesn't call checkStorage still resolves.
const mockFetch = vi.fn(() =>
  Promise.resolve(new Response(JSON.stringify({ status: 'ready' }), { status: 200 }))
);
vi.stubGlobal('fetch', mockFetch);

// ── Mock the entire API module ──────────────────────────────────────────────
vi.mock('./api', () => ({
  API_BASE_URL: 'http://localhost:8000/api/v1',
  ApiError: class extends Error {
    constructor(public status: number, message: string) {
      super(message);
      this.name = 'ApiError';
    }
  },
  api: {
    health: vi.fn(),
    getModelInfo: vi.fn(),
    listTwins: vi.fn(),
    createTwin: vi.fn(),
    listEvents: vi.fn(),
    appendEvent: vi.fn(),
    getState: vi.fn(),
    listSnapshots: vi.fn(),
    createSnapshot: vi.fn(),
    listPredictions: vi.fn(),
    createPrediction: vi.fn(),
    listAudits: vi.fn(),
  },
}));

// ── Shared fixtures ─────────────────────────────────────────────────────────
const emptyPage = { items: [], total: 0, limit: 50, offset: 0 };

const mockTwin = { twin_id: 'TWIN_001', state_version: 1 };

const mockState = {
  schema_version: '0.1.0' as const,
  twin_id: 'TWIN_001',
  state_version: 1,
  as_of: '2026-09-01T10:00:00Z',
  event_ids: ['evt_1'],
  data_version: 'synthetic-0.1.0',
  values: { tumour_size_mm: 20, grade: 2, positive_nodes: null },
  missing_fields: ['positive_nodes'],
  quality_warnings: [],
};

const mockSnapshot = {
  schema_version: '0.1.0' as const,
  twin_id: 'TWIN_001',
  snapshot_id: 'snap_abc',
  state_version: 1,
  created_at: '2026-09-01T10:05:00Z',
  data_version: 'synthetic-0.1.0',
  feature_set_version: 'brca-features-0.1.0',
  features: { tumour_size_mm: 20, grade: 2, positive_nodes: null },
  missing_fields: ['positive_nodes'],
};

const mockPrediction = {
  schema_version: '0.1.0' as const,
  twin_id: 'TWIN_001',
  prediction_id: 'pred_xyz',
  snapshot_id: 'snap_abc',
  state_version: 1,
  data_version: 'synthetic-0.1.0',
  audit_id: 'audit_001',
  created_at: '2026-09-01T10:10:00Z',
  model_name: 'MockBRCAModel',
  model_version: '0.0.1-mock',
  is_mock: true,
  risk_probability: 0.42,
  horizon_months: 60,
  confidence: 'not_assessed' as const,
  ood_flag: null,
  shap_values: [
    { feature: 'tumour_size_mm', value: 0.35 },
    { feature: 'grade', value: -0.12 },
  ],
  warnings: ['Mock output — not a clinical result.'],
};

const mockAudit = {
  schema_version: '0.1.0' as const,
  twin_id: 'TWIN_001',
  audit_id: 'audit_001',
  recorded_at: '2026-09-01T10:10:00Z',
  action: 'PREDICTION_CREATED' as const,
  actor: 'oncotwin-backend',
  event_ids: ['evt_1'],
  state_version: 1,
  snapshot_id: 'snap_abc',
  prediction_id: 'pred_xyz',
  model_version: '0.0.1-mock',
  data_version: 'synthetic-0.1.0',
};

const mockModelInfo = {
  status: 'ok',
  inference_mode: 'mock',
  model_name: 'MockBRCAModel',
  model_version: '0.0.1-mock',
};

// ── Setup helpers ───────────────────────────────────────────────────────────
// /ready is fetched directly (not through the api mock), so stub fetch here
function stubReady(ok = true) {
  mockFetch.mockResolvedValue(new Response(JSON.stringify({ status: 'ready' }), { status: ok ? 200 : 503 }));
}

function setupEmptyOnline() {
  stubReady();
  vi.mocked(api.health).mockResolvedValue(true);
  vi.mocked(api.getModelInfo).mockResolvedValue(mockModelInfo);
  vi.mocked(api.listTwins).mockResolvedValue(emptyPage);
  vi.mocked(api.listEvents).mockResolvedValue(emptyPage);
  vi.mocked(api.getState).mockRejectedValue(new ApiError(409, 'Twin has no accepted events.'));
  vi.mocked(api.listSnapshots).mockResolvedValue(emptyPage);
  vi.mocked(api.listPredictions).mockResolvedValue(emptyPage);
  vi.mocked(api.listAudits).mockResolvedValue(emptyPage);
}

function setupWithTwin() {
  stubReady();
  vi.mocked(api.health).mockResolvedValue(true);
  vi.mocked(api.getModelInfo).mockResolvedValue(mockModelInfo);
  vi.mocked(api.listTwins).mockResolvedValue({ items: [mockTwin], total: 1, limit: 50, offset: 0 });
  vi.mocked(api.listEvents).mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
  vi.mocked(api.getState).mockResolvedValue(mockState);
  vi.mocked(api.listSnapshots).mockResolvedValue({ items: [mockSnapshot], total: 1, limit: 50, offset: 0 });
  vi.mocked(api.listPredictions).mockResolvedValue({ items: [mockPrediction], total: 1, limit: 50, offset: 0 });
  vi.mocked(api.listAudits).mockResolvedValue({ items: [mockAudit], total: 1, limit: 50, offset: 0 });
}

// ── Tests ───────────────────────────────────────────────────────────────────
describe('App — connection states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Restore default fetch stub after clearAllMocks resets it
    mockFetch.mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({ status: 'ready' }), { status: 200 }))
    );
  });
  afterEach(() => vi.clearAllMocks());

  it('shows checking state then backend-connected when health passes', async () => {
    setupEmptyOnline();
    render(<App />);
    expect(screen.getByText('Checking API')).toBeDefined();
    await waitFor(() => expect(screen.getByText('Backend connected')).toBeDefined(), WAIT);
  });

  it('shows offline state and retry button when health fails', async () => {
    vi.mocked(api.health).mockResolvedValue(false);
    render(<App />);
    await waitFor(() => expect(screen.getByText('Backend offline')).toBeDefined());
    expect(screen.getByRole('button', { name: /retry connection/i })).toBeDefined();
  });

  it('retries connection when retry button is clicked', async () => {
    vi.mocked(api.health).mockResolvedValue(false);
    render(<App />);
    await waitFor(() => expect(screen.getByRole('button', { name: /retry connection/i })).toBeDefined());

    vi.mocked(api.health).mockResolvedValue(true);
    vi.mocked(api.listTwins).mockResolvedValue(emptyPage);
    fireEvent.click(screen.getByRole('button', { name: /retry connection/i }));

    await waitFor(() => expect(screen.getByText('Backend connected')).toBeDefined());
  });
});

describe('App — empty / no-twins state', () => {
  beforeEach(() => { vi.clearAllMocks(); setupEmptyOnline(); });

  it('shows welcome card when no twin is selected', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Create your first digital twin/i)).toBeDefined());
  });

  it('shows "No twins yet" hint in sidebar', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText(/No twins yet/i)).toBeDefined());
  });
});

describe('App — twin creation', () => {
  beforeEach(() => vi.clearAllMocks());

  it('creates a twin and shows success notice', async () => {
    setupEmptyOnline();
    vi.mocked(api.createTwin).mockResolvedValue({ twin_id: 'TWIN_NEW', status: 'created' });
    vi.mocked(api.listTwins).mockResolvedValueOnce(emptyPage).mockResolvedValue({ items: [{ twin_id: 'TWIN_NEW', state_version: 0 }], total: 1, limit: 50, offset: 0 });

    render(<App />);
    await waitFor(() => expect(screen.getByText('Backend connected')).toBeDefined());

    const input = screen.getByLabelText(/New synthetic twin ID/i);
    fireEvent.change(input, { target: { value: 'TWIN_NEW' } });
    fireEvent.click(screen.getByRole('button', { name: /Create twin/i }));

    await waitFor(() => expect(screen.getByText(/Twin TWIN_NEW created/i)).toBeDefined());
    expect(api.createTwin).toHaveBeenCalledWith('TWIN_NEW');
  });

  it('shows error when twin creation fails', async () => {
    setupEmptyOnline();
    vi.mocked(api.createTwin).mockRejectedValue(new ApiError(409, 'Twin already exists.'));

    render(<App />);
    await waitFor(() => expect(screen.getByText('Backend connected')).toBeDefined());
    fireEvent.click(screen.getByRole('button', { name: /Create twin/i }));

    await waitFor(() => expect(screen.getByText('Twin already exists.')).toBeDefined());
  });
});

describe('App — twin detail view', () => {
  beforeEach(() => { vi.clearAllMocks(); setupWithTwin(); });

  it('renders metric cards with correct data after selecting a twin', async () => {
    render(<App />);
    // Twin is auto-selected (first item) — wait for detail data to load
    await waitFor(() => expect(screen.getByText('42%')).toBeDefined(), WAIT);
    expect(screen.getByText('60-month horizon')).toBeDefined();
  });

  it('shows missing values highlighted in the state panel', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText('Missing')).toBeDefined(), WAIT);
  });

  it('shows the state version badge', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText(/State version 1/i)).toBeDefined(), WAIT);
  });
});

describe('App — clinical event form', () => {
  beforeEach(() => { vi.clearAllMocks(); setupWithTwin(); });

  it('submits an event and shows rebuild notice', async () => {
    vi.mocked(api.appendEvent).mockResolvedValue({ twin_id: 'TWIN_001', event_id: 'evt_new', status: 'accepted', state_version: 2 });

    render(<App />);
    await waitFor(() => fireEvent.click(screen.getAllByText('TWIN_001')[0]));
    await waitFor(() => screen.getByText(/Accept event/i));

    fireEvent.click(screen.getByText(/Accept event & rebuild state/i));
    await waitFor(() => expect(screen.getByText(/Clinical event accepted/i)).toBeDefined());
    expect(api.appendEvent).toHaveBeenCalledOnce();
  });

  it('shows error when payload is invalid JSON', async () => {
    render(<App />);
    await waitFor(() => fireEvent.click(screen.getAllByText('TWIN_001')[0]));
    await waitFor(() => screen.getByText(/Accept event/i));

    // Find the textarea by querying all textareas
    const textareas = document.querySelectorAll('textarea');
    fireEvent.change(textareas[0], { target: { value: 'not-json{{{' } });
    fireEvent.click(screen.getByText(/Accept event & rebuild state/i));

    await waitFor(() => expect(screen.getByText(/not valid JSON/i)).toBeDefined());
  });

  it('shows a server error when append fails', async () => {
    vi.mocked(api.appendEvent).mockRejectedValue(new ApiError(412, 'State version conflict. Current version is 2.'));

    render(<App />);
    await waitFor(() => fireEvent.click(screen.getAllByText('TWIN_001')[0]));
    await waitFor(() => screen.getByText(/Accept event/i));

    fireEvent.click(screen.getByText(/Accept event & rebuild state/i));
    await waitFor(() => expect(screen.getByText(/State version conflict/i)).toBeDefined());
  });
});

describe('App — snapshot workflow', () => {
  beforeEach(() => { vi.clearAllMocks(); setupWithTwin(); });

  it('creates a snapshot and shows success', async () => {
    vi.mocked(api.createSnapshot).mockResolvedValue(mockSnapshot);

    render(<App />);
    await waitFor(() => fireEvent.click(screen.getAllByText('TWIN_001')[0]));
    await waitFor(() => screen.getByText(/Create feature snapshot/i));

    fireEvent.click(screen.getByText(/Create feature snapshot/i));
    await waitFor(() => expect(screen.getByText(/Feature snapshot created/i)).toBeDefined());
  });

  it('shows snapshot detail when row is expanded', async () => {
    render(<App />);
    await waitFor(() => fireEvent.click(screen.getAllByText('TWIN_001')[0]));
    await waitFor(() => expect(screen.getAllByText('snap_abc').length).toBeGreaterThan(0), WAIT);

    const snapshotButtons = screen.getAllByRole('button', { name: /snap_abc/i });
    fireEvent.click(snapshotButtons[0]);
    await waitFor(() => expect(screen.getAllByText('Missing fields').length).toBeGreaterThan(1), WAIT);
  });

  it('disables "Create feature snapshot" when there is no state', async () => {
    vi.mocked(api.getState).mockRejectedValue(new ApiError(409, 'Twin has no accepted events.'));
    vi.mocked(api.listSnapshots).mockResolvedValue(emptyPage);

    render(<App />);
    await waitFor(() => fireEvent.click(screen.getAllByText('TWIN_001')[0]));
    await waitFor(() => screen.getByText(/Create feature snapshot/i));

    expect((screen.getByText(/Create feature snapshot/i) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('App — prediction & SHAP', () => {
  beforeEach(() => { vi.clearAllMocks(); setupWithTwin(); });

  it('shows mock badge on prediction', async () => {
    render(<App />);
    await waitFor(() => fireEvent.click(screen.getAllByText('TWIN_001')[0]));
    await waitFor(() => expect(screen.getByText('Mock')).toBeDefined());
  });

  it('displays SHAP feature contribution bars', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Feature Contributions/i)).toBeDefined(), WAIT);
    // Feature names appear in state panel AND SHAP bars — use getAllByText
    expect(screen.getAllByText('Tumour size mm').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Grade').length).toBeGreaterThan(0);
  });

  it('shows SHAP legend with risk direction labels', async () => {
    render(<App />);
    await waitFor(() => fireEvent.click(screen.getAllByText('TWIN_001')[0]));
    await waitFor(() => expect(screen.getByText(/Increases risk/i)).toBeDefined());
    expect(screen.getByText(/Decreases risk/i)).toBeDefined();
  });

  it('shows model warning text', async () => {
    render(<App />);
    await waitFor(() => fireEvent.click(screen.getAllByText('TWIN_001')[0]));
    await waitFor(() => expect(screen.getByText(/Mock output/i)).toBeDefined());
  });

  it('creates a prediction and shows success', async () => {
    vi.mocked(api.createPrediction).mockResolvedValue({ ...mockPrediction, prediction_id: 'pred_new' });

    render(<App />);
    await waitFor(() => fireEvent.click(screen.getAllByText('TWIN_001')[0]));
    await waitFor(() => screen.getByText(/Generate mock prediction/i));

    fireEvent.click(screen.getByText(/Generate mock prediction/i));
    await waitFor(() => expect(screen.getByText(/Mock prediction and linked audit record created/i)).toBeDefined());
  });

  it('displays confidence pill for model prediction', async () => {
    render(<App />);
    await waitFor(() => fireEvent.click(screen.getAllByText('TWIN_001')[0]));
    await waitFor(() => expect(screen.getByText('not assessed')).toBeDefined());
  });

  it('displays out-of-distribution warning when ood_flag is true', async () => {
    vi.mocked(api.listPredictions).mockResolvedValue({
      items: [{ ...mockPrediction, ood_flag: true }],
      total: 1,
      limit: 50,
      offset: 0,
    });
    render(<App />);
    await waitFor(() => fireEvent.click(screen.getAllByText('TWIN_001')[0]));
    await waitFor(() => expect(screen.getByText(/Out-of-Distribution Input Detected/i)).toBeDefined());
  });

  it('displays trained model badge when prediction is not mock', async () => {
    vi.mocked(api.getModelInfo).mockResolvedValue({
      status: 'ok',
      inference_mode: 'trained',
      model_name: 'BRCA-Survival-LightGBM',
      model_version: '1.0.0',
    });
    vi.mocked(api.listPredictions).mockResolvedValue({
      items: [{
        ...mockPrediction,
        is_mock: false,
        model_name: 'BRCA-Survival-LightGBM',
        model_version: '1.0.0',
        confidence: 'high' as const,
        ood_flag: false,
      }],
      total: 1,
      limit: 50,
      offset: 0,
    });
    render(<App />);
    await waitFor(() => fireEvent.click(screen.getAllByText('TWIN_001')[0]));
    await waitFor(() => expect(screen.getAllByText('Trained Model').length).toBeGreaterThan(0));
    expect(screen.getByText('high')).toBeDefined();
  });
});

describe('App — audit traceability', () => {
  beforeEach(() => { vi.clearAllMocks(); setupWithTwin(); });

  it('renders audit records with action label', async () => {
    render(<App />);
    await waitFor(() => fireEvent.click(screen.getAllByText('TWIN_001')[0]));
    await waitFor(() => expect(screen.getByText('Prediction created')).toBeDefined());
  });

  it('expands audit detail to show full lineage', async () => {
    render(<App />);
    await waitFor(() => fireEvent.click(screen.getAllByText('TWIN_001')[0]));
    await waitFor(() => screen.getByText('Prediction created'));

    fireEvent.click(screen.getByText('Prediction created'));
    await waitFor(() => expect(screen.getByText('Prediction ID')).toBeDefined());
    expect(screen.getByText('Snapshot ID')).toBeDefined();
    expect(screen.getByText('Model version')).toBeDefined();
    expect(screen.getByText('Actor')).toBeDefined();
  });
});

describe('App — accessibility', () => {
  beforeEach(() => { vi.clearAllMocks(); setupWithTwin(); });

  it('risk ring has an accessible aria-label', async () => {
    render(<App />);
    await waitFor(() => fireEvent.click(screen.getAllByText('TWIN_001')[0]));
    await waitFor(() => expect(screen.getByRole('img', { name: /42% mock risk/i })).toBeDefined());
  });

  it('connection status has role="status"', async () => {
    setupEmptyOnline();
    render(<App />);
    await waitFor(() => expect(screen.getByRole('status')).toBeDefined());
  });
});

describe('App — refresh button', () => {
  beforeEach(() => { vi.clearAllMocks(); setupEmptyOnline(); });

  it('shows a Refresh button when online', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByRole('button', { name: /Refresh all data/i })).toBeDefined());
  });

  it('refresh button is disabled when offline', async () => {
    vi.mocked(api.health).mockResolvedValue(false);
    render(<App />);
    await waitFor(() => {
      const btn = screen.getByRole('button', { name: /Refresh all data/i });
      expect((btn as HTMLButtonElement).disabled).toBe(true);
    });
  });
});

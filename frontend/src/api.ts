import type {
  AuditRecord,
  ClinicalEvent,
  FeatureSnapshot,
  Page,
  Prediction,
  TwinState,
  TwinSummary,
} from './types';

const configuredBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1';
export const API_BASE_URL = configuredBase.replace(/\/$/, '');
const API_ROOT = API_BASE_URL.replace(/\/api\/v1$/, '');
const configuredKey = import.meta.env.VITE_API_KEY as string | undefined;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');
  if (options.body) headers.set('Content-Type', 'application/json');
  if (configuredKey) headers.set('X-API-Key', configuredKey);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(0, 'Cannot reach the backend. Check that it is running on port 8000.');
  }

  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  if (!response.ok) {
    const detail = typeof body?.detail === 'string' ? body.detail : `Request failed with status ${response.status}.`;
    throw new ApiError(response.status, detail);
  }
  return body as T;
}

const twinPath = (twinId: string) => `/twins/${encodeURIComponent(twinId)}`;

export const api = {
  async health(): Promise<boolean> {
    try {
      const response = await fetch(`${API_ROOT}/health`, { headers: { Accept: 'application/json' } });
      return response.ok;
    } catch {
      return false;
    }
  },
  listTwins: () => request<Page<TwinSummary>>('/twins'),
  createTwin: (twinId: string) => request<{ twin_id: string; status: 'created' }>('/twins', {
    method: 'POST',
    body: JSON.stringify({ twin_id: twinId }),
  }),
  listEvents: (twinId: string) => request<Page<ClinicalEvent>>(`${twinPath(twinId)}/events?limit=200`),
  appendEvent: (twinId: string, event: ClinicalEvent, expectedVersion: number) =>
    request<{ twin_id: string; event_id: string; status: 'accepted'; state_version: number }>(
      `${twinPath(twinId)}/events?expected_state_version=${expectedVersion}`,
      { method: 'POST', body: JSON.stringify(event) },
    ),
  getState: (twinId: string) => request<TwinState>(`${twinPath(twinId)}/state`),
  listSnapshots: (twinId: string) => request<Page<FeatureSnapshot>>(`${twinPath(twinId)}/snapshots?limit=200`),
  createSnapshot: (twinId: string) => request<FeatureSnapshot>(`${twinPath(twinId)}/snapshots`, { method: 'POST' }),
  listPredictions: (twinId: string) => request<Page<Prediction>>(`${twinPath(twinId)}/predictions?limit=200`),
  createPrediction: (twinId: string, snapshotId: string) => request<Prediction>(
    `${twinPath(twinId)}/snapshots/${encodeURIComponent(snapshotId)}/predictions`,
    { method: 'POST' },
  ),
  listAudits: (twinId: string) => request<Page<AuditRecord>>(`${twinPath(twinId)}/audits?limit=200`),
};


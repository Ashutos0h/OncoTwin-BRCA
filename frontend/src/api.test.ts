import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, API_BASE_URL } from './api';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('backend API client', () => {
  it('loads the paginated twin list with JSON headers', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      items: [{ twin_id: 'twin-1', state_version: 2 }],
      total: 1,
      limit: 50,
      offset: 0,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);

    const page = await api.listTwins();

    expect(page.items[0]).toEqual({ twin_id: 'twin-1', state_version: 2 });
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${API_BASE_URL}/twins`);
    expect(new Headers(options.headers).get('Accept')).toBe('application/json');
  });

  it('sends optimistic state version and a contract-shaped event', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      twin_id: 'twin 1', event_id: 'event-1', status: 'accepted', state_version: 4,
    }), { status: 201, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    const event = {
      schema_version: '0.1.0' as const,
      twin_id: 'twin 1',
      event_id: 'event-1',
      event_type: 'FOLLOW_UP' as const,
      effective_time: '2026-09-01T00:00:00Z',
      received_time: '2026-09-01T00:00:00Z',
      source: 'synthetic',
      quality_status: 'valid' as const,
      provenance: { source_system: 'test', source_record_id: 'event-1', data_version: 'v1' },
      payload: { grade: 2 },
    };

    await api.appendEvent('twin 1', event, 3);

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/twins/twin%201/events?expected_state_version=3');
    expect(options.method).toBe('POST');
    expect(JSON.parse(String(options.body))).toEqual(event);
    expect(new Headers(options.headers).get('Content-Type')).toBe('application/json');
  });

  it('surfaces the backend detail for an expected API error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'Twin already exists.' }),
      { status: 409, headers: { 'Content-Type': 'application/json' } },
    )));

    await expect(api.createTwin('existing')).rejects.toEqual(
      new ApiError(409, 'Twin already exists.'),
    );
  });

  it('turns a network failure into an actionable message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fetch failed')));

    await expect(api.listTwins()).rejects.toMatchObject({
      status: 0,
      message: 'Cannot reach the backend. Check that it is running on port 8000.',
    });
  });
});

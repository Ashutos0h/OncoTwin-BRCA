import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';
import { api, ApiError } from './api';

vi.mock('./api', () => ({
  API_BASE_URL: 'http://localhost:8000',
  ApiError: class extends Error {
    constructor(public status: number, message: string) {
      super(message);
    }
  },
  api: {
    health: vi.fn(),
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
  }
}));

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.health).mockResolvedValue(true);
    vi.mocked(api.listTwins).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(api.listEvents).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(api.getState).mockRejectedValue(new ApiError(409, 'Not found'));
    vi.mocked(api.listSnapshots).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(api.listPredictions).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(api.listAudits).mockResolvedValue({ items: [], total: 0 });
  });

  it('handles connection state and basic interactions', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Backend connected')).toBeDefined();
    });
    
    // Create twin
    vi.mocked(api.createTwin).mockResolvedValue({ twin_id: 'TWIN_123', status: 'created' });
    vi.mocked(api.listTwins).mockResolvedValue({ items: [{ twin_id: 'TWIN_123', state_version: 0 }], total: 1 });

    const input = screen.getByLabelText(/New synthetic twin ID/i);
    fireEvent.change(input, { target: { value: 'TWIN_123' } });
    fireEvent.click(screen.getByRole('button', { name: /Create twin/i }));
    
    await waitFor(() => {
      expect(api.createTwin).toHaveBeenCalledWith('TWIN_123');
    });
    
    // Simulate selection
    fireEvent.click(screen.getAllByText('TWIN_123')[0]);
    
    await waitFor(() => {
      expect(api.getState).toHaveBeenCalled();
    });
  });
});

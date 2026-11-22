import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as api from '../api';

// Mock fetch
global.fetch = vi.fn();

const mockFetch = global.fetch as ReturnType<typeof vi.fn>;

describe('API Service', () => {
  beforeEach(() => {
    mockFetch.mockClear();
    localStorage.clear();
    // Reset location
    delete (window as any).location;
    window.location = { href: '/', pathname: '/' } as any;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Authentication', () => {
    it('should check auth status successfully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ authenticated: true, user: { id: 1 } }),
      } as Response);

      const result = await api.checkAuthStatus();
      
      expect(result).toEqual({ authenticated: true, user: { id: 1 } });
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/auth/status',
        expect.objectContaining({
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        })
      );
    });

    it('should handle 401 unauthorized and redirect to login', async () => {
      localStorage.setItem('session_id', 'test-session');
      
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Unauthorized' }),
      } as Response);

      await expect(api.checkAuthStatus()).rejects.toThrow('Session expired');
      expect(localStorage.getItem('session_id')).toBeNull();
      expect(window.location.href).toBe('/login');
    });

    it('should logout and clear session data', async () => {
      localStorage.setItem('session_id', 'test-session');
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      } as Response);

      await api.logout();
      
      expect(localStorage.getItem('session_id')).toBeNull();
    });
  });

  describe('Orders API', () => {
    it('should sync orders successfully', async () => {
      const mockOrders = [
        { id: '1', restaurant_name: 'Test Restaurant', order_total: 500 },
      ];
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ orders: mockOrders, synced: 1 }),
      } as Response);

      const result = await api.syncOrders();
      
      expect(result).toEqual({ orders: mockOrders, synced: 1 });
    });

    it('should list orders with filters', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ orders: [], total: 0 }),
      } as Response);

      await api.listOrders({ restaurant: 'Test', limit: 10 });
      
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/orders/list?restaurant=Test&limit=10'),
        expect.any(Object)
      );
    });

    it('should get order statistics', async () => {
      const mockStats = {
        total_orders: 100,
        total_spent: 50000,
        average_order: 500,
      };
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockStats,
      } as Response);

      const result = await api.getOrderStats();
      
      expect(result).toEqual(mockStats);
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      await expect(api.checkAuthStatus()).rejects.toThrow('Network error');
    });

    it('should handle API errors with details', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ 
          detail: 'Invalid request',
          details: { field: 'restaurant_id' }
        }),
      } as Response);

      await expect(api.syncOrders()).rejects.toThrow('Invalid request');
    });

    it('should handle malformed error responses', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('Invalid JSON');
        },
      } as Response);

      await expect(api.checkAuthStatus()).rejects.toThrow('HTTP 500');
    });
  });

  describe('Session Management', () => {
    it('should include session ID in headers when available', async () => {
      localStorage.setItem('session_id', 'test-session-123');
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      } as Response);

      await api.checkAuthStatus();
      
      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'X-Session-ID': 'test-session-123',
          }),
        })
      );
    });

    it('should work without session ID', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      } as Response);

      await api.checkAuthStatus();
      
      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.not.objectContaining({
            'X-Session-ID': expect.any(String),
          }),
        })
      );
    });
  });
});

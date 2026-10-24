/**
 * API service for MealMind backend
 * Handles all HTTP requests with session authentication
 */

const API_BASE_URL = '/api';

/**
 * Get session ID from localStorage
 */
const getSessionId = (): string | null => {
  return localStorage.getItem('session_id');
};

/**
 * Make an authenticated API request
 */
const fetchAPI = async (endpoint: string, options: RequestInit = {}) => {
  const sessionId = getSessionId();
  
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };
  
  if (sessionId) {
    headers['X-Session-ID'] = sessionId;
  }
  
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
    credentials: 'include',
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  
  return response.json();
};

// ============================================================================
// Authentication
// ============================================================================

export const checkAuthStatus = async () => {
  return fetchAPI('/auth/status');
};

export const logout = async () => {
  const result = await fetchAPI('/auth/logout', { method: 'POST' });
  localStorage.removeItem('session_id');
  return result;
};

// ============================================================================
// Orders
// ============================================================================

export interface OrderFilters {
  startDate?: string;
  endDate?: string;
  restaurant?: string;
  limit?: number;
}

export interface OrderItem {
  item_id?: string;
  name?: string;
  item_name?: string;
  quantity?: number;
  price?: number;
  is_veg?: boolean;
}

export interface Order {
  id?: string;
  order_id?: string;
  restaurant_name: string;
  restaurant_area?: string;
  restaurant_locality?: string;
  restaurant_city?: string;
  order_total: number;
  order_time: string;
  delivery_time?: string | null;
  is_veg?: boolean;
  order_items?: string[];
  items?: OrderItem[] | string[];
  cuisines?: string[];
  order_status?: string;
  payment_method?: string;
}

export const getOrders = async (filters?: OrderFilters): Promise<{ orders: Order[]; total_count: number } | Order[]> => {
  const params = new URLSearchParams();
  if (filters?.startDate) params.set('start_date', filters.startDate);
  if (filters?.endDate) params.set('end_date', filters.endDate);
  if (filters?.restaurant) params.set('restaurant', filters.restaurant);
  if (filters?.limit) params.set('limit', filters.limit.toString());
  
  const query = params.toString();
  return fetchAPI(`/orders${query ? `?${query}` : ''}`);
};

export interface OrderSyncResult {
  orders_received: number;
  new_orders_fetched: number;
  total_orders: number;
  date_coverage: string;
}

export const syncOrders = async (): Promise<OrderSyncResult> => {
  return fetchAPI('/orders/sync', { method: 'POST' });
};

// ============================================================================
// Analytics
// ============================================================================

export interface AnalyticsSummary {
  total_orders?: number;
  total_spent?: number;
  average_order_value?: number;
  order_count?: number;
  avg_order_value?: number;
  first_order?: string | null;
  last_order?: string | null;
}

export interface CuisineStatItem {
  cuisine: string;
  order_count?: number;
  orders?: number;
  count?: number;
  total_spent?: number;
  avg_order?: number;
  percentage?: number;
}

export interface MonthlyTrendItem {
  month: string;
  total_spent?: number;
  total?: number;
  order_count?: number;
  orders?: number;
  avg_order?: number;
}

export interface Analytics {
  summary?: AnalyticsSummary;
  period?: {
    start_date?: string;
    end_date?: string;
  };
  total_spent?: number;
  order_count?: number;
  avg_order_value?: number;
  date_range?: {
    start?: string;
    end?: string;
  };
  top_restaurants?: Array<{ name: string; count?: number; order_count?: number; total_spent: number }>;
  top_cuisines?: Array<CuisineStatItem>;
  cuisine_breakdown?: Array<CuisineStatItem>;
  monthly_spending?: Array<MonthlyTrendItem>;
  monthly_trends?: Array<MonthlyTrendItem>;
  peak_hours?: Array<{ hour: string; order_count?: number; orders?: number }>;
  day_distribution?: Array<{ day: string; order_count?: number; orders?: number }>;
  veg_vs_nonveg?: {
    veg_orders: number;
    nonveg_orders: number;
  };
}

export const getAnalytics = async (startDate?: string, endDate?: string): Promise<Analytics> => {
  const params = new URLSearchParams();
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);
  
  const query = params.toString();
  return fetchAPI(`/analytics${query ? `?${query}` : ''}`);
};

// ============================================================================
// Insights
// ============================================================================

export const getInsights = async () => {
  return fetchAPI('/insights');
};

// ============================================================================
// Food Delivery
// ============================================================================

export interface Address {
  id: string;
  addressLine: string;
  addressCategory?: string;
  addressTag?: string;
  phoneNumber?: string;
  lat?: number;
  lng?: number;
}

export const getAddresses = async (): Promise<{ addresses: Address[] }> => {
  return fetchAPI('/food/addresses');
};

export const searchRestaurants = async (addressId: string, query: string) => {
  return fetchAPI('/food/search-restaurants', {
    method: 'POST',
    body: JSON.stringify({ address_id: addressId, query }),
  });
};

export const getRestaurantMenu = async (restaurantId: string, addressId: string) => {
  return fetchAPI(`/food/menu/${restaurantId}?address_id=${addressId}`);
};

export const updateFoodCart = async (
  addressId: string,
  restaurantId: string,
  itemId: string,
  quantity: number = 1
) => {
  return fetchAPI('/food/cart', {
    method: 'POST',
    body: JSON.stringify({ address_id: addressId, restaurant_id: restaurantId, item_id: itemId, quantity }),
  });
};

// ============================================================================
// Instamart
// ============================================================================

export const searchProducts = async (addressId: string, query: string, offset: number = 0) => {
  return fetchAPI('/instamart/search', {
    method: 'POST',
    body: JSON.stringify({ address_id: addressId, query, offset }),
  });
};

// ============================================================================
// Dineout
// ============================================================================

export const searchVenues = async (
  query: string,
  options?: { addressId?: string; lat?: number; lng?: number }
) => {
  return fetchAPI('/dineout/search', {
    method: 'POST',
    body: JSON.stringify({
      query,
      address_id: options?.addressId,
      lat: options?.lat,
      lng: options?.lng,
    }),
  });
};

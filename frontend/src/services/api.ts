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
 * Clear session data on auth failure
 */
const clearSession = () => {
  localStorage.removeItem('session_id');
  document.cookie = 'session_id=; path=/; max-age=0; SameSite=Lax';
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
  
  // Handle 401 Unauthorized - clear session and redirect to login
  if (response.status === 401) {
    clearSession();
    // Only redirect if not already on login page
    if (!window.location.pathname.includes('/login') && !window.location.pathname.includes('/oauth/callback')) {
      window.location.href = '/login';
    }
    throw new Error('Session expired. Please log in again.');
  }
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const message = error.detail || error.message || error.error || `HTTP ${response.status}`;
    const details = error.details ? ` (${JSON.stringify(error.details)})` : '';
    throw new Error(`${message}${details} [HTTP ${response.status}]`);
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
  document.cookie = 'session_id=; path=/; max-age=0; SameSite=Lax';
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

export const getRestaurantMenu = async (restaurantId: string, addressId: string, page = 1, pageSize = 5) => {
  const query = new URLSearchParams({ address_id: addressId, page: String(page), page_size: String(pageSize) });
  return fetchAPI(`/food/menu/${encodeURIComponent(restaurantId)}?${query.toString()}`);
};

export const searchMenu = async (addressId: string, query: string, restaurantId: string, offset = 0) => {
  const params = new URLSearchParams({ address_id: addressId, query, restaurant_id: restaurantId, offset: String(offset) });
  return fetchAPI(`/food/menu-search?${params.toString()}`);
};

export const updateFoodCart = async (
  addressId: string,
  restaurantId: string,
  items: Array<{ menu_item_id: string; quantity: number; variants?: any[]; variantsV2?: any[]; addons?: any[] }>
) => {
  return fetchAPI('/food/cart', {
    method: 'POST',
    body: JSON.stringify({ address_id: addressId, restaurant_id: restaurantId, items }),
  });
};

export const clearFoodCart = async (
  addressId: string,
  restaurantId: string
) => {
  return fetchAPI('/food/cart', {
    method: 'DELETE',
    body: JSON.stringify({ address_id: addressId, restaurant_id: restaurantId }),
  });
};

export interface FeeBreakdownItem {
  label: string;
  amount: number;
}

export interface PaymentOptions {
  breakdown: FeeBreakdownItem[];
  item_total?: number | null;
  grand_total: number | null;
  breakdown_available?: boolean;
  payment_methods: string[];
  raw?: unknown;
}

export const getPaymentOptions = async (
  addressId: string,
  restaurantId: string,
  items: Array<{ menu_item_id: string; quantity: number; variants?: any[]; variantsV2?: any[]; addons?: any[] }>
): Promise<PaymentOptions> => {
  return fetchAPI('/food/checkout-summary', {
    method: 'POST',
    body: JSON.stringify({ address_id: addressId, restaurant_id: restaurantId, items }),
  });
};

// ============================================================================
// Instamart
// ============================================================================

export interface InstamartCartItem {
  spinId: string;
  quantity: number;
}

export interface InstamartCart {
  success?: boolean;
  error?: { message?: string };
  items?: Array<{ spinId: string; quantity: number; product?: any }>;
  total?: number;
  item_count?: number;
}

export const searchProducts = async (addressId: string, query: string, offset: number = 0) => {
  return fetchAPI('/instamart/search', {
    method: 'POST',
    body: JSON.stringify({ address_id: addressId, query, offset }),
  });
};

export const getInstamartCart = async (addressId?: string): Promise<InstamartCart> => {
  const query = addressId ? `?address_id=${encodeURIComponent(addressId)}` : '';
  return fetchAPI(`/instamart/cart${query}`);
};

export const updateInstamartCart = async (addressId: string, items: InstamartCartItem[]): Promise<{ success: boolean; error?: { message?: string }; cart: InstamartCart }> => {
  return fetchAPI('/instamart/cart', {
    method: 'POST',
    body: JSON.stringify({ address_id: addressId, items }),
  });
};

export const clearInstamartCart = async (): Promise<{ success: boolean; cart: InstamartCart }> => {
  return fetchAPI('/instamart/cart', { method: 'DELETE' });
};

export const placeFoodOrder = async (
  addressId: string,
  restaurantId: string,
  items: Array<{ menu_item_id: string; quantity: number; variants?: any[]; variantsV2?: any[]; addons?: any[] }>,
  paymentMethod: string = "Cash"
): Promise<{ success: boolean; order_id?: string; message?: string }> => {
  return fetchAPI('/food/place-order', {
    method: 'POST',
    body: JSON.stringify({ address_id: addressId, restaurant_id: restaurantId, items, payment_method: paymentMethod }),
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

// ============================================================================
// Swiggy Sync Integration
// ============================================================================

export interface SwiggySyncStatus {
  last_orders_sync: string | null;
  last_cart_sync: string | null;
  pending_orders: number;
  failed_syncs_24h: number;
  total_orders_synced: number;
  connection_status: 'connected' | 'disconnected' | 'expired';
  next_auto_sync: string | null;
}

export const getSwiggySyncStatus = async (): Promise<SwiggySyncStatus> => {
  return fetchAPI('/swiggy/sync/status');
};

export interface SyncOrdersResult {
  new_orders: number;
  updated_orders: number;
  skipped_duplicates: number;
  failed_orders: number;
  new_mappings_created: number;
  sync_log_id: number;
  completed_at: string;
}

export const syncOrdersFromSwiggy = async (addressId?: string, maxOrders = 100): Promise<SyncOrdersResult> => {
  return fetchAPI('/swiggy/sync/orders', {
    method: 'POST',
    body: JSON.stringify({ address_id: addressId, max_orders: maxOrders }),
  });
};

export interface CartSyncResult {
  success: boolean;
  cart_url: string | null;
  items_added: number;
  items_not_found: string[];
  mappings_used: number;
  error: string | null;
  sync_log_id: number;
}

export const syncMealPlanToCart = async (mealPlanId: number, addressId: string, restaurantId?: string): Promise<CartSyncResult> => {
  return fetchAPI('/swiggy/sync/cart-from-mealplan', {
    method: 'POST',
    body: JSON.stringify({ meal_plan_id: mealPlanId, address_id: addressId, restaurant_id: restaurantId }),
  });
};

export interface SyncLogEntry {
  id: number;
  sync_type: string;
  direction: string;
  external_id: string;
  internal_id: string | null;
  status: string;
  items_synced: number;
  items_failed: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export const getSwiggySyncHistory = async (limit = 50, offset = 0): Promise<{ logs: SyncLogEntry[]; total: number }> => {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return fetchAPI(`/swiggy/sync/history?${params.toString()}`);
};

export const disconnectSwiggy = async (): Promise<{ success: boolean; message: string }> => {
  return fetchAPI('/swiggy/sync/disconnect', { method: 'POST' });
};

export interface FoodMapping {
  id: number;
  swiggy_restaurant_id: string;
  swiggy_menu_item_id: string;
  swiggy_item_name: string;
  mealmind_food_id: number | null;
  confidence: number;
  verified_by_user: boolean;
  food: {
    id: number;
    name: string;
    calories_per_100g: number | null;
    protein_g_per_100g: number | null;
    carbs_g_per_100g: number | null;
    fat_g_per_100g: number | null;
  } | null;
}

export const getFoodMappings = async (limit = 100, offset = 0, verifiedOnly = false): Promise<{ mappings: FoodMapping[]; total: number }> => {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset), verified_only: String(verifiedOnly) });
  return fetchAPI(`/swiggy/food-mappings?${params.toString()}`);
};

export const updateFoodMapping = async (mappingId: number, data: { mealmind_food_id?: number; verified_by_user?: boolean; confidence?: number }) => {
  return fetchAPI(`/swiggy/food-mappings/${mappingId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
};

export interface MealMindFood {
  id: number;
  user_id: number;
  name: string;
  canonical_name: string;
  calories_per_100g: number | null;
  protein_g_per_100g: number | null;
  carbs_g_per_100g: number | null;
  fat_g_per_100g: number | null;
  fiber_g_per_100g: number | null;
  sodium_mg_per_100g: number | null;
  sugar_g_per_100g: number | null;
  serving_size_g: number;
  is_veg: boolean | null;
  source: string;
  tags: string;
  created_at: string;
  updated_at: string;
}

export const createMealMindFood = async (data: Partial<MealMindFood>): Promise<{ success: boolean; food_id: number }> => {
  return fetchAPI('/swiggy/foods', { method: 'POST', body: JSON.stringify(data) });
};

export const listMealMindFoods = async (limit = 100, offset = 0, search?: string): Promise<{ foods: MealMindFood[]; total: number }> => {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (search) params.set('search', search);
  return fetchAPI(`/swiggy/foods?${params.toString()}`);
};

export interface NutritionLogRequest {
  log_date: string;
  meal_type: 'breakfast' | 'lunch' | 'dinner' | 'snack';
  food_id: number;
  quantity_g: number;
  swiggy_order_id?: string;
  source?: string;
  notes?: string;
}

export const logNutrition = async (data: NutritionLogRequest): Promise<{ success: boolean; log_id: number }> => {
  return fetchAPI('/nutrition/log', { method: 'POST', body: JSON.stringify(data) });
};

export interface DailyNutritionSummary {
  date: string;
  meals: Record<string, { items: any[]; totals: { calories: number; protein_g: number; carbs_g: number; fat_g: number } }>;
  totals: { calories: number; protein_g: number; carbs_g: number; fat_g: number; fiber_g: number; sugar_g: number; sodium_mg: number };
  items_count: number;
}

export const getDailyNutrition = async (date: string): Promise<DailyNutritionSummary> => {
  return fetchAPI(`/nutrition/daily/${date}`);
};

export interface WeeklyNutritionSummary {
  week_start: string;
  week_end: string;
  daily: Record<string, { calories: number; protein_g: number; carbs_g: number; fat_g: number; fiber_g: number; sugar_g: number; sodium_mg: number; items: number }>;
}

export const getWeeklyNutrition = async (startDate?: string): Promise<WeeklyNutritionSummary> => {
  const params = startDate ? `?start_date=${startDate}` : '';
  return fetchAPI(`/nutrition/weekly${params}`);
};

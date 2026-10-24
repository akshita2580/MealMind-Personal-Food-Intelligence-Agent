import { useState, useEffect } from 'react'
import { Calendar, MapPin, Package, Search, Filter, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { getOrders, syncOrders, type Order } from '@/services/api'

export default function OrderHistory() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [filteredOrders, setFilteredOrders] = useState<Order[]>([])
  const [syncing, setSyncing] = useState(false)
  const [syncMessage, setSyncMessage] = useState<string | null>(null)

  useEffect(() => {
    loadOrders()
  }, [])

  useEffect(() => {
    // Filter orders based on search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim()
      const filtered = orders.filter(order => {
        const name = (order.restaurant_name || '').toLowerCase()
        const locality = (order.restaurant_locality || order.restaurant_area || '').toLowerCase()
        const city = (order.restaurant_city || '').toLowerCase()
        return name.includes(q) || locality.includes(q) || city.includes(q)
      })
      setFilteredOrders(filtered)
    } else {
      setFilteredOrders(orders)
    }
  }, [searchQuery, orders])

  const loadOrders = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getOrders({ limit: 100 })
      console.log('Orders API response:', data)
      console.log('Type of data:', typeof data)
      console.log('Is data an array?', Array.isArray(data))
      
      // Handle both response formats: array or { orders: [...], total_count: ... }
      const ordersList: Order[] = Array.isArray(data) ? data : (data?.orders || [])
      console.log('Final orders list:', ordersList)
      
      setOrders(ordersList)
      setFilteredOrders(ordersList)
    } catch (err) {
      console.error('Load orders error:', err)
      setError(err instanceof Error ? err.message : 'Failed to load orders')
    } finally {
      setLoading(false)
    }
  }

  const handleSync = async () => {
    try {
      setSyncing(true)
      setSyncMessage(null)
      const result = await syncOrders()
      await loadOrders()
      setSyncMessage(
        `Sync complete. Swiggy returned ${result.orders_received} orders; ` +
        `${result.new_orders_fetched} new orders added; ${result.total_orders} orders available.`
      )
    } catch (err) {
      setSyncMessage(err instanceof Error ? err.message : 'Unable to sync orders')
    } finally {
      setSyncing(false)
    }
  }

  const formatDate = (dateString?: string | null) => {
    if (!dateString) return 'Date unavailable'
    try {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return dateString
      return date.toLocaleDateString('en-IN', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch {
      return dateString
    }
  }

  const formatCurrency = (amount?: number | null) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(amount || 0)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <div className="h-12 w-12 animate-spin rounded-full border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">Loading your orders...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="text-destructive">Error</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={loadOrders}>Try Again</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Order History</h1>
          <p className="text-muted-foreground mt-1">{orders.length} orders found</p>
        </div>
        <Button onClick={handleSync} disabled={syncing}>
          <RefreshCw className={`mr-2 h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
          {syncing ? 'Syncing…' : 'Sync orders'}
        </Button>
      </div>
      {syncMessage && <p role="status" className="text-sm text-muted-foreground">{syncMessage}</p>}

      {/* Search */}
      <div className="flex gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by restaurant or location..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <Button variant="outline">
          <Filter className="h-4 w-4 mr-2" />
          Filters
        </Button>
      </div>

      {/* Orders List */}
      {!filteredOrders || filteredOrders.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Package className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground">
              {searchQuery ? 'No orders found matching your search' : 'No orders synced yet. Select “Sync orders” to import your Swiggy history.'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {filteredOrders.map((order, idx) => {
            const orderId = order.order_id || order.id || `order-${idx}`
            const restaurantLocality = order.restaurant_locality || order.restaurant_area || ''
            const locationStr = [restaurantLocality, order.restaurant_city].filter(Boolean).join(', ')
            const rawItems = order.items || order.order_items || []
            const items = Array.isArray(rawItems) ? rawItems : []

            return (
              <Card key={orderId} className="hover:shadow-md transition-shadow">
                <CardContent className="p-6">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-start gap-4">
                        <div className="flex-1">
                          <h3 className="font-semibold text-lg">{order.restaurant_name || 'Restaurant'}</h3>
                          <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
                            {locationStr && (
                              <div className="flex items-center gap-1">
                                <MapPin className="h-4 w-4" />
                                <span>{locationStr}</span>
                              </div>
                            )}
                            <div className="flex items-center gap-1">
                              <Calendar className="h-4 w-4" />
                              <span>{formatDate(order.order_time)}</span>
                            </div>
                          </div>
                          
                          {items.length > 0 && (
                            <div className="mt-3">
                              <p className="text-sm text-muted-foreground">
                                {items.length} item{items.length > 1 ? 's' : ''}
                              </p>
                              <div className="mt-1 flex flex-wrap gap-2">
                                {items.slice(0, 3).map((item: any, itemIdx) => {
                                  const itemName = typeof item === 'string' ? item : (item?.name || item?.item_name || 'Item')
                                  return (
                                    <span
                                      key={itemIdx}
                                      className="text-xs bg-secondary px-2 py-1 rounded"
                                    >
                                      {itemName}
                                    </span>
                                  )
                                })}
                                {items.length > 3 && (
                                  <span className="text-xs text-muted-foreground px-2 py-1">
                                    +{items.length - 3} more
                                  </span>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                        
                        <div className="text-right">
                          <p className="text-2xl font-bold">{formatCurrency(order.order_total)}</p>
                          {order.is_veg && (
                            <span className="inline-block mt-2 text-xs bg-green-100 text-green-700 px-2 py-1 rounded">
                              🌱 Veg
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}

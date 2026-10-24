import { useState, useEffect } from 'react'
import { TrendingUp, DollarSign, Package, PieChart as PieChartIcon, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { getAnalytics, type Analytics } from '@/services/api'

export default function AnalyticsPage() {
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadAnalytics()
  }, [])

  const loadAnalytics = async () => {
    try {
      setLoading(true)
      setError(null)
      console.log('=== ANALYTICS REQUEST ===')
      const data = await getAnalytics()
      console.log('=== ANALYTICS RESPONSE ===')
      console.log('Analytics data:', data)
      console.log('Analytics type:', typeof data)
      console.log('Analytics keys:', Object.keys(data || {}))
      setAnalytics(data)
    } catch (err) {
      console.error('=== ANALYTICS ERROR ===')
      console.error('Error details:', err)
      setError(err instanceof Error ? err.message : 'Failed to load analytics')
    } finally {
      setLoading(false)
    }
  }

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(amount)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <div className="h-12 w-12 animate-spin rounded-full border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">Loading analytics...</p>
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
            <Button onClick={loadAnalytics}>Try Again</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (!analytics) {
    return null
  }

  const totalSpent = analytics?.summary?.total_spent ?? analytics?.total_spent ?? 0
  const orderCount = analytics?.summary?.total_orders ?? analytics?.summary?.order_count ?? analytics?.order_count ?? 0
  const avgOrderValue = analytics?.summary?.average_order_value ?? analytics?.summary?.avg_order_value ?? analytics?.avg_order_value ?? 0

  const dateRangeText = (() => {
    if (analytics?.period?.start_date && analytics?.period?.end_date) {
      return `${analytics.period.start_date} to ${analytics.period.end_date}`
    }
    if (analytics?.date_range?.start && analytics?.date_range?.end) {
      return `${analytics.date_range.start} to ${analytics.date_range.end}`
    }
    if (analytics?.summary?.first_order && analytics?.summary?.last_order) {
      return `${analytics.summary.first_order} to ${analytics.summary.last_order}`
    }
    return 'All time'
  })()

  const vegOrders = analytics?.veg_vs_nonveg?.veg_orders ?? 0
  const nonvegOrders = analytics?.veg_vs_nonveg?.nonveg_orders ?? 0
  const totalVegNonVeg = vegOrders + nonvegOrders
  const vegPercentage = totalVegNonVeg > 0 ? Math.round((vegOrders / totalVegNonVeg) * 100) : 0

  const topRestaurants = analytics?.top_restaurants || []
  const cuisines = analytics?.cuisine_breakdown || analytics?.top_cuisines || []
  const monthlyTrends = analytics?.monthly_trends || analytics?.monthly_spending || []
  const peakHours = analytics?.peak_hours || []
  const dayDistribution = analytics?.day_distribution || []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Analytics</h1>
          <p className="text-muted-foreground mt-1">
            Track your spending patterns and order trends
          </p>
        </div>
        <Button onClick={loadAnalytics} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Stats Overview */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Spent</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(totalSpent)}</div>
            <p className="text-xs text-muted-foreground mt-1">
              Across {orderCount} orders
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Orders</CardTitle>
            <Package className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{orderCount}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {dateRangeText}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Avg Order Value</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(avgOrderValue)}</div>
            <p className="text-xs text-muted-foreground mt-1">
              Per order
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Top Restaurants */}
      <Card>
        <CardHeader>
          <CardTitle>Top Restaurants</CardTitle>
          <CardDescription>Your most frequently ordered restaurants</CardDescription>
        </CardHeader>
        <CardContent>
          {topRestaurants.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">No data available</p>
          ) : (
            <div className="space-y-4">
              {topRestaurants.slice(0, 5).map((restaurant, idx) => {
                const count = restaurant.order_count ?? (restaurant as any).count ?? 0
                return (
                  <div key={idx} className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center font-semibold text-sm">
                        {idx + 1}
                      </div>
                      <div>
                        <p className="font-medium">{restaurant.name}</p>
                        <p className="text-sm text-muted-foreground">
                          {count} order{count !== 1 ? 's' : ''}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold">{formatCurrency(restaurant.total_spent || 0)}</p>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Two Column Layout */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Veg vs Non-Veg */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PieChartIcon className="h-5 w-5" />
              Food Preferences
            </CardTitle>
            <CardDescription>Veg vs Non-Veg orders</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-green-500"></span>
                    Vegetarian
                  </span>
                  <span className="text-sm font-semibold">
                    {vegOrders} ({vegPercentage}%)
                  </span>
                </div>
                <div className="h-2 bg-secondary rounded-full overflow-hidden">
                  <div
                    className="h-full bg-green-500"
                    style={{ width: `${vegPercentage}%` }}
                  ></div>
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-red-500"></span>
                    Non-Vegetarian
                  </span>
                  <span className="text-sm font-semibold">
                    {nonvegOrders} ({100 - vegPercentage}%)
                  </span>
                </div>
                <div className="h-2 bg-secondary rounded-full overflow-hidden">
                  <div
                    className="h-full bg-red-500"
                    style={{ width: `${100 - vegPercentage}%` }}
                  ></div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Top Cuisines */}
        <Card>
          <CardHeader>
            <CardTitle>Top Cuisines</CardTitle>
            <CardDescription>Your favorite cuisines</CardDescription>
          </CardHeader>
          <CardContent>
            {cuisines.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">No data available</p>
            ) : (
              <div className="space-y-3">
                {cuisines.slice(0, 5).map((cuisine, idx) => {
                  const cuisineName = cuisine.cuisine || (cuisine as any).name || 'Unknown'
                  const count = cuisine.order_count ?? (cuisine as any).orders ?? (cuisine as any).count ?? 0
                  return (
                    <div key={idx} className="flex items-center justify-between">
                      <span className="text-sm font-medium">{cuisineName}</span>
                      <span className="text-sm text-muted-foreground">
                        {count} order{count !== 1 ? 's' : ''}
                        {cuisine.total_spent ? ` • ${formatCurrency(cuisine.total_spent)}` : ''}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Monthly Spending */}
      {monthlyTrends && monthlyTrends.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Monthly Spending</CardTitle>
            <CardDescription>Your spending trend over time</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {monthlyTrends.map((month, idx) => {
                const total = month.total_spent ?? (month as any).total ?? 0
                const count = month.order_count ?? (month as any).orders
                return (
                  <div key={idx} className="flex items-center justify-between py-2 border-b last:border-0">
                    <div>
                      <span className="text-sm font-medium">{month.month}</span>
                      {count !== undefined && (
                        <span className="text-xs text-muted-foreground ml-2">({count} orders)</span>
                      )}
                    </div>
                    <span className="text-sm font-semibold">{formatCurrency(total)}</span>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Peak Hours & Day Distribution (if available) */}
      {(peakHours.length > 0 || dayDistribution.length > 0) && (
        <div className="grid gap-4 md:grid-cols-2">
          {peakHours.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Peak Ordering Hours</CardTitle>
                <CardDescription>When you order the most</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {peakHours.slice(0, 5).map((item, idx) => {
                    const count = item.order_count ?? (item as any).orders ?? 0
                    return (
                      <div key={idx} className="flex items-center justify-between py-1 border-b last:border-0">
                        <span className="text-sm font-medium">{item.hour}</span>
                        <span className="text-sm text-muted-foreground">{count} orders</span>
                      </div>
                    )
                  })}
                </div>
              </CardContent>
            </Card>
          )}

          {dayDistribution.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Day Distribution</CardTitle>
                <CardDescription>Orders by day of the week</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {dayDistribution.map((item, idx) => {
                    const count = item.order_count ?? (item as any).orders ?? 0
                    return (
                      <div key={idx} className="flex items-center justify-between py-1 border-b last:border-0">
                        <span className="text-sm font-medium">{item.day}</span>
                        <span className="text-sm text-muted-foreground">{count} orders</span>
                      </div>
                    )
                  })}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}

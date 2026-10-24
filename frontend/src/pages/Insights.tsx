import { useState, useEffect } from 'react'
import { Lightbulb, RefreshCw, Sparkles, AlertCircle, CheckCircle, Info } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { getInsights } from '@/services/api'

interface Insight {
  type: string;
  severity: string;
  title: string;
  message: string;
  value?: number | string | null;
  unit?: string | null;
  period?: string | null;
  supporting_data?: Record<string, any>;
}

interface InsightsData {
  insights: Insight[];
  generated_at?: string | null;
  period?: string | null;
}

export default function InsightsPage() {
  const [insights, setInsights] = useState<InsightsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadInsights()
  }, [])

  const loadInsights = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getInsights()
      console.log('Insights data:', data)
      setInsights(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load insights')
    } finally {
      setLoading(false)
    }
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Never'
    const date = new Date(dateString)
    if (isNaN(date.getTime())) {
      return dateString
    }
    return date.toLocaleString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'SUCCESS':
        return <CheckCircle className="h-5 w-5 text-green-600" />
      case 'WARNING':
        return <AlertCircle className="h-5 w-5 text-yellow-600" />
      case 'ALERT':
        return <AlertCircle className="h-5 w-5 text-red-600" />
      default:
        return <Info className="h-5 w-5 text-blue-600" />
    }
  }

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'SUCCESS':
        return 'bg-green-50 border-green-200'
      case 'WARNING':
        return 'bg-yellow-50 border-yellow-200'
      case 'ALERT':
        return 'bg-red-50 border-red-200'
      default:
        return 'bg-blue-50 border-blue-200'
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <div className="h-12 w-12 animate-spin rounded-full border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">Generating insights...</p>
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
            <Button onClick={loadInsights}>Try Again</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Sparkles className="h-8 w-8 text-primary" />
            Food Insights
          </h1>
          <p className="text-muted-foreground mt-1">
            Personalized recommendations based on your order history
          </p>
          {(insights?.generated_at || insights?.period) && (
            <p className="text-sm text-muted-foreground mt-1">
              Last updated: {formatDate(insights.generated_at || insights.period || '')}
            </p>
          )}
        </div>
        <Button onClick={loadInsights} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {!insights || !insights.insights || insights.insights.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Lightbulb className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground">
              No insights available yet. Order more food to get personalized recommendations!
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {insights.insights.map((insight, idx) => (
            <Card key={idx} className={`hover:shadow-md transition-shadow border ${getSeverityColor(insight.severity)}`}>
              <CardContent className="p-6">
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 mt-1">
                    {getSeverityIcon(insight.severity)}
                  </div>
                  <div className="flex-1">
                    <h3 className="font-semibold text-lg mb-2">{insight.title}</h3>
                    <p className="text-base leading-relaxed text-muted-foreground">{insight.message}</p>
                    
                    {(insight.value !== null && insight.value !== undefined) && (
                      <div className="mt-3 flex items-baseline gap-2">
                        <span className="text-2xl font-bold text-primary">
                          {insight.value}
                        </span>
                        {insight.unit && (
                          <span className="text-sm text-muted-foreground">{insight.unit}</span>
                        )}
                        {insight.period && (
                          <span className="text-sm text-muted-foreground">• {insight.period}</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Info Card */}
      <Card className="border-primary/20 bg-primary/5">
        <CardHeader>
          <CardTitle className="text-lg">How Insights Work</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            💡 <strong>Personalized recommendations</strong> based on your order patterns
          </p>
          <p>
            🍽️ <strong>Cuisine preferences</strong> identified from your history
          </p>
          <p>
            💰 <strong>Spending patterns</strong> to help you budget better
          </p>
          <p>
            🥗 <strong>Dietary habits</strong> analysis (veg vs non-veg)
          </p>
          <p>
            📍 <strong>Favorite restaurants</strong> and areas you order from
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

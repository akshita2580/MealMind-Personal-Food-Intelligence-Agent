import { Link } from 'react-router-dom'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { UtensilsCrossed, ShoppingCart, Calendar, Lightbulb, LineChart, History } from 'lucide-react'

export default function Dashboard() {
  const features = [
    {
      icon: UtensilsCrossed,
      title: 'Food Delivery',
      description: 'Order from your favorite restaurants',
      link: '/food',
      color: 'text-orange-500'
    },
    {
      icon: ShoppingCart,
      title: 'Instamart',
      description: 'Shop for groceries and essentials',
      link: '/instamart',
      color: 'text-green-500'
    },
    {
      icon: Calendar,
      title: 'Dineout',
      description: 'Book tables at restaurants',
      link: '/dineout',
      color: 'text-purple-500'
    },
    {
      icon: Lightbulb,
      title: 'Food Insights',
      description: 'Get personalized recommendations',
      link: '/insights',
      color: 'text-yellow-500'
    },
    {
      icon: LineChart,
      title: 'Analytics',
      description: 'Track your spending patterns',
      link: '/analytics',
      color: 'text-blue-500'
    },
    {
      icon: History,
      title: 'Order History',
      description: 'View your past orders',
      link: '/orders',
      color: 'text-gray-500'
    }
  ]

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="space-y-2">
        <h1 className="text-4xl font-bold tracking-tight">Welcome to MealMind</h1>
        <p className="text-lg text-muted-foreground">
          Your personal food intelligence agent powered by Swiggy
        </p>
      </div>

      {/* Features Grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {features.map((feature) => {
          const Icon = feature.icon
          return (
            <Link key={feature.link} to={feature.link}>
              <Card className="transition-all hover:shadow-lg hover:scale-105 cursor-pointer h-full">
                <CardHeader>
                  <div className="flex items-center space-x-4">
                    <div className={`p-2 rounded-lg bg-secondary`}>
                      <Icon className={`h-6 w-6 ${feature.color}`} />
                    </div>
                    <CardTitle>{feature.title}</CardTitle>
                  </div>
                  <CardDescription>{feature.description}</CardDescription>
                </CardHeader>
                <CardContent>
                  <Button variant="outline" className="w-full">
                    Get Started →
                  </Button>
                </CardContent>
              </Card>
            </Link>
          )
        })}
      </div>

      {/* Quick Stats */}
      <Card>
        <CardHeader>
          <CardTitle>Getting Started</CardTitle>
          <CardDescription>
            Connect your Swiggy account to access all features
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Note: Some features require a connected Swiggy account with valid OAuth credentials.
            Make sure you've completed the OAuth flow to access ordering and insights.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

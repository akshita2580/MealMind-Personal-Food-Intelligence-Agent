import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { UtensilsCrossed } from 'lucide-react'

export default function Login() {
  const handleLogin = () => {
    // Redirect to backend OAuth initiation
    window.location.href = '/api/auth/login'
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-orange-50 to-orange-100">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-4 text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary">
            <UtensilsCrossed className="h-8 w-8 text-white" />
          </div>
          <CardTitle className="text-3xl">Welcome to MealMind</CardTitle>
          <CardDescription className="text-base">
            Your Personal Food Intelligence Agent
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2 text-sm text-muted-foreground">
            <p>✓ Order food from your favorite restaurants</p>
            <p>✓ Shop groceries on Instamart</p>
            <p>✓ Book tables at restaurants</p>
            <p>✓ Get personalized food insights</p>
          </div>
          <Button 
            onClick={handleLogin}
            className="w-full"
            size="lg"
          >
            Connect with Swiggy
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

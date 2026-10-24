import { Link, useNavigate } from 'react-router-dom'
import { Home, UtensilsCrossed, ShoppingCart, Calendar, LineChart, Lightbulb, Package, LogOut } from 'lucide-react'
import { logout } from '@/services/api'

export default function Navbar() {
  const navigate = useNavigate()

  const handleLogout = async () => {
    try {
      await logout()
    } catch (err) {
      console.error('Logout error:', err)
    } finally {
      navigate('/login')
    }
  }

  return (
    <nav className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-16 items-center px-4">
        <div className="flex items-center space-x-2 font-bold text-xl">
          <UtensilsCrossed className="h-6 w-6 text-primary" />
          <span>MealMind</span>
        </div>
        
        <div className="ml-auto flex items-center space-x-6">
          <Link to="/dashboard" className="flex items-center space-x-2 text-sm font-medium transition-colors hover:text-primary">
            <Home className="h-4 w-4" />
            <span>Dashboard</span>
          </Link>
          <Link to="/orders" className="flex items-center space-x-2 text-sm font-medium transition-colors hover:text-primary">
            <Package className="h-4 w-4" />
            <span>Orders</span>
          </Link>
          <Link to="/food" className="flex items-center space-x-2 text-sm font-medium transition-colors hover:text-primary">
            <UtensilsCrossed className="h-4 w-4" />
            <span>Food</span>
          </Link>
          <Link to="/instamart" className="flex items-center space-x-2 text-sm font-medium transition-colors hover:text-primary">
            <ShoppingCart className="h-4 w-4" />
            <span>Instamart</span>
          </Link>
          <Link to="/dineout" className="flex items-center space-x-2 text-sm font-medium transition-colors hover:text-primary">
            <Calendar className="h-4 w-4" />
            <span>Dineout</span>
          </Link>
          <Link to="/insights" className="flex items-center space-x-2 text-sm font-medium transition-colors hover:text-primary">
            <Lightbulb className="h-4 w-4" />
            <span>Insights</span>
          </Link>
          <Link to="/analytics" className="flex items-center space-x-2 text-sm font-medium transition-colors hover:text-primary">
            <LineChart className="h-4 w-4" />
            <span>Analytics</span>
          </Link>
          <button
            onClick={handleLogout}
            className="flex items-center space-x-2 text-sm font-medium text-destructive hover:text-destructive/80 transition-colors ml-2"
          >
            <LogOut className="h-4 w-4" />
            <span>Logout</span>
          </button>
        </div>
      </div>
    </nav>
  )
}

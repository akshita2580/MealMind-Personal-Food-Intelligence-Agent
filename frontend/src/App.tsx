import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import { Toaster } from 'sonner'
import { ErrorBoundary } from '@/components/ui/error-boundary'
import { LoadingPage } from '@/components/ui/loading-spinner'

// Layout
import Layout from '@/components/layout/Layout'

// Pages
import Dashboard from '@/pages/Dashboard'
import Login from '@/pages/Login'
import OAuthCallback from '@/pages/OAuthCallback'
import FoodDelivery from '@/pages/FoodDelivery'
import Instamart from '@/pages/Instamart'
import Dineout from '@/pages/Dineout'
import OrderHistory from '@/pages/OrderHistory'
import Insights from '@/pages/Insights'
import Analytics from '@/pages/Analytics'

// Protected Route Component
import { useAuth } from '@/hooks/useAuth'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading } = useAuth()
  
  if (loading) {
    return <LoadingPage message="Verifying authentication..." />
  }
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  
  return <>{children}</>
}

function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <Router>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/oauth/callback" element={<OAuthCallback />} />
            
            <Route path="/" element={<Layout />}>
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route
                path="dashboard"
                element={
                  <ProtectedRoute>
                    <Dashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="food"
                element={
                  <ProtectedRoute>
                    <FoodDelivery />
                  </ProtectedRoute>
                }
              />
              <Route
                path="instamart"
                element={
                  <ProtectedRoute>
                    <Instamart />
                  </ProtectedRoute>
                }
              />
              <Route
                path="dineout"
                element={
                  <ProtectedRoute>
                    <Dineout />
                  </ProtectedRoute>
                }
              />
              <Route
                path="orders"
                element={
                  <ProtectedRoute>
                    <OrderHistory />
                  </ProtectedRoute>
                }
              />
              <Route
                path="insights"
                element={
                  <ProtectedRoute>
                    <Insights />
                  </ProtectedRoute>
                }
              />
              <Route
                path="analytics"
                element={
                  <ProtectedRoute>
                    <Analytics />
                  </ProtectedRoute>
                }
              />
            </Route>
          </Routes>
          <Toaster 
            position="bottom-right"
            toastOptions={{
              duration: 4000,
              className: 'swiggy-shadow',
            }}
          />
        </Router>
      </AuthProvider>
    </ErrorBoundary>
  )
}

export default App

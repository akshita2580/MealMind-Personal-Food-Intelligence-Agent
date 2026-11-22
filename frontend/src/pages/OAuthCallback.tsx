import { useEffect, useContext, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { AuthContext } from '../context/AuthContext'
import { syncOrders } from '@/services/api'
import { toast } from 'sonner'

export default function OAuthCallback() {
  const navigate = useNavigate()
  const { checkAuth, isAuthenticated } = useContext(AuthContext)
  const [searchParams] = useSearchParams()
  const [checking, setChecking] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // Extract session_id from URL and store it
    const handleCallback = async () => {
      console.log('OAuthCallback: Processing OAuth callback...')
      
      const sessionId = searchParams.get('session_id')
      if (sessionId) {
        console.log('OAuthCallback: Session ID received, storing...')
        localStorage.setItem('session_id', sessionId)
        // Also set a cookie for server-side session validation
        document.cookie = `session_id=${sessionId}; path=/; max-age=2592000; SameSite=Lax` // 30 days
      } else {
        console.error('OAuthCallback: No session_id in URL')
        setError('No session ID received from Swiggy')
        setChecking(false)
        return
      }
      
      console.log('OAuthCallback: Checking authentication...')
      await checkAuth() // Refresh auth state with new session
      setChecking(false)
      console.log('OAuthCallback: Auth check complete')
    }
    
    handleCallback()
  }, [checkAuth, searchParams])
  
  // Redirect after auth check completes
  useEffect(() => {
    if (!checking) {
      console.log('OAuthCallback: Auth status =', isAuthenticated)
      if (isAuthenticated) {
        // Auto-sync orders after successful login
        const autoSyncOrders = async () => {
          setSyncing(true)
          try {
            console.log('OAuthCallback: Auto-syncing orders...')
            const result = await syncOrders()
            console.log('OAuthCallback: Sync complete', result)
            toast.success('Welcome! Your orders have been synced from Swiggy.', {
              description: `${result.orders_received || 0} orders synced successfully.`
            })
          } catch (err) {
            console.error('OAuthCallback: Auto-sync failed', err)
            // Don't block login if sync fails
            toast.warning('Orders sync will happen in background', {
              description: 'You can manually sync from the Orders page.'
            })
          } finally {
            setSyncing(false)
            setTimeout(() => {
              navigate('/dashboard')
            }, 1000)
          }
        }
        
        autoSyncOrders()
      } else {
        setError('Authentication failed. Please try again.')
      }
    }
  }, [checking, isAuthenticated, navigate])

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <div className="text-destructive text-6xl mb-4">❌</div>
          <p className="text-lg font-medium text-destructive">Authentication Failed</p>
          <p className="text-sm text-muted-foreground mt-2">{error}</p>
          <button 
            onClick={() => navigate('/login')}
            className="mt-4 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:opacity-90"
          >
            Try Again
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <div className="h-32 w-32 animate-spin rounded-full border-b-2 border-primary mx-auto"></div>
        {syncing ? (
          <>
            <p className="mt-4 text-lg font-medium">Syncing your orders...</p>
            <p className="text-sm text-muted-foreground">Fetching your Swiggy order history</p>
          </>
        ) : (
          <>
            <p className="mt-4 text-lg font-medium">Connecting to Swiggy...</p>
            <p className="text-sm text-muted-foreground">Please wait</p>
          </>
        )}
      </div>
    </div>
  )
}

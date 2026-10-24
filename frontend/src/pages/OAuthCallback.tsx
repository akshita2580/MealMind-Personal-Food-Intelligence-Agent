import { useEffect, useContext, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { AuthContext } from '../context/AuthContext'

export default function OAuthCallback() {
  const navigate = useNavigate()
  const { checkAuth, isAuthenticated } = useContext(AuthContext)
  const [searchParams] = useSearchParams()
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    // Extract session_id from URL and store it
    const handleCallback = async () => {
      console.log('OAuthCallback: Processing OAuth callback...')
      
      const sessionId = searchParams.get('session_id')
      if (sessionId) {
        console.log('OAuthCallback: Session ID received, storing...')
        localStorage.setItem('session_id', sessionId)
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
      setTimeout(() => {
        navigate('/dashboard')
      }, 1000)
    }
  }, [checking, isAuthenticated, navigate])

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <div className="h-32 w-32 animate-spin rounded-full border-b-2 border-primary mx-auto"></div>
        <p className="mt-4 text-lg font-medium">Connecting to Swiggy...</p>
        <p className="text-sm text-muted-foreground">Please wait</p>
      </div>
    </div>
  )
}

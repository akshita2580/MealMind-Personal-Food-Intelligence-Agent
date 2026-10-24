import { createContext, useState, useEffect, ReactNode } from 'react'

interface AuthContextType {
  isAuthenticated: boolean
  loading: boolean
  checkAuth: () => Promise<void>
}

export const AuthContext = createContext<AuthContextType>({
  isAuthenticated: false,
  loading: true,
  checkAuth: async () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [loading, setLoading] = useState(true)

  const checkAuth = async () => {
    try {
      console.log('AuthContext: Checking authentication status...')
      
      // Get session_id from localStorage
      const sessionId = localStorage.getItem('session_id')
      console.log('AuthContext: Session ID from localStorage:', sessionId ? 'present' : 'missing')
      
      const headers: HeadersInit = {}
      if (sessionId) {
        headers['X-Session-ID'] = sessionId
      }
      
      const response = await fetch('/api/auth/status', {
        credentials: 'include', // Still include for cookie fallback
        headers,
      })
      
      console.log('AuthContext: /api/auth/status response:', response.status)
      
      if (response.ok) {
        const data = await response.json()
        console.log('AuthContext: Auth data:', data)
        setIsAuthenticated(data.authenticated === true)
      } else {
        console.log('AuthContext: Auth check failed with status:', response.status)
        setIsAuthenticated(false)
      }
    } catch (error) {
      console.error('AuthContext: Auth check error:', error)
      setIsAuthenticated(false)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    checkAuth()
  }, [])

  return (
    <AuthContext.Provider value={{ isAuthenticated, loading, checkAuth }}>
      {children}
    </AuthContext.Provider>
  )
}

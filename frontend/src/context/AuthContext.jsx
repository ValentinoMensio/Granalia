import { createContext, useContext, useEffect, useState } from 'react'
import { request, setCsrfToken } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)

  async function refreshSession() {
    const data = await request('/api/auth/session')
    setCsrfToken(data.authenticated ? data.csrf_token : '')
    setSession(data.authenticated ? data : null)
    return data
  }

  async function login(username, password) {
    const data = await request('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    setCsrfToken(data.csrf_token)
    setSession(data)
    return data
  }

  async function logout() {
    try {
      await request('/api/auth/logout', { method: 'POST' })
    } finally {
      setCsrfToken('')
      setSession(null)
    }
  }

  useEffect(() => {
    refreshSession()
      .catch(() => {
        setCsrfToken('')
        setSession(null)
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    function handleUnauthorized() {
      setCsrfToken('')
      setSession(null)
    }

    window.addEventListener('granalia:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('granalia:unauthorized', handleUnauthorized)
  }, [])

  return <AuthContext.Provider value={{ session, loading, login, logout, refreshSession }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}

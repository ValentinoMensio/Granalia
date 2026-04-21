import { createContext, useContext, useEffect, useState } from 'react'
import { request } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)

  async function refreshSession() {
    const data = await request('/api/auth/session')
    setSession(data.authenticated ? data : null)
    return data
  }

  async function login(username, password) {
    const data = await request('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    setSession(data)
    return data
  }

  async function logout() {
    await request('/api/auth/logout', { method: 'POST' })
    setSession(null)
  }

  useEffect(() => {
    refreshSession().finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    function handleUnauthorized() {
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

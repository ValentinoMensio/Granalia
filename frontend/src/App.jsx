import { Component } from 'react'
import { BrowserRouter, Navigate, Routes, Route } from 'react-router-dom'
import Login from './pages/Login'
import { AuthProvider, useAuth } from './context/AuthContext'
import { GranaliaProvider } from './context/GranaliaContext'
import AppHeader from './components/layout/AppHeader'
import StatusBar from './components/layout/StatusBar'
import OrderCreator from './pages/OrderCreator'
import InvoiceHistory from './pages/InvoiceHistory'
import InvoiceStats from './pages/InvoiceStats'
import Management from './pages/Management'
import CustomerEditor from './pages/CustomerEditor'
import ProductEditor from './pages/ProductEditor'
import TransportEditor from './pages/TransportEditor'

class AppErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="app-shell py-16">
          <div className="surface mx-auto max-w-2xl p-6 text-center">
            <h1 className="subsection-title text-xl">No se pudo cargar la pantalla</h1>
            <p className="mt-3 text-sm text-slate-500">{this.state.error.message}</p>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

function AppLayout() {
  const { session } = useAuth()
  const isAdmin = session?.role === 'admin'

  return (
    <div className="app-shell">
      <AppHeader />

      <Routes>
        <Route path="/" element={<OrderCreator />} />
        <Route path="/history" element={<InvoiceHistory />} />
        <Route path="/history/stats" element={isAdmin ? <InvoiceStats /> : <Navigate to="/history" replace />} />
        <Route path="/management" element={isAdmin ? <Management /> : <Navigate to="/history" replace />} />
        <Route path="/customers/new" element={isAdmin ? <CustomerEditor /> : <Navigate to="/history" replace />} />
        <Route path="/customers/:id" element={isAdmin ? <CustomerEditor /> : <Navigate to="/history" replace />} />
        <Route path="/products/new" element={isAdmin ? <ProductEditor /> : <Navigate to="/history" replace />} />
        <Route path="/products/:id" element={isAdmin ? <ProductEditor /> : <Navigate to="/history" replace />} />
        <Route path="/transports/new" element={isAdmin ? <TransportEditor /> : <Navigate to="/history" replace />} />
        <Route path="/transports/:id" element={isAdmin ? <TransportEditor /> : <Navigate to="/history" replace />} />
      </Routes>

      <StatusBar />
    </div>
  )
}

function ProtectedApp() {
  const { loading, session } = useAuth()

  if (loading) {
    return <div className="app-shell py-16 text-center text-sm text-brand-ink/70">Verificando sesión...</div>
  }

  if (!session?.authenticated) {
    return <Login />
  }

  return <GranaliaProvider><AppLayout /></GranaliaProvider>
}

function App() {
  return (
    <AppErrorBoundary>
      <AuthProvider>
        <BrowserRouter>
          <ProtectedApp />
        </BrowserRouter>
      </AuthProvider>
    </AppErrorBoundary>
  )
}

export default App

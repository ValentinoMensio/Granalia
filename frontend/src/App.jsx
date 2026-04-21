import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom'
import Login from './pages/Login'
import { AuthProvider, useAuth } from './context/AuthContext'
import { GranaliaProvider } from './context/GranaliaContext'
import AppHeader from './components/layout/AppHeader'
import StatusBar from './components/layout/StatusBar'
import OrderCreator from './pages/OrderCreator'
import InvoiceHistory from './pages/InvoiceHistory'
import Management from './pages/Management'
import CustomerEditor from './pages/CustomerEditor'
import ProductEditor from './pages/ProductEditor'
import TransportEditor from './pages/TransportEditor'

function AppLayout() {
  const location = useLocation()
  const isCreator = location.pathname === '/'

  if (isCreator) {
    return (
      <div className="app-shell">
        <AppHeader />

        <Routes>
          <Route path="/" element={<OrderCreator />} />
          <Route path="/history" element={<InvoiceHistory />} />
          <Route path="/management" element={<Management />} />
          <Route path="/customers/new" element={<CustomerEditor />} />
          <Route path="/customers/:id" element={<CustomerEditor />} />
          <Route path="/products/new" element={<ProductEditor />} />
          <Route path="/products/:id" element={<ProductEditor />} />
          <Route path="/transports/new" element={<TransportEditor />} />
          <Route path="/transports/:id" element={<TransportEditor />} />
        </Routes>

        <StatusBar />
      </div>
    )
  }

  return (
    <div className="app-shell">
      <AppHeader />

      <Routes>
        <Route path="/" element={<OrderCreator />} />
        <Route path="/history" element={<InvoiceHistory />} />
        <Route path="/management" element={<Management />} />
        <Route path="/customers/new" element={<CustomerEditor />} />
        <Route path="/customers/:id" element={<CustomerEditor />} />
        <Route path="/products/new" element={<ProductEditor />} />
        <Route path="/products/:id" element={<ProductEditor />} />
        <Route path="/transports/new" element={<TransportEditor />} />
        <Route path="/transports/:id" element={<TransportEditor />} />
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
    <AuthProvider>
      <BrowserRouter>
        <ProtectedApp />
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App

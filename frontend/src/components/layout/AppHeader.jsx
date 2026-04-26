import { Link, useLocation } from 'react-router-dom'
import logoImage from '../../../../img/logo.png'
import Button from '../ui/Button'
import { useAuth } from '../../context/AuthContext'

function AppHeader() {
  const location = useLocation()
  const { logout } = useAuth()
  const links = [
    { to: '/', label: 'Creador' },
    { to: '/history', label: 'Facturas' },
    { to: '/management', label: 'Gestión' },
  ]

  return (
    <header className="surface-strong px-5 py-4 lg:px-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-4">
          <Link to="/" aria-label="Ir al creador" className="flex h-20 w-15 items-center justify-center rounded-xl border border-slate-200 bg-white shadow-sm">
            <img src={logoImage} alt="Granalia" className="h-20 w-auto object-contain" />
          </Link>
            <div className="text-sm text-center tracking-[-0.03em] text-brand-ink">Sistema de facturación y gestión comercial</div>
        </div>
        <div className="flex flex-col gap-4 lg:items-end">
          <div className="flex flex-wrap items-center gap-3">
            <nav className="tab-nav">
              {links.map((link) => {
                const active = location.pathname === link.to
                return (
                  <Link
                    key={link.to}
                    to={link.to}
                    className={`tab-button ${active ? 'tab-button-active' : ''}`.trim()}
                  >
                    {link.label}
                  </Link>
                )
              })}
            </nav>
            <Button variant="danger" onClick={logout}>
              Salir
            </Button>
          </div>
        </div>
      </div>
    </header>
  )
}

export default AppHeader

import { Link, useLocation } from 'react-router-dom'
import logoImage from '../../../../img/logo.png'
import Button from '../ui/Button'
import { useAuth } from '../../context/AuthContext'

function AppHeader() {
  const location = useLocation()
  const { logout } = useAuth()
  const links = [
    { to: '/', label: 'Creador', exact: true },
    { to: '/history', label: 'Facturas', exact: true },
    { to: '/history/stats', label: 'Estadística', exact: true },
    { to: '/management', label: 'Gestión' },
    { to: '/history/stats', label: 'Estadística' },
  ]

  return (
    <header className="surface-strong px-3 py-3 sm:px-5 sm:py-4 lg:px-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-3 sm:gap-4">
          <Link to="/" aria-label="Ir al creador" className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white shadow-sm sm:h-20 sm:w-16">
            <img src={logoImage} alt="Granalia" className="h-14 w-auto object-contain sm:h-20" />
          </Link>
            <div className="text-sm leading-5 tracking-[-0.03em] text-brand-ink sm:text-center">Sistema de facturación y gestión comercial</div>
        </div>
        <div className="flex w-full flex-col gap-4 lg:w-auto lg:items-end">
          <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-center lg:w-auto">
            <nav className="tab-nav">
              {links.map((link) => {
                const active = link.exact ? location.pathname === link.to : location.pathname.startsWith(link.to)
                return (
                  <Link
                    key={link.to}
                    to={link.to}
                    aria-current={active ? 'page' : undefined}
                    className={`tab-button ${active ? 'tab-button-active' : ''}`.trim()}
                  >
                    {link.label}
                  </Link>
                )
              })}
            </nav>
            <Button variant="danger" className="w-full sm:w-auto" onClick={logout}>
              Salir
            </Button>
          </div>
        </div>
      </div>
    </header>
  )
}

export default AppHeader

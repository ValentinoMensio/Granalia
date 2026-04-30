import { Link, useLocation } from 'react-router-dom'
import logoImage from '../../../../img/logof.png'
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
  ]

  return (
    <header className="surface-strong px-3 py-3 sm:px-5 sm:py-4 lg:px-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex items-center gap-3 sm:gap-4">
          <Link
            to="/"
            aria-label="Ir al creador"
            className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl border border-slate-200 bg-white p-2 shadow-sm transition hover:shadow-md sm:h-20 sm:w-20"
          >
            <img
              src={logoImage}
              alt="Granalia"
              className="max-h-full max-w-full object-contain"
            />
          </Link>

          <div className="min-w-0">
            <p className="text-base font-semibold leading-tight tracking-[-0.02em] text-brand-ink sm:text-lg">
              Granalia
            </p>
            <p className="mt-0.5 max-w-[260px] text-xs leading-4 text-slate-500 sm:text-sm sm:leading-5">
              Sistema de facturación y gestión comercial
            </p>
          </div>
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

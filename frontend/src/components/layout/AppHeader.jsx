import { Link, useLocation } from 'react-router-dom'
import { BarChart3, FilePlus2, LogOut, ReceiptText, Settings } from '../ui/Icons'
import logoImage from '../../../../img/logof.png'
import Button from '../ui/Button'
import { useAuth } from '../../context/AuthContext'

const icons = {
  Creador: FilePlus2,
  Facturas: ReceiptText,
  Estadística: BarChart3,
  Gestión: Settings,
}

function AppHeader() {
  const location = useLocation()
  const { logout, session } = useAuth()
  const isAdmin = session?.role === 'admin'
  const links = [
    { to: '/', label: 'Creador', exact: true },
    { to: '/history', label: 'Facturas', exact: true },
    ...(isAdmin ? [
      { to: '/history/stats', label: 'Estadística', exact: true },
      { to: '/management', label: 'Gestión' },
    ] : []),
  ]

  function isActive(link) {
    if (link.exact) return location.pathname === link.to
    return location.pathname.startsWith(link.to)
  }

  return (
    <header className="surface-strong overflow-hidden px-3 py-3 sm:px-5 sm:py-4 lg:px-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-3 sm:gap-4">
          <Link
            to="/"
            aria-label="Ir al creador"
            className="brand-mark hover:-translate-y-0.5 hover:shadow-lg"
          >
            <img
              src={logoImage}
              alt="Granalia"
              className="max-h-full max-w-full object-contain"
            />
          </Link>

          <div className="min-w-0">
            <p className="text-lg font-extrabold leading-tight tracking-[-0.05em] text-white sm:text-xl">
              Granalia
            </p>
            <p className="mt-0.5 max-w-[320px] text-xs font-semibold leading-4 text-white/72 sm:text-sm sm:leading-5">
              Sistema de facturación y gestión comercial
            </p>
          </div>
        </div>
        <div className="flex w-full flex-col gap-4 lg:w-auto lg:items-end">
          <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-center lg:w-auto">
            <nav className="tab-nav">
              {links.map((link) => {
                const active = isActive(link)
                const Icon = icons[link.label]
                return (
                  <Link
                    key={link.to}
                    to={link.to}
                    aria-current={active ? 'page' : undefined}
                    className={`tab-button ${active ? 'tab-button-active' : ''}`.trim()}
                  >
                    {Icon ? <Icon size={17} strokeWidth={2.2} /> : null}
                    {link.label}
                  </Link>
                )
              })}
            </nav>
            <Button variant="danger" className="w-full sm:w-auto" onClick={logout}>
              <LogOut size={16} strokeWidth={2.2} />
              Salir
            </Button>
          </div>
        </div>
      </div>
    </header>
  )
}

export default AppHeader

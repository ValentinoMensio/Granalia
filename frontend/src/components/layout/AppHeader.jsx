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
    <header className="surface-strong px-7 py-7 lg:px-8 lg:py-8">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center">
          <Link to="/" aria-label="Ir al creador">
            <img src={logoImage} alt="Granalia" className="h-16 w-auto rounded-2xl object-contain lg:h-20" />
          </Link>
        </div>
        <div className="flex flex-col gap-5 lg:items-end">
          <div className="flex items-center gap-3">
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

import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { request } from '../lib/api'
import { summarizeDiscounts } from '../lib/format'
import { useGranalia } from '../context/GranaliaContext'
import Button from '../components/ui/Button'
import PageSectionHeader from '../components/ui/PageSectionHeader'

export default function Management() {
  const { setStatus, customers, bootstrap, catalog, refreshAll } = useGranalia()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedTab = searchParams.get('tab')
  const [tab, setTab] = useState(['customers', 'transports', 'products'].includes(requestedTab) ? requestedTab : 'customers')
  const [searchTerm, setSearchTerm] = useState('')
  const [loading, setLoading] = useState(false)
  const normalizedSearch = searchTerm.trim().toLowerCase()
  const filteredCustomers = normalizedSearch
    ? customers.filter((customer) => customer.name.toLowerCase().includes(normalizedSearch))
    : customers
  const filteredTransports = normalizedSearch
    ? (bootstrap?.transports || []).filter((transport) => transport.name.toLowerCase().includes(normalizedSearch))
    : (bootstrap?.transports || [])
  const filteredProducts = normalizedSearch
    ? catalog.filter((product) => product.name.toLowerCase().includes(normalizedSearch))
    : catalog

  function selectTab(nextTab) {
    setTab(nextTab)
    setSearchTerm('')
    setSearchParams({ tab: nextTab })
  }

  useEffect(() => {
    if (['customers', 'transports', 'products'].includes(requestedTab) && requestedTab !== tab) {
      setTab(requestedTab)
    }
  }, [requestedTab, tab])

  async function handleDelete(type, id) {
    if (!confirm('¿Estás seguro de eliminar este elemento?')) return
    setLoading(true)
    try {
      const path = type === 'customer' 
        ? `/api/customers/${id}` 
        : type === 'transport' 
        ? `/api/transports/${id}` 
        : `/api/products/${id}`
      
      await request(path, { method: 'DELETE' })
      await refreshAll()
      setStatus(`${type} eliminado correctamente.`)
    } catch (e) {
      setStatus(`Error al eliminar: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mt-8 space-y-6">
      <PageSectionHeader
        eyebrow="Administración"
        title="Gestión del sistema"
      />

      <div className="page-header">
        <div className="soft-note">Elegí una sección para editar registros, crear nuevos elementos y depurar datos.</div>
        <nav className="tab-nav">
          {['customers', 'transports', 'products'].map((t) => (
            <button
              key={t}
              onClick={() => selectTab(t)}
              className={`tab-button ${
                tab === t ? 'tab-button-active' : ''
              }`}
            >
              {t === 'customers' ? 'Clientes' : t === 'transports' ? 'Transportes' : 'Productos'}
            </button>
          ))}
        </nav>
      </div>

      <div className="surface p-6">
        {tab === 'customers' && (
          <div className="space-y-6">
            <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div>
                <h2 className="subsection-title">Clientes</h2>
                <input
                  type="search"
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  placeholder="Buscar clientes por nombre..."
                  className="mt-3 w-full min-w-[280px] rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-red/20 focus:border-brand-red md:w-96"
                />
              </div>
              <Button variant="primary" onClick={() => navigate('/customers/new')}>
                Nuevo Cliente
              </Button>
            </div>

            <div className="table-shell">
              <table className="table-base">
                <thead className="table-head">
                  <tr>
                    <th>ID</th>
                    <th>Nombre</th>
                    <th>Transporte</th>
                    <th>Descuentos</th>
                    <th className="text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCustomers.map((c) => (
                    <tr key={c.id} className="table-row">
                      <td className="table-cell font-mono text-xs">{c.id}</td>
                      <td className="table-cell font-medium">{c.name}</td>
                      <td className="table-cell text-slate-600">{c.transport || '—'}</td>
                      <td className="table-cell text-slate-600">{summarizeDiscounts(c)}</td>
                      <td className="table-cell">
                        <div className="flex items-center justify-end gap-2">
                          <Button variant="ghost" onClick={() => navigate(`/customers/${c.id}`)}>
                            Editar
                          </Button>
                          <Button variant="danger" onClick={() => handleDelete('customer', c.id)} disabled={loading}>
                            Eliminar
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {filteredCustomers.length === 0 && (
                    <tr>
                      <td colSpan="5" className="table-cell py-8 text-center text-slate-400 italic">No hay clientes que coincidan con la búsqueda.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === 'transports' && (
          <div className="space-y-6">
            <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div>
                <h2 className="subsection-title">Transportes</h2>
                <input
                  type="search"
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  placeholder="Buscar transportes por nombre..."
                  className="mt-3 w-full min-w-[280px] rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-red/20 focus:border-brand-red md:w-96"
                />
              </div>
              <Button variant="primary" onClick={() => navigate('/transports/new')}>
                Nuevo Transporte
              </Button>
            </div>

            <div className="table-shell">
              <table className="table-base">
                <thead className="table-head">
                  <tr>
                    <th>ID</th>
                    <th>Nombre</th>
                    <th className="text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTransports.map((t) => (
                    <tr key={t.transport_id} className="table-row">
                      <td className="table-cell font-mono text-xs">{t.transport_id}</td>
                      <td className="table-cell font-medium">{t.name}</td>
                      <td className="table-cell text-right space-x-2">
                        <Button variant="ghost" onClick={() => navigate(`/transports/${t.transport_id}`)}>
                          Editar
                        </Button>
                        <Button variant="danger" onClick={() => handleDelete('transport', t.transport_id)} disabled={loading}>
                          Eliminar
                        </Button>
                      </td>
                    </tr>
                  ))}
                  {filteredTransports.length === 0 && (
                    <tr>
                      <td colSpan="3" className="table-cell py-8 text-center text-slate-400 italic">No hay transportes que coincidan con la búsqueda.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === 'products' && (
          <div className="space-y-6">
            <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div>
                <h2 className="subsection-title">Productos</h2>
                <input
                  type="search"
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  placeholder="Buscar productos por nombre..."
                  className="mt-3 w-full min-w-[280px] rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-red/20 focus:border-brand-red md:w-96"
                />
              </div>
              <Button variant="primary" onClick={() => navigate('/products/new')}>
                Nuevo Producto
              </Button>
            </div>

            <div className="table-shell">
              <table className="table-base">
                <thead className="table-head">
                  <tr>
                    <th>ID</th>
                    <th>Nombre</th>
                    <th>Presentaciones</th>
                    <th className="text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredProducts.map((p) => (
                    <tr key={p.id} className="table-row">
                      <td className="table-cell font-mono text-xs">{p.id}</td>
                      <td className="table-cell font-medium">{p.name}</td>
                      <td className="table-cell text-slate-600">
                        {p.offerings?.length
                          ? p.offerings.map((offering) => offering.label).join(', ')
                          : 'Sin presentaciones'}
                      </td>
                      <td className="table-cell text-right space-x-2">
                        <Button variant="ghost" onClick={() => navigate(`/products/${p.id}`)}>
                          Editar
                        </Button>
                        <Button variant="danger" onClick={() => handleDelete('product', p.id)} disabled={loading}>
                          Eliminar
                        </Button>
                      </td>
                    </tr>
                  ))}
                  {filteredProducts.length === 0 && (
                    <tr>
                      <td colSpan="4" className="table-cell py-8 text-center text-slate-400 italic">No hay productos que coincidan con la búsqueda.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { request } from '../lib/api'
import { summarizeAutomaticBonuses, summarizeDiscounts } from '../lib/format'
import { useGranalia } from '../context/GranaliaContext'
import Button from '../components/ui/Button'
import PageSectionHeader from '../components/ui/PageSectionHeader'
import PriceListPanel from '../components/sidebar/PriceListPanel'

export default function Management() {
  const { setStatus, customers, bootstrap, catalog, priceListUploadName, priceListUploadTargetId, uploading, setPdfFile, setPriceListUploadName, setPriceListUploadTargetId, uploadPriceList, deletePriceList, renamePriceList, refreshAll } = useGranalia()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedTab = searchParams.get('tab')
  const [tab, setTab] = useState(['customers', 'transports', 'products'].includes(requestedTab) ? requestedTab : 'customers')
  const [searchTerm, setSearchTerm] = useState('')
  const [loading, setLoading] = useState(false)
  const normalizedSearch = searchTerm.trim().toLowerCase()
  const filteredCustomers = normalizedSearch
    ? customers.filter((customer) => [customer.name, customer.business_name, customer.cuit, customer.email]
      .some((value) => String(value || '').toLowerCase().includes(normalizedSearch)))
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

  async function handleDeletePriceList(priceList) {
    if (!window.confirm(`¿Eliminar la lista de precios "${priceList.name}"? Las facturas existentes conservarán sus importes, pero quedarán sin lista asociada.`)) return
    setLoading(true)
    try {
      await deletePriceList(priceList.id)
    } catch (e) {
      setStatus(`Error al eliminar lista: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  async function handleRenamePriceList(priceList) {
    const nextName = window.prompt('Nuevo nombre de la lista de precios', priceList.name)?.trim()
    if (!nextName || nextName === priceList.name) return
    setLoading(true)
    try {
      await renamePriceList(priceList.id, nextName)
    } catch (e) {
      setStatus(`Error al renombrar lista: ${e.message}`)
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
              type="button"
              onClick={() => selectTab(t)}
              aria-current={tab === t ? 'page' : undefined}
              className={`tab-button ${
                tab === t ? 'tab-button-active' : ''
              }`}
            >
              {t === 'customers' ? 'Clientes' : t === 'transports' ? 'Transportes' : 'Productos'}
            </button>
          ))}
        </nav>
      </div>

      <div className="surface p-4 sm:p-6">
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
                  className="input mt-3 md:w-96"
                />
              </div>
              <Button variant="primary" className="w-full sm:w-auto" onClick={() => navigate('/customers/new')}>
                Nuevo Cliente
              </Button>
            </div>

            <div className="mobile-list">
              {filteredCustomers.map((c) => (
                <article key={c.id} className="mobile-card">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="mobile-card-kicker">#{c.id}</div>
                      <h3 className="mobile-card-title mt-1 break-words">{c.name}</h3>
                    </div>
                  </div>
                  <div className="mobile-field-grid">
                    <div className="mobile-field">
                      <span className="mobile-field-label">Transporte</span>
                      <span className="mobile-field-value">{c.transport || 'Sin transporte'}</span>
                    </div>
                    <div className="mobile-field">
                      <span className="mobile-field-label">Descuentos</span>
                      <span className="mobile-field-value break-words">{summarizeDiscounts(c)}</span>
                    </div>
                    <div className="mobile-field">
                      <span className="mobile-field-label">Bonificación</span>
                      <span className="mobile-field-value break-words">{summarizeAutomaticBonuses(c, catalog)}</span>
                    </div>
                  </div>
                  <div className="mobile-actions">
                    <Button variant="secondary" className="w-full" onClick={() => navigate(`/customers/${c.id}`)}>
                      Editar
                    </Button>
                    <Button variant="danger" className="w-full" onClick={() => handleDelete('customer', c.id)} disabled={loading}>
                      Eliminar
                    </Button>
                  </div>
                </article>
              ))}
              {filteredCustomers.length === 0 && (
                <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm italic text-slate-400">
                  No hay clientes que coincidan con la búsqueda.
                </div>
              )}
            </div>

            <div className="table-shell hidden lg:block">
              <table className="table-base">
                <thead className="table-head">
                  <tr>
                    <th>ID</th>
                    <th>Nombre</th>
                    <th>Transporte</th>
                    <th>Descuentos</th>
                    <th>Bonificación</th>
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
                      <td className="table-cell text-slate-600">{summarizeAutomaticBonuses(c, catalog)}</td>
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
                      <td colSpan="6" className="table-cell py-8 text-center text-slate-400 italic">No hay clientes que coincidan con la búsqueda.</td>
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
                  className="input mt-3 md:w-96"
                />
              </div>
              <Button variant="primary" className="w-full sm:w-auto" onClick={() => navigate('/transports/new')}>
                Nuevo Transporte
              </Button>
            </div>

            <div className="mobile-list">
              {filteredTransports.map((t) => (
                <article key={t.transport_id} className="mobile-card">
                  <div className="min-w-0">
                    <div className="mobile-card-kicker">#{t.transport_id}</div>
                    <h3 className="mobile-card-title mt-1 break-words">{t.name}</h3>
                  </div>
                  <div className="mobile-actions">
                    <Button variant="secondary" className="w-full" onClick={() => navigate(`/transports/${t.transport_id}`)}>
                      Editar
                    </Button>
                    <Button variant="danger" className="w-full" onClick={() => handleDelete('transport', t.transport_id)} disabled={loading}>
                      Eliminar
                    </Button>
                  </div>
                </article>
              ))}
              {filteredTransports.length === 0 && (
                <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm italic text-slate-400">
                  No hay transportes que coincidan con la búsqueda.
                </div>
              )}
            </div>

            <div className="table-shell hidden lg:block">
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
                  className="input mt-3 md:w-96"
                />
              </div>
              <Button variant="primary" className="w-full sm:w-auto" onClick={() => navigate('/products/new')}>
                Nuevo Producto
              </Button>
            </div>

            <div className="mobile-list">
              {filteredProducts.map((p) => (
                <article key={p.id} className="mobile-card">
                  <div className="min-w-0">
                    <div className="mobile-card-kicker">#{p.id}</div>
                    <h3 className="mobile-card-title mt-1 break-words">{p.name}</h3>
                  </div>
                  <div className="mobile-field-grid">
                    <div className="mobile-field">
                      <span className="mobile-field-label">Presentaciones</span>
                      <span className="mobile-field-value break-words">
                        {p.offerings?.length
                          ? p.offerings.map((offering) => offering.label).join(', ')
                          : 'Sin presentaciones'}
                      </span>
                    </div>
                  </div>
                  <div className="mobile-actions">
                    <Button variant="secondary" className="w-full" onClick={() => navigate(`/products/${p.id}`)}>
                      Editar
                    </Button>
                    <Button variant="danger" className="w-full" onClick={() => handleDelete('product', p.id)} disabled={loading}>
                      Eliminar
                    </Button>
                  </div>
                </article>
              ))}
              {filteredProducts.length === 0 && (
                <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm italic text-slate-400">
                  No hay productos que coincidan con la búsqueda.
                </div>
              )}
            </div>

            <div className="table-shell hidden lg:block">
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

            <PriceListPanel
              bootstrap={bootstrap}
              priceListUploadName={priceListUploadName}
              priceListUploadTargetId={priceListUploadTargetId}
              uploading={uploading}
              onDelete={handleDeletePriceList}
              onRename={handleRenamePriceList}
              onFileChange={setPdfFile}
              onUploadNameChange={setPriceListUploadName}
              onUploadTargetChange={setPriceListUploadTargetId}
              onUpload={uploadPriceList}
            />
          </div>
        )}
      </div>
    </div>
  )
}

import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGranalia } from '../context/GranaliaContext'
import { money } from '../lib/format'
import Button from '../components/ui/Button'
import PageSectionHeader from '../components/ui/PageSectionHeader'

const PAGE_SIZE = 10
const EMPTY_FILTERS = { customerId: '', dateFrom: '', dateTo: '', transport: '', minTotal: '', maxTotal: '' }

export default function InvoiceHistory() {
  const navigate = useNavigate()
  const { bootstrap, invoices, customers, invoiceDetail, loadInvoiceDetail, clearInvoiceDetail, invoiceDownloadUrl, invoicePdfUrl, startInvoiceEdit, deleteInvoice } = useGranalia()
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [deletingInvoiceId, setDeletingInvoiceId] = useState(null)
  const [page, setPage] = useState(1)
  const todayKey = new Date().toLocaleDateString('en-CA')

  const filteredInvoices = useMemo(() => {
    const minTotal = filters.minTotal === '' ? null : Number(filters.minTotal)
    const maxTotal = filters.maxTotal === '' ? null : Number(filters.maxTotal)

    return invoices.filter((invoice) => {
      const matchesCustomer = !filters.customerId || String(invoice.customer_id || '') === String(filters.customerId)
      const matchesDateFrom = !filters.dateFrom || invoice.order_date >= filters.dateFrom
      const matchesDateTo = !filters.dateTo || invoice.order_date <= filters.dateTo
      const matchesDate = matchesDateFrom && matchesDateTo
      const matchesTransport = !filters.transport || String(invoice.transport_id || '') === String(filters.transport)
      const matchesMinTotal = minTotal === null || Number(invoice.final_total || 0) >= minTotal
      const matchesMaxTotal = maxTotal === null || Number(invoice.final_total || 0) <= maxTotal
      return matchesCustomer && matchesDate && matchesTransport && matchesMinTotal && matchesMaxTotal
    })
  }, [filters, invoices])

  const totalPages = Math.max(1, Math.ceil(filteredInvoices.length / PAGE_SIZE))

  const paginatedInvoices = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE
    return filteredInvoices.slice(start, start + PAGE_SIZE)
  }, [filteredInvoices, page])

  function updateFilter(field, value) {
    setFilters((current) => ({ ...current, [field]: value }))
    setPage(1)
  }

  function resetFilters() {
    setFilters(EMPTY_FILTERS)
    setPage(1)
  }

  async function handleSelectInvoice(invoiceId) {
    setLoadingDetail(true)
    try {
      await loadInvoiceDetail(invoiceId)
    } finally {
      setLoadingDetail(false)
    }
  }

  async function handleEditInvoice(invoiceId) {
    setLoadingDetail(true)
    try {
      await startInvoiceEdit(invoiceId)
      navigate('/')
    } finally {
      setLoadingDetail(false)
    }
  }

  async function handleDeleteInvoice(invoiceId) {
    if (!window.confirm(`¿Eliminar la factura #${invoiceId}? Esta acción no se puede deshacer.`)) {
      return
    }
    setDeletingInvoiceId(invoiceId)
    try {
      await deleteInvoice(invoiceId)
    } finally {
      setDeletingInvoiceId(null)
    }
  }

  function itemSecondaryLabel(item) {
    const productName = String(item.product_name || '').trim()
    const offeringLabel = String(item.offering_label || '').trim()
    const fullLabel = String(item.label || '').trim().toLowerCase()
    const normalizedOfferingLabel = offeringLabel.toLowerCase()

    if (!productName && !offeringLabel) return ''
    if (fullLabel && productName && offeringLabel && fullLabel === `${productName} ${offeringLabel}`.trim().toLowerCase()) {
      return ''
    }
    if (normalizedOfferingLabel && fullLabel.endsWith(normalizedOfferingLabel)) {
      return ''
    }
    return [productName, offeringLabel].filter(Boolean).join(' · ')
  }

  return (
    <div className="mt-8 space-y-6">
      <PageSectionHeader title="Facturas emitidas" />

      <div className="grid w-full items-start gap-4 sm:gap-6 xl:grid-cols-[220px_minmax(0,1fr)]">
      <div className="space-y-4">
        <aside className="surface w-full self-start p-4 sm:p-6">
          <div className="flex min-h-0 items-start justify-between gap-4 border-b border-stone-200 pb-4 pt-1 sm:min-h-[4.5rem]">
            <div>
              <h2 className="subsection-title text-xl sm:text-2xl">Filtros</h2>
            </div>
          </div>

          <div className="mt-6 space-y-3">
            <select
              value={filters.customerId}
              onChange={(event) => updateFilter('customerId', event.target.value)}
              className="input"
            >
              <option value="">Todos los clientes</option>
              {customers.map((customer) => (
                <option key={customer.id} value={customer.id}>{customer.name}</option>
              ))}
            </select>
            <input
              type="date"
              value={filters.dateFrom}
              onChange={(event) => updateFilter('dateFrom', event.target.value)}
              className="input"
            />
            <input
              type="date"
              value={filters.dateTo}
              onChange={(event) => updateFilter('dateTo', event.target.value)}
              className="input"
            />
            <select
              value={filters.transport}
              onChange={(event) => updateFilter('transport', event.target.value)}
              className="input"
            >
              <option value="">Todos los transportes</option>
              {(bootstrap?.transports || []).map((transport) => (
                <option key={transport.transport_id} value={transport.transport_id}>{transport.name}</option>
              ))}
            </select>
            <input
              type="number"
              min="0"
              value={filters.minTotal}
              onChange={(event) => updateFilter('minTotal', event.target.value)}
              placeholder="Total minimo"
              className="input"
            />
            <input
              type="number"
              min="0"
              value={filters.maxTotal}
              onChange={(event) => updateFilter('maxTotal', event.target.value)}
              placeholder="Total maximo"
              className="input"
            />
          </div>

          <div className="mt-3 flex justify-end">
            <Button variant="secondary" onClick={resetFilters} className="w-full">
              Limpiar filtros
            </Button>
          </div>
        </aside>

      </div>

      <section className="surface w-full self-start p-4 sm:p-6">
        <div className="flex min-h-0 flex-col gap-4 border-b border-stone-200 pb-4 pt-1 md:min-h-[4.5rem] md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="subsection-title text-xl sm:text-2xl">Facturas</h2>
          </div>
          <div className="badge self-start md:mt-1">{filteredInvoices.length} resultados</div>
        </div>

        <div className="mobile-list mt-6">
          {paginatedInvoices.map((invoice) => {
            const isUpcoming = invoice.order_date >= todayKey

            return (
              <article key={invoice.invoice_id} className={`rounded-2xl border p-4 ${isUpcoming ? 'border-slate-300 bg-stone-100' : 'border-slate-200 bg-white'}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-mono text-xs text-slate-500">#{invoice.invoice_id}</div>
                    <h3 className="mt-1 truncate font-semibold text-brand-ink">{invoice.client_name}</h3>
                  </div>
                  <div className="shrink-0 whitespace-nowrap text-right text-sm font-semibold text-brand-red">${money(invoice.final_total)}</div>
                </div>
                <div className="mt-3 grid gap-2 text-sm text-slate-600">
                  <div className="flex justify-between gap-3">
                    <span>Fecha</span>
                    <span className="font-medium text-slate-800">{invoice.order_date}</span>
                  </div>
                  <div className="flex justify-between gap-3">
                    <span>Transporte</span>
                    <span className="min-w-0 truncate text-right font-medium text-slate-800">{invoice.transport || 'Sin transporte'}</span>
                  </div>
                  <div className="flex justify-between gap-3">
                    <span>Tipo</span>
                    <span className="font-medium text-slate-800">{invoice.declared ? 'Declarada' : 'No declarada'}</span>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
                  <Button variant="secondary" className="w-full" onClick={() => handleSelectInvoice(invoice.invoice_id)}>
                    Detalle
                  </Button>
                  <Button variant="secondary" className="w-full" onClick={() => handleEditInvoice(invoice.invoice_id)}>
                    Editar
                  </Button>
                  <a
                    href={invoiceDownloadUrl(invoice.invoice_id)}
                    target="_blank"
                    rel="noreferrer"
                    className="btn-secondary w-full"
                  >
                    XLSX
                  </a>
                  <a
                    href={invoicePdfUrl(invoice.invoice_id)}
                    target="_blank"
                    rel="noreferrer"
                    className="btn-secondary w-full"
                  >
                    PDF
                  </a>
                  <Button
                    variant="danger"
                    className="col-span-2"
                    onClick={() => handleDeleteInvoice(invoice.invoice_id)}
                    disabled={deletingInvoiceId === invoice.invoice_id}
                  >
                    {deletingInvoiceId === invoice.invoice_id ? 'Eliminando...' : 'Eliminar'}
                  </Button>
                </div>
              </article>
            )
          })}
          {filteredInvoices.length === 0 && (
            <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-400">
              No hay facturas que coincidan con los filtros.
            </div>
          )}
        </div>

        <div className="table-shell mt-6 hidden lg:block">
          <table className="table-base min-w-[960px] table-fixed">
            <colgroup>
              <col className="w-[7%]" />
              <col className="w-[21%]" />
              <col className="w-[11%]" />
              <col className="w-[16%]" />
              <col className="w-[12%]" />
              <col className="w-[13%]" />
              <col className="w-[20%]" />
            </colgroup>
            <thead className="table-head">
              <tr>
                <th className="text-center">Factura</th>
                <th>Cliente</th>
                <th className="text-center">Fecha</th>
                <th>Transporte</th>
                <th className="text-center">Tipo</th>
                <th className="text-right">Total</th>
                <th className="text-center">Acciones</th>
              </tr>
            </thead>
            <tbody className="bg-white">
              {paginatedInvoices.map((invoice) => {
                const isUpcoming = invoice.order_date >= todayKey

                return (
                  <tr key={invoice.invoice_id} className={`table-row ${isUpcoming ? 'bg-stone-100 text-brand-ink' : ''}`}>
                    <td className="table-cell text-center font-mono text-xs">#{invoice.invoice_id}</td>
                    <td className="table-cell break-words font-medium leading-snug" title={invoice.client_name}>{invoice.client_name}</td>
                    <td className={`table-cell whitespace-nowrap text-center ${isUpcoming ? 'text-slate-800' : 'text-slate-600'}`}>{invoice.order_date}</td>
                    <td className={`table-cell break-words leading-snug ${isUpcoming ? 'text-slate-800' : 'text-slate-600'}`} title={invoice.transport || 'Sin transporte'}>{invoice.transport || 'Sin transporte'}</td>
                    <td className="table-cell text-center">{invoice.declared ? 'Declarada' : 'No declarada'}</td>
                    <td className="table-cell whitespace-nowrap text-right font-medium">${money(invoice.final_total)}</td>
                    <td className="table-cell">
                      <div className="flex items-center justify-center gap-x-2 whitespace-nowrap text-xs leading-tight">
                        <Button variant="ghost" className="px-0 py-0 text-brand-red" onClick={() => handleSelectInvoice(invoice.invoice_id)}>
                          Ver detalle
                        </Button>
                        <Button variant="ghost" className="px-0 py-0 text-brand-ink" onClick={() => handleEditInvoice(invoice.invoice_id)}>
                          Editar
                        </Button>
                        <a
                          href={invoicePdfUrl(invoice.invoice_id)}
                          target="_blank"
                          rel="noreferrer"
                          className="font-semibold text-brand-ink hover:text-brand-red"
                        >
                          PDF
                        </a>
                        <Button
                          variant="ghost"
                          className="px-0 py-0 text-xs text-red-600"
                          onClick={() => handleDeleteInvoice(invoice.invoice_id)}
                          disabled={deletingInvoiceId === invoice.invoice_id}
                        >
                          {deletingInvoiceId === invoice.invoice_id ? 'Eliminando...' : 'Eliminar'}
                        </Button>
                      </div>
                    </td>
                  </tr>
                )
              })}
              {filteredInvoices.length === 0 && (
                <tr>
                  <td colSpan="7" className="table-cell py-10 text-center text-slate-400">No hay facturas que coincidan con los filtros.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="mt-4 flex flex-col gap-3 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between">
          <div>Pagina {page} de {totalPages}</div>
          <div className="grid grid-cols-2 gap-2 sm:flex">
            <Button variant="secondary" className="w-full sm:w-auto" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={page === 1}>
              Anterior
            </Button>
            <Button variant="secondary" className="w-full sm:w-auto" onClick={() => setPage((current) => Math.min(totalPages, current + 1))} disabled={page === totalPages}>
              Siguiente
            </Button>
          </div>
        </div>
      </section>

      <aside className="surface w-full self-start p-4 sm:p-6 xl:col-span-2">
        <div className="flex min-h-0 items-start justify-between gap-4 border-b border-stone-200 pb-4 pt-1 sm:min-h-[4.5rem]">
          <div>
            <h2 className="subsection-title text-xl sm:text-2xl">Detalle</h2>
          </div>
          {invoiceDetail && (
            <Button variant="ghost" onClick={clearInvoiceDetail}>
              Cerrar
            </Button>
          )}
        </div>

        {!invoiceDetail && !loadingDetail && (
          <div className="mt-6 rounded-2xl border border-dashed border-slate-300 px-6 py-10 text-center text-sm text-slate-400">
            Seleccioná una factura para ver el detalle.
          </div>
        )}

        {loadingDetail && (
          <div className="mt-6 text-sm text-slate-500">Cargando detalle...</div>
        )}

        {invoiceDetail && !loadingDetail && (
          <div className="mt-6 space-y-6">
            <div className="surface-muted grid gap-4 p-4 text-sm md:grid-cols-3 xl:grid-cols-8">
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Factura</div>
                <div className="mt-1 font-mono">#{invoiceDetail.id}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Fecha</div>
                <div className="mt-1">{invoiceDetail.order_date}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Cliente</div>
                <div className="mt-1">{invoiceDetail.client_name}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Transporte</div>
                <div className="mt-1">{invoiceDetail.transport || 'Sin transporte'}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Cliente asociado</div>
                <div className="mt-1">{invoiceDetail.customer_name || 'Sin asociar'}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Transporte asociado</div>
                <div className="mt-1">{invoiceDetail.transport_name || (invoiceDetail.transport_id ? `#${invoiceDetail.transport_id}` : 'Sin asociar')}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Tipo</div>
                <div className="mt-1">{invoiceDetail.declared ? 'Declarada' : 'No declarada'}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Lista</div>
                <div className="mt-1">{invoiceDetail.price_list_name || 'Sin lista'}</div>
              </div>
            </div>

            <div>
              <div className="mb-3 flex items-center justify-between">
                <h3 className="font-medium">Lineas</h3>
              </div>
              <div className="mobile-list">
                {invoiceDetail.items.map((item) => (
                  <article key={item.id} className="mobile-card">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="mobile-card-kicker">Línea {item.line_number}</div>
                        <h4 className="mobile-card-title mt-1 break-words">{item.label}</h4>
                        {itemSecondaryLabel(item) ? (
                          <div className="mt-1 text-xs text-slate-400">{itemSecondaryLabel(item)}</div>
                        ) : null}
                      </div>
                      <div className="shrink-0 text-right text-sm font-semibold text-brand-red">${money(item.total)}</div>
                    </div>
                    <div className="mobile-field-grid">
                      <div className="mobile-field">
                        <span className="mobile-field-label">Cantidad</span>
                        <span className="mobile-field-value">{item.quantity}</span>
                      </div>
                      <div className="mobile-field">
                        <span className="mobile-field-label">Precio</span>
                        <span className="mobile-field-value">${money(item.unit_price)}</span>
                      </div>
                    </div>
                  </article>
                ))}
              </div>

              <div className="table-shell hidden lg:block">
                <table className="table-base">
                  <thead className="table-head">
                    <tr>
                      <th>#</th>
                      <th>Producto</th>
                      <th className="text-right">Cant.</th>
                      <th className="text-right">Precio</th>
                      <th className="text-right">Total</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white">
                    {invoiceDetail.items.map((item) => (
                      <tr key={item.id} className="table-row">
                        <td className="table-cell font-mono text-xs">{item.line_number}</td>
                        <td className="table-cell">
                          <div className="font-medium">{item.label}</div>
                          {itemSecondaryLabel(item) ? (
                            <div className="text-xs text-slate-400">{itemSecondaryLabel(item)}</div>
                          ) : null}
                        </td>
                        <td className="table-cell text-right">{item.quantity}</td>
                        <td className="table-cell text-right">${money(item.unit_price)}</td>
                        <td className="table-cell text-right font-medium">${money(item.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              <div className="metric-card">
                <div className="text-xs uppercase tracking-wide text-slate-400">Bruto</div>
                <div className="mt-2 text-lg font-semibold">${money(invoiceDetail.gross_total)}</div>
              </div>
              <div className="metric-card">
                <div className="text-xs uppercase tracking-wide text-slate-400">Descuento</div>
                <div className="mt-2 text-lg font-semibold">${money(invoiceDetail.discount_total)}</div>
              </div>
              <div className="metric-card">
                <div className="text-xs uppercase tracking-wide text-slate-400">Final</div>
                <div className="mt-2 text-lg font-semibold text-brand-red">${money(invoiceDetail.final_total)}</div>
              </div>
            </div>

            <div className="flex flex-col gap-3 border-t border-stone-200 pt-4 sm:flex-row sm:flex-wrap sm:justify-end">
              <Button variant="secondary" className="w-full sm:w-auto" onClick={() => handleEditInvoice(invoiceDetail.id)}>
                Editar factura
              </Button>
              <a
                href={invoiceDownloadUrl(invoiceDetail.id)}
                target="_blank"
                rel="noreferrer"
                className="btn-secondary w-full sm:w-auto"
              >
                Descargar XLSX
              </a>
              <a
                href={invoicePdfUrl(invoiceDetail.id)}
                target="_blank"
                rel="noreferrer"
                className="btn-secondary w-full sm:w-auto"
              >
                Descargar PDF
              </a>
              <Button
                variant="danger"
                className="w-full sm:w-auto"
                onClick={() => handleDeleteInvoice(invoiceDetail.id)}
                disabled={deletingInvoiceId === invoiceDetail.id}
              >
                {deletingInvoiceId === invoiceDetail.id ? 'Eliminando...' : 'Eliminar factura'}
              </Button>
            </div>
          </div>
        )}
      </aside>
      </div>
    </div>
  )
}

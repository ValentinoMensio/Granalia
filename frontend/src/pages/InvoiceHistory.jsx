import { useMemo, useState } from 'react'
import { useGranalia } from '../context/GranaliaContext'
import { money } from '../lib/format'
import Button from '../components/ui/Button'
import PageSectionHeader from '../components/ui/PageSectionHeader'

const PAGE_SIZE = 10
const EMPTY_FILTERS = { customerId: '', dateFrom: '', dateTo: '', transport: '', minTotal: '', maxTotal: '' }

export default function InvoiceHistory() {
  const { bootstrap, invoices, customers, invoiceDetail, loadInvoiceDetail, clearInvoiceDetail, invoiceDownloadUrl } = useGranalia()
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [page, setPage] = useState(1)

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

  function itemSecondaryLabel(item) {
    const productName = String(item.product_name || '').trim()
    const offeringLabel = String(item.offering_label || '').trim()
    const fullLabel = String(item.label || '').trim().toLowerCase()

    if (!productName && !offeringLabel) return ''
    if (fullLabel && productName && offeringLabel && fullLabel === `${productName} ${offeringLabel}`.trim().toLowerCase()) {
      return ''
    }
    return [productName, offeringLabel].filter(Boolean).join(' · ')
  }

  return (
    <div className="mt-8 space-y-6">
      <PageSectionHeader title="Facturas emitidas" />

      <div className="grid w-full items-start gap-6 xl:grid-cols-[220px_minmax(0,1fr)]">
      <aside className="surface w-full self-start p-6">
        <div className="flex min-h-[4.5rem] items-start justify-between gap-4 border-b border-stone-200 pb-4 pt-1">
          <div>
            <h2 className="subsection-title text-2xl">Filtros</h2>
          </div>
        </div>

        <div className="mt-6 space-y-3">
          <select
            value={filters.customerId}
            onChange={(event) => updateFilter('customerId', event.target.value)}
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-brand-red focus:outline-none"
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
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-brand-red focus:outline-none"
          />
          <input
            type="date"
            value={filters.dateTo}
            onChange={(event) => updateFilter('dateTo', event.target.value)}
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-brand-red focus:outline-none"
          />
          <select
            value={filters.transport}
            onChange={(event) => updateFilter('transport', event.target.value)}
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-brand-red focus:outline-none"
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
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-brand-red focus:outline-none"
          />
          <input
            type="number"
            min="0"
            value={filters.maxTotal}
            onChange={(event) => updateFilter('maxTotal', event.target.value)}
            placeholder="Total maximo"
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-brand-red focus:outline-none"
          />
        </div>

        <div className="mt-3 flex justify-end">
          <Button variant="secondary" onClick={resetFilters} className="w-full">
            Limpiar filtros
          </Button>
        </div>
      </aside>

      <section className="surface w-full self-start p-6">
        <div className="flex min-h-[4.5rem] flex-col gap-4 border-b border-stone-200 pb-4 pt-1 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="subsection-title text-2xl">Facturas</h2>
          </div>
          <div className="badge self-start md:mt-1">{filteredInvoices.length} resultados</div>
        </div>

        <div className="table-shell mt-6">
          <table className="table-base">
            <thead className="table-head">
              <tr>
                <th>Factura</th>
                <th>Cliente</th>
                <th>Fecha</th>
                <th>Transporte</th>
                <th className="text-right">Total</th>
                <th className="text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="bg-white">
              {paginatedInvoices.map((invoice) => (
                <tr key={invoice.invoice_id} className="table-row">
                  <td className="table-cell font-mono text-xs">#{invoice.invoice_id}</td>
                  <td className="table-cell font-medium">{invoice.client_name}</td>
                  <td className="table-cell text-slate-600">{invoice.order_date}</td>
                  <td className="table-cell text-slate-600">{invoice.transport || 'Sin transporte'}</td>
                  <td className="table-cell text-right font-medium">${money(invoice.final_total)}</td>
                  <td className="table-cell">
                    <div className="flex items-center justify-end gap-3">
                      <Button variant="ghost" className="px-0 py-0 text-sm text-brand-red" onClick={() => handleSelectInvoice(invoice.invoice_id)}>
                        Ver detalle
                      </Button>
                      <a
                        href={invoiceDownloadUrl(invoice.invoice_id)}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sm font-semibold text-brand-ink hover:text-brand-red"
                      >
                        Descargar
                      </a>
                    </div>
                  </td>
                </tr>
              ))}
              {filteredInvoices.length === 0 && (
                <tr>
                  <td colSpan="6" className="table-cell py-10 text-center text-slate-400">No hay facturas que coincidan con los filtros.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="mt-4 flex items-center justify-between text-sm text-slate-500">
          <div>Pagina {page} de {totalPages}</div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={page === 1}>
              Anterior
            </Button>
            <Button variant="secondary" onClick={() => setPage((current) => Math.min(totalPages, current + 1))} disabled={page === totalPages}>
              Siguiente
            </Button>
          </div>
        </div>
      </section>

      <aside className="surface w-full self-start p-6 xl:col-span-2">
        <div className="flex min-h-[4.5rem] items-start justify-between gap-4 border-b border-stone-200 pb-4 pt-1">
          <div>
            <h2 className="subsection-title text-2xl">Detalle</h2>
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
            <div className="surface-muted grid gap-4 p-4 text-sm md:grid-cols-3 xl:grid-cols-6">
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
            </div>

            <div>
              <div className="mb-3 flex items-center justify-between">
                <h3 className="font-medium">Lineas</h3>
                <a
                  href={invoiceDownloadUrl(invoiceDetail.id)}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm font-semibold text-brand-red hover:underline"
                >
                  Descargar XLSX
                </a>
              </div>
              <div className="table-shell">
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
          </div>
        )}
      </aside>
      </div>
    </div>
  )
}

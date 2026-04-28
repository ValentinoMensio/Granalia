import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGranalia } from '../context/GranaliaContext'
import { request } from '../lib/api'
import { money } from '../lib/format'
import Button from '../components/ui/Button'
import Metric from '../components/ui/Metric'
import PageSectionHeader from '../components/ui/PageSectionHeader'

const EMPTY_FILTERS = { customerId: '', dateFrom: '', dateTo: '', transport: '' }
const EMPTY_PRODUCT_FILTERS = { productId: '', offeringId: '' }

function monthLabel(value) {
  if (!value) return 'Sin fecha'
  const [year, month] = String(value).split('-')
  return `${month}/${year}`
}

function buildRanking(invoices, keyFn) {
  const grouped = new Map()
  for (const invoice of invoices) {
    const key = keyFn(invoice)
    const current = grouped.get(key) || { label: key, count: 0, bultos: 0, gross: 0, discount: 0, total: 0 }
    current.count += 1
    current.bultos += Number(invoice.total_bultos || 0)
    current.gross += Number(invoice.gross_total || 0)
    current.discount += Number(invoice.discount_total || 0)
    current.total += Number(invoice.final_total || 0)
    grouped.set(key, current)
  }
  return Array.from(grouped.values()).sort((a, b) => b.total - a.total)
}

function buildProductRanking(items) {
  const grouped = new Map()
  for (const item of items) {
    const product = item.product_name || String(item.label || '').trim() || 'Sin producto'
    const offering = item.offering_label || 'Sin formato'
    const key = `${product} / ${offering}`
    const current = grouped.get(key) || { label: key, count: 0, bultos: 0, gross: 0, discount: 0, total: 0 }
    current.count += 1
    current.bultos += Number(item.quantity || 0)
    current.gross += Number(item.gross || 0)
    current.discount += Number(item.discount || 0)
    current.total += Number(item.total || 0)
    grouped.set(key, current)
  }
  return Array.from(grouped.values()).sort((a, b) => b.total - a.total)
}

function RankingTable({ title, rows, countLabel = 'Facturas' }) {
  return (
    <section className="surface p-4 sm:p-6">
      <div className="mb-4 flex items-start justify-between gap-3 border-b border-stone-200 pb-3">
        <h2 className="subsection-title text-xl">{title}</h2>
        <div className="badge">{rows.length} filas</div>
      </div>
      <div className="table-shell max-h-[30rem] overflow-y-auto">
        <table className="table-base">
          <thead className="table-head">
            <tr>
              <th>Grupo</th>
              <th className="text-right">{countLabel}</th>
              <th className="text-right">Bultos</th>
              <th className="text-right">Descuento</th>
              <th className="text-right">Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className="table-row">
                <td className="table-cell font-medium">{row.label}</td>
                <td className="table-cell text-right">{row.count}</td>
                <td className="table-cell text-right">{money(row.bultos)}</td>
                <td className="table-cell text-right">${money(row.discount)}</td>
                <td className="table-cell text-right font-semibold text-brand-red">${money(row.total)}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan="5" className="table-cell py-8 text-center text-slate-400">No hay datos para estos filtros.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default function InvoiceStats() {
  const navigate = useNavigate()
  const { bootstrap, customers, invoices } = useGranalia()
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [productFilters, setProductFilters] = useState(EMPTY_PRODUCT_FILTERS)
  const [statsInvoices, setStatsInvoices] = useState(invoices)
  const [invoiceItems, setInvoiceItems] = useState([])
  const [loadingItems, setLoadingItems] = useState(false)

  useEffect(() => {
    setLoadingItems(true)
    Promise.all([request('/api/invoices?limit=10000'), request('/api/invoices/stats/items')])
      .then(([nextInvoices, nextItems]) => {
        setStatsInvoices(nextInvoices)
        setInvoiceItems(nextItems)
      })
      .finally(() => setLoadingItems(false))
  }, [])

  const filteredInvoices = useMemo(() => {
    return statsInvoices.filter((invoice) => {
      const matchesCustomer = !filters.customerId || String(invoice.customer_id || '') === String(filters.customerId)
      const matchesDateFrom = !filters.dateFrom || invoice.order_date >= filters.dateFrom
      const matchesDateTo = !filters.dateTo || invoice.order_date <= filters.dateTo
      const matchesTransport = !filters.transport || String(invoice.transport_id || '') === String(filters.transport)
      return matchesCustomer && matchesDateFrom && matchesDateTo && matchesTransport
    })
  }, [filters, statsInvoices])

  const summary = useMemo(() => {
    const gross = filteredInvoices.reduce((sum, invoice) => sum + Number(invoice.gross_total || 0), 0)
    const discount = filteredInvoices.reduce((sum, invoice) => sum + Number(invoice.discount_total || 0), 0)
    const total = filteredInvoices.reduce((sum, invoice) => sum + Number(invoice.final_total || 0), 0)
    const bultos = filteredInvoices.reduce((sum, invoice) => sum + Number(invoice.total_bultos || 0), 0)
    const average = filteredInvoices.length ? Math.round(total / filteredInvoices.length) : 0
    return { gross, discount, total, bultos, average }
  }, [filteredInvoices])

  const byCustomer = useMemo(() => buildRanking(filteredInvoices, (invoice) => invoice.client_name || 'Sin cliente'), [filteredInvoices])
  const byMonth = useMemo(() => buildRanking(filteredInvoices, (invoice) => monthLabel(invoice.order_date)), [filteredInvoices])
  const filteredInvoiceIds = useMemo(() => new Set(filteredInvoices.map((invoice) => String(invoice.invoice_id))), [filteredInvoices])
  const productOptions = useMemo(() => {
    const grouped = new Map()
    for (const item of invoiceItems) {
      const id = String(item.product_id || '')
      const label = item.product_name || 'Sin producto'
      const key = id || label
      if (!grouped.has(key)) grouped.set(key, { id, label })
    }
    return Array.from(grouped.values()).sort((a, b) => a.label.localeCompare(b.label, 'es'))
  }, [invoiceItems])
  const offeringOptions = useMemo(() => {
    const grouped = new Map()
    for (const item of invoiceItems) {
      const matchesProduct = !productFilters.productId || String(item.product_id || '') === String(productFilters.productId)
      if (!matchesProduct) continue
      const id = String(item.offering_id || '')
      const label = item.offering_label || 'Sin formato'
      const key = id || label
      if (!grouped.has(key)) grouped.set(key, { id, label })
    }
    return Array.from(grouped.values()).sort((a, b) => a.label.localeCompare(b.label, 'es'))
  }, [invoiceItems, productFilters.productId])
  const filteredItems = useMemo(
    () => invoiceItems.filter((item) => {
      const matchesInvoice = filteredInvoiceIds.has(String(item.invoice_id))
      const matchesProduct = !productFilters.productId || String(item.product_id || '') === String(productFilters.productId)
      const matchesOffering = !productFilters.offeringId || String(item.offering_id || '') === String(productFilters.offeringId)
      return matchesInvoice && matchesProduct && matchesOffering
    }),
    [filteredInvoiceIds, invoiceItems, productFilters]
  )
  const byProduct = useMemo(() => buildProductRanking(filteredItems), [filteredItems])

  function updateFilter(field, value) {
    setFilters((current) => ({ ...current, [field]: value }))
  }

  function updateProductFilter(field, value) {
    setProductFilters((current) => ({
      ...current,
      [field]: value,
      ...(field === 'productId' ? { offeringId: '' } : {}),
    }))
  }

  return (
    <div className="mt-8 space-y-6">
      <PageSectionHeader
        eyebrow="Facturas"
        title="Estadística"
        description="Analizá ventas, bultos, descuentos y rankings usando las facturas emitidas."
        aside={<Button variant="ghost" onClick={() => navigate('/history')}>Volver a facturas</Button>}
      />

      <section className="surface p-4 sm:p-6">
        <div className="mb-4 border-b border-stone-200 pb-3">
          <h2 className="subsection-title text-xl">Filtros generales</h2>
        </div>
        <div className="grid gap-3 md:grid-cols-5">
          <select className="input" value={filters.customerId} onChange={(event) => updateFilter('customerId', event.target.value)}>
            <option value="">Todos los clientes</option>
            {customers.map((customer) => (
              <option key={customer.id} value={customer.id}>{customer.name}</option>
            ))}
          </select>
          <input className="input" type="date" value={filters.dateFrom} onChange={(event) => updateFilter('dateFrom', event.target.value)} />
          <input className="input" type="date" value={filters.dateTo} onChange={(event) => updateFilter('dateTo', event.target.value)} />
          <select className="input" value={filters.transport} onChange={(event) => updateFilter('transport', event.target.value)}>
            <option value="">Todos los transportes</option>
            {(bootstrap?.transports || []).map((transport) => (
              <option key={transport.transport_id} value={transport.transport_id}>{transport.name}</option>
            ))}
          </select>
          <Button variant="secondary" onClick={() => setFilters(EMPTY_FILTERS)}>Limpiar</Button>
        </div>
      </section>

      <section className="surface p-4 sm:p-6">
        <div className="mb-4 border-b border-stone-200 pb-3">
          <h2 className="subsection-title text-xl">Filtros de producto</h2>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <select className="input" value={productFilters.productId} onChange={(event) => updateProductFilter('productId', event.target.value)}>
            <option value="">Todos los productos</option>
            {productOptions.map((product) => (
              <option key={product.id || product.label} value={product.id}>{product.label}</option>
            ))}
          </select>
          <select className="input" value={productFilters.offeringId} onChange={(event) => updateProductFilter('offeringId', event.target.value)}>
            <option value="">Todos los formatos</option>
            {offeringOptions.map((offering) => (
              <option key={offering.id || offering.label} value={offering.id}>{offering.label}</option>
            ))}
          </select>
          <Button variant="secondary" onClick={() => setProductFilters(EMPTY_PRODUCT_FILTERS)}>Limpiar productos</Button>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-5">
        <Metric label="Facturas" value={money(filteredInvoices.length)} />
        <Metric label="Bultos" value={money(summary.bultos)} />
        <Metric label="Bruto" value={`$${money(summary.gross)}`} />
        <Metric label="Descuentos" value={`$${money(summary.discount)}`} />
        <Metric label="Total" value={`$${money(summary.total)}`} />
      </section>

      <section className="grid gap-3 md:grid-cols-2">
        <Metric label="Promedio por factura" value={`$${money(summary.average)}`} />
        <Metric label="Clientes con facturas" value={money(new Set(filteredInvoices.map((invoice) => invoice.customer_id || invoice.client_name)).size)} />
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <RankingTable title="Ranking por cliente" rows={byCustomer} />
        <RankingTable title={loadingItems ? 'Ranking por producto/formato (cargando...)' : 'Ranking por producto/formato'} rows={byProduct} countLabel="Líneas" />
        <div className="xl:col-span-2">
          <RankingTable title="Totales por mes" rows={byMonth} />
        </div>
      </div>
    </div>
  )
}

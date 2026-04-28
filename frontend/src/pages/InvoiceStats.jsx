import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGranalia } from '../context/GranaliaContext'
import { money } from '../lib/format'
import Button from '../components/ui/Button'
import Metric from '../components/ui/Metric'
import PageSectionHeader from '../components/ui/PageSectionHeader'

const EMPTY_FILTERS = { customerId: '', dateFrom: '', dateTo: '', transport: '' }

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

function RankingTable({ title, rows }) {
  return (
    <section className="surface p-4 sm:p-6">
      <div className="mb-4 border-b border-stone-200 pb-3">
        <h2 className="subsection-title text-xl">{title}</h2>
      </div>
      <div className="table-shell">
        <table className="table-base">
          <thead className="table-head">
            <tr>
              <th>Grupo</th>
              <th className="text-right">Facturas</th>
              <th className="text-right">Bultos</th>
              <th className="text-right">Descuento</th>
              <th className="text-right">Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 12).map((row) => (
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

  const filteredInvoices = useMemo(() => {
    return invoices.filter((invoice) => {
      const matchesCustomer = !filters.customerId || String(invoice.customer_id || '') === String(filters.customerId)
      const matchesDateFrom = !filters.dateFrom || invoice.order_date >= filters.dateFrom
      const matchesDateTo = !filters.dateTo || invoice.order_date <= filters.dateTo
      const matchesTransport = !filters.transport || String(invoice.transport_id || '') === String(filters.transport)
      return matchesCustomer && matchesDateFrom && matchesDateTo && matchesTransport
    })
  }, [filters, invoices])

  const summary = useMemo(() => {
    const gross = filteredInvoices.reduce((sum, invoice) => sum + Number(invoice.gross_total || 0), 0)
    const discount = filteredInvoices.reduce((sum, invoice) => sum + Number(invoice.discount_total || 0), 0)
    const total = filteredInvoices.reduce((sum, invoice) => sum + Number(invoice.final_total || 0), 0)
    const bultos = filteredInvoices.reduce((sum, invoice) => sum + Number(invoice.total_bultos || 0), 0)
    const average = filteredInvoices.length ? Math.round(total / filteredInvoices.length) : 0
    return { gross, discount, total, bultos, average }
  }, [filteredInvoices])

  const byCustomer = useMemo(() => buildRanking(filteredInvoices, (invoice) => invoice.client_name || 'Sin cliente'), [filteredInvoices])
  const byTransport = useMemo(() => buildRanking(filteredInvoices, (invoice) => invoice.transport || 'Sin transporte'), [filteredInvoices])
  const byMonth = useMemo(() => buildRanking(filteredInvoices, (invoice) => monthLabel(invoice.order_date)), [filteredInvoices])

  function updateFilter(field, value) {
    setFilters((current) => ({ ...current, [field]: value }))
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
        <RankingTable title="Ranking por transporte" rows={byTransport} />
        <div className="xl:col-span-2">
          <RankingTable title="Totales por mes" rows={byMonth} />
        </div>
      </div>
    </div>
  )
}

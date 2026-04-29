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
const MONTH_LABELS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

const weight = (value) => new Intl.NumberFormat('es-AR', { maximumFractionDigits: 1 }).format(Number(value || 0))

function monthLabel(value) {
  if (!value) return 'Sin fecha'
  const [year, month] = String(value).split('-')
  return `${month}/${year}`
}

function buildRanking(invoices, keyFn) {
  const grouped = new Map()
  for (const invoice of invoices) {
    const key = keyFn(invoice)
    const current = grouped.get(key) || { label: key, count: 0, bultos: 0, weight: 0, gross: 0, discount: 0, total: 0 }
    current.count += 1
    current.bultos += Number(invoice.total_bultos || 0)
    current.gross += Number(invoice.gross_total || 0)
    current.discount += Number(invoice.discount_total || 0)
    current.total += Number(invoice.final_total || 0)
    grouped.set(key, current)
  }
  return Array.from(grouped.values()).sort((a, b) => b.total - a.total)
}

function buildMonthlyRanking(invoices) {
  const grouped = new Map()
  for (const invoice of invoices) {
    const key = String(invoice.order_date || '').slice(0, 7) || 'Sin fecha'
    const current = grouped.get(key) || { label: monthLabel(key), monthKey: key, count: 0, bultos: 0, weight: 0, gross: 0, discount: 0, total: 0 }
    current.count += 1
    current.bultos += Number(invoice.total_bultos || 0)
    current.gross += Number(invoice.gross_total || 0)
    current.discount += Number(invoice.discount_total || 0)
    current.total += Number(invoice.final_total || 0)
    grouped.set(key, current)
  }
  return Array.from(grouped.values()).sort((a, b) => String(b.monthKey).localeCompare(String(a.monthKey)))
}

function yearFromFilters(filters, invoices) {
  const filteredYear = String(filters.dateFrom || filters.dateTo || '').slice(0, 4)
  if (filteredYear) return filteredYear

  const latestInvoice = [...invoices]
    .filter((invoice) => invoice.order_date)
    .sort((a, b) => String(b.order_date).localeCompare(String(a.order_date)))[0]
  return String(latestInvoice?.order_date || new Date().toISOString()).slice(0, 4)
}

function buildYearMonthlyRows(rows, year) {
  const rowsByMonth = new Map(rows.map((row) => [row.monthKey, row]))
  return MONTH_LABELS.map((month, index) => {
    const monthKey = `${year}-${String(index + 1).padStart(2, '0')}`
    return rowsByMonth.get(monthKey) || {
      label: month,
      monthKey,
      count: 0,
      bultos: 0,
      weight: 0,
      gross: 0,
      discount: 0,
      total: 0,
    }
  })
}

function itemOfferingLabel(item) {
  const explicit = String(item.offering_label || '').trim()
  if (explicit) return explicit

  const label = String(item.label || '').trim()
  const product = String(item.product_name || '').trim()

  if (label && product && label.toLowerCase().startsWith(product.toLowerCase())) {
    const suffix = label.slice(product.length).trim()
    if (suffix) return suffix
  }

  const formatMatch = label.match(/(?:16x300|12x300|12x350|12x400|10x500|12x500|10x\s*1\s*kg|10x1000|x\s*(?:4|5|25|30)\s*kg)\b/i)
  return formatMatch ? formatMatch[0].replace(/\s+/g, ' ') : 'Sin formato'
}

function itemProductLabel(item) {
  const explicit = String(item.product_name || '').trim()
  if (explicit) return explicit

  const label = String(item.label || '').trim()
  const offering = itemOfferingLabel(item)
  return offering !== 'Sin formato' ? label.replace(offering, '').trim() || label : label || 'Sin producto'
}

function kilogramsPerUnit(label) {
  const text = String(label || '').toLowerCase().replace(/\s+/g, '')
  const packMatch = text.match(/(\d+)x(\d+(?:[.,]\d+)?)(kg|gr|g)?/)
  if (packMatch) {
    const units = Number(packMatch[1] || 0)
    const size = Number(String(packMatch[2] || 0).replace(',', '.'))
    const unit = packMatch[3] || 'gr'
    return units * (unit === 'kg' ? size : size / 1000)
  }

  const bagMatch = text.match(/x(\d+(?:[.,]\d+)?)kg/)
  if (bagMatch) return Number(String(bagMatch[1] || 0).replace(',', '.'))

  return 0
}

function itemWeight(item) {
  return Number(item.quantity || 0) * kilogramsPerUnit(itemOfferingLabel(item))
}

function buildProductRanking(items) {
  const grouped = new Map()
  for (const item of items) {
    const product = itemProductLabel(item)
    const offering = itemOfferingLabel(item)
    const key = `${product} / ${offering}`
    const current = grouped.get(key) || { label: key, count: 0, bultos: 0, weight: 0, gross: 0, discount: 0, total: 0 }
    current.count += 1
    current.bultos += Number(item.quantity || 0)
    current.gross += Number(item.gross || 0)
    current.discount += Number(item.discount || 0)
    current.total += Number(item.total || 0)
    current.weight += itemWeight(item)
    grouped.set(key, current)
  }
  return Array.from(grouped.values()).sort((a, b) => b.total - a.total)
}

function buildProductTotalRanking(items) {
  const grouped = new Map()
  for (const item of items) {
    const key = itemProductLabel(item)
    const current = grouped.get(key) || { label: key, count: 0, bultos: 0, weight: 0, gross: 0, discount: 0, total: 0 }
    current.count += 1
    current.bultos += Number(item.quantity || 0)
    current.weight += itemWeight(item)
    current.gross += Number(item.gross || 0)
    current.discount += Number(item.discount || 0)
    current.total += Number(item.total || 0)
    grouped.set(key, current)
  }
  return Array.from(grouped.values()).sort((a, b) => b.total - a.total)
}

function buildCustomerProductRanking(items) {
  const grouped = new Map()
  for (const item of items) {
    const key = item.client_name || 'Sin cliente'
    const current = grouped.get(key) || { label: key, invoiceIds: new Set(), count: 0, bultos: 0, weight: 0, gross: 0, discount: 0, total: 0 }
    current.invoiceIds.add(String(item.invoice_id))
    current.bultos += Number(item.quantity || 0)
    current.weight += itemWeight(item)
    current.gross += Number(item.gross || 0)
    current.discount += Number(item.discount || 0)
    current.total += Number(item.total || 0)
    grouped.set(key, current)
  }
  return Array.from(grouped.values())
    .map((row) => ({ ...row, count: row.invoiceIds.size, invoiceIds: undefined }))
    .sort((a, b) => b.total - a.total)
}

function RankingTable({ title, rows, countLabel = 'Facturas', showWeight = false, onRowClick, selectedLabel = '', embedded = false }) {
  const [sort, setSort] = useState({ key: 'total', direction: 'desc' })
  const columns = [
    { key: 'label', label: 'Grupo', align: 'left' },
    { key: 'count', label: countLabel, align: 'right' },
    { key: 'bultos', label: 'Bultos', align: 'right' },
    ...(showWeight ? [{ key: 'weight', label: 'Peso', align: 'right' }] : []),
    { key: 'discount', label: 'Descuento', align: 'right' },
    { key: 'total', label: 'Total', align: 'right' },
  ]
  const sortedRows = useMemo(() => {
    return [...rows].sort((a, b) => {
      if (sort.key === 'label') {
        const result = String(a.label || '').localeCompare(String(b.label || ''), 'es')
        return sort.direction === 'asc' ? result : -result
      }
      const result = Number(b[sort.key] || 0) - Number(a[sort.key] || 0)
      return sort.direction === 'desc' ? result : -result
    })
  }, [rows, sort])

  function updateSort(key) {
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === 'desc' ? 'asc' : 'desc',
    }))
  }

  function sortIndicator(key) {
    if (sort.key !== key) return ''
    return sort.direction === 'desc' ? '↓' : '↑'
  }

  return (
    <section className={embedded ? '' : 'surface p-4 pr-5 sm:p-6 sm:pr-8'}>
      <div className="mb-4 flex items-start justify-between gap-3 border-b border-stone-200 pb-3">
        <h2 className="subsection-title text-xl">{title}</h2>
        <div className="badge">{rows.length} filas</div>
      </div>
      <div className="table-shell max-h-[30rem] overflow-x-hidden overflow-y-auto pr-3 [scrollbar-gutter:stable]">
        <table className="table-base !min-w-0 table-fixed text-xs sm:text-sm">
          <colgroup>
            <col className={showWeight ? 'w-[30%]' : 'w-[34%]'} />
            <col className={showWeight ? 'w-[12%]' : 'w-[13%]'} />
            <col className={showWeight ? 'w-[13%]' : 'w-[15%]'} />
            {showWeight ? <col className="w-[15%]" /> : null}
            <col className={showWeight ? 'w-[14%]' : 'w-[18%]'} />
            <col className={showWeight ? 'w-[16%]' : 'w-[20%]'} />
          </colgroup>
          <thead className="table-head">
            <tr>
              {columns.map((column) => (
                <th
                  key={column.key}
                  className={`sticky top-0 z-10 bg-stone-100 !px-2 ${column.align === 'right' ? 'text-right' : ''} ${column.key === 'total' ? '!pl-2 !pr-5' : ''}`.trim()}
                >
                  <button
                    type="button"
                    className={`inline-flex w-full items-center gap-1 ${column.align === 'right' ? 'justify-end' : 'justify-start'}`.trim()}
                    onClick={() => updateSort(column.key)}
                  >
                    <span>{column.label}</span>
                    <span className="text-[10px] text-slate-400">{sortIndicator(column.key)}</span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row) => (
              <tr
                key={row.label}
                className={`table-row ${onRowClick ? 'cursor-pointer' : ''} ${selectedLabel === row.label ? 'bg-brand-sand/40' : ''}`.trim()}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
              >
                <td className="table-cell break-words !px-2 font-medium leading-snug">{row.label}</td>
                <td className="table-cell whitespace-nowrap !px-2 text-right">{row.count}</td>
                <td className="table-cell whitespace-nowrap !px-2 text-right">{money(row.bultos)}</td>
                {showWeight ? <td className="table-cell whitespace-nowrap !px-2 text-right">{weight(row.weight)} kg</td> : null}
                <td className="table-cell whitespace-nowrap !px-2 text-right">${money(row.discount)}</td>
                <td className="table-cell whitespace-nowrap !pl-2 !pr-5 text-right font-semibold text-brand-red">${money(row.total)}</td>
              </tr>
            ))}
            {sortedRows.length === 0 && (
              <tr>
                <td colSpan={showWeight ? 6 : 5} className="table-cell py-8 text-center text-slate-400">No hay datos para estos filtros.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function MonthlyBarChart({ rows, year, embedded = false }) {
  const safeRows = Array.isArray(rows) ? rows : []
  const maxTotal = safeRows.reduce((max, row) => Math.max(max, Number(row?.total || 0)), 0)
  const chartMax = maxTotal || 1
  const ticks = [1, 0.75, 0.5, 0.25, 0]

  return (
    <section className={embedded ? '' : 'surface p-4 pr-5 sm:p-6 sm:pr-8'}>
      <div className="mb-4 flex items-start justify-between gap-3 border-b border-stone-200 pb-3">
        <h2 className="subsection-title text-xl">Evolución mensual {year}</h2>
        <div className="badge">12 meses</div>
      </div>
      <div className="grid grid-cols-[4rem_minmax(0,1fr)] gap-3">
        <div className="relative h-72 text-right text-[11px] font-medium text-slate-400">
          {ticks.map((tick) => (
            <div key={tick} className="absolute right-0" style={{ top: `${(1 - tick) * 100}%`, transform: 'translateY(-50%)' }}>
              ${money(chartMax * tick)}
            </div>
          ))}
        </div>
        <div>
          <div className="relative grid h-72 grid-cols-12 items-end gap-1 border-b border-l border-stone-300 pl-2 pr-3 sm:gap-3">
            {ticks.slice(0, -1).map((tick) => (
              <div key={tick} className="pointer-events-none absolute left-0 right-3 border-t border-dashed border-stone-200" style={{ bottom: `${tick * 100}%` }} />
            ))}
            {safeRows.map((row, index) => {
              const total = Number(row.total || 0)
              const percentage = Math.round((total / chartMax) * 100)
              return (
                <div key={row.monthKey || row.label} className="relative z-10 flex h-full min-w-0 flex-col justify-end gap-2">
                  <div className="text-center text-[10px] font-semibold text-brand-red sm:text-xs">{total ? `$${money(total)}` : ''}</div>
                  <div className="mx-auto w-full max-w-10 rounded-t-lg bg-brand-red" style={{ height: `${percentage}%`, minHeight: total ? '0.35rem' : '0' }} title={`${MONTH_LABELS[index]}: $${money(total)}`} />
                </div>
              )
            })}
          </div>
          <div className="mt-2 grid grid-cols-12 gap-1 pr-3 pl-2 text-center text-[11px] font-semibold text-slate-500 sm:gap-3 sm:text-xs">
            {MONTH_LABELS.map((month) => <div key={month}>{month}</div>)}
          </div>
          <div className="mt-2 text-center text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Mes</div>
        </div>
      </div>
    </section>
  )
}

export default function InvoiceStats() {
  const navigate = useNavigate()
  const { bootstrap, customers, invoices } = useGranalia()
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [productFilters, setProductFilters] = useState(EMPTY_PRODUCT_FILTERS)
  const [selectedProductLabel, setSelectedProductLabel] = useState('')
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

  const byMonth = useMemo(() => buildMonthlyRanking(filteredInvoices), [filteredInvoices])
  const chartYear = useMemo(() => yearFromFilters(filters, filteredInvoices), [filters, filteredInvoices])
  const monthlyChartRows = useMemo(() => buildYearMonthlyRows(byMonth, chartYear), [byMonth, chartYear])
  const filteredInvoiceIds = useMemo(() => new Set(filteredInvoices.map((invoice) => String(invoice.invoice_id))), [filteredInvoices])
  const productOptions = useMemo(() => {
    const grouped = new Map()
    for (const item of invoiceItems) {
      const id = String(item.product_id || '')
      const label = itemProductLabel(item)
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
      const label = itemOfferingLabel(item)
      const key = productFilters.productId ? id || label : label
      if (!grouped.has(key)) grouped.set(key, { id: productFilters.productId ? id : label, label })
    }
    return Array.from(grouped.values()).sort((a, b) => a.label.localeCompare(b.label, 'es'))
  }, [invoiceItems, productFilters.productId])
  const filteredItems = useMemo(
    () => invoiceItems.filter((item) => {
      const matchesInvoice = filteredInvoiceIds.has(String(item.invoice_id))
      const matchesProduct = !productFilters.productId || String(item.product_id || '') === String(productFilters.productId)
      const matchesOffering = !productFilters.offeringId || (productFilters.productId
        ? String(item.offering_id || '') === String(productFilters.offeringId)
        : itemOfferingLabel(item) === String(productFilters.offeringId))
      return matchesInvoice && matchesProduct && matchesOffering
    }),
    [filteredInvoiceIds, invoiceItems, productFilters]
  )
  const hasProductFilter = Boolean(productFilters.productId || productFilters.offeringId)
  const byCustomer = useMemo(
    () => hasProductFilter
      ? buildCustomerProductRanking(filteredItems)
      : buildRanking(filteredInvoices, (invoice) => invoice.client_name || 'Sin cliente'),
    [filteredInvoices, filteredItems, hasProductFilter]
  )
  const byProduct = useMemo(() => buildProductRanking(filteredItems), [filteredItems])
  const byProductTotal = useMemo(() => buildProductTotalRanking(filteredItems), [filteredItems])
  const selectedProductFormats = useMemo(
    () => selectedProductLabel
      ? buildProductRanking(filteredItems.filter((item) => itemProductLabel(item) === selectedProductLabel))
      : [],
    [filteredItems, selectedProductLabel]
  )

  function updateFilter(field, value) {
    setFilters((current) => ({ ...current, [field]: value }))
  }

  function updateProductFilter(field, value) {
    setSelectedProductLabel('')
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

      <div className="pt-4">
        <div className="mb-4 flex items-center gap-3">
          <div className="h-px flex-1 bg-stone-200" />
          <div className="rounded-full border border-stone-200 bg-white px-4 py-1 text-xs font-bold uppercase tracking-[0.16em] text-slate-500">
            Resultados
          </div>
          <div className="h-px flex-1 bg-stone-200" />
        </div>

        <section className="grid gap-3 md:grid-cols-5">
          <Metric label="Facturas" value={money(filteredInvoices.length)} />
          <Metric label="Bultos" value={money(summary.bultos)} />
          <Metric label="Bruto" value={`$${money(summary.gross)}`} />
          <Metric label="Descuentos" value={`$${money(summary.discount)}`} />
          <Metric label="Total" value={`$${money(summary.total)}`} />
        </section>
      </div>

      <section className="grid gap-3 md:grid-cols-2">
        <Metric label="Promedio por factura" value={`$${money(summary.average)}`} />
        <Metric label="Clientes con facturas" value={money(new Set(filteredInvoices.map((invoice) => invoice.customer_id || invoice.client_name)).size)} />
      </section>

      <div className="space-y-6">
        <RankingTable title="Ranking por cliente" rows={byCustomer} showWeight={hasProductFilter} />

        <section className="surface p-4 pr-5 sm:p-6 sm:pr-8">
          <div className="grid gap-6 xl:grid-cols-2">
            <RankingTable
              title={loadingItems ? 'Total por producto (cargando...)' : 'Total por producto'}
              rows={byProductTotal}
              countLabel="Líneas"
              showWeight
              selectedLabel={selectedProductLabel}
              embedded
              onRowClick={(row) => setSelectedProductLabel((current) => current === row.label ? '' : row.label)}
            />
            <RankingTable
              title={selectedProductLabel ? `Desglose por formato: ${selectedProductLabel}` : 'Desglose por formato'}
              rows={selectedProductFormats}
              countLabel="Líneas"
              showWeight
              embedded
            />
          </div>
        </section>

        <section className="surface p-4 pr-5 sm:p-6 sm:pr-8">
          <RankingTable title="Totales por mes" rows={byMonth} embedded />
          <div className="mt-6 border-t border-stone-200 pt-6">
            <MonthlyBarChart rows={monthlyChartRows} year={chartYear} embedded />
          </div>
        </section>
      </div>
    </div>
  )
}

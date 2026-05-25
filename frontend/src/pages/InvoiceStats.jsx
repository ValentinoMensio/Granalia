import { useEffect, useMemo, useState } from 'react'
import { useGranalia } from '../context/GranaliaContext'
import { request } from '../lib/api'
import { money } from '../lib/format'
import Button from '../components/ui/Button'
import DateRangePicker from '../components/ui/DateRangePicker'
import Metric from '../components/ui/Metric'
import PageSectionHeader from '../components/ui/PageSectionHeader'

const EMPTY_FILTERS = { customerIds: [''], dateFrom: '', dateTo: '', transport: '', priceListId: '', declared: '' }
const EMPTY_PRODUCT_FILTERS = { lines: [{ productId: '', offeringId: '' }] }
const MONTH_LABELS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
const MONTHLY_METRICS = [
  { key: 'total', label: 'Total', format: (value) => `$${money(value)}` },
  { key: 'discount', label: 'Descuento', format: (value) => `$${money(value)}` },
  { key: 'bultos', label: 'Bultos', format: (value) => money(value) },
  { key: 'weight', label: 'Peso', format: (value) => `${weight(value)} kg` },
  { key: 'count', label: 'Facturas', format: (value) => money(value) },
]

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

function buildMonthlyItemRanking(items) {
  const grouped = new Map()
  const invoiceIdsByMonth = new Map()
  for (const item of items) {
    const key = String(item.order_date || '').slice(0, 7) || 'Sin fecha'
    const current = grouped.get(key) || { label: monthLabel(key), monthKey: key, count: 0, bultos: 0, weight: 0, gross: 0, discount: 0, total: 0 }
    const invoiceIds = invoiceIdsByMonth.get(key) || new Set()
    invoiceIds.add(String(item.invoice_id || ''))
    current.count = invoiceIds.size
    current.bultos += Number(item.quantity || 0)
    current.weight += itemWeight(item)
    current.gross += Number(item.gross || 0)
    current.discount += Number(item.discount || 0)
    current.total += Number(item.total || 0)
    grouped.set(key, current)
    invoiceIdsByMonth.set(key, invoiceIds)
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
  return String(item.offering_label || '').trim() || 'Sin formato'
}

function itemProductLabel(item) {
  return String(item.product_name || '').trim() || 'Sin producto'
}

function itemWeight(item) {
  return Number(item.quantity || 0) * Number(item.offering_net_weight_kg || 0)
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
  const [showAllMobile, setShowAllMobile] = useState(false)
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

  const mobileRows = showAllMobile ? sortedRows : sortedRows.slice(0, 8)

  return (
    <section className={embedded ? '' : 'surface p-4 pr-5 sm:p-6 sm:pr-8'}>
      <div className="mb-4 flex flex-col gap-3 border-b border-stone-200 pb-3 sm:flex-row sm:items-start sm:justify-between">
        <h2 className="subsection-title text-xl">{title}</h2>
        <div className="badge">{rows.length} filas</div>
      </div>

      <div className="mb-3 flex gap-2 overflow-x-auto pb-1 sm:hidden">
        {columns.filter((column) => ['total', 'label', 'bultos', 'weight'].includes(column.key)).map((column) => (
          <button
            key={column.key}
            type="button"
            className={`shrink-0 rounded-full border border-stone-200 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.12em] ${sort.key === column.key ? 'bg-brand-red text-white' : 'bg-white text-slate-500'}`.trim()}
            onClick={() => updateSort(column.key)}
          >
            {column.label} {sortIndicator(column.key)}
          </button>
        ))}
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white sm:hidden">
        {mobileRows.map((row) => (
          <button
            key={row.label}
            type="button"
            className={`grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-slate-100 px-3 py-2.5 text-left last:border-b-0 ${onRowClick ? 'cursor-pointer' : 'cursor-default'} ${selectedLabel === row.label ? 'bg-blue-100 ring-1 ring-inset ring-brand-red/30' : ''}`.trim()}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
          >
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-slate-900">{row.label}</div>
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] font-medium text-slate-500">
                <span>{countLabel}: {row.count}</span>
                <span>Bultos: {money(row.bultos)}</span>
                {showWeight ? <span>{weight(row.weight)} kg</span> : null}
              </div>
            </div>
            <div className="text-right">
              <div className="text-sm font-bold text-brand-red">${money(row.total)}</div>
              {Number(row.discount || 0) > 0 ? <div className="text-[11px] text-slate-400">Dto ${money(row.discount)}</div> : null}
            </div>
          </button>
        ))}
        {sortedRows.length === 0 && (
          <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-400">No hay datos para estos filtros.</div>
        )}
        {sortedRows.length > 8 && (
          <button
            type="button"
            className="w-full bg-slate-50 px-3 py-2 text-center text-xs font-bold uppercase tracking-[0.12em] text-slate-500"
            onClick={() => setShowAllMobile((current) => !current)}
          >
            {showAllMobile ? 'Ver menos' : `Ver ${sortedRows.length - 8} más`}
          </button>
        )}
      </div>

      <div className="stats-table-scroll table-shell hidden max-h-[30rem] overflow-x-hidden overflow-y-auto [scrollbar-gutter:stable] sm:block">
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
                className={`table-row ${onRowClick ? 'cursor-pointer' : ''} ${selectedLabel === row.label ? '!bg-blue-100 ring-1 ring-inset ring-brand-red/30' : ''}`.trim()}
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

function MonthlyBarChart({ rows, year, metricKey = 'total', metricLabel = 'Total', formatValue = (value) => `$${money(value)}`, onMetricChange, embedded = false }) {
  const safeRows = Array.isArray(rows) ? rows : []
  const maxValue = safeRows.reduce((max, row) => Math.max(max, Number(row?.[metricKey] || 0)), 0)
  const chartMax = maxValue || 1
  const ticks = [1, 0.75, 0.5, 0.25, 0]

  return (
    <section className={embedded ? '' : 'surface p-4 pr-5 sm:p-6 sm:pr-8'}>
      <div className="mb-4 flex items-start justify-between gap-3 border-b border-stone-200 pb-3">
        <h2 className="subsection-title text-xl">Evolución mensual {year}</h2>
        <div className="badge">12 meses</div>
      </div>
      <div className="mb-4 max-w-xs">
        <label className="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">Campo</label>
        <select className="input mt-1" value={metricKey} onChange={(event) => onMetricChange?.(event.target.value)}>
          {MONTHLY_METRICS.map((metric) => (
            <option key={metric.key} value={metric.key}>{metric.label}</option>
          ))}
        </select>
      </div>
      <div className="space-y-3 sm:hidden">
        {safeRows.map((row, index) => {
          const value = Number(row[metricKey] || 0)
          const percentage = Math.round((value / chartMax) * 100)
          return (
            <div key={row.monthKey || row.label} className="grid grid-cols-[2.5rem_minmax(0,1fr)_5rem] items-center gap-2">
              <div className="text-xs font-bold text-slate-500">{MONTH_LABELS[index]}</div>
              <div className="h-4 overflow-hidden rounded-full bg-stone-100">
                <div className="h-full rounded-full bg-brand-red" style={{ width: `${percentage}%` }} />
              </div>
              <div className="text-right text-xs font-semibold text-brand-red">{formatValue(value)}</div>
            </div>
          )
        })}
      </div>
      <div className="hidden grid-cols-[4rem_minmax(0,1fr)] gap-3 sm:grid">
        <div className="relative h-72 text-right text-[11px] font-medium text-slate-400">
          {ticks.map((tick) => (
            <div key={tick} className="absolute right-0" style={{ top: `${(1 - tick) * 100}%`, transform: 'translateY(-50%)' }}>
              {formatValue(chartMax * tick)}
            </div>
          ))}
        </div>
        <div>
          <div className="relative grid h-72 grid-cols-12 items-end gap-1 border-b border-l border-stone-300 pl-2 pr-3 sm:gap-3">
            {ticks.slice(0, -1).map((tick) => (
              <div key={tick} className="pointer-events-none absolute left-0 right-3 border-t border-dashed border-stone-200" style={{ bottom: `${tick * 100}%` }} />
            ))}
            {safeRows.map((row, index) => {
              const value = Number(row[metricKey] || 0)
              const percentage = Math.round((value / chartMax) * 100)
              return (
                <div key={row.monthKey || row.label} className="relative z-10 flex h-full min-w-0 flex-col justify-end gap-2">
                  <div className="text-center text-[10px] font-semibold text-brand-red sm:text-xs">{value ? formatValue(value) : ''}</div>
                  <div className="mx-auto w-full max-w-10 rounded-t-lg bg-brand-red" style={{ height: `${percentage}%`, minHeight: value ? '0.35rem' : '0' }} title={`${MONTH_LABELS[index]} ${metricLabel}: ${formatValue(value)}`} />
                </div>
              )
            })}
          </div>
          <div className="mt-2 grid grid-cols-12 gap-1 pr-3 pl-2 text-center text-[11px] font-semibold text-slate-500 sm:gap-3 sm:text-xs">
            {MONTH_LABELS.map((month) => <div key={month}>{month}</div>)}
          </div>
          <div className="mt-2 text-center text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Mes · {metricLabel}</div>
        </div>
      </div>
    </section>
  )
}

export default function InvoiceStats() {
  const { bootstrap, customers, invoices } = useGranalia()
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [productFilters, setProductFilters] = useState(EMPTY_PRODUCT_FILTERS)
  const [monthlyMetricKey, setMonthlyMetricKey] = useState('total')
  const [selectedProductLabel, setSelectedProductLabel] = useState('')
  const [statsInvoices, setStatsInvoices] = useState(invoices)
  const [invoiceItems, setInvoiceItems] = useState([])
  const [loadingItems, setLoadingItems] = useState(false)

  useEffect(() => {
    setLoadingItems(true)
    Promise.all([request('/api/invoices?limit=10000'), request('/api/invoices/stats/items')])
      .then(([nextInvoices, nextItems]) => {
        setStatsInvoices(nextInvoices)
        setInvoiceItems(nextItems.map((item) => ({
          ...item,
          discount: Number(item.effective_discount ?? item.discount ?? 0),
          total: Number(item.effective_total ?? item.total ?? 0),
        })))
      })
      .finally(() => setLoadingItems(false))
  }, [])

  const filteredInvoices = useMemo(() => {
    const selectedCustomerIds = (filters.customerIds || []).filter(Boolean).map(String)
    return statsInvoices.filter((invoice) => {
      const matchesCustomer = !selectedCustomerIds.length || selectedCustomerIds.includes(String(invoice.customer_id || ''))
      const matchesDateFrom = !filters.dateFrom || invoice.order_date >= filters.dateFrom
      const matchesDateTo = !filters.dateTo || invoice.order_date <= filters.dateTo
      const matchesTransport = !filters.transport || String(invoice.transport_id || '') === String(filters.transport)
      const matchesPriceList = !filters.priceListId || String(invoice.price_list_id || '') === String(filters.priceListId)
      const matchesDeclared = !filters.declared || String(Boolean(invoice.declared)) === String(filters.declared)
      return matchesCustomer && matchesDateFrom && matchesDateTo && matchesTransport && matchesPriceList && matchesDeclared
    })
  }, [filters, statsInvoices])

  const filteredInvoiceIds = useMemo(() => new Set(filteredInvoices.map((invoice) => String(invoice.invoice_id))), [filteredInvoices])
  const productOptions = useMemo(() => {
    const grouped = new Map()
    for (const item of invoiceItems) {
      const label = itemProductLabel(item)
      if (!grouped.has(label)) grouped.set(label, { id: label, label })
    }
    return Array.from(grouped.values()).sort((a, b) => a.label.localeCompare(b.label, 'es'))
  }, [invoiceItems])
  const offeringOptionsByProduct = useMemo(() => {
    const grouped = new Map()
    for (const item of invoiceItems) {
      const productKey = itemProductLabel(item)
      const label = itemOfferingLabel(item)
      const productMap = grouped.get(productKey) || new Map()
      if (!productMap.has(label)) productMap.set(label, { id: label, label })
      grouped.set(productKey, productMap)

      const allMap = grouped.get('') || new Map()
      if (!allMap.has(label)) allMap.set(label, { id: label, label })
      grouped.set('', allMap)
    }
    return Object.fromEntries(
      Array.from(grouped.entries()).map(([productId, offerings]) => [
        productId,
        Array.from(offerings.values()).sort((a, b) => a.label.localeCompare(b.label, 'es')),
      ])
    )
  }, [invoiceItems])
  const activeProductLines = useMemo(
    () => (productFilters.lines || []).filter((line) => line.productId || line.offeringId),
    [productFilters.lines]
  )
  const filteredItems = useMemo(
    () => invoiceItems.filter((item) => {
      const matchesInvoice = filteredInvoiceIds.has(String(item.invoice_id))
      const matchesProductLines = !activeProductLines.length || activeProductLines.some((line) => {
        const matchesProduct = !line.productId || itemProductLabel(item) === String(line.productId)
        const matchesOffering = !line.offeringId || itemOfferingLabel(item) === String(line.offeringId)
        return matchesProduct && matchesOffering
      })
      return matchesInvoice && matchesProductLines
    }),
    [activeProductLines, invoiceItems, filteredInvoiceIds]
  )
  const totalWeight = useMemo(
    () => filteredItems.reduce((sum, item) => sum + itemWeight(item), 0),
    [filteredItems]
  )
  const hasProductFilter = activeProductLines.length > 0
  const filteredItemInvoiceIds = useMemo(() => new Set(filteredItems.map((item) => String(item.invoice_id || ''))), [filteredItems])
  const invoiceCount = hasProductFilter ? filteredItemInvoiceIds.size : filteredInvoices.length
  const summary = useMemo(() => {
    if (hasProductFilter) {
      const gross = filteredItems.reduce((sum, item) => sum + Number(item.gross || 0), 0)
      const discount = filteredItems.reduce((sum, item) => sum + Number(item.discount || 0), 0)
      const total = filteredItems.reduce((sum, item) => sum + Number(item.total || 0), 0)
      const bultos = filteredItems.reduce((sum, item) => sum + Number(item.quantity || 0), 0)
      const average = invoiceCount ? Math.round(total / invoiceCount) : 0
      return { gross, discount, total, bultos, average }
    }

    const gross = filteredInvoices.reduce((sum, invoice) => sum + Number(invoice.gross_total || 0), 0)
    const discount = filteredInvoices.reduce((sum, invoice) => sum + Number(invoice.discount_total || 0), 0)
    const total = filteredInvoices.reduce((sum, invoice) => sum + Number(invoice.final_total || 0), 0)
    const bultos = filteredInvoices.reduce((sum, invoice) => sum + Number(invoice.total_bultos || 0), 0)
    const average = filteredInvoices.length ? Math.round(total / filteredInvoices.length) : 0
    return { gross, discount, total, bultos, average }
  }, [filteredInvoices, filteredItems, hasProductFilter, invoiceCount])
  const byMonth = useMemo(() => buildMonthlyItemRanking(filteredItems), [filteredItems])
  const chartYear = useMemo(
    () => yearFromFilters(filters, hasProductFilter ? filteredItems : filteredInvoices),
    [filteredInvoices, filteredItems, filters, hasProductFilter]
  )
  const monthlyChartRows = useMemo(() => buildYearMonthlyRows(byMonth, chartYear), [byMonth, chartYear])
  const monthlyMetric = MONTHLY_METRICS.find((metric) => metric.key === monthlyMetricKey) || MONTHLY_METRICS[0]
  const byCustomer = useMemo(() => buildCustomerProductRanking(filteredItems), [filteredItems])
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

  function updateDateRange(range) {
    setFilters((current) => ({ ...current, ...range }))
  }

  function resetFilters() {
    setFilters(EMPTY_FILTERS)
  }

  function updateCustomerFilter(index, value) {
    setFilters((current) => {
      const customerIds = [...(current.customerIds || [''])]
      customerIds[index] = value
      return { ...current, customerIds }
    })
  }

  function addCustomerFilter() {
    setFilters((current) => ({ ...current, customerIds: [...(current.customerIds || ['']), ''] }))
  }

  function removeCustomerFilter(index) {
    setFilters((current) => {
      const customerIds = (current.customerIds || ['']).filter((_, itemIndex) => itemIndex !== index)
      return { ...current, customerIds: customerIds.length ? customerIds : [''] }
    })
  }

  function updateProductFilter(index, field, value) {
    setSelectedProductLabel('')
    setProductFilters((current) => ({
      lines: (current.lines || [{ productId: '', offeringId: '' }]).map((line, itemIndex) => (
        itemIndex === index
          ? { ...line, [field]: value, ...(field === 'productId' ? { offeringId: '' } : {}) }
          : line
      )),
    }))
  }

  function addProductFilter() {
    setProductFilters((current) => ({ lines: [...(current.lines || [{ productId: '', offeringId: '' }]), { productId: '', offeringId: '' }] }))
  }

  function removeProductFilter(index) {
    setSelectedProductLabel('')
    setProductFilters((current) => {
      const lines = (current.lines || [{ productId: '', offeringId: '' }]).filter((_, itemIndex) => itemIndex !== index)
      return { lines: lines.length ? lines : [{ productId: '', offeringId: '' }] }
    })
  }

  return (
    <div className="mt-8 space-y-6">
      <PageSectionHeader
        eyebrow="Facturas"
        title="Estadística"
        description="Analizá ventas, bultos, descuentos y rankings usando las facturas emitidas."
      />

      <section className="surface p-4 sm:p-6">
        <div className="mb-4 border-b border-stone-200 pb-3">
          <h2 className="subsection-title text-xl">Filtros generales</h2>
        </div>
        <div className="grid gap-3 md:grid-cols-4">
          <DateRangePicker dateFrom={filters.dateFrom} dateTo={filters.dateTo} onChange={updateDateRange} />
          <select className="input" value={filters.transport} onChange={(event) => updateFilter('transport', event.target.value)}>
            <option value="">Todos los transportes</option>
            {(bootstrap?.transports || []).map((transport) => (
              <option key={transport.transport_id} value={transport.transport_id}>{transport.name}</option>
            ))}
          </select>
          <select className="input" value={filters.priceListId} onChange={(event) => updateFilter('priceListId', event.target.value)}>
            <option value="">Todas las listas</option>
            {(bootstrap?.price_lists || []).map((priceList) => (
              <option key={priceList.id} value={priceList.id}>{priceList.name}</option>
            ))}
          </select>
          <select className="input" value={filters.declared} onChange={(event) => updateFilter('declared', event.target.value)}>
            <option value="">Declaradas y no declaradas</option>
            <option value="true">Declaradas</option>
            <option value="false">No declaradas</option>
          </select>
        </div>

        <div className="mt-4 space-y-3">
          <div className="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">Clientes a comparar</div>
          {(filters.customerIds || ['']).map((customerId, index) => (
            <div key={index} className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
              <select className="input" value={customerId} onChange={(event) => updateCustomerFilter(index, event.target.value)}>
                <option value="">Todos los clientes</option>
                {customers.map((customer) => (
                  <option key={customer.id} value={customer.id}>{customer.name}</option>
                ))}
              </select>
              <Button variant="secondary" onClick={() => removeCustomerFilter(index)} disabled={(filters.customerIds || ['']).length === 1}>
                Quitar
              </Button>
            </div>
          ))}
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button variant="ghost" onClick={addCustomerFilter}>+ Agregar cliente</Button>
            <Button variant="secondary" onClick={resetFilters}>Limpiar</Button>
          </div>
        </div>
      </section>

      <section className="surface p-4 sm:p-6">
        <div className="mb-4 border-b border-stone-200 pb-3">
          <h2 className="subsection-title text-xl">Filtros de producto</h2>
        </div>
        <div className="space-y-3">
          {(productFilters.lines || [{ productId: '', offeringId: '' }]).map((line, index) => {
            const offeringOptions = offeringOptionsByProduct[line.productId || ''] || []
            return (
              <div key={index} className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
                <select className="input" value={line.productId} onChange={(event) => updateProductFilter(index, 'productId', event.target.value)}>
                  <option value="">Todos los productos</option>
                  {productOptions.map((product) => (
                    <option key={product.id || product.label} value={product.id}>{product.label}</option>
                  ))}
                </select>
                <select className="input" value={line.offeringId} onChange={(event) => updateProductFilter(index, 'offeringId', event.target.value)}>
                  <option value="">Todos los formatos</option>
                  {offeringOptions.map((offering) => (
                    <option key={offering.id || offering.label} value={offering.id}>{offering.label}</option>
                  ))}
                </select>
                <Button variant="secondary" onClick={() => removeProductFilter(index)} disabled={(productFilters.lines || []).length === 1}>
                  Quitar
                </Button>
              </div>
            )
          })}
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button variant="ghost" onClick={addProductFilter}>+ Agregar producto</Button>
            <Button variant="secondary" onClick={() => { setSelectedProductLabel(''); setProductFilters(EMPTY_PRODUCT_FILTERS) }}>Limpiar productos</Button>
          </div>
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

        <section className="grid gap-3 md:grid-cols-6">
          <Metric label="Facturas" value={money(invoiceCount)} />
          <Metric label="Bultos" value={money(summary.bultos)} />
          <Metric label="Kilos" value={`${weight(totalWeight)} kg`} />
          <Metric label="Bruto" value={`$${money(summary.gross)}`} />
          <Metric label="Descuentos" value={`$${money(summary.discount)}`} />
          <Metric label="Total" value={`$${money(summary.total)}`} />
        </section>
      </div>

      <section className="grid gap-3 md:grid-cols-2">
        <Metric label="Promedio por factura" value={`$${money(summary.average)}`} />
        <Metric label="Clientes con facturas" value={money(new Set((hasProductFilter ? filteredItems : filteredInvoices).map((row) => row.customer_id || row.client_name)).size)} />
      </section>

      <div className="space-y-6">
        <RankingTable title={loadingItems ? 'Ranking por cliente (cargando...)' : 'Ranking por cliente'} rows={byCustomer} showWeight />

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
          <RankingTable title={loadingItems ? 'Totales por mes (cargando...)' : 'Totales por mes'} rows={byMonth} showWeight embedded />
          <div className="mt-6 border-t border-stone-200 pt-6">
            <MonthlyBarChart
              rows={monthlyChartRows}
              year={chartYear}
              metricKey={monthlyMetric.key}
              metricLabel={monthlyMetric.label}
              formatValue={monthlyMetric.format}
              onMetricChange={setMonthlyMetricKey}
              embedded
            />
          </div>
        </section>
      </div>
    </div>
  )
}

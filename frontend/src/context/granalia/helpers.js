import { discountKeyForLabel } from '../../lib/format'

function splitNotes(value) {
  return String(value || '')
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

function buildProductsById(catalog) {
  return Object.fromEntries(catalog.map((product) => [product.id, product]))
}

function buildTotals(form, productsById) {
  let subtotal = 0
  let bultos = 0
  let total = 0

  for (const item of form.items) {
    const product = productsById[item.product_id]
    const offering = product?.offerings.find((entry) => entry.id === item.offering_id)
    if (!offering) continue

    const qty = Number(item.quantity || 0)
    const bonus = Number(item.bonus_quantity || 0)
    const gross = qty * Number(offering.price || 0)
    subtotal += gross
    bultos += qty + bonus
    total += gross
  }

  for (const discount of form.footerDiscounts || []) {
    total -= total * Number(discount.rate || 0)
  }

  return { subtotal, bultos, total }
}

function buildAvailableDiscountGroups(catalog) {
  return Array.from(
    new Set(catalog.flatMap((product) => product.offerings.map((offering) => discountKeyForLabel(offering.label))))
  ).sort()
}

function applyCustomerToForm(current, profile) {
  return {
    ...current,
    customerId: profile ? String(profile.id) : '',
    clientName: profile?.name || current.clientName,
    secondaryLine: profile?.secondary_line || '',
    transport: profile?.transport || '',
    notes: (profile?.notes || []).join('\n'),
    footerDiscounts: [...(profile?.footer_discounts || [])],
    lineDiscountsByGroup: { ...(profile?.line_discounts_by_format || {}) },
  }
}

function buildProfilePayload(currentCustomer, form) {
  const base = currentCustomer || {
    footer_discounts: [],
    line_discounts_by_format: {},
    source_count: 0,
  }

  return {
    ...base,
    name: form.clientName,
    secondary_line: form.secondaryLine,
    transport: form.transport,
    notes: splitNotes(form.notes),
    footer_discounts: (form.footerDiscounts || []).filter((item) => Number(item?.rate) > 0),
    line_discounts_by_format: Object.fromEntries(
      Object.entries(form.lineDiscountsByGroup || {}).filter(([, value]) => Number(value) > 0)
    ),
  }
}

function buildInvoicePayload(form, currentCustomer) {
  const profile = buildProfilePayload(currentCustomer, form)

  return {
    order: {
      client_name: form.clientName,
      date: form.date,
      secondary_line: form.secondaryLine,
      transport: form.transport,
      notes: splitNotes(form.notes),
      items: form.items.filter((item) => item.product_id && item.offering_id && (item.quantity > 0 || item.bonus_quantity > 0)),
    },
    profile,
  }
}

function buildFormFromInvoiceDetail(invoiceDetail, customers) {
  const matchingCustomer = customers.find((customer) => String(customer.id) === String(invoiceDetail.customer_id || ''))
  const grouped = new Map()

  for (const item of invoiceDetail.items || []) {
    const key = `${item.product_id || ''}:${item.offering_id || ''}`
    const current = grouped.get(key) || {
      product_id: item.product_id || '',
      offering_id: item.offering_id || '',
      quantity: 0,
      bonus_quantity: 0,
    }

    if (Number(item.unit_price || 0) === 0) {
      current.bonus_quantity += Number(item.quantity || 0)
    } else {
      current.quantity += Number(item.quantity || 0)
    }
    grouped.set(key, current)
  }

  return {
    customerId: matchingCustomer ? String(matchingCustomer.id) : '',
    clientName: invoiceDetail.client_name || '',
    date: invoiceDetail.order_date || new Date().toISOString().slice(0, 10),
    secondaryLine: invoiceDetail.secondary_line || '',
    transport: invoiceDetail.transport || '',
    notes: (invoiceDetail.notes || []).join('\n'),
    footerDiscounts: [...(invoiceDetail.footer_discounts || [])],
    lineDiscountsByGroup: { ...(invoiceDetail.line_discounts_by_format || {}) },
    items: Array.from(grouped.values()),
  }
}

export {
  applyCustomerToForm,
  buildAvailableDiscountGroups,
  buildFormFromInvoiceDetail,
  buildInvoicePayload,
  buildProductsById,
  buildProfilePayload,
  buildTotals,
  splitNotes,
}

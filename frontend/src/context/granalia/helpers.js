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
    const hasManualPrice = item.unit_price !== '' && item.unit_price !== undefined
    if (!offering && !hasManualPrice) continue

    const qty = Number(item.quantity || 0)
    const bonus = Number(item.bonus_quantity || 0)
    const unitPrice = hasManualPrice ? Number(item.unit_price || 0) : Number(offering.price || 0)
    const gross = qty * unitPrice
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

function normalizeBonusText(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
}

function isAutomaticBonusExcluded(item) {
  const productName = normalizeBonusText(item.product_name)
  const offeringLabel = normalizeBonusText(item.offering_label)
  const isCornFlour = productName.includes('maiz') && (productName.includes('harina') || productName.includes('h. maiz') || productName.includes('h maiz'))
  return isCornFlour && (offeringLabel.includes('1 kg') || offeringLabel.includes('1000'))
}

function normalizeAutomaticBonusRules(rules) {
  return (rules || [])
    .map((rule) => ({
      product_id: rule.product_id === '' || rule.product_id === undefined ? null : rule.product_id,
      offering_id: rule.offering_id === '' || rule.offering_id === undefined ? null : rule.offering_id,
      offering_label: String(rule.offering_label || '').trim(),
      buy_quantity: Number(rule.buy_quantity || 0),
      bonus_quantity: Number(rule.bonus_quantity || 0),
    }))
    .filter((rule) => rule.buy_quantity > 0 && rule.bonus_quantity > 0)
}

function matchingAutomaticBonusRule(item, rules) {
  if (isAutomaticBonusExcluded(item)) return null

  let best = null
  let bestScore = -1

  for (const rule of normalizeAutomaticBonusRules(rules)) {
    const productMatches = rule.product_id === null || String(rule.product_id) === String(item.product_id || '')
    const offeringMatches = rule.offering_id !== null
      ? String(rule.offering_id) === String(item.offering_id || '')
      : !rule.offering_label || normalizeBonusText(rule.offering_label) === normalizeBonusText(item.offering_label)
    if (!productMatches || !offeringMatches) continue

    const score = (rule.product_id === null ? 0 : 1) + (rule.offering_id === null && !rule.offering_label ? 0 : 1)
    if (score > bestScore) {
      best = rule
      bestScore = score
    }
  }

  return best
}

function applyAutomaticBonusRulesToItems(items, rules) {
  const normalizedRules = normalizeAutomaticBonusRules(rules)
  if (!normalizedRules.length) {
    return items.map((item) => (isAutomaticBonusExcluded(item) ? { ...item, bonus_quantity: 0 } : item))
  }

  return items.map((item) => {
    if (item.bonus_quantity_manual && !isAutomaticBonusExcluded(item)) return item
    const rule = matchingAutomaticBonusRule(item, normalizedRules)
    const quantity = Number(item.quantity || 0)
    const bonusQuantity = rule ? Math.floor(quantity / rule.buy_quantity) * rule.bonus_quantity : 0
    return { ...item, bonus_quantity: bonusQuantity }
  })
}

function applyCustomerToForm(current, profile) {
  const next = {
    ...current,
    customerId: profile ? String(profile.id) : '',
    clientName: profile?.name || current.clientName,
    secondaryLine: profile?.secondary_line || '',
    transport: profile?.transport || '',
    notes: (profile?.notes || []).join('\n'),
    footerDiscounts: [...(profile?.footer_discounts || [])],
    lineDiscountsByGroup: { ...(profile?.line_discounts_by_format || {}) },
    automaticBonusRules: [...(profile?.automatic_bonus_rules || [])],
  }
  return { ...next, items: applyAutomaticBonusRulesToItems(next.items || [], next.automaticBonusRules) }
}

function buildProfilePayload(currentCustomer, form) {
  const base = currentCustomer || {
    footer_discounts: [],
    line_discounts_by_format: {},
    automatic_bonus_rules: [],
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
    automatic_bonus_rules: normalizeAutomaticBonusRules(form.automaticBonusRules),
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
      items: form.items
        .filter((item) => item.product_id && item.offering_id && (item.quantity > 0 || item.bonus_quantity > 0))
        .map((item) => ({
          product_id: item.product_id,
          offering_id: item.offering_id,
          quantity: item.quantity,
          bonus_quantity: item.bonus_quantity,
          unit_price: item.unit_price === '' || item.unit_price === undefined ? undefined : Number(item.unit_price || 0),
        })),
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
      unit_price: item.unit_price || '',
      product_name: item.product_name || '',
      offering_label: item.offering_label || '',
      bonus_quantity_manual: false,
    }

    if (Number(item.unit_price || 0) === 0) {
      current.bonus_quantity += Number(item.quantity || 0)
      current.bonus_quantity_manual = true
    } else {
      current.quantity += Number(item.quantity || 0)
      current.unit_price = Number(item.unit_price || 0)
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
    automaticBonusRules: matchingCustomer?.automatic_bonus_rules || [],
    items: Array.from(grouped.values()),
  }
}

export {
  applyCustomerToForm,
  applyAutomaticBonusRulesToItems,
  buildAvailableDiscountGroups,
  buildFormFromInvoiceDetail,
  buildInvoicePayload,
  buildProductsById,
  buildProfilePayload,
  buildTotals,
  splitNotes,
}

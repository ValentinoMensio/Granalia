const emptyItem = () => ({ product_id: '', offering_id: '', quantity: 0, bonus_quantity: 0, unit_price: '' })

const normalize = (value) =>
  (value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
    .replace(/\s+/g, ' ')

const money = (value) => new Intl.NumberFormat('es-AR').format(Math.round(value || 0))

const percent = (value) => `${Math.round(Number(value || 0) * 10000) / 100}%`

const compactFormatLabel = (value) =>
  String(value || '')
    .replace(/gr$/i, '')
    .replace(/_/g, ' ')
    .trim()

const mergeDiscountLabels = (labels) => {
  const next = new Set(labels)
  const hasPackBase = next.has('Pack 300/350/400')
  const hasPack500 = next.has('Pack 500')

  if (hasPackBase && hasPack500) {
    next.delete('Pack 300/350/400')
    next.delete('Pack 500')
    next.add('Pack 300/350/400/500 gr')
  }

  const bolsaLabels = ['Bolsa 4 kg', 'Bolsa 5 kg', 'Bolsa 25 kg', 'Bolsa 30 kg']
  const bolsasPresentes = bolsaLabels.filter((label) => next.has(label))
  if (bolsasPresentes.length > 1) {
    bolsasPresentes.forEach((label) => next.delete(label))
    next.add(`Bolsa ${bolsasPresentes.map((label) => label.replace('Bolsa ', '').replace(' kg', '')).join('/')} kg`)
  }

  return Array.from(next).sort((a, b) => a.localeCompare(b, 'es'))
}

const discountKeyForLabel = (label) => {
  const text = String(label || '').toLowerCase().trim()
  if (text.includes('16x300')) return 'Pack 300/350/400 gr'
  if (text.includes('12x300')) return 'Pack 300/350/400 gr'
  if (text.includes('12x350') || text.includes('12x400')) return 'Pack 300/350/400 gr'
  if (text.includes('10x500') || text.includes('12x500')) return 'Pack 500 gr'
  if (text.includes('10x1 kg') || text.includes('10x1000') || text.includes('10x 1 kg')) return 'Pack 1 kg'
  if (text.includes('x 4 kg') || text.includes('x4 kg')) return 'Bolsa 4 kg'
  if (text.includes('x 5 kg') || text.includes('x5 kg')) return 'Bolsa 5 kg'
  if (text.includes('x 25 kg') || text.includes('x25 kg')) return 'Bolsa 25 kg'
  if (text.includes('x 30 kg') || text.includes('x30 kg')) return 'Bolsa 30 kg'
  return String(label || '').trim() || 'Otros'
}

const summarizeDiscounts = (customer) => {
  const groupedLineEntries = Object.entries(customer?.line_discounts_by_format || {})
    .filter(([, rate]) => Number(rate) > 0)
    .reduce((acc, [format, rate]) => {
      const key = String(rate)
      if (!acc[key]) acc[key] = { rate, labels: [] }
      acc[key].labels.push(compactFormatLabel(format))
      return acc
    }, {})

  const lineEntries = Object.values(groupedLineEntries).flatMap(({ rate, labels }) =>
    mergeDiscountLabels(labels).map((label) => `${label} ${percent(rate)}`)
  )

  if (lineEntries.length) return lineEntries.join(', ')

  const footerEntries = (customer?.footer_discounts || [])
    .filter((item) => Number(item?.rate) > 0)
    .map((item) => percent(item.rate))

  if (footerEntries.length) return `Global ${footerEntries.join(' + ')}`

  return 'Sin descuentos'
}

const summarizeAutomaticBonuses = (customer, catalog = []) => {
  const rules = (customer?.automatic_bonus_rules || []).filter(
    (rule) => Number(rule.buy_quantity) > 0 && Number(rule.bonus_quantity) > 0
  )
  if (!rules.length) return 'Sin bonificación automática'

  const productsById = Object.fromEntries(catalog.map((product) => [String(product.id), product]))

  return rules
    .map((rule) => {
      const product = productsById[String(rule.product_id || '')]
      const offering = product?.offerings?.find((entry) => String(entry.id) === String(rule.offering_id || ''))
      const productName = product?.name || (rule.product_id ? `Producto #${rule.product_id}` : '')
      const scope = rule.product_id
        ? [productName, offering?.label].filter(Boolean).join('/')
        : 'Todos los productos'
      return `${scope}: ${rule.bonus_quantity} cada ${rule.buy_quantity}`
    })
    .join(', ')
}

export { discountKeyForLabel, emptyItem, money, normalize, percent, summarizeAutomaticBonuses, summarizeDiscounts }

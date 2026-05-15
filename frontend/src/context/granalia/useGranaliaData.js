import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { API_BASE, request } from '../../lib/api'
import { emptyItem } from '../../lib/format'
import { savePriceListPreview } from '../../lib/priceListPreview'
import { createInitialForm } from './form'
import {
  applyCustomerToForm,
  applyAutomaticBonusRulesToItems,
  buildAvailableDiscountGroups,
  buildFormFromInvoiceDetail,
  buildInvoicePayload,
  buildProductsById,
  buildProfilePayload,
  buildTotals,
  removeAutomaticBonusFromItems,
} from './helpers'

const DEFAULT_PRICE_LIST_PRODUCT_ORDER = [
  'Arvejas Partidas',
  'Avena Arrollada',
  'Avena Instantánea',
  'Garbanzos',
  'Harina de Maíz Cocción Rápida',
  'Harina de Maíz',
  'Harina de Maíz Blanca',
  'Lentejas',
  'Maíz Pisingallo',
  'Maíz Partido Blanco',
  'Porotos Alubia',
  'Maíz Partido Colorado',
  'Porotos Negros',
  'Porotos Colorados',
  'Porotos Soja',
  'Sémola de Trigo',
  'Trigo Burgol',
  'Trigo Pelado',
  'Mijo',
  'Alpiste',
  'Mezcla para Pájaros',
  'Arvejas Enteras',
  'Arroz Parbolizado',
  'Arroz 5/0 Largo Fino',
  'Arroz Integral Largo Fino',
  'Arroz Yamaní',
  'Harina de Maíz Abatí',
  'Harina de Garbanzos',
]

function normalizeOrderName(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .toLowerCase()
}

function sortCatalogByDefaultPriceListOrder(sourceCatalog) {
  const orderIndex = new Map(DEFAULT_PRICE_LIST_PRODUCT_ORDER.map((name, index) => [normalizeOrderName(name), index]))
  return [...sourceCatalog].sort((a, b) => {
    const namesA = [a.name, ...(a.aliases || [])].map(normalizeOrderName)
    const namesB = [b.name, ...(b.aliases || [])].map(normalizeOrderName)
    const indexA = Math.min(...namesA.map((name) => orderIndex.get(name) ?? Number.MAX_SAFE_INTEGER))
    const indexB = Math.min(...namesB.map((name) => orderIndex.get(name) ?? Number.MAX_SAFE_INTEGER))
    if (indexA !== indexB) return indexA - indexB
    return 0
  })
}

function isX1KgLabel(label) {
  return ['x 1 kg', 'x1 kg', 'x1kg'].includes(String(label || '').trim().toLowerCase())
}

function ensureX1KgOfferings(sourceCatalog) {
  return sourceCatalog.map((product) => {
    const offerings = [...(product.offerings || [])]
    if (offerings.some((offering) => isX1KgLabel(offering.label))) return { ...product, offerings }
    const sourceOffering = offerings.find((offering) => Number(offering.price || 0) > 0 && Number(offering.net_weight_kg || 0) > 0)
    if (!sourceOffering) return { ...product, offerings }
    return {
      ...product,
      offerings: [
        ...offerings,
        {
          id: 'x1kg',
          label: 'x 1 kg',
          price: Math.round(Number(sourceOffering.price || 0) / Number(sourceOffering.net_weight_kg || 1)),
          net_weight_kg: 1,
        },
      ],
    }
  })
}

function useGranaliaData() {
  const navigate = useNavigate()
  const [bootstrap, setBootstrap] = useState(null)
  const [customers, setCustomers] = useState([])
  const [catalog, setCatalog] = useState([])
  const [invoices, setInvoices] = useState([])
  const [invoiceDetail, setInvoiceDetail] = useState(null)
  const [internalCreditNoteItems, setInternalCreditNoteItems] = useState([])
  const [editingInvoiceId, setEditingInvoiceId] = useState(null)
  const [status, setStatus] = useState('')
  const [uploading, setUploading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [pdfFile, setPdfFile] = useState(null)
  const [priceListUploadName, setPriceListUploadName] = useState('')
  const [priceListUploadTargetId, setPriceListUploadTargetId] = useState('')
  const [form, setForm] = useState(createInitialForm)

  const productsById = useMemo(() => buildProductsById(catalog), [catalog])
  const currentCustomer = useMemo(
    () => customers.find((item) => String(item.id) === String(form.customerId || '')),
    [customers, form.customerId]
  )
  const totals = useMemo(() => buildTotals(form, productsById), [form, productsById])
  const availableDiscountGroups = useMemo(() => buildAvailableDiscountGroups(catalog), [catalog])

  function isCreditNoteDocument(invoice) {
    return String(invoice?.document_type || '').toUpperCase() === 'NOTA_CREDITO'
  }

  function documentLabel(invoice) {
    return isCreditNoteDocument(invoice) ? 'Nota de crédito' : 'Factura'
  }

  useEffect(() => {
    loadAll().catch((error) => setStatus(error.message))
  }, [])

  useEffect(() => {
    function handleStorage(event) {
      if (event.key === 'granalia:price-list-saved-at') {
        loadAll().catch((error) => setStatus(error.message))
      }
    }
    window.addEventListener('storage', handleStorage)
    return () => window.removeEventListener('storage', handleStorage)
  }, [])

  function applyBootstrap(nextBootstrap) {
    setBootstrap(nextBootstrap)
    setCustomers(Object.values(nextBootstrap.profiles || {}))
    setCatalog(nextBootstrap.catalog || [])
  }

  function primeForm(nextBootstrap) {
    const defaultPriceListId = nextBootstrap.price_list?.id ? String(nextBootstrap.price_list.id) : ''
    const sourceCustomers = Object.values(nextBootstrap.profiles || {})
    if (!sourceCustomers.length) {
      setForm({ ...createInitialForm(), priceListId: defaultPriceListId, internalPriceListId: defaultPriceListId, fiscalPriceListId: defaultPriceListId })
      return
    }

    const firstCustomer = sourceCustomers[0]
    setForm(applyCustomerToForm({ ...createInitialForm(), priceListId: defaultPriceListId, internalPriceListId: defaultPriceListId, fiscalPriceListId: defaultPriceListId }, firstCustomer))
  }

  async function loadAll() {
    const [nextBootstrap, nextInvoices] = await Promise.all([request('/api/bootstrap'), request('/api/invoices')])
    applyBootstrap(nextBootstrap)
    setInvoices(nextInvoices)
    primeForm(nextBootstrap)
  }

  async function loadInvoiceDetail(invoiceId) {
    const data = await request(`/api/invoices/${invoiceId}`)
    setInvoiceDetail(data)
    return data
  }

  async function loadInternalCreditNoteItems(customerId, creditNoteInvoiceId = null) {
    if (!customerId) {
      setInternalCreditNoteItems([])
      return []
    }
    const params = new URLSearchParams({ customer_id: String(customerId) })
    if (creditNoteInvoiceId) {
      params.set('credit_note_invoice_id', String(creditNoteInvoiceId))
    }
    const data = await request(`/api/invoices/internal-credit-note-items?${params.toString()}`)
    setInternalCreditNoteItems(data)
    return data
  }

  function clearInvoiceDetail() {
    setInvoiceDetail(null)
  }

  function clearInvoiceEditing(options = {}) {
    const silent = Boolean(options?.silent)
    const sourceCustomers = customers
    const defaultPriceListId = bootstrap?.price_list?.id ? String(bootstrap.price_list.id) : ''
    setEditingInvoiceId(null)
    if (!sourceCustomers.length) {
      setForm({ ...createInitialForm(), priceListId: defaultPriceListId, internalPriceListId: defaultPriceListId, fiscalPriceListId: defaultPriceListId })
      if (!silent) setStatus('Edición cancelada.')
      return
    }
    setForm(applyCustomerToForm({ ...createInitialForm(), priceListId: defaultPriceListId, internalPriceListId: defaultPriceListId, fiscalPriceListId: defaultPriceListId }, sourceCustomers[0]))
    if (!silent) setStatus('Edición cancelada.')
  }

  function clearCurrentInvoice() {
    const isInternalCreditNote = (form.billingMode || 'internal_only') === 'internal_credit_note'
    const sourceCustomers = customers
    const defaultPriceListId = bootstrap?.price_list?.id ? String(bootstrap.price_list.id) : ''
    setEditingInvoiceId(null)
    if (!sourceCustomers.length) {
      setForm({ ...createInitialForm(), priceListId: defaultPriceListId, internalPriceListId: defaultPriceListId, fiscalPriceListId: defaultPriceListId })
      setStatus(isInternalCreditNote ? 'Nota de crédito limpiada.' : 'Factura limpiada.')
      return
    }
    setForm(applyCustomerToForm({ ...createInitialForm(), priceListId: defaultPriceListId, internalPriceListId: defaultPriceListId, fiscalPriceListId: defaultPriceListId }, sourceCustomers[0]))
    setStatus(isInternalCreditNote ? 'Nota de crédito limpiada.' : 'Factura limpiada.')
  }

  function invoicePdfUrl(invoiceId) {
    return `${API_BASE}/api/invoices/${invoiceId}/pdf`
  }

  function openInvoicePdfPreview(invoiceId, previewWindow = null) {
    const url = invoicePdfUrl(invoiceId)
    if (previewWindow && !previewWindow.closed) {
      previewWindow.location.href = url
      return true
    }
    return Boolean(window.open(url, '_blank'))
  }

  function applyCustomer(customerId, profile, sourceCustomers = customers) {
    const nextProfile = profile || sourceCustomers.find((item) => String(item.id) === String(customerId))
    setForm((current) => applyCustomerToForm(current, nextProfile))
  }

  function normalizedLookupText(value) {
    return String(value || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .trim()
      .replace(/\s+/g, ' ')
  }

  function repriceItemsForCatalog(items, nextCatalog) {
    return (items || []).map((item) => {
      if (!item.product_id && !item.offering_id) return item

      const currentProduct = catalog.find((entry) => String(entry.id) === String(item.product_id || ''))
      const productName = item.product_name || currentProduct?.name || ''
      const nextProduct = nextCatalog.find((entry) => normalizedLookupText(entry.name) === normalizedLookupText(productName))
        || nextCatalog.find((entry) => String(entry.id) === String(item.product_id || ''))
      if (!nextProduct) return item

      const currentOffering = currentProduct?.offerings?.find((entry) => String(entry.id) === String(item.offering_id || ''))
      const offeringLabel = item.offering_label || currentOffering?.label || ''
      const nextOffering = (nextProduct.offerings || []).find((entry) => normalizedLookupText(entry.label) === normalizedLookupText(offeringLabel))
        || (nextProduct.offerings || []).find((entry) => String(entry.id) === String(item.offering_id || ''))

      return {
        ...item,
        product_id: nextProduct.id,
        product_name: nextProduct.name,
        offering_id: nextOffering?.id || item.offering_id,
        offering_label: nextOffering?.label || item.offering_label,
        unit_price: nextOffering ? Number(nextOffering.price || 0) : item.unit_price,
      }
    })
  }

  function applyPriceListChange(value, extraUpdates = {}) {
    if (value) {
      request(`/api/price-lists/${value}/catalog`)
        .then((nextCatalog) => {
          setCatalog(nextCatalog)
          setForm((current) => ({
            ...current,
            ...extraUpdates,
            priceListId: value,
            items: ['fiscal_only', 'internal_credit_note'].includes(extraUpdates.billingMode || current.billingMode)
              ? removeAutomaticBonusFromItems(repriceItemsForCatalog(current.items, nextCatalog))
              : applyAutomaticBonusRulesToItems(repriceItemsForCatalog(current.items, nextCatalog), current.automaticBonusRules),
          }))
        })
        .catch((error) => setStatus(error.message))
    } else {
      const nextCatalog = bootstrap?.catalog || []
      setCatalog(nextCatalog)
      setForm((current) => ({
        ...current,
        ...extraUpdates,
        priceListId: value,
        items: ['fiscal_only', 'internal_credit_note'].includes(extraUpdates.billingMode || current.billingMode)
          ? removeAutomaticBonusFromItems(repriceItemsForCatalog(current.items, nextCatalog))
          : applyAutomaticBonusRulesToItems(repriceItemsForCatalog(current.items, nextCatalog), current.automaticBonusRules),
      }))
    }
  }

  function updateFormField(field, value) {
    if (field === 'priceListId') {
      applyPriceListChange(value, { internalPriceListId: value, fiscalPriceListId: value })
      return
    }
    if (field === 'billingMode') {
      const declared = value === 'fiscal_only' || value === 'split'
      const targetPriceListId = value === 'fiscal_only' ? form.fiscalPriceListId : form.internalPriceListId
      if (targetPriceListId !== form.priceListId) {
        applyPriceListChange(targetPriceListId, { billingMode: value, declared })
      } else {
        setForm((current) => ({
          ...current,
          billingMode: value,
          declared,
          items: ['fiscal_only', 'internal_credit_note'].includes(value) ? removeAutomaticBonusFromItems(current.items) : applyAutomaticBonusRulesToItems(current.items, current.automaticBonusRules),
        }))
      }
      return
    }
    if (field === 'internalPriceListId') {
      if (form.billingMode === 'internal_only' || form.billingMode === 'split') {
        applyPriceListChange(value, { internalPriceListId: value })
      } else {
        setForm((current) => ({ ...current, internalPriceListId: value }))
      }
      return
    }
    if (field === 'fiscalPriceListId') {
      if (form.billingMode === 'fiscal_only') {
        applyPriceListChange(value, { fiscalPriceListId: value })
      } else {
        setForm((current) => ({ ...current, fiscalPriceListId: value }))
      }
      return
    }
    setForm((current) => ({ ...current, [field]: value }))
  }

  function addFooterDiscountRow() {
    setForm((current) => ({
      ...current,
      footerDiscounts: [...(current.footerDiscounts || []), { label: 'Nuevo Dto', rate: 0 }],
    }))
  }

  function updateFooterDiscountRow(index, field, value) {
    setForm((current) => {
      const next = [...(current.footerDiscounts || [])]
      next[index] = { ...next[index], [field]: field === 'rate' ? Number(value) / 100 : value }
      return { ...current, footerDiscounts: next }
    })
  }

  function removeFooterDiscountRow(index) {
    setForm((current) => ({
      ...current,
      footerDiscounts: (current.footerDiscounts || []).filter((_, currentIndex) => currentIndex !== index),
    }))
  }

  function updateLineDiscountGroup(group, rate) {
    setForm((current) => ({
      ...current,
      lineDiscountsByGroup: {
        ...(current.lineDiscountsByGroup || {}),
        [group]: Number(rate) / 100,
      },
    }))
  }

  function addAutomaticBonusRule() {
    setForm((current) => {
      const automaticBonusRules = [
        ...(current.automaticBonusRules || []),
        { product_id: null, offering_id: null, offering_label: '', buy_quantity: 10, bonus_quantity: 1 },
      ]
      return {
        ...current,
        automaticBonusRules,
        items: ['fiscal_only', 'internal_credit_note'].includes(current.billingMode) ? removeAutomaticBonusFromItems(current.items) : applyAutomaticBonusRulesToItems(current.items, automaticBonusRules),
      }
    })
  }

  function updateAutomaticBonusRule(index, field, value) {
    setForm((current) => {
      const automaticBonusRules = [...(current.automaticBonusRules || [])]
      const nextValue = ['product_id', 'offering_id'].includes(field)
        ? (value === '' ? null : Number(value))
        : field === 'offering_label'
        ? value
        : Number(value || 0)
      automaticBonusRules[index] = { ...automaticBonusRules[index], [field]: nextValue }
      if (field === 'product_id') {
        automaticBonusRules[index].offering_id = null
        automaticBonusRules[index].offering_label = ''
      }
      return {
        ...current,
        automaticBonusRules,
        items: ['fiscal_only', 'internal_credit_note'].includes(current.billingMode) ? removeAutomaticBonusFromItems(current.items) : applyAutomaticBonusRulesToItems(current.items, automaticBonusRules),
      }
    })
  }

  function removeAutomaticBonusRule(index) {
    setForm((current) => {
      const automaticBonusRules = (current.automaticBonusRules || []).filter((_, currentIndex) => currentIndex !== index)
      return {
        ...current,
        automaticBonusRules,
        items: ['fiscal_only', 'internal_credit_note'].includes(current.billingMode) ? removeAutomaticBonusFromItems(current.items) : applyAutomaticBonusRulesToItems(current.items, automaticBonusRules),
      }
    })
  }

  function updateItem(index, field, value) {
    setForm((current) => {
      const items = [...current.items]
      items[index] = { ...items[index], [field]: value }
      if (field === 'source_product_id') {
        const source = internalCreditNoteItems.find((entry) => String(entry.product_id || '') === String(value || ''))
        items[index].source_invoice_item_id = ''
        items[index].product_id = source?.product_id || ''
        items[index].product_name = source?.product_name || source?.label || ''
        items[index].offering_id = ''
        items[index].offering_label = ''
        items[index].unit_price = ''
        items[index].bonus_quantity = 0
        items[index].quantity = 0
        return { ...current, items }
      }
      if (field === 'source_offering_id') {
        const source = internalCreditNoteItems.find((entry) => String(entry.product_id || '') === String(items[index].product_id || '') && String(entry.offering_id || '') === String(value || ''))
        items[index].source_invoice_item_id = ''
        items[index].offering_id = source?.offering_id || ''
        items[index].offering_label = source?.offering_label || ''
        items[index].unit_price = ''
        items[index].bonus_quantity = 0
        items[index].quantity = 0
        return { ...current, items }
      }
      if (field === 'source_invoice_item_id') {
        const source = internalCreditNoteItems.find((entry) => String(entry.invoice_item_id) === String(value || ''))
        items[index].source_invoice_item_id = value || ''
        items[index].product_id = source?.product_id || ''
        items[index].product_name = source?.product_name || source?.label || ''
        items[index].offering_id = source?.offering_id || ''
        items[index].offering_label = source?.offering_label || ''
        items[index].unit_price = source ? Number(source.unit_price || 0) : ''
        items[index].bonus_quantity = 0
        items[index].quantity = 0
        return { ...current, items }
      }
      if (field === 'product_id') {
        const product = catalog.find((entry) => entry.id === value)
        items[index].product_name = product?.name || ''
        items[index].offering_id = ''
        items[index].offering_label = ''
        items[index].bonus_quantity_manual = false
        items[index].unit_price = ''
      }
      if (field === 'offering_id') {
        const product = catalog.find((entry) => entry.id === items[index].product_id)
        const offering = product?.offerings.find((entry) => entry.id === value)
        items[index].product_name = product?.name || ''
        items[index].offering_label = offering?.label || ''
        items[index].bonus_quantity_manual = false
        items[index].unit_price = offering ? Number(offering.price || 0) : ''
      }
      if (field === 'bonus_quantity') {
        items[index].bonus_quantity_manual = true
        return { ...current, items: ['fiscal_only', 'internal_credit_note'].includes(current.billingMode) ? removeAutomaticBonusFromItems(items) : applyAutomaticBonusRulesToItems(items, current.automaticBonusRules) }
      }
      return { ...current, items: ['fiscal_only', 'internal_credit_note'].includes(current.billingMode) ? removeAutomaticBonusFromItems(items) : applyAutomaticBonusRulesToItems(items, current.automaticBonusRules) }
    })
  }

  function addItemRow() {
    setForm((current) => ({ ...current, items: [...current.items, emptyItem()] }))
  }

  function removeItemRow(index) {
    setForm((current) => {
      const nextItems = current.items.filter((_, rowIndex) => rowIndex !== index)
      return { ...current, items: nextItems.length ? nextItems : [emptyItem()] }
    })
  }

  async function refreshInvoices() {
    setInvoices(await request('/api/invoices'))
  }

  async function startInvoiceEdit(invoiceId) {
    const detail = await loadInvoiceDetail(invoiceId)
    if (detail.price_list_id) {
      setCatalog(await request(`/api/price-lists/${detail.price_list_id}/catalog`))
    }
    if (String(detail?.document_type || '').toUpperCase() === 'NOTA_CREDITO' && String(detail?.fiscal_status || '') === 'internal') {
      await loadInternalCreditNoteItems(detail.customer_id, invoiceId)
    }
    setEditingInvoiceId(invoiceId)
    setForm(buildFormFromInvoiceDetail(detail, customers))
    setStatus(`Editando ${documentLabel(detail).toLowerCase()} ${invoiceId}.`)
    return detail
  }

  async function deleteInvoice(invoiceId) {
    const target = invoices.find((invoice) => String(invoice.invoice_id || invoice.id) === String(invoiceId)) || invoiceDetail
    const label = documentLabel(target)
    await request(`/api/invoices/${invoiceId}`, { method: 'DELETE' })
    await refreshInvoices()
    if (String(invoiceDetail?.id || '') === String(invoiceId)) {
      clearInvoiceDetail()
    }
    if (String(editingInvoiceId || '') === String(invoiceId)) {
      clearInvoiceEditing()
    }
    setStatus(`${label} ${invoiceId} eliminada.`)
  }

  async function authorizeInvoiceInArca(invoiceId, password) {
    const data = await request(`/api/invoices/${invoiceId}/arca/authorize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    })
    await refreshInvoices()
    if (String(invoiceDetail?.id || '') === String(invoiceId)) {
      await loadInvoiceDetail(invoiceId)
    }
    setStatus(data.message || `Factura ${invoiceId} autorizada en ARCA.`)
    return data
  }

  async function createCreditNote(invoiceId, payload) {
    const data = await request(`/api/invoices/${invoiceId}/credit-notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    await refreshInvoices()
    if (String(invoiceDetail?.id || '') === String(invoiceId)) {
      await loadInvoiceDetail(invoiceId)
    }
    setStatus(`Nota de crédito ${data.invoice_id} generada.`)
    return data
  }

  async function saveCustomer() {
    if (!form.clientName.trim()) {
      setStatus('Ingresá un cliente.')
      return
    }

    setSaving(true)
    try {
      const method = form.customerId ? 'PUT' : 'POST'
      const path = form.customerId ? `/api/customers/${form.customerId}` : '/api/customers'
      const data = await request(path, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildProfilePayload(currentCustomer, form)),
      })
      applyBootstrap(data.bootstrap)
      await refreshInvoices()
      setForm((current) => ({ ...current, customerId: String(data.customer.id) }))
      setStatus('Cliente guardado en PostgreSQL.')
    } finally {
      setSaving(false)
    }
  }

  async function updateCustomer(id, payload) {
    setSaving(true)
    try {
      const data = await request(`/api/customers/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      applyBootstrap(data.bootstrap)
      await refreshInvoices()
      setStatus('Cliente actualizado correctamente.')
      return data
    } catch (error) {
      setStatus(`Error al actualizar: ${error.message}`)
      throw error
    } finally {
      setSaving(false)
    }
  }

  async function uploadPriceList() {
    if (!pdfFile) {
      setStatus('Elegí un PDF primero.')
      return
    }

    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', pdfFile)
      const uploadName = priceListUploadName.trim()
      if (uploadName || !priceListUploadTargetId) {
        formData.append('name', uploadName || pdfFile.name.replace(/\.pdf$/i, ''))
      }
      formData.append('activate', 'true')
      if (priceListUploadTargetId) {
        formData.append('price_list_id', priceListUploadTargetId)
      }
      const data = await request('/api/price-lists/preview', { method: 'POST', body: formData })
      savePriceListPreview({
        ...data,
        filename: pdfFile.name,
        name: uploadName,
        source: 'upload',
        targetId: priceListUploadTargetId,
      })
      setStatus('Preview generado.')
      navigate('/price-list-preview')
    } catch (error) {
      setStatus(`Error al generar preview: ${error.message}`)
      throw error
    } finally {
      setUploading(false)
    }
  }

  async function startManualPriceList() {
    setUploading(true)
    try {
      const targetCatalog = priceListUploadTargetId
        ? await request(`/api/price-lists/${priceListUploadTargetId}/catalog`)
        : catalog
      savePriceListPreview({
        catalog: ensureX1KgOfferings(sortCatalogByDefaultPriceListOrder(targetCatalog)),
        warnings: [],
        filename: 'lista-manual.pdf',
        name: priceListUploadName.trim(),
        source: 'manual',
        targetId: priceListUploadTargetId,
      })
      setStatus('Carga manual preparada.')
      navigate('/price-list-preview')
    } catch (error) {
      setStatus(`Error al preparar carga manual: ${error.message}`)
      throw error
    } finally {
      setUploading(false)
    }
  }

  async function deletePriceList(priceListId) {
    if (!priceListId) return
    await request(`/api/price-lists/${priceListId}`, { method: 'DELETE' })
    const nextBootstrap = await request('/api/bootstrap')
    applyBootstrap(nextBootstrap)
    setForm((current) => ({
      ...current,
      priceListId: nextBootstrap.price_list?.id ? String(nextBootstrap.price_list.id) : '',
      items: [emptyItem()],
    }))
    await refreshInvoices()
    setStatus('Lista de precios eliminada.')
  }

  async function renamePriceList(priceListId, name) {
    if (!priceListId) return
    await request(`/api/price-lists/${priceListId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    const nextBootstrap = await request('/api/bootstrap')
    applyBootstrap(nextBootstrap)
    setStatus('Lista de precios renombrada.')
  }

  async function activatePriceList(priceListId) {
    if (!priceListId) return
    await request(`/api/price-lists/${priceListId}/activate`, { method: 'POST' })
    const nextBootstrap = await request('/api/bootstrap')
    applyBootstrap(nextBootstrap)
    setForm((current) => ({
      ...current,
      priceListId: String(priceListId),
      internalPriceListId: String(priceListId),
      fiscalPriceListId: String(priceListId),
    }))
    setStatus('Lista predeterminada actualizada.')
  }

  async function generateInvoice() {
    const isInternalCreditNote = (form.billingMode || 'internal_only') === 'internal_credit_note'
    if (!form.clientName.trim()) {
      setStatus('Ingresá un cliente.')
      return
    }

    if (isInternalCreditNote && !form.customerId) {
      setStatus('Seleccioná un cliente histórico para editar la nota de crédito.')
      return
    }

    const validItems = form.items.filter((item) => item.product_id && item.offering_id && (item.quantity > 0 || item.bonus_quantity > 0))
    const manualCreditNoteItems = form.creditNoteManualItems || [{ description: form.creditNoteManualDescription || '', amount: form.creditNoteManualAmount || '' }]
    const completeManualCreditNoteItems = manualCreditNoteItems.filter((item) => String(item.description || '').trim() && Number(item.amount || 0) > 0)
    const incompleteManualCreditNoteItems = manualCreditNoteItems.filter((item) => String(item.description || '').trim() || Number(item.amount || 0) > 0).length !== completeManualCreditNoteItems.length
    if (!validItems.length && !completeManualCreditNoteItems.length) {
      setStatus(isInternalCreditNote ? 'Completá al menos un producto a devolver o un concepto manual.' : 'Completá al menos un producto con presentación y cantidad.')
      return
    }

    if (isInternalCreditNote && incompleteManualCreditNoteItems) {
      setStatus('Completá descripción e importe del concepto manual.')
      return
    }

    if (isInternalCreditNote && validItems.some((item) => !item.source_invoice_item_id)) {
      setStatus('Seleccioná el remito origen de cada producto de la nota de crédito.')
      return
    }

    setGenerating(true)
    const previewWindow = window.open('', '_blank')
    if (previewWindow) {
      previewWindow.document.title = isInternalCreditNote ? 'Generando nota de crédito...' : 'Generando factura...'
      previewWindow.document.body.innerHTML = '<p style="font-family: sans-serif; padding: 24px;">Generando previsualización...</p>'
    }
    try {
      const isEditing = editingInvoiceId !== null
      const invoiceId = editingInvoiceId
      const data = await request(isEditing ? `/api/invoices/${invoiceId}` : '/api/invoices', {
        method: isEditing ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildInvoicePayload(form, currentCustomer)),
      })
      const createdInvoices = data.invoices || []
      const previewInvoiceId = data.invoice_id || createdInvoices[0]?.invoice_id
      const previewOpened = previewInvoiceId ? openInvoicePdfPreview(previewInvoiceId, previewWindow) : false
      await refreshInvoices()
      if (isEditing) {
        await loadInvoiceDetail(invoiceId)
      }
      setEditingInvoiceId(null)
      const defaultPriceListId = bootstrap?.price_list?.id ? String(bootstrap.price_list.id) : ''
      setForm({ ...createInitialForm(), priceListId: defaultPriceListId, internalPriceListId: defaultPriceListId, fiscalPriceListId: defaultPriceListId })
      const docLabel = isInternalCreditNote ? 'Nota de crédito' : 'Factura'
      const createdText = createdInvoices.length > 1
        ? `Comprobantes ${createdInvoices.map((invoice) => invoice.invoice_id).join(' y ')} guardados`
        : `${docLabel} ${previewInvoiceId} ${isEditing ? 'actualizada' : 'guardada'}`
      setStatus(`${createdText}${previewOpened ? ' y abierta para previsualizar' : ''}.`)
      return { invoiceId: previewInvoiceId, updated: isEditing }
    } catch (error) {
      if (previewWindow && !previewWindow.closed) {
        previewWindow.close()
      }
      const docLabel = isInternalCreditNote ? 'la nota de crédito' : 'la factura'
      setStatus(`Error al ${editingInvoiceId !== null ? 'actualizar' : 'guardar'} ${docLabel}: ${error.message}`)
    } finally {
      setGenerating(false)
    }
  }

  return {
    bootstrap,
    customers,
    catalog,
    invoices,
    invoiceDetail,
    internalCreditNoteItems,
    editingInvoiceId,
    status,
    uploading,
    saving,
    generating,
    pdfFile,
    priceListUploadName,
    priceListUploadTargetId,
    form,
    productsById,
    totals,
    availableDiscountGroups,
    setPdfFile,
    setPriceListUploadName,
    setPriceListUploadTargetId,
    setStatus,
    loadInvoiceDetail,
    loadInternalCreditNoteItems,
    clearInvoiceDetail,
    clearInvoiceEditing,
    clearCurrentInvoice,
    startInvoiceEdit,
    deleteInvoice,
    authorizeInvoiceInArca,
    createCreditNote,
    invoicePdfUrl,
    applyCustomer,
    updateFormField,
    addFooterDiscountRow,
    updateFooterDiscountRow,
    removeFooterDiscountRow,
    updateLineDiscountGroup,
    addAutomaticBonusRule,
    updateAutomaticBonusRule,
    removeAutomaticBonusRule,
    updateItem,
    addItemRow,
    removeItemRow,
    saveCustomer,
    updateCustomer,
    uploadPriceList,
    startManualPriceList,
    deletePriceList,
    renamePriceList,
    activatePriceList,
    generateInvoice,
    refreshAll: loadAll,
  }
}

export { useGranaliaData }

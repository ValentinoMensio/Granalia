import { useEffect, useMemo, useState } from 'react'
import { API_BASE, request } from '../../lib/api'
import { emptyItem } from '../../lib/format'
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
} from './helpers'

function useGranaliaData() {
  const [bootstrap, setBootstrap] = useState(null)
  const [customers, setCustomers] = useState([])
  const [catalog, setCatalog] = useState([])
  const [invoices, setInvoices] = useState([])
  const [invoiceDetail, setInvoiceDetail] = useState(null)
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

  useEffect(() => {
    loadAll().catch((error) => setStatus(error.message))
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
      setForm({ ...createInitialForm(), priceListId: defaultPriceListId })
      return
    }

    const firstCustomer = sourceCustomers[0]
    setForm(applyCustomerToForm({ ...createInitialForm(), priceListId: defaultPriceListId }, firstCustomer))
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

  function clearInvoiceDetail() {
    setInvoiceDetail(null)
  }

  function clearInvoiceEditing() {
    const sourceCustomers = customers
    setEditingInvoiceId(null)
    if (!sourceCustomers.length) {
      setForm(createInitialForm())
      setStatus('Edición cancelada.')
      return
    }
    setForm(applyCustomerToForm(createInitialForm(), sourceCustomers[0]))
    setStatus('Edición cancelada.')
  }

  function clearCurrentInvoice() {
    const sourceCustomers = customers
    setEditingInvoiceId(null)
    if (!sourceCustomers.length) {
      setForm(createInitialForm())
      setStatus('Factura limpiada.')
      return
    }
    setForm(applyCustomerToForm(createInitialForm(), sourceCustomers[0]))
    setStatus('Factura limpiada.')
  }

  function invoiceDownloadUrl(invoiceId) {
    return `${API_BASE}/api/invoices/${invoiceId}/xlsx`
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

  function downloadInvoice(invoiceId) {
    const link = document.createElement('a')
    link.href = invoiceDownloadUrl(invoiceId)
    link.target = '_blank'
    link.rel = 'noreferrer'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
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

  function updateFormField(field, value) {
    if (field === 'priceListId') {
      if (value) {
        request(`/api/price-lists/${value}/catalog`)
          .then((nextCatalog) => {
            setCatalog(nextCatalog)
            setForm((current) => ({
              ...current,
              priceListId: value,
              items: applyAutomaticBonusRulesToItems(repriceItemsForCatalog(current.items, nextCatalog), current.automaticBonusRules),
            }))
          })
          .catch((error) => setStatus(error.message))
      } else {
        const nextCatalog = bootstrap?.catalog || []
        setCatalog(nextCatalog)
        setForm((current) => ({
          ...current,
          priceListId: value,
          items: applyAutomaticBonusRulesToItems(repriceItemsForCatalog(current.items, nextCatalog), current.automaticBonusRules),
        }))
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
        items: applyAutomaticBonusRulesToItems(current.items, automaticBonusRules),
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
        items: applyAutomaticBonusRulesToItems(current.items, automaticBonusRules),
      }
    })
  }

  function removeAutomaticBonusRule(index) {
    setForm((current) => {
      const automaticBonusRules = (current.automaticBonusRules || []).filter((_, currentIndex) => currentIndex !== index)
      return {
        ...current,
        automaticBonusRules,
        items: applyAutomaticBonusRulesToItems(current.items, automaticBonusRules),
      }
    })
  }

  function updateItem(index, field, value) {
    setForm((current) => {
      const items = [...current.items]
      items[index] = { ...items[index], [field]: value }
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
        return { ...current, items: applyAutomaticBonusRulesToItems(items, current.automaticBonusRules) }
      }
      return { ...current, items: applyAutomaticBonusRulesToItems(items, current.automaticBonusRules) }
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
    setEditingInvoiceId(invoiceId)
    setForm(buildFormFromInvoiceDetail(detail, customers))
    setStatus(`Editando factura ${invoiceId}.`)
    return detail
  }

  async function deleteInvoice(invoiceId) {
    await request(`/api/invoices/${invoiceId}`, { method: 'DELETE' })
    await refreshInvoices()
    if (String(invoiceDetail?.id || '') === String(invoiceId)) {
      clearInvoiceDetail()
    }
    if (String(editingInvoiceId || '') === String(invoiceId)) {
      clearInvoiceEditing()
    }
    setStatus(`Factura ${invoiceId} eliminada.`)
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
      formData.append('name', priceListUploadName.trim() || pdfFile.name.replace(/\.pdf$/i, ''))
      formData.append('activate', 'true')
      if (priceListUploadTargetId) {
        formData.append('price_list_id', priceListUploadTargetId)
      }
      const data = await request('/api/price-lists/upload', { method: 'POST', body: formData })
      applyBootstrap(data.bootstrap)
      setForm((current) => ({ ...current, priceListId: data.bootstrap?.price_list?.id ? String(data.bootstrap.price_list.id) : current.priceListId }))
      setStatus('Lista de precios actualizada en la base.')
      setPdfFile(null)
      setPriceListUploadName('')
      setPriceListUploadTargetId('')
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

  async function generateInvoice() {
    if (!form.clientName.trim()) {
      setStatus('Ingresá un cliente.')
      return
    }

    const validItems = form.items.filter((item) => item.product_id && item.offering_id && (item.quantity > 0 || item.bonus_quantity > 0))
    if (!validItems.length) {
      setStatus('Completá al menos un producto con presentación y cantidad.')
      return
    }

    setGenerating(true)
    const previewWindow = window.open('', '_blank')
    if (previewWindow) {
      previewWindow.document.title = 'Generando factura...'
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
      const previewOpened = openInvoicePdfPreview(data.invoice_id, previewWindow)
      await refreshInvoices()
      setEditingInvoiceId(null)
      setForm({ ...createInitialForm(), priceListId: bootstrap?.price_list?.id ? String(bootstrap.price_list.id) : '' })
      setStatus(`Factura ${data.invoice_id} ${isEditing ? 'actualizada' : 'guardada'}${previewOpened ? ' y abierta para previsualizar' : ''}.`)
      return { invoiceId: data.invoice_id, updated: isEditing }
    } catch (error) {
      if (previewWindow && !previewWindow.closed) {
        previewWindow.close()
      }
      setStatus(`Error al ${editingInvoiceId !== null ? 'actualizar' : 'guardar'} la factura: ${error.message}`)
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
    clearInvoiceDetail,
    clearInvoiceEditing,
    clearCurrentInvoice,
    startInvoiceEdit,
    deleteInvoice,
    invoiceDownloadUrl,
    invoicePdfUrl,
    downloadInvoice,
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
    deletePriceList,
    renamePriceList,
    generateInvoice,
    refreshAll: loadAll,
  }
}

export { useGranaliaData }

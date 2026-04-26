import { useEffect, useMemo, useState } from 'react'
import { API_BASE, request } from '../../lib/api'
import { emptyItem } from '../../lib/format'
import { createInitialForm } from './form'
import {
  applyCustomerToForm,
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
    const sourceCustomers = Object.values(nextBootstrap.profiles || {})
    if (!sourceCustomers.length) {
      setForm(createInitialForm())
      return
    }

    const firstCustomer = sourceCustomers[0]
    setForm(applyCustomerToForm(createInitialForm(), firstCustomer))
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

  function invoiceDownloadUrl(invoiceId) {
    return `${API_BASE}/api/invoices/${invoiceId}/xlsx`
  }

  function invoicePdfUrl(invoiceId) {
    return `${API_BASE}/api/invoices/${invoiceId}/pdf`
  }

  function downloadInvoicePdf(invoiceId) {
    const link = document.createElement('a')
    link.href = invoicePdfUrl(invoiceId)
    link.target = '_blank'
    link.rel = 'noreferrer'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
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

  function updateFormField(field, value) {
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

  function updateItem(index, field, value) {
    setForm((current) => {
      const items = [...current.items]
      items[index] = { ...items[index], [field]: value }
      if (field === 'product_id') {
        items[index].offering_id = ''
      }
      return { ...current, items }
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
      const data = await request('/api/price-lists/upload', { method: 'POST', body: formData })
      applyBootstrap(data.bootstrap)
      setStatus('Lista de precios actualizada en la base.')
      setPdfFile(null)
    } finally {
      setUploading(false)
    }
  }

  async function generateInvoice() {
    if (!form.clientName.trim()) {
      setStatus('Ingresá un cliente.')
      return
    }

    setGenerating(true)
    try {
      const isEditing = editingInvoiceId !== null
      const invoiceId = editingInvoiceId
      const data = await request(isEditing ? `/api/invoices/${invoiceId}` : '/api/invoices', {
        method: isEditing ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildInvoicePayload(form, currentCustomer)),
      })
      const shouldDownload = window.confirm(`Factura ${data.invoice_id} ${isEditing ? 'actualizada' : 'guardada'}. ¿Querés descargarla en PDF?`)
      if (shouldDownload) {
        downloadInvoicePdf(data.invoice_id)
      }
      await refreshInvoices()
      setEditingInvoiceId(null)
      setForm(createInitialForm())
      setStatus(`Factura ${data.invoice_id} ${isEditing ? 'actualizada' : 'guardada'}${shouldDownload ? ' y descargada en PDF' : ''}.`)
      return { invoiceId: data.invoice_id, updated: isEditing }
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
    form,
    productsById,
    totals,
    availableDiscountGroups,
    setPdfFile,
    setStatus,
    loadInvoiceDetail,
    clearInvoiceDetail,
    clearInvoiceEditing,
    startInvoiceEdit,
    deleteInvoice,
    invoiceDownloadUrl,
    invoicePdfUrl,
    downloadInvoice,
    downloadInvoicePdf,
    applyCustomer,
    updateFormField,
    addFooterDiscountRow,
    updateFooterDiscountRow,
    removeFooterDiscountRow,
    updateLineDiscountGroup,
    updateItem,
    addItemRow,
    removeItemRow,
    saveCustomer,
    updateCustomer,
    uploadPriceList,
    generateInvoice,
    refreshAll: loadAll,
  }
}

export { useGranaliaData }

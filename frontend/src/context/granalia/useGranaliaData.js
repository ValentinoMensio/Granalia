import { useEffect, useMemo, useState } from 'react'
import { API_BASE, request } from '../../lib/api'
import { emptyItem } from '../../lib/format'
import { createInitialForm } from './form'
import {
  applyCustomerToForm,
  buildAvailableDiscountGroups,
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
    if (!sourceCustomers.length) return

    const firstCustomer = sourceCustomers[0]
    setForm((current) => applyCustomerToForm(current, firstCustomer))
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

  function invoiceDownloadUrl(invoiceId) {
    return `${API_BASE}/api/invoices/${invoiceId}/xlsx`
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
      const data = await request('/api/invoices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildInvoicePayload(form, currentCustomer)),
      })
      downloadInvoice(data.invoice_id)
      await refreshInvoices()
      setStatus(`Factura ${data.invoice_id} guardada y descargada.`)
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
    invoiceDownloadUrl,
    downloadInvoice,
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

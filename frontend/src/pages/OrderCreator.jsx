import InvoiceFormCard from '../components/invoices/InvoiceFormCard'
import ProductRowsCard from '../components/invoices/ProductRowsCard'
import { useGranalia } from '../context/GranaliaContext'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useEffect, useMemo, useState } from 'react'
import { request } from '../lib/api'

function normalizeLookup(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
    .replace(/\s+/g, ' ')
}

function findMatchingProduct(catalog, product) {
  return catalog.find((entry) => String(entry.id) === String(product?.id || ''))
    || catalog.find((entry) => normalizeLookup(entry.name) === normalizeLookup(product?.name))
}

function buildSplitPreview(form, productsById, fiscalCatalog) {
  const billingMode = form.billingMode || (form.declared ? 'fiscal_only' : 'internal_only')
  const declaredPercentage = Math.max(0, Math.min(100, Number(form.declaredPercentage || 0)))
  if (billingMode !== 'split') {
    return { enabled: false, rows: [], warnings: [], declaredPercentage }
  }

  const warnings = []
  const warningSet = new Set()
  const rows = []
  let internalQuantityTotal = 0
  let declaredQuantityTotal = 0
  let internalTotal = 0
  let fiscalTotal = 0

  for (const item of form.items || []) {
    if (!item.product_id || !item.offering_id) continue
    const product = productsById[item.product_id]
    const offering = product?.offerings?.find((entry) => String(entry.id) === String(item.offering_id))
    const quantity = Number(item.quantity || 0)
    if (!product || !offering || quantity <= 0) continue
    if (!Number.isInteger(quantity)) {
      warningSet.add('El modo dividido no acepta cantidades decimales. Ajustá las cantidades antes de generar.')
    }

    const fiscalProduct = findMatchingProduct(fiscalCatalog, product)
    const fiscalOffering = fiscalProduct?.offerings?.find((entry) => normalizeLookup(entry.label) === normalizeLookup(offering.label))
      || fiscalProduct?.offerings?.find((entry) => String(entry.id) === String(offering.id))
    if (!fiscalProduct) warningSet.add(`Falta el producto "${product.name}" en la lista declarada.`)
    if (fiscalProduct && !fiscalOffering) warningSet.add(`Falta la presentación "${offering.label}" de "${product.name}" en la lista declarada.`)
    if (fiscalProduct && fiscalProduct.iva_rate == null) warningSet.add(`Falta configurar IVA fiscal para "${fiscalProduct.name}".`)

    const declaredQuantity = Math.ceil(quantity * declaredPercentage / 100)
    const internalQuantity = Math.max(0, quantity - declaredQuantity)
    const internalBonus = Math.max(0, Math.round(Number(item.bonus_quantity || 0)))
    const internalUnitPrice = item.unit_price === '' || item.unit_price === undefined ? Number(offering.price || 0) : Number(item.unit_price || 0)
    const fiscalUnitPrice = Number(fiscalOffering?.price || 0)
    const rowInternalTotal = internalQuantity * internalUnitPrice
    const rowFiscalTotal = declaredQuantity * fiscalUnitPrice

    internalQuantityTotal += internalQuantity + internalBonus
    declaredQuantityTotal += declaredQuantity
    internalTotal += rowInternalTotal
    fiscalTotal += rowFiscalTotal
    rows.push({
      productName: product.name,
      offeringLabel: offering.label,
      totalQuantity: quantity,
      internalQuantity,
      internalBonus,
      declaredQuantity,
      internalTotal: rowInternalTotal,
      fiscalTotal: rowFiscalTotal,
    })
  }

  warnings.push(...warningSet)
  return { enabled: true, rows, warnings, declaredPercentage, internalQuantityTotal, declaredQuantityTotal, internalTotal, fiscalTotal }
}

export default function OrderCreator() {
  const navigate = useNavigate()
  const { session } = useAuth()
  const isAdmin = session?.role === 'admin'
  const [fiscalCatalog, setFiscalCatalog] = useState([])
  const {
    bootstrap,
    customers,
    catalog,
    availableDiscountGroups,
    editingInvoiceId,
    saving,
    generating,
    form,
    productsById,
    totals,
    addAutomaticBonusRule,
    addFooterDiscountRow,
    applyCustomer,
    updateAutomaticBonusRule,
    updateFooterDiscountRow,
    updateLineDiscountGroup,
    updateFormField,
    updateItem,
    addItemRow,
    removeItemRow,
    removeAutomaticBonusRule,
    removeFooterDiscountRow,
    saveCustomer,
    generateInvoice,
    clearCurrentInvoice,
    clearInvoiceEditing,
  } = useGranalia()

  useEffect(() => {
    let cancelled = false
    async function loadFiscalCatalog() {
      if ((form.billingMode || 'internal_only') !== 'split') {
        setFiscalCatalog([])
        return
      }
      try {
        const nextCatalog = form.fiscalPriceListId ? await request(`/api/price-lists/${form.fiscalPriceListId}/catalog`) : (bootstrap?.catalog || [])
        if (!cancelled) setFiscalCatalog(nextCatalog)
      } catch {
        if (!cancelled) setFiscalCatalog([])
      }
    }
    loadFiscalCatalog()
    return () => {
      cancelled = true
    }
  }, [bootstrap, form.billingMode, form.fiscalPriceListId])

  const splitPreview = useMemo(
    () => buildSplitPreview(form, productsById, fiscalCatalog),
    [form, productsById, fiscalCatalog]
  )

  function handleCancelInvoiceEdit() {
    clearInvoiceEditing()
    navigate('/history')
  }

  async function handleGenerateInvoice() {
    const result = await generateInvoice()
    if (result?.updated) {
      navigate('/history')
    }
  }

  function handleClearInvoice() {
    if (!window.confirm('¿Limpiar la factura actual? Se borrarán productos, cantidades y cambios sin guardar.')) return
    clearCurrentInvoice()
  }

  return (
    <main className="mt-8">
      <section className="space-y-6">
        <InvoiceFormCard
          bootstrap={bootstrap}
          customers={customers}
          availableDiscountGroups={availableDiscountGroups}
          editingInvoiceId={editingInvoiceId}
          form={form}
          saving={saving}
          generating={generating}
          onAddFooterDiscount={addFooterDiscountRow}
          onAddAutomaticBonusRule={addAutomaticBonusRule}
          onApplyCustomer={applyCustomer}
          onAutomaticBonusRuleChange={updateAutomaticBonusRule}
          onFooterDiscountChange={updateFooterDiscountRow}
          onFieldChange={updateFormField}
          onLineDiscountChange={updateLineDiscountGroup}
          onGenerate={handleGenerateInvoice}
          onRemoveFooterDiscount={removeFooterDiscountRow}
          onRemoveAutomaticBonusRule={removeAutomaticBonusRule}
          onSave={isAdmin ? saveCustomer : null}
          onCancelEdit={handleCancelInvoiceEdit}
        />

        <ProductRowsCard
          editingInvoiceId={editingInvoiceId}
          form={form}
          catalog={catalog}
          productsById={productsById}
          splitPreview={splitPreview}
          totals={totals}
          generating={generating}
          onAddItem={addItemRow}
          onCancelEdit={handleCancelInvoiceEdit}
          onClearInvoice={handleClearInvoice}
          onGenerate={handleGenerateInvoice}
          onRemoveItem={removeItemRow}
          onUpdateItem={updateItem}
        />

      </section>
    </main>
  )
}

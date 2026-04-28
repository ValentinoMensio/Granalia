import InvoiceFormCard from '../components/invoices/InvoiceFormCard'
import ProductRowsCard from '../components/invoices/ProductRowsCard'
import { useGranalia } from '../context/GranaliaContext'
import { useNavigate } from 'react-router-dom'

export default function OrderCreator() {
  const navigate = useNavigate()
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
          onSave={saveCustomer}
          onCancelEdit={handleCancelInvoiceEdit}
        />

        <ProductRowsCard
          editingInvoiceId={editingInvoiceId}
          form={form}
          catalog={catalog}
          productsById={productsById}
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

import InvoiceFormCard from '../components/invoices/InvoiceFormCard'
import ProductRowsCard from '../components/invoices/ProductRowsCard'
import PriceListPanel from '../components/sidebar/PriceListPanel'
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
    uploading,
    saving,
    generating,
    form,
    productsById,
    totals,
    setPdfFile,
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
    uploadPriceList,
    generateInvoice,
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

  return (
    <main className="mt-8">
      <section className="space-y-6">
        <PriceListPanel
          bootstrap={bootstrap}
          uploading={uploading}
          onFileChange={setPdfFile}
          onUpload={uploadPriceList}
        />

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
          onGenerate={handleGenerateInvoice}
          onRemoveItem={removeItemRow}
          onUpdateItem={updateItem}
        />
      </section>
    </main>
  )
}

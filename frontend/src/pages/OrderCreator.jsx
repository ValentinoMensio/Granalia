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
    addFooterDiscountRow,
    applyCustomer,
    updateFooterDiscountRow,
    updateLineDiscountGroup,
    updateFormField,
    updateItem,
    addItemRow,
    removeItemRow,
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
    <main className="relative mt-8 xl:pr-[330px]">
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
          onApplyCustomer={applyCustomer}
          onFooterDiscountChange={updateFooterDiscountRow}
          onFieldChange={updateFormField}
          onLineDiscountChange={updateLineDiscountGroup}
          onGenerate={handleGenerateInvoice}
          onRemoveFooterDiscount={removeFooterDiscountRow}
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

      <aside className="mt-6 space-y-6 xl:absolute xl:right-0 xl:top-0 xl:mt-0 xl:w-[290px]">
        <PriceListPanel
          bootstrap={bootstrap}
          uploading={uploading}
          onFileChange={setPdfFile}
          onUpload={uploadPriceList}
        />
      </aside>
    </main>
  )
}

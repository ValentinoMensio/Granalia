import Field from '../ui/Field'
import Button from '../ui/Button'

function InvoiceFormCard({
  bootstrap,
  customers,
  availableDiscountGroups,
  editingInvoiceId,
  form,
  saving,
  generating,
  onAddFooterDiscount,
  onApplyCustomer,
  onFooterDiscountChange,
  onLineDiscountChange,
  onFieldChange,
  onGenerate,
  onRemoveFooterDiscount,
  onSave,
  onCancelEdit,
}) {
  return (
    <div className="surface p-6 lg:p-7">
      <div className="mb-6 flex items-center justify-between gap-4 border-b border-stone-200 pb-5">
        <div>
          <h2 className="subsection-title text-2xl">{editingInvoiceId ? `Editar factura #${editingInvoiceId}` : 'Nueva factura'}</h2>
        </div>
        {editingInvoiceId && (
          <Button variant="ghost" onClick={onCancelEdit}>
            Cancelar edición
          </Button>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Cliente histórico">
          <select className="input" value={form.customerId} onChange={(event) => onApplyCustomer(event.target.value)}>
            <option value="">Nuevo cliente</option>
            {customers.map((customer) => (
              <option key={customer.id} value={customer.id}>{customer.name}</option>
            ))}
          </select>
        </Field>

        <Field label="Fecha">
          <input className="input" type="date" value={form.date} onChange={(event) => onFieldChange('date', event.target.value)} />
        </Field>

        <Field label="Cliente" full>
          <input className="input" value={form.clientName} onChange={(event) => onFieldChange('clientName', event.target.value)} />
        </Field>

        <Field label="Línea secundaria" full>
          <input className="input" value={form.secondaryLine} onChange={(event) => onFieldChange('secondaryLine', event.target.value)} />
        </Field>

        <Field label="Transporte" full>
          <select className="input" value={form.transport} onChange={(event) => onFieldChange('transport', event.target.value)}>
            <option value="">Sin transporte</option>
            {(bootstrap?.transports || []).map((transport) => (
              <option key={transport.transport_id} value={transport.name}>{transport.name}</option>
            ))}
          </select>
        </Field>

        <Field label="Observaciones" full>
          <textarea className="input min-h-28" value={form.notes} onChange={(event) => onFieldChange('notes', event.target.value)} />
        </Field>
      </div>

      <div className="mt-6 border-t border-stone-200 pt-6">
        <h3 className="subsection-title mb-5 text-xl">Configuración de descuentos</h3>

        <div className="grid gap-8 md:grid-cols-2">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-slate-700">Descuentos Globales (al pie)</label>
              <Button variant="ghost" className="px-0 py-0 text-xs text-brand-red" onClick={onAddFooterDiscount}>
                + Agregar
              </Button>
            </div>
            <div className="space-y-2">
              {(form.footerDiscounts || []).map((discount, index) => (
                <div key={index} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={discount.label}
                    onChange={(event) => onFooterDiscountChange(index, 'label', event.target.value)}
                    placeholder="Ej: Mayorista"
                    className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs focus:outline-none focus:border-brand-red"
                  />
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      value={Number(discount.rate || 0) * 100}
                      onChange={(event) => onFooterDiscountChange(index, 'rate', event.target.value)}
                      className="w-16 rounded-lg border border-slate-300 px-2 py-1.5 text-xs text-right focus:outline-none focus:border-brand-red"
                    />
                    <span className="text-xs text-slate-400">%</span>
                  </div>
                  <button onClick={() => onRemoveFooterDiscount(index)} className="text-slate-300 hover:text-red-500">
                    ✕
                  </button>
                </div>
              ))}
              {(!form.footerDiscounts || form.footerDiscounts.length === 0) && (
                <p className="text-xs italic text-slate-400">No hay descuentos globales configurados.</p>
              )}
            </div>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-slate-700">Descuentos por Grupo (línea)</label>
            </div>
            <div className="max-h-64 space-y-2 overflow-y-auto pr-2">
              {availableDiscountGroups.map((group) => (
                <div key={group} className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 p-2">
                  <span className="text-xs font-medium text-slate-600">{group}</span>
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      value={(form.lineDiscountsByGroup?.[group] || 0) * 100}
                      onChange={(event) => onLineDiscountChange(group, event.target.value)}
                      className="w-14 rounded border border-slate-300 px-1 py-0.5 text-xs text-right focus:outline-none focus:border-brand-red"
                    />
                    <span className="text-xs text-slate-400">%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-6 flex flex-wrap gap-3 border-t border-stone-200 pt-5">
        <Button variant="primary" className="min-w-[180px]" onClick={onSave} disabled={saving}>
          {saving ? 'Guardando...' : 'Guardar cambios'}
        </Button>
      </div>
    </div>
  )
}

export default InvoiceFormCard

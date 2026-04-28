import Field from '../ui/Field'
import Button from '../ui/Button'
import AutomaticBonusRules from './AutomaticBonusRules'

function InvoiceFormCard({
  bootstrap,
  customers,
  availableDiscountGroups,
  editingInvoiceId,
  form,
  saving,
  generating,
  onAddFooterDiscount,
  onAddAutomaticBonusRule,
  onApplyCustomer,
  onAutomaticBonusRuleChange,
  onFooterDiscountChange,
  onLineDiscountChange,
  onFieldChange,
  onGenerate,
  onRemoveFooterDiscount,
  onRemoveAutomaticBonusRule,
  onSave,
  onClearInvoice,
  onCancelEdit,
}) {
  return (
    <div className="surface p-4 sm:p-6 lg:p-7">
      <div className="mb-5 flex items-center justify-between gap-4 border-b border-stone-200 pb-5 sm:mb-6">
        <div>
          <h2 className="subsection-title text-xl sm:text-2xl">{editingInvoiceId ? `Editar factura #${editingInvoiceId}` : 'Nueva factura'}</h2>
        </div>
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
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <label className="text-sm font-medium text-slate-700">Descuentos Globales (al pie)</label>
              <Button variant="ghost" className="px-0 py-0 text-xs text-brand-red" onClick={onAddFooterDiscount}>
                + Agregar
              </Button>
            </div>
            <div className="space-y-2">
              {(form.footerDiscounts || []).map((discount, index) => (
                <div key={index} className="grid grid-cols-[minmax(0,1fr)_5rem_auto] items-center gap-2">
                  <input
                    type="text"
                    value={discount.label}
                    onChange={(event) => onFooterDiscountChange(index, 'label', event.target.value)}
                    placeholder="Ej: Mayorista"
                    className="input flex-1 py-1.5 text-xs"
                  />
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      value={Number(discount.rate || 0) * 100}
                      onChange={(event) => onFooterDiscountChange(index, 'rate', event.target.value)}
                      className="input w-16 py-1.5 text-right text-xs"
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
                      className="input w-14 px-1 py-0.5 text-right text-xs"
                    />
                    <span className="text-xs text-slate-400">%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-6 border-t border-stone-200 pt-6">
        <AutomaticBonusRules
          rules={form.automaticBonusRules}
          catalog={bootstrap?.catalog || []}
          onAdd={onAddAutomaticBonusRule}
          onChange={onAutomaticBonusRuleChange}
          onRemove={onRemoveAutomaticBonusRule}
        />
      </div>

      <div className="mt-6 flex flex-wrap gap-3 border-t border-stone-200 pt-5">
        <Button variant="primary" className="w-full sm:min-w-[180px] sm:w-auto" onClick={onSave} disabled={saving}>
          {saving ? 'Guardando...' : 'Guardar cambios'}
        </Button>
        <Button variant="secondary" className="w-full sm:min-w-[180px] sm:w-auto" onClick={onClearInvoice} disabled={saving}>
          Limpiar factura
        </Button>
      </div>
    </div>
  )
}

export default InvoiceFormCard

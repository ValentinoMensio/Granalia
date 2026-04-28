import Button from '../ui/Button'
import { discountKeyForLabel } from '../../lib/format'

function AutomaticBonusRules({ rules, catalog, disablesLineDiscount, onAdd, onChange, onRemove, onDisablesLineDiscountChange }) {
  const allOfferings = Array.from(
    new Set(catalog.flatMap((product) => (product.offerings || []).map((offering) => discountKeyForLabel(offering.label))))
  ).sort((a, b) => a.localeCompare(b, 'es'))

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <label className="text-sm font-medium text-slate-700">Bonificación automática</label>
          <p className="mt-1 text-xs text-slate-400">Ej: cada 10 productos agrega 1 bonificado.</p>
        </div>
        <Button variant="ghost" className="px-0 py-0 text-xs text-brand-red" onClick={onAdd}>
          + Agregar
        </Button>
      </div>

      <label className="flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs font-medium text-slate-600">
        <input
          type="checkbox"
          checked={Boolean(disablesLineDiscount)}
          onChange={(event) => onDisablesLineDiscountChange(event.target.checked)}
          className="mt-0.5"
        />
        <span>Si una línea bonifica, no aplica descuento. Si no bonifica, mantiene el descuento configurado.</span>
      </label>

      <div className="space-y-3">
        {(rules || []).map((rule, index) => {
          const product = catalog.find((entry) => String(entry.id) === String(rule.product_id || ''))
          const offerings = product?.offerings || []
          const formatValue = rule.product_id ? (rule.offering_id || '') : (rule.offering_label || '')

          return (
            <div key={index} className="grid gap-2 rounded-lg border border-slate-100 bg-slate-50 p-3 lg:grid-cols-[1fr_1fr_6rem_6rem_auto] lg:items-end">
              <div>
                <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">Producto</div>
                <select
                  className="input w-full py-1.5 text-xs"
                  value={rule.product_id || ''}
                  onChange={(event) => onChange(index, 'product_id', event.target.value)}
                >
                  <option value="">Todos</option>
                  {catalog.map((productItem) => (
                    <option key={productItem.id} value={productItem.id}>{productItem.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">Formato</div>
                <select
                  className="input w-full py-1.5 text-xs"
                  value={formatValue}
                  onChange={(event) => onChange(index, rule.product_id ? 'offering_id' : 'offering_label', event.target.value)}
                >
                  <option value="">Todos</option>
                  {rule.product_id
                    ? offerings.map((offering) => (
                        <option key={offering.id} value={offering.id}>{offering.label}</option>
                      ))
                    : allOfferings.map((label) => (
                        <option key={label} value={label}>{label}</option>
                      ))}
                </select>
              </div>

              <div>
                <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">Cada</div>
                <input
                  className="input w-full py-1.5 text-right text-xs"
                  type="number"
                  min="1"
                  value={rule.buy_quantity || ''}
                  onChange={(event) => onChange(index, 'buy_quantity', event.target.value)}
                />
              </div>

              <div>
                <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">Bonifica</div>
                <input
                  className="input w-full py-1.5 text-right text-xs"
                  type="number"
                  min="1"
                  value={rule.bonus_quantity || ''}
                  onChange={(event) => onChange(index, 'bonus_quantity', event.target.value)}
                />
              </div>

              <button onClick={() => onRemove(index)} className="text-left text-xs text-slate-400 hover:text-red-500 lg:pb-2 lg:text-center">
                Quitar
              </button>
            </div>
          )
        })}

        {(!rules || rules.length === 0) && (
          <p className="text-xs italic text-slate-400">No hay bonificaciones automáticas configuradas.</p>
        )}
      </div>
    </div>
  )
}

export default AutomaticBonusRules

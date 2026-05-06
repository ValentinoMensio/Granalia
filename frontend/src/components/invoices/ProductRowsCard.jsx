import Button from '../ui/Button'
import Metric from '../ui/Metric'
import { isX1KgLabel, money } from '../../lib/format'

function optionsWithHistoricalSelection(options, selectedId, selectedLabel) {
  if (!selectedId || options.some((entry) => String(entry.id) === String(selectedId))) {
    return options
  }
  return [...options, { id: selectedId, label: `${selectedLabel || 'Presentación anterior'} (inactiva)`, price: 0 }]
}

function productsWithHistoricalSelection(catalog, selectedId, selectedName) {
  if (!selectedId || catalog.some((entry) => String(entry.id) === String(selectedId))) {
    return catalog
  }
  return [...catalog, { id: selectedId, name: `${selectedName || 'Producto anterior'} (inactivo)`, offerings: [] }]
}

function parseQuantityInput(value, allowsFractionalQuantity) {
  if (value === '') return 0
  const quantity = Number(value)
  return allowsFractionalQuantity ? quantity : Math.round(quantity)
}

function ProductRowsCard({
  editingInvoiceId,
  form,
  catalog,
  productsById,
  splitPreview,
  totals,
  generating,
  onAddItem,
  onGenerate,
  onClearInvoice,
  onCancelEdit,
  onRemoveItem,
  onUpdateItem,
}) {
  return (
    <div className="surface p-4 sm:p-6 lg:p-7">
      <div className="mb-5">
        <div>
          <div className="eyebrow">Detalle</div>
          <h2 className="subsection-title mt-2 text-xl sm:text-2xl">Productos y cantidades</h2>
        </div>
      </div>

      <div className="overflow-hidden rounded-[26px] border border-stone-200 bg-stone-50/70">
        <div className="hidden lg:block">
          <table className="table-base w-full table-fixed border-collapse">
            <colgroup>
              <col className="w-[27%]" />
              <col className="w-[18%]" />
              <col className="w-[12%]" />
              <col className="w-[12%]" />
              <col className="w-[15%]" />
              <col className="w-[9%]" />
              <col className="w-[7%]" />
            </colgroup>

            <thead className="table-head">
              <tr>
                <th className="table-cell text-center text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">
                  Producto
                </th>
                <th className="table-cell text-center text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">
                  Presentación
                </th>
                <th className="table-cell text-center text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">
                  Cantidad
                </th>
                <th className="table-cell text-center text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">
                  Bonificación
                </th>
                <th className="table-cell text-center text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">
                  Precio
                </th>
                <th className="table-cell text-center text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">
                  Total
                </th>
                <th className="table-cell" />
              </tr>
            </thead>

            <tbody>
              {form.items.map((item, index) => {
                const product = productsById[item.product_id]
                const offeringOptions = editingInvoiceId ? optionsWithHistoricalSelection(product?.offerings || [], item.offering_id, item.offering_label) : (product?.offerings || [])
                const offering = offeringOptions.find((entry) => String(entry.id) === String(item.offering_id))
                const allowsFractionalQuantity = isX1KgLabel(offering?.label || item.offering_label)
                const price = item.unit_price === '' || item.unit_price === undefined ? Number(offering?.price || 0) : Number(item.unit_price || 0)
                const quantity = Number(item.quantity || 0)
                const rowTotal = quantity * price
                const productOptions = editingInvoiceId ? productsWithHistoricalSelection(catalog, item.product_id, item.product_name) : catalog

                return (
                    <tr key={index} className="table-row">
                      <td className="table-cell align-middle">
                      <select
                        className="input w-full min-w-0"
                        value={item.product_id}
                        onChange={(event) =>
                          onUpdateItem(
                            index,
                            'product_id',
                            event.target.value ? Number(event.target.value) : ''
                          )
                        }
                      >
                        <option value="">Producto</option>
                        {productOptions.map((productItem) => (
                          <option key={productItem.id} value={productItem.id}>
                            {productItem.name}
                          </option>
                        ))}
                      </select>
                    </td>

                      <td className="table-cell align-middle">
                      <select
                        className="input w-full min-w-0"
                        value={item.offering_id}
                        onChange={(event) =>
                          onUpdateItem(
                            index,
                            'offering_id',
                            event.target.value ? Number(event.target.value) : ''
                          )
                        }
                      >
                        <option value="">Presentación</option>
                        {offeringOptions.map((entry) => (
                          <option key={entry.id} value={entry.id}>
                            {entry.label}
                          </option>
                        ))}
                      </select>
                    </td>

                      <td className="table-cell align-middle">
                      <input
                        className="input w-full min-w-0"
                        type="number"
                        min="0"
                        step={allowsFractionalQuantity ? '0.01' : '1'}
                        value={item.quantity || ''}
                        onChange={(event) =>
                          onUpdateItem(index, 'quantity', parseQuantityInput(event.target.value, allowsFractionalQuantity))
                        }
                      />
                    </td>

                      <td className="table-cell align-middle">
                      <input
                        className="input w-full min-w-0"
                        type="number"
                        min="0"
                        step="1"
                        value={item.bonus_quantity ?? ''}
                        onChange={(event) =>
                          onUpdateItem(index, 'bonus_quantity', event.target.value === '' ? 0 : Math.round(Number(event.target.value)))
                        }
                      />
                    </td>

                      <td className="table-cell align-middle">
                      <input
                        className="input w-full min-w-0 text-right"
                        type="number"
                        min="0"
                        value={item.unit_price === undefined ? '' : item.unit_price}
                        onChange={(event) => onUpdateItem(index, 'unit_price', event.target.value === '' ? '' : Number(event.target.value))}
                      />
                    </td>

                      <td className="table-cell text-right align-middle">
                      <span className="text-sm font-semibold text-brand-red">
                        ${money(rowTotal)}
                      </span>
                    </td>

                      <td className="table-cell text-right align-middle">
                      <Button
                        variant="ghost"
                        className="px-2 py-2 text-xs text-slate-500"
                        onClick={() => onRemoveItem(index)}
                      >
                        Quitar
                      </Button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <div className="grid gap-4 p-4 lg:hidden">
          {form.items.map((item, index) => {
            const product = productsById[item.product_id]
            const offeringOptions = editingInvoiceId ? optionsWithHistoricalSelection(product?.offerings || [], item.offering_id, item.offering_label) : (product?.offerings || [])
            const offering = offeringOptions.find((entry) => String(entry.id) === String(item.offering_id))
            const allowsFractionalQuantity = isX1KgLabel(offering?.label || item.offering_label)
            const price = item.unit_price === '' || item.unit_price === undefined ? Number(offering?.price || 0) : Number(item.unit_price || 0)
            const quantity = Number(item.quantity || 0)
            const rowTotal = quantity * price
            const productOptions = editingInvoiceId ? productsWithHistoricalSelection(catalog, item.product_id, item.product_name) : catalog

            return (
              <div key={index} className="surface-muted p-4">
                <div className="grid gap-3">
                  <div>
                    <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">
                      Producto
                    </div>
                    <select
                      className="input w-full min-w-0"
                      value={item.product_id}
                      onChange={(event) =>
                        onUpdateItem(
                          index,
                          'product_id',
                          event.target.value ? Number(event.target.value) : ''
                        )
                      }
                    >
                      <option value="">Producto</option>
                      {productOptions.map((productItem) => (
                        <option key={productItem.id} value={productItem.id}>
                          {productItem.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">
                      Presentación
                    </div>
                    <select
                      className="input w-full min-w-0"
                      value={item.offering_id}
                      onChange={(event) =>
                        onUpdateItem(
                          index,
                          'offering_id',
                          event.target.value ? Number(event.target.value) : ''
                        )
                      }
                    >
                      <option value="">Presentación</option>
                      {offeringOptions.map((entry) => (
                        <option key={entry.id} value={entry.id}>
                          {entry.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">
                        Cantidad
                      </div>
                      <input
                        className="input w-full min-w-0"
                        type="number"
                        min="0"
                        step={allowsFractionalQuantity ? '0.01' : '1'}
                        value={item.quantity || ''}
                        onChange={(event) =>
                          onUpdateItem(index, 'quantity', parseQuantityInput(event.target.value, allowsFractionalQuantity))
                        }
                      />
                    </div>

                    <div>
                      <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">
                        Bonificación
                      </div>
                      <input
                        className="input w-full min-w-0"
                        type="number"
                        min="0"
                        step="1"
                        value={item.bonus_quantity ?? ''}
                        onChange={(event) =>
                          onUpdateItem(index, 'bonus_quantity', event.target.value === '' ? 0 : Math.round(Number(event.target.value)))
                        }
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">
                        Precio
                      </div>
                      <input
                        className="input w-full min-w-0 text-right"
                        type="number"
                        min="0"
                        value={item.unit_price === undefined ? '' : item.unit_price}
                        onChange={(event) => onUpdateItem(index, 'unit_price', event.target.value === '' ? '' : Number(event.target.value))}
                      />
                    </div>

                    <div className="text-right">
                      <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">
                        Total
                      </div>
                      <div className="text-sm font-semibold text-brand-red">
                        ${money(rowTotal)}
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-end">
                    <Button
                      variant="ghost"
                      className="px-2 py-2 text-xs text-slate-500"
                      onClick={() => onRemoveItem(index)}
                    >
                      Quitar
                    </Button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="mt-4">
        <Button variant="secondary" className="w-full sm:w-auto" onClick={onAddItem}>
          Agregar fila
        </Button>
      </div>

      {splitPreview?.enabled && (
        <div className="mt-6 rounded-[26px] border border-amber-200 bg-amber-50/80 p-4 sm:p-5">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="eyebrow text-amber-700">Preview de división</div>
              <h3 className="mt-1 font-semibold text-brand-ink">Cantidades internas y declaradas</h3>
            </div>
            <div className="text-sm font-semibold text-amber-800">
              {splitPreview.declaredPercentage}% declarado / resto interno
            </div>
          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="table-base min-w-[760px] bg-white/80">
              <thead className="table-head">
                <tr>
                  <th>Producto</th>
                  <th className="text-right">Total</th>
                  <th className="text-right">Interna</th>
                  <th className="text-right">Declarada</th>
                  <th className="text-right">Total interno</th>
                  <th className="text-right">Total declarado</th>
                </tr>
              </thead>
              <tbody>
                {splitPreview.rows.map((row, index) => (
                  <tr key={index} className="table-row">
                    <td className="table-cell font-medium">{row.productName} / {row.offeringLabel}</td>
                    <td className="table-cell text-right">{row.totalQuantity}</td>
                    <td className="table-cell text-right">{row.internalQuantity}</td>
                    <td className="table-cell text-right">{row.declaredQuantity}</td>
                    <td className="table-cell text-right">${money(row.internalTotal)}</td>
                    <td className="table-cell text-right">${money(row.fiscalTotal)}</td>
                  </tr>
                ))}
                {!splitPreview.rows.length && (
                  <tr>
                    <td colSpan="6" className="table-cell py-6 text-center text-slate-400">Agregá productos para ver el preview.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
            <Metric label="Bultos internos" value={splitPreview.internalQuantityTotal} />
            <Metric label="Bultos declarados" value={splitPreview.declaredQuantityTotal} />
            <Metric label="Total estimado interno" value={`$${money(splitPreview.internalTotal)}`} />
            <Metric label="Total declarado estimado" value={`$${money(splitPreview.fiscalTotal)}`} />
          </div>

          {splitPreview.warnings.length ? (
            <div className="mt-4 rounded-2xl border border-amber-300 bg-white px-4 py-3 text-sm text-amber-800">
              <div className="font-semibold">Advertencias</div>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {splitPreview.warnings.map((warning, index) => <li key={index}>{warning}</li>)}
              </ul>
            </div>
          ) : null}
        </div>
      )}

      <div className="mt-6 grid gap-3 md:grid-cols-3">
        <Metric label="Total bultos" value={money(totals.bultos)} />
        <Metric label="Subtotal" value={money(totals.subtotal)} />
        <Metric label="Total estimado" value={money(totals.total)} />
      </div>

      <div className="mt-6 flex flex-col gap-3 border-t border-stone-200 pt-5 sm:flex-row sm:flex-wrap sm:justify-start">
        <Button
          variant="primary"
          className="w-full sm:min-w-[180px] sm:w-auto"
          onClick={onGenerate}
          disabled={generating}
        >
          {generating ? 'Guardando...' : editingInvoiceId ? 'Actualizar factura' : 'Generar factura'}
        </Button>
        <Button
          variant="secondary"
          className="w-full sm:min-w-[180px] sm:w-auto"
          onClick={onClearInvoice}
          disabled={generating}
        >
          Limpiar factura
        </Button>
        {editingInvoiceId && (
          <Button variant="secondary" className="w-full sm:min-w-[180px] sm:w-auto" onClick={onCancelEdit}>
            Cancelar edición
          </Button>
        )}
      </div>
    </div>
  )
}

export default ProductRowsCard

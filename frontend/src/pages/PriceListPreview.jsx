import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { request } from '../lib/api'
import { clearPriceListPreview, loadPriceListPreview } from '../lib/priceListPreview'
import { useGranalia } from '../context/GranaliaContext'
import Button from '../components/ui/Button'

const FORMAT_ORDER = [
  '16x300 gr',
  '12x400 gr',
  '12x350 gr',
  '10x500 gr',
  '10x1 kg',
  'x 1 kg',
  'x 4 kg',
  'x 5 kg',
  'x 25 kg',
  'x 30 kg',
]

function warningKey(productId, offeringLabel = '') {
  return `${productId}::${offeringLabel}`
}

function PriceListPreview() {
  const navigate = useNavigate()
  const { setStatus, refreshAll } = useGranalia()
  const [preview, setPreview] = useState(() => loadPriceListPreview())
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  const columns = useMemo(() => {
    const labels = new Set()
    for (const product of preview?.catalog || []) {
      for (const offering of product.offerings || []) labels.add(offering.label)
    }
    return Array.from(labels).sort((a, b) => {
      const sortA = FORMAT_ORDER.indexOf(a)
      const sortB = FORMAT_ORDER.indexOf(b)
      const orderA = sortA === -1 ? FORMAT_ORDER.length : sortA
      const orderB = sortB === -1 ? FORMAT_ORDER.length : sortB
      if (orderA !== orderB) return orderA - orderB
      return a.localeCompare(b)
    })
  }, [preview])

  const warningsByCell = useMemo(() => {
    const map = new Map()
    for (const warning of preview?.warnings || []) {
      map.set(warningKey(warning.product_id, warning.offering_label || ''), warning)
    }
    return map
  }, [preview])

  if (!preview) {
    return (
      <div className="mt-8 rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
        <h1 className="text-xl font-bold text-slate-800">No hay preview cargada</h1>
        <p className="mt-2 text-sm text-slate-500">Volvé a listas de precios y generá una previsualización.</p>
        <Button className="mt-4" variant="primary" onClick={() => navigate('/management?tab=products')}>Volver</Button>
      </div>
    )
  }

  function updatePrice(productIndex, offeringIndex, value) {
    const price = Math.max(0, Number(value || 0))
    setPreview((current) => ({
      ...current,
      catalog: current.catalog.map((product, pIndex) => {
        if (pIndex !== productIndex) return product
        return {
          ...product,
          offerings: product.offerings.map((offering, oIndex) => (
            oIndex === offeringIndex ? { ...offering, price } : offering
          )),
        }
      }),
    }))
  }

  async function savePreview() {
    setSaving(true)
    setMessage('')
    try {
      const data = await request('/api/price-lists/commit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: preview.name || '',
          filename: preview.filename || 'lista-manual.pdf',
          price_list_id: preview.targetId || null,
          activate: true,
          source: preview.source || 'manual',
          catalog: preview.catalog,
        }),
      })
      clearPriceListPreview()
      setStatus('Lista de precios actualizada en la base.')
      setMessage('Lista guardada correctamente.')
      await refreshAll()
      if (data?.bootstrap) {
        window.localStorage.setItem('granalia:price-list-saved-at', new Date().toISOString())
      }
    } catch (error) {
      setMessage(`Error al guardar: ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  function closePreview() {
    clearPriceListPreview()
    navigate('/management?tab=products')
  }

  return (
    <div className="mt-6 space-y-4 print:mt-0">
      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm print:hidden md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-xl font-black text-slate-900">Previsualización de lista de precios</h1>
          <p className="text-sm text-slate-500">Editá los precios y confirmá. Los campos resaltados fueron conservados o calculados automáticamente.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" onClick={() => window.print()}>Imprimir</Button>
          <Button variant="secondary" onClick={closePreview} disabled={saving}>Cancelar</Button>
          <Button variant="primary" onClick={savePreview} disabled={saving}>{saving ? 'Guardando...' : 'Guardar lista'}</Button>
        </div>
      </div>

      {message ? <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 print:hidden">{message}</div> : null}

      {(preview.warnings || []).length ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900 print:hidden">
          <div className="font-bold uppercase tracking-[0.12em]">Advertencias</div>
          <div className="mt-2 grid gap-1 md:grid-cols-2">
            {preview.warnings.map((warning, index) => (
              <div key={`${warning.kind}-${warning.product_id}-${warning.offering_label || 'product'}-${index}`}>
                <span className="font-semibold">{warning.product_name}</span>{warning.offering_label ? ` / ${warning.offering_label}` : ''}: {warning.message}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="overflow-auto rounded-2xl border border-slate-300 bg-white shadow-sm print:rounded-none print:border-slate-700 print:shadow-none">
        <table className="min-w-full border-collapse text-xs print:text-[10px]">
          <thead>
            <tr className="bg-slate-900 text-white print:bg-white print:text-black">
              <th className="sticky left-0 z-20 min-w-60 border border-slate-300 bg-slate-900 px-3 py-3 text-left print:static print:bg-white">Producto</th>
              {columns.map((label) => (
                <th key={label} className="min-w-28 border border-slate-300 px-2 py-3 text-center font-bold">{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.catalog.map((product, productIndex) => {
              const offeringByLabel = new Map((product.offerings || []).map((offering, offeringIndex) => [offering.label, { offering, offeringIndex }]))
              const productWarning = warningsByCell.get(warningKey(product.id, ''))
              return (
                <tr key={product.id || product.name} className={productWarning ? 'bg-amber-50' : 'odd:bg-white even:bg-slate-50'} title={productWarning?.message || ''}>
                  <td className="sticky left-0 z-10 border border-slate-300 bg-inherit px-3 py-2 font-semibold text-slate-900 print:static">
                    {product.name}
                  </td>
                  {columns.map((label) => {
                    const cell = offeringByLabel.get(label)
                    const warning = cell ? warningsByCell.get(warningKey(product.id, label)) : null
                    const highlighted = productWarning || warning
                    return (
                      <td key={label} className={`border border-slate-300 px-2 py-1 text-center ${highlighted ? 'bg-amber-100' : ''}`} title={warning?.message || productWarning?.message || ''}>
                        {cell ? (
                          <input
                            className="h-8 w-24 rounded-md border border-slate-300 bg-white px-2 text-right font-mono text-xs print:border-0 print:bg-transparent print:p-0 print:text-center"
                            type="number"
                            min="0"
                            value={cell.offering.price}
                            onChange={(event) => updatePrice(productIndex, cell.offeringIndex, event.target.value)}
                          />
                        ) : (
                          <span className="text-slate-300">-</span>
                        )}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default PriceListPreview

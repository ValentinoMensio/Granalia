import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useGranalia } from '../context/GranaliaContext'
import { request } from '../lib/api'
import Button from '../components/ui/Button'
import PageSectionHeader from '../components/ui/PageSectionHeader'

const BASE_OFFERING_LABELS = [
  'x 25 kg',
  'x 30 kg',
  '12x400 gr',
  '16x300 gr',
  '12x350 gr',
  '10x500 gr',
  '10x1 kg',
  'x 4 kg',
  'x 5 kg',
]

function netWeightForLabel(label) {
  const text = String(label || '').toLowerCase().replace(/\s+/g, '')
  const packMatch = text.match(/(\d+)x(\d+(?:[.,]\d+)?)(kg|gr|g)?/)
  if (packMatch) {
    const units = Number(packMatch[1] || 0)
    const size = Number(String(packMatch[2] || 0).replace(',', '.'))
    const unit = packMatch[3] || 'gr'
    return units * (unit === 'kg' ? size : size / 1000)
  }

  const bagMatch = text.match(/x(\d+(?:[.,]\d+)?)kg/)
  if (bagMatch) return Number(String(bagMatch[1] || 0).replace(',', '.'))

  return 0
}

export default function ProductEditor() {
  const { id } = useParams()
  const productId = Number(id)
  const isNewProduct = !id || id === 'new' || Number.isNaN(productId)
  const navigate = useNavigate()
  const { bootstrap, catalog, setStatus, saving, refreshAll } = useGranalia()
  const managementPath = '/management?tab=products'
  const priceLists = bootstrap?.price_lists || []
  const activePriceListId = bootstrap?.price_list?.id ? String(bootstrap.price_list.id) : ''
  const [selectedPriceListId, setSelectedPriceListId] = useState('')
  const [selectedCatalog, setSelectedCatalog] = useState(catalog)
  const [loadingCatalog, setLoadingCatalog] = useState(false)

  const product = selectedCatalog.find((p) => String(p.id) === String(productId))
  const [formData, setFormData] = useState(null)
  const [offerings, setOfferings] = useState([])
  const availableOfferingLabels = Array.from(new Set([
    ...BASE_OFFERING_LABELS,
    ...selectedCatalog.flatMap((entry) => (entry.offerings || []).map((offering) => offering.label)),
  ])).sort()

  useEffect(() => {
    if (!selectedPriceListId && activePriceListId) {
      setSelectedPriceListId(activePriceListId)
    }
  }, [activePriceListId, selectedPriceListId])

  useEffect(() => {
    let cancelled = false

    async function loadSelectedCatalog() {
      if (!selectedPriceListId || selectedPriceListId === activePriceListId) {
        setSelectedCatalog(catalog)
        return
      }

      setLoadingCatalog(true)
      try {
        const nextCatalog = await request(`/api/price-lists/${selectedPriceListId}/catalog`)
        if (!cancelled) setSelectedCatalog(nextCatalog)
      } catch (error) {
        if (!cancelled) setStatus(`Error al cargar lista: ${error.message}`)
      } finally {
        if (!cancelled) setLoadingCatalog(false)
      }
    }

    loadSelectedCatalog()
    return () => {
      cancelled = true
    }
  }, [activePriceListId, catalog, selectedPriceListId, setStatus])

  useEffect(() => {
    if (isNewProduct) {
      setFormData({ name: '', aliases: [] })
      setOfferings([])
    } else if (product) {
      setFormData({ 
        id: product.id,
        name: product.name, 
        aliases: product.aliases || [] 
      })
      setOfferings([...product.offerings])
    }
  }, [product, isNewProduct])

  const missingSelectedProduct = !isNewProduct && !loadingCatalog && !product

  if (!isNewProduct && !product && loadingCatalog) return <div className="mt-8 p-4 text-center">Cargando catálogo...</div>
  if (!formData) return null

  async function handleSave() {
    try {
      const normalizedOfferings = offerings
        .map((off) => ({
          ...off,
          label: String(off.label || '').trim(),
          price: Number(off.price || 0),
          net_weight_kg: Number(off.net_weight_kg || 0),
        }))
        .filter((off) => off.label)

      if (!selectedPriceListId) {
        setStatus('Seleccioná una lista de precios para guardar el producto.')
        return
      }

      await request(`/api/price-lists/${selectedPriceListId}/products`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product: formData, offerings: normalizedOfferings }),
      })

      await refreshAll()
      setStatus(isNewProduct ? 'Producto creado correctamente.' : 'Producto y presentaciones actualizados.')
      navigate(managementPath)
    } catch (e) {
      setStatus(`Error al guardar: ${e.message}`)
    }
  }

  const addOffering = () => {
    setOfferings([...offerings, { label: '', price: 0, net_weight_kg: 0 }])
  }

  const updateOffering = (index, field, value) => {
    const next = [...offerings]
    const updated = { ...next[index], [field]: value }
    if (field === 'label' && !Number(updated.net_weight_kg || 0)) {
      updated.net_weight_kg = netWeightForLabel(value)
    }
    next[index] = updated
    setOfferings(next)
  }

  const removeOffering = (index) => {
    setOfferings(offerings.filter((_, i) => i !== index))
  }

  return (
    <div className="editor-shell">
      <PageSectionHeader
        title={isNewProduct ? 'Nuevo producto' : `Editar producto: ${product?.name || formData.name}`}
        description="Organizá el nombre comercial y las presentaciones con una estructura simple y consistente."
        aside={<Button variant="ghost" onClick={() => navigate(managementPath)}>Volver a gestión</Button>}
      />

      <div className="editor-card grid gap-6">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2 md:col-span-2">
            <label className="text-sm font-medium text-slate-700">Nombre Comercial</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="input"
            />
          </div>

          <div className="space-y-2 md:col-span-2">
            <label className="text-sm font-medium text-slate-700">Lista de precios</label>
            <select
              value={selectedPriceListId}
              onChange={(event) => setSelectedPriceListId(event.target.value)}
              className="input"
              disabled={!priceLists.length || loadingCatalog}
            >
              {!priceLists.length ? <option value="">Sin listas disponibles</option> : null}
              {priceLists.map((priceList) => (
                <option key={priceList.id} value={String(priceList.id)}>
                  {priceList.name}{priceList.active ? ' (activa)' : ''}
                </option>
              ))}
            </select>
            <p className="text-xs text-slate-500">
              Los cambios se guardan en esta lista. Si no está activa, no modifican el catálogo global.
            </p>
            {missingSelectedProduct ? (
              <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                Este producto no existe en la lista seleccionada. Al guardar se agregará con las presentaciones configuradas abajo.
              </p>
            ) : null}
          </div>
        </div>

        <div className="border-t pt-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="subsection-title">Presentaciones y precios</h3>
          </div>

          <div className="mobile-list">
            {offerings.map((off, i) => (
              <article key={i} className="mobile-card">
                <div className="mobile-card-kicker">Presentación {i + 1}</div>
                <div className="mt-3 grid gap-3">
                  <div>
                    <label className="field-label">Etiqueta</label>
                    <select
                      value={off.label}
                      onChange={(e) => updateOffering(i, 'label', e.target.value)}
                      className="input"
                    >
                      <option value="">Seleccionar etiqueta</option>
                      {availableOfferingLabels.map((label) => (
                        <option key={label} value={label}>{label}</option>
                      ))}
                      {off.label && !availableOfferingLabels.includes(off.label) ? (
                        <option value={off.label}>{off.label}</option>
                      ) : null}
                    </select>
                  </div>
                  <div>
                    <label className="field-label">Peso neto por bulto (kg)</label>
                    <input
                      type="number"
                      min="0"
                      step="0.001"
                      value={off.net_weight_kg || ''}
                      onChange={(e) => updateOffering(i, 'net_weight_kg', e.target.value)}
                      className="input text-right"
                    />
                  </div>
                  <div>
                    <label className="field-label">Precio</label>
                    <input
                      type="number"
                      value={off.price}
                      onChange={(e) => updateOffering(i, 'price', e.target.value)}
                      className="input text-right"
                    />
                  </div>
                  <Button variant="danger" className="w-full" onClick={() => removeOffering(i)}>
                    Eliminar presentación
                  </Button>
                </div>
              </article>
            ))}
            {offerings.length === 0 && (
              <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm italic text-slate-400">
                No hay presentaciones configuradas para este producto.
              </div>
            )}
          </div>

          <div className="table-shell hidden lg:block">
            <table className="table-base">
              <thead className="table-head">
                <tr>
                  <th>Etiqueta</th>
                  <th>Peso neto kg</th>
                  <th>Precio</th>
                  <th className="text-right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {offerings.map((off, i) => (
                  <tr key={i} className="table-row">
                    <td className="table-cell">
                      <select
                        value={off.label}
                        onChange={(e) => updateOffering(i, 'label', e.target.value)}
                        className="input py-1.5 text-xs"
                      >
                        <option value="">Seleccionar etiqueta</option>
                        {availableOfferingLabels.map((label) => (
                          <option key={label} value={label}>{label}</option>
                        ))}
                        {off.label && !availableOfferingLabels.includes(off.label) ? (
                          <option value={off.label}>{off.label}</option>
                        ) : null}
                      </select>
                    </td>
                    <td className="table-cell">
                      <input
                        type="number"
                        min="0"
                        step="0.001"
                        value={off.net_weight_kg || ''}
                        onChange={(e) => updateOffering(i, 'net_weight_kg', e.target.value)}
                        className="input py-1.5 text-right text-xs"
                      />
                    </td>
                    <td className="table-cell">
                      <input
                        type="number"
                        value={off.price}
                        onChange={(e) => updateOffering(i, 'price', e.target.value)}
                        className="input py-1.5 text-right text-xs"
                      />
                    </td>
                    <td className="table-cell text-right">
                      <Button variant="danger" onClick={() => removeOffering(i)}>
                        Eliminar
                      </Button>
                    </td>
                  </tr>
                ))}
                {offerings.length === 0 && (
                  <tr>
                    <td colSpan="4" className="table-cell py-8 text-center text-slate-400 italic">
                      No hay presentaciones configuradas para este producto.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div>
            <Button variant="secondary" className="w-full text-xs sm:w-auto" onClick={addOffering}>
              Agregar presentación
            </Button>
          </div>
        </div>

        <div className="flex flex-col gap-3 pt-6 border-t sm:flex-row sm:justify-end">
          <Button variant="secondary" className="w-full sm:w-auto" onClick={() => navigate(managementPath)}>
            Cancelar
          </Button>
          <Button variant="primary" className="w-full sm:w-auto" onClick={handleSave} disabled={saving}>
            {saving ? 'Guardando...' : 'Guardar Cambios'}
          </Button>
        </div>
      </div>
    </div>
  )
}

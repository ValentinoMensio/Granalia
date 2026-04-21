import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useGranalia } from '../context/GranaliaContext'
import { request } from '../lib/api'
import Button from '../components/ui/Button'
import PageSectionHeader from '../components/ui/PageSectionHeader'

export default function ProductEditor() {
  const { id } = useParams()
  const productId = Number(id)
  const isNewProduct = !id || id === 'new' || Number.isNaN(productId)
  const navigate = useNavigate()
  const { catalog, setStatus, saving, refreshAll } = useGranalia()
  
  const product = catalog.find((p) => p.id === productId)
  const [formData, setFormData] = useState(null)
  const [offerings, setOfferings] = useState([])
  const availableOfferingLabels = Array.from(new Set(catalog.flatMap((entry) => (entry.offerings || []).map((offering) => offering.label)))).sort()

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

  if (!isNewProduct && !product) return <div className="mt-8 p-4 text-center">Producto no encontrado.</div>
  if (!formData) return null

  async function handleSave() {
    try {
      const normalizedOfferings = offerings
        .map((off) => ({
          ...off,
          label: String(off.label || '').trim(),
          price: Number(off.price || 0),
        }))
        .filter((off) => off.label)

      // 1. Save basic product info
      const savedProduct = await request('/api/products', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      })

      // 2. Save offerings
      const targetProductId = isNewProduct ? savedProduct.id : product?.id
      if (targetProductId) {
        await request(`/api/products/${targetProductId}/offerings`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(normalizedOfferings),
        })
      }

      await refreshAll()
      setStatus(isNewProduct ? 'Producto creado correctamente.' : 'Producto y presentaciones actualizados.')
      navigate('/management')
    } catch (e) {
      setStatus(`Error al guardar: ${e.message}`)
    }
  }

  const addOffering = () => {
    setOfferings([...offerings, { label: '', price: 0 }])
  }

  const updateOffering = (index, field, value) => {
    const next = [...offerings]
    next[index] = { ...next[index], [field]: value }
    setOfferings(next)
  }

  const removeOffering = (index) => {
    setOfferings(offerings.filter((_, i) => i !== index))
  }

  return (
    <div className="editor-shell">
      <PageSectionHeader
        title={isNewProduct ? 'Nuevo producto' : `Editar producto: ${product.name}`}
        description="Organizá el nombre comercial y las presentaciones con una estructura simple y consistente."
        aside={<Button variant="ghost" onClick={() => navigate('/management')}>Volver a gestión</Button>}
      />

      <div className="editor-card grid gap-6">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2 md:col-span-2">
            <label className="text-sm font-medium text-slate-700">Nombre Comercial</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-red/20 focus:border-brand-red"
            />
          </div>
        </div>

        <div className="border-t pt-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="subsection-title">Presentaciones y precios</h3>
          </div>

          <div className="table-shell">
            <table className="table-base">
              <thead className="table-head">
                <tr>
                  <th>Etiqueta</th>
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
                        className="w-full rounded border border-slate-300 px-2 py-1 text-xs focus:outline-none focus:border-brand-red"
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
                        value={off.price}
                        onChange={(e) => updateOffering(i, 'price', e.target.value)}
                        className="w-full rounded border border-slate-300 px-2 py-1 text-xs text-right focus:outline-none focus:border-brand-red"
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
                    <td colSpan="3" className="table-cell py-8 text-center text-slate-400 italic">
                      No hay presentaciones configuradas para este producto.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div>
            <Button variant="secondary" className="text-xs" onClick={addOffering}>
              Agregar presentación
            </Button>
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-6 border-t">
          <Button variant="secondary" onClick={() => navigate('/management')}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={handleSave} disabled={saving}>
            {saving ? 'Guardando...' : 'Guardar Cambios'}
          </Button>
        </div>
      </div>
    </div>
  )
}

import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useGranalia } from '../context/GranaliaContext'
import { request } from '../lib/api'
import { discountKeyForLabel } from '../lib/format'
import Button from '../components/ui/Button'
import PageSectionHeader from '../components/ui/PageSectionHeader'
import AutomaticBonusRules from '../components/invoices/AutomaticBonusRules'

export default function CustomerEditor() {
  const { id } = useParams()
  const customerId = Number(id)
  const isNewCustomer = !id || id === 'new' || Number.isNaN(customerId)
  const navigate = useNavigate()
  const { customers, bootstrap, catalog, updateCustomer, saving, refreshAll, setStatus } = useGranalia()
  const managementPath = '/management?tab=customers'
  
  const customer = customers.find((c) => c.id === customerId)
  const [formData, setFormData] = useState(null)

  useEffect(() => {
    if (isNewCustomer) {
      setFormData({
        name: '',
        secondary_line: '',
        transport: '',
        notes: [],
        footer_discounts: [],
        line_discounts_by_format: {},
        automatic_bonus_rules: [],
        automatic_bonus_disables_line_discount: false,
        source_count: 0,
      })
    } else if (customer) {
      setFormData({ ...customer })
    }
  }, [customer, isNewCustomer])

  if (!isNewCustomer && !customer) return <div className="mt-8 p-4 text-center">Cliente no encontrado.</div>
  if (!formData) return null

  const availableDiscountGroups = Array.from(
    new Set(catalog.flatMap((p) => p.offerings.map((o) => discountKeyForLabel(o.label))))
  ).sort()

  async function handleSave() {
    try {
      const { id: _customerId, created_at, updated_at, ...payload } = formData

      if (isNewCustomer) {
        await request('/api/customers', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
      } else {
        await updateCustomer(customerId, payload)
      }
      await refreshAll()
      navigate(managementPath)
    } catch (e) {
      setStatus(`No se pudo guardar el cliente: ${e.message}`)
    }
  }

  const addFooterDiscount = () => {
    setFormData({
      ...formData,
      footer_discounts: [...(formData.footer_discounts || []), { label: 'Nuevo Dto', rate: 0 }]
    })
  }

  const updateFooterDiscount = (index, field, value) => {
    const next = [...formData.footer_discounts]
    next[index] = { ...next[index], [field]: field === 'rate' ? Number(value) / 100 : value }
    setFormData({ ...formData, footer_discounts: next })
  }

  const removeFooterDiscount = (index) => {
    setFormData({
      ...formData,
      footer_discounts: formData.footer_discounts.filter((_, i) => i !== index)
    })
  }

  const updateLineDiscount = (group, rate) => {
    const next = { ...formData.line_discounts_by_format }
    next[group] = Number(rate) / 100
    setFormData({ ...formData, line_discounts_by_format: next })
  }

  const addAutomaticBonusRule = () => {
    setFormData({
      ...formData,
      automatic_bonus_rules: [
        ...(formData.automatic_bonus_rules || []),
        { product_id: null, offering_id: null, offering_label: '', buy_quantity: 10, bonus_quantity: 1 },
      ],
    })
  }

  const updateAutomaticBonusRule = (index, field, value) => {
    const next = [...(formData.automatic_bonus_rules || [])]
    const nextValue = ['product_id', 'offering_id'].includes(field)
      ? (value === '' ? null : Number(value))
      : field === 'offering_label'
      ? value
      : Number(value || 0)
    next[index] = { ...next[index], [field]: nextValue }
    if (field === 'product_id') {
      next[index].offering_id = null
      next[index].offering_label = ''
    }
    setFormData({ ...formData, automatic_bonus_rules: next })
  }

  const removeAutomaticBonusRule = (index) => {
    setFormData({
      ...formData,
      automatic_bonus_rules: (formData.automatic_bonus_rules || []).filter((_, i) => i !== index),
    })
  }

  return (
    <div className="editor-shell">
      <PageSectionHeader
        eyebrow="Ficha comercial"
        title={isNewCustomer ? 'Nuevo cliente' : `Editar cliente: ${customer.name}`}
        description="Definí transporte, notas y reglas de descuento con un esquema simple y consistente."
        aside={<Button variant="ghost" onClick={() => navigate(managementPath)}>Volver a gestión</Button>}
      />

      <div className="editor-card grid gap-6">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-700">Nombre</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="input"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-700">Línea Secundaria</label>
            <input
              type="text"
              value={formData.secondary_line}
              onChange={(e) => setFormData({ ...formData, secondary_line: e.target.value })}
              className="input"
            />
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-700">Transporte</label>
          <select
            value={formData.transport}
            onChange={(e) => setFormData({ ...formData, transport: e.target.value })}
            className="input"
          >
            <option value="">Sin transporte</option>
            {bootstrap?.transports.map((t) => (
              <option key={t.transport_id} value={t.name}>{t.name}</option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-700">Notas</label>
          <textarea
            rows={3}
            value={formData.notes.join('\\n')}
            onChange={(e) => setFormData({ ...formData, notes: e.target.value.split('\\n').filter(Boolean) })}
            className="input"
          />
        </div>

        <div className="border-t pt-6 space-y-8">
          <h3 className="subsection-title">Configuración de precios y descuentos</h3>
          
          <div className="grid gap-8 md:grid-cols-2">
            {/* Footer Discounts */}
              <div className="space-y-4">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <label className="text-sm font-medium text-slate-700">Descuentos Globales (al pie)</label>
                <Button variant="ghost" className="px-0 py-0 text-xs text-brand-red" onClick={addFooterDiscount}>
                  + Agregar
                </Button>
              </div>
              <div className="space-y-2">
                {(formData.footer_discounts || []).map((disc, i) => (
                  <div key={i} className="grid grid-cols-[minmax(0,1fr)_5rem_auto] items-center gap-2">
                    <input
                      type="text"
                      value={disc.label}
                      onChange={(e) => updateFooterDiscount(i, 'label', e.target.value)}
                      placeholder="Ej: Mayorista"
                      className="input flex-1 py-1.5 text-xs"
                    />
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        value={disc.rate * 100}
                        onChange={(e) => updateFooterDiscount(i, 'rate', e.target.value)}
                        className="input w-16 py-1.5 text-right text-xs"
                      />
                      <span className="text-xs text-slate-400">%</span>
                    </div>
                    <button 
                      onClick={() => removeFooterDiscount(i)}
                      className="text-slate-300 hover:text-red-500"
                    >
                      ✕
                    </button>
                  </div>
                ))}
                {(!formData.footer_discounts || formData.footer_discounts.length === 0) && (
                  <p className="text-xs text-slate-400 italic">No hay descuentos globales configurados.</p>
                )}
              </div>
            </div>

            {/* Line Discounts */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-slate-700">Descuentos por Grupo (línea)</label>
              </div>
              <div className="max-h-64 overflow-y-auto space-y-2 pr-2">
                {availableDiscountGroups.map((group) => (
                  <div key={group} className="flex items-center justify-between p-2 rounded-lg bg-slate-50 border border-slate-100">
                    <span className="text-xs font-medium text-slate-600">{group}</span>
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        value={(formData.line_discounts_by_format?.[group] || 0) * 100}
                        onChange={(e) => updateLineDiscount(group, e.target.value)}
                        className="input w-14 px-1 py-0.5 text-right text-xs"
                      />
                      <span className="text-xs text-slate-400">%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="border-t pt-6">
            <AutomaticBonusRules
              rules={formData.automatic_bonus_rules}
              disablesLineDiscount={formData.automatic_bonus_disables_line_discount}
              catalog={catalog}
              onAdd={addAutomaticBonusRule}
              onChange={updateAutomaticBonusRule}
              onRemove={removeAutomaticBonusRule}
              onDisablesLineDiscountChange={(value) => setFormData({ ...formData, automatic_bonus_disables_line_discount: value })}
            />
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

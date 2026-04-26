import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useGranalia } from '../context/GranaliaContext'
import { request } from '../lib/api'
import Button from '../components/ui/Button'
import PageSectionHeader from '../components/ui/PageSectionHeader'

export default function TransportEditor() {
  const { id } = useParams()
  const transportId = Number(id)
  const isNewTransport = !id || id === 'new' || Number.isNaN(transportId)
  const navigate = useNavigate()
  const { bootstrap, setStatus, saving, refreshAll } = useGranalia()
  const managementPath = '/management?tab=transports'
  
  const transport = bootstrap?.transports.find((t) => t.transport_id === transportId)
  const [formData, setFormData] = useState(null)

  useEffect(() => {
    if (isNewTransport) {
      setFormData({ name: '', notes: [] })
    } else if (transport) {
      setFormData({ ...transport })
    }
  }, [transport, isNewTransport])

  if (!isNewTransport && !transport) return <div className="mt-8 p-4 text-center">Transporte no encontrado.</div>
  if (!formData) return null

  async function handleSave() {
    try {
      await request(isNewTransport ? '/api/transports' : `/api/transports/${id}`, {
        method: isNewTransport ? 'POST' : 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formData.name,
          notes: formData.notes || [],
        }),
      })
      await refreshAll()
      setStatus('Transporte actualizado correctamente.')
      navigate(managementPath)
    } catch (e) {
      setStatus(`Error al guardar: ${e.message}`)
    }
  }

  return (
    <div className="editor-shell max-w-3xl">
      <PageSectionHeader
        title={isNewTransport ? 'Nuevo transporte' : 'Editar transporte'}
        description="Mantené el nombre y las observaciones de transporte con el mismo criterio visual del resto del sistema."
        aside={<Button variant="ghost" onClick={() => navigate(managementPath)}>Volver a gestión</Button>}
      />

      <div className="editor-card grid gap-6">
        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-700">Nombre del Transporte</label>
          <input
            type="text"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            className="input"
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-700">Notas / Observaciones</label>
          <textarea
            rows={4}
            value={formData.notes?.join('\\n') || ''}
            onChange={(e) => setFormData({ ...formData, notes: e.target.value.split('\\n').filter(Boolean) })}
            className="input"
          />
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

import Panel from '../ui/Panel'
import Button from '../ui/Button'

function PriceListPanel({ bootstrap, uploading, onFileChange, onUpload }) {
  return (
    <Panel title="Lista de precios">
      <input className="input" type="file" accept="application/pdf" onChange={(event) => onFileChange(event.target.files?.[0] || null)} />
      <Button variant="secondary" className="mt-4 w-full justify-center" onClick={onUpload} disabled={uploading}>
        {uploading ? 'Procesando...' : 'Subir PDF y actualizar base'}
      </Button>
      <div className="mt-4 rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-brand-ink/70">
        Activa: <span className="font-medium text-brand-ink">{bootstrap?.price_list?.filename || 'Sin lista cargada'}</span>
      </div>
    </Panel>
  )
}

export default PriceListPanel

import Panel from '../ui/Panel'
import Button from '../ui/Button'

function PriceListPanel({ bootstrap, uploading, onFileChange, onUpload }) {
  return (
    <Panel title="Lista de precios">
      <input className="input file:mr-3 file:rounded-lg file:border-0 file:bg-brand-red file:px-3 file:py-2 file:text-sm file:font-medium file:text-white file:cursor-pointer" type="file" accept="application/pdf" onChange={(event) => onFileChange(event.target.files?.[0] || null)} />
      <Button variant="primary" className="mt-3 w-full justify-center" onClick={onUpload} disabled={uploading}>
        {uploading ? 'Procesando...' : 'Subir PDF y actualizar base'}
      </Button>
      <div className="mt-3 text-xs text-slate-500">
        Activa: <span className="font-medium text-slate-700">{bootstrap?.price_list?.filename || 'Sin lista cargada'}</span>
      </div>
    </Panel>
  )
}

export default PriceListPanel

import Panel from '../ui/Panel'
import Button from '../ui/Button'

function PriceListPanel({ bootstrap, priceListUploadName, priceListUploadTargetId, uploading, onDelete, onRename, onFileChange, onUpload, onUploadNameChange, onUploadTargetChange }) {
  return (
    <Panel title="Lista de precios">
      <input className="input text-xs file:mr-3 file:rounded-lg file:border-0 file:bg-brand-red file:px-3 file:py-2 file:text-sm file:font-medium file:text-white file:cursor-pointer sm:text-sm" type="file" accept="application/pdf" onChange={(event) => onFileChange(event.target.files?.[0] || null)} />
      <label className="mt-3 block text-xs font-bold uppercase tracking-[0.12em] text-slate-400">
        Reemplazar lista
      </label>
      <select className="input mt-1" value={priceListUploadTargetId} onChange={(event) => onUploadTargetChange(event.target.value)}>
        <option value="">Crear nueva lista</option>
        {(bootstrap?.price_lists || []).map((priceList) => (
          <option key={priceList.id} value={priceList.id}>Reemplazar: {priceList.name}</option>
        ))}
      </select>
      <label className="mt-3 block text-xs font-bold uppercase tracking-[0.12em] text-slate-400">
        Nombre de lista
      </label>
      <input
        className="input mt-1"
        value={priceListUploadName}
        onChange={(event) => onUploadNameChange(event.target.value)}
        placeholder={priceListUploadTargetId ? 'Mantener nombre actual' : 'Ej: Mayorista Abril'}
      />
      <Button variant="primary" className="mt-3 w-full justify-center" onClick={onUpload} disabled={uploading}>
        {uploading ? 'Procesando...' : priceListUploadTargetId ? 'Subir PDF y reemplazar lista' : 'Subir PDF y crear lista'}
      </Button>
      <div className="mt-3 text-xs text-slate-500">
        Activa: <span className="font-medium text-slate-700">{bootstrap?.price_list?.name || bootstrap?.price_list?.filename || 'Sin lista cargada'}</span>
      </div>
      <div className="mt-3 space-y-1 text-xs text-slate-500">
        <div className="font-bold uppercase tracking-[0.12em] text-slate-400">Listas</div>
        {(bootstrap?.price_lists || []).map((priceList) => (
          <div key={priceList.id} className="flex items-center gap-3">
            <span className="min-w-0 truncate text-slate-700">{priceList.name}</span>
            <div className="flex shrink-0 items-center gap-4">
              {priceList.active ? <span className="font-semibold text-brand-red">Activa</span> : null}
              <button
                type="button"
                className="font-semibold text-slate-600 hover:text-slate-900"
                onClick={() => onRename(priceList)}
              >
                Renombrar
              </button>
              <button
                type="button"
                className="font-semibold text-red-600 hover:text-red-700"
                onClick={() => onDelete(priceList)}
              >
                Eliminar
              </button>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  )
}

export default PriceListPanel

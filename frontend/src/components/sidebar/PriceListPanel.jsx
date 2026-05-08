import Panel from '../ui/Panel'
import Button from '../ui/Button'

function formatDate(value) {
  const text = String(value || '').trim()
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (match) return `${match[3]}-${match[2]}-${match[1]}`
  return text || '-'
}

function PriceListPanel({ bootstrap, priceListUploadName, priceListUploadTargetId, uploading, onActivate, onDelete, onRename, onFileChange, onUpload, onUploadNameChange, onUploadTargetChange }) {
  const versions = bootstrap?.price_list_versions || []
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
          <div key={priceList.id} className="flex items-center gap-10">
            <span className="min-w-0 truncate text-slate-700">{priceList.name}</span>
            <div className="flex shrink-0 items-center gap-4">
              {priceList.active ? <span className="font-semibold text-brand-red">Activa</span> : null}
              {!priceList.active && (
                <button
                  type="button"
                  className="font-semibold text-blue-700 hover:text-blue-900"
                  onClick={() => onActivate(priceList)}
                >
                  Predeterminada
                </button>
              )}
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
      <div className="mt-5 space-y-2 border-t border-slate-200 pt-4 text-xs text-slate-500">
        <div className="font-bold uppercase tracking-[0.12em] text-slate-400">Historial de PDFs</div>
        {versions.length === 0 && (
          <div className="rounded-xl border border-dashed border-slate-200 px-3 py-2 text-slate-400">Sin cargas registradas.</div>
        )}
        {versions.length > 0 && (
          <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
            {versions.map((version) => (
              <div key={version.id} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="flex items-center justify-between gap-3">
                  <span className="min-w-0 truncate font-semibold text-slate-700">{version.name}</span>
                  <span className="shrink-0 text-slate-400">v{version.version_number}</span>
                </div>
                <div className="mt-1 truncate text-slate-500">{version.filename}</div>
                <div className="mt-1 flex items-center justify-between gap-3 font-mono text-[11px] text-slate-400">
                  <span>{formatDate(version.uploaded_at)}</span>
                  <span>{String(version.pdf_sha256 || '').slice(0, 10)}</span>
                </div>
              </div>
            ))}
            </div>
        )}
      </div>
    </Panel>
  )
}

export default PriceListPanel

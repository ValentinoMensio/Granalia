import Panel from '../ui/Panel'
import Button from '../ui/Button'

function formatDate(value) {
  const text = String(value || '').trim()
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (match) return `${match[3]}-${match[2]}-${match[1]}`
  return text || '-'
}

function PriceListPanel({ bootstrap, priceListUploadName, priceListUploadTargetId, uploading, onActivate, onDelete, onRename, onFileChange, onUploadNameChange, onUploadTargetChange, onUpload, onManual }) {
  const versions = bootstrap?.price_list_versions || []
  const priceLists = bootstrap?.price_lists || []
  const selectedPriceList = priceLists.find((priceList) => String(priceList.id) === String(priceListUploadTargetId || ''))

  return (
    <Panel title="Lista de precios">
      <div className="mb-3 flex items-center gap-3 text-xs font-bold uppercase tracking-[0.12em] text-blue-700">
        <span className="h-px flex-1 bg-blue-200" />
        Carga manual
        <span className="h-px flex-1 bg-blue-200" />
      </div>
      <div className="space-y-3 rounded-2xl border border-blue-100 bg-blue-50/50 p-3">
        <div>
          <label className="field-label">Destino de la lista</label>
          <select className="input" value={priceListUploadTargetId || ''} onChange={(event) => onUploadTargetChange(event.target.value)}>
            <option value="">Crear lista nueva</option>
            {priceLists.map((priceList) => (
              <option key={priceList.id} value={priceList.id}>Actualizar: {priceList.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="field-label">Nombre de lista</label>
          <input
            className="input"
            value={priceListUploadName || ''}
            onChange={(event) => onUploadNameChange(event.target.value)}
            placeholder={selectedPriceList ? `Mantener: ${selectedPriceList.name}` : 'Ej: Mayorista Abril'}
          />
          <p className="mt-1 text-xs text-slate-500">
            {selectedPriceList ? 'Completalo solo si querés cambiar el nombre de la lista seleccionada.' : 'Si lo dejás vacío, se usará el nombre del archivo o Lista manual.'}
          </p>
        </div>
      </div>
      <Button variant="primary" className="mt-3 w-full justify-center" onClick={onManual} disabled={uploading}>
        Cargar precios manualmente
      </Button>

      <div className="my-5 flex items-center gap-3 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">
        <span className="h-px flex-1 bg-slate-200" />
        Carga PDF
        <span className="h-px flex-1 bg-slate-200" />
      </div>

      <label className="block text-xs font-bold uppercase tracking-[0.12em] text-slate-400">
        Carga desde archivo
      </label>
      <input className="input mt-1 text-xs file:mr-3 file:rounded-lg file:border-0 file:bg-brand-red file:px-3 file:py-2 file:text-sm file:font-medium file:text-white file:cursor-pointer sm:text-sm" type="file" accept="application/pdf" onChange={(event) => onFileChange(event.target.files?.[0] || null)} />

      <Button variant="primary" className="mt-3 w-full justify-center" onClick={onUpload} disabled={uploading}>
        {uploading ? 'Procesando...' : 'Previsualizar PDF'}
      </Button>
      <div className="mt-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
        La previsualización se abre en esta misma pestaña con formato de tabla para revisar, editar e imprimir antes de guardar.
      </div>
      <div className="mt-3 text-xs text-slate-500">
        Activa: <span className="font-medium text-slate-700">{bootstrap?.price_list?.name || bootstrap?.price_list?.filename || 'Sin lista cargada'}</span>
      </div>
      <div className="mt-3 space-y-1 text-xs text-slate-500">
        <div className="font-bold uppercase tracking-[0.12em] text-slate-400">Listas</div>
        {priceLists.map((priceList) => (
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

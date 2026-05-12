import Panel from '../ui/Panel'
import Button from '../ui/Button'

function formatDate(value) {
  const text = String(value || '').trim()
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (match) return `${match[3]}-${match[2]}-${match[1]}`
  return text || '-'
}

function PriceListPanel({ bootstrap, priceListUploadName, priceListUploadTargetId, preview, uploading, onActivate, onDelete, onRename, onFileChange, onUpload, onManual, onUploadNameChange, onUploadTargetChange, onPreviewPriceChange, onCancelPreview, onCommitPreview }) {
  const versions = bootstrap?.price_list_versions || []
  const warnings = preview?.warnings || []

  function warningFor(product, offering) {
    return warnings.find((warning) => (
      String(warning.product_id) === String(product.id) &&
      (offering ? (!warning.offering_label || warning.offering_label === offering.label) : !warning.offering_label)
    ))
  }

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
        {uploading ? 'Procesando...' : 'Previsualizar PDF'}
      </Button>
      <Button variant="secondary" className="mt-2 w-full justify-center" onClick={onManual} disabled={uploading}>
        Cargar precios manualmente
      </Button>
      {preview ? (
        <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="text-sm font-bold text-amber-900">Preview editable</div>
              <div className="text-xs text-amber-800">Los productos o presentaciones ausentes del PDF se conservan y quedan resaltados.</div>
            </div>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={onCancelPreview} disabled={uploading}>Cancelar</Button>
              <Button variant="primary" onClick={onCommitPreview} disabled={uploading}>Guardar lista</Button>
            </div>
          </div>
          {warnings.length > 0 ? (
            <div className="mt-3 max-h-28 space-y-1 overflow-y-auto text-xs text-amber-800">
              {warnings.map((warning, index) => (
                <div key={`${warning.kind}-${warning.product_id}-${warning.offering_label || 'product'}-${index}`}>
                  <span className="font-semibold">{warning.product_name}</span>{warning.offering_label ? ` / ${warning.offering_label}` : ''}: {warning.message}
                </div>
              ))}
            </div>
          ) : null}
          <div className="mt-4 max-h-[34rem] overflow-auto rounded-xl border border-amber-200 bg-white">
            <table className="min-w-full text-xs">
              <thead className="sticky top-0 bg-slate-100 text-left uppercase tracking-[0.08em] text-slate-500">
                <tr>
                  <th className="px-3 py-2">Producto</th>
                  <th className="px-3 py-2">Presentación</th>
                  <th className="px-3 py-2">Precio</th>
                </tr>
              </thead>
              <tbody>
                {(preview.catalog || []).flatMap((product, productIndex) => {
                  const productWarning = warningFor(product)
                  return (product.offerings || []).map((offering, offeringIndex) => {
                    const offeringWarning = warningFor(product, offering)
                    const highlighted = productWarning || offeringWarning
                    return (
                      <tr key={`${product.id}-${offering.id || offering.label}-${offeringIndex}`} className={highlighted ? 'bg-amber-50' : ''} title={offeringWarning?.message || productWarning?.message || ''}>
                        <td className="border-t border-slate-100 px-3 py-2 font-medium text-slate-700">{product.name}</td>
                        <td className="border-t border-slate-100 px-3 py-2 text-slate-600">{offering.label}</td>
                        <td className="border-t border-slate-100 px-3 py-2">
                          <input
                            className="input h-9 w-28 text-right"
                            type="number"
                            min="0"
                            value={offering.price}
                            onChange={(event) => onPreviewPriceChange(productIndex, offeringIndex, event.target.value)}
                          />
                        </td>
                      </tr>
                    )
                  })
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
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

const PRICE_LIST_PREVIEW_STORAGE_KEY = 'granalia:price-list-preview'

function savePriceListPreview(payload) {
  window.localStorage.setItem(PRICE_LIST_PREVIEW_STORAGE_KEY, JSON.stringify(payload))
}

function loadPriceListPreview() {
  const raw = window.localStorage.getItem(PRICE_LIST_PREVIEW_STORAGE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function clearPriceListPreview() {
  window.localStorage.removeItem(PRICE_LIST_PREVIEW_STORAGE_KEY)
}

function openPriceListPreviewTab(previewWindow = null) {
  const url = `${window.location.origin}/price-list-preview`
  if (previewWindow && !previewWindow.closed) {
    previewWindow.location.href = url
    previewWindow.focus()
    return true
  }
  return Boolean(window.open(url, '_blank'))
}

export { clearPriceListPreview, loadPriceListPreview, openPriceListPreviewTab, savePriceListPreview }

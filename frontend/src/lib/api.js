const API_BASE = import.meta.env.VITE_API_URL || (window.location.port === '5173' ? `${window.location.protocol}//${window.location.hostname}:8000` : '')
const CSRF_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

let csrfToken = ''

function setCsrfToken(token) {
  csrfToken = token || ''
}

function formatErrorDetail(detail) {
  if (Array.isArray(detail)) {
    return detail
      .map((entry) => {
        if (typeof entry === 'string') return entry
        if (entry && typeof entry === 'object') {
          const location = Array.isArray(entry.loc) ? entry.loc.join(' > ') : ''
          const message = entry.msg || entry.message || JSON.stringify(entry)
          return location ? `${location}: ${message}` : message
        }
        return String(entry)
      })
      .join(' | ')
  }

  if (detail && typeof detail === 'object') {
    return detail.message || JSON.stringify(detail)
  }

  return String(detail || 'Error')
}

async function request(path, options = {}) {
  const method = String(options.method || 'GET').toUpperCase()
  const headers = new Headers(options.headers || {})

  if (csrfToken && CSRF_METHODS.has(method) && !headers.has('X-CSRF-Token')) {
    headers.set('X-CSRF-Token', csrfToken)
  }

  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...options,
    headers,
  })
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/api/auth/')) {
      window.dispatchEvent(new CustomEvent('granalia:unauthorized'))
    }
    let error = 'Error'
    try {
      const raw = await response.text()
      try {
        const data = JSON.parse(raw)
        error = formatErrorDetail(data.detail || data.error || error)
      } catch {
        error = raw || error
      }
    } catch {
      error = error
    }
    throw new Error(error)
  }
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return response.json()
  }
  return response
}

export { API_BASE, request, setCsrfToken }

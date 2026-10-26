// URL base del backend. Configurable en build time con VITE_API_URL.
export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000')
  .replace(/\/+$/, '')

const TIMEOUT_MS = 30000

async function request(path, options = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    return await fetch(`${API_URL}${path}`, { ...options, signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}

/** GET /health — comprueba que la API responde y que el modelo está cargado. */
export async function checkHealth() {
  const response = await request('/health', {
    method: 'GET',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new Error(`La API respondió con el estado HTTP ${response.status}.`)
  }
  return response.json()
}

/**
 * POST /score — contrato real del backend:
 *   entrada: los 13 campos numéricos del dataset
 *   salida:  { "score": number }
 */
export async function predict(values) {
  let response
  try {
    response = await request('/score', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(values),
    })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('La solicitud tardó demasiado y se canceló. Inténtalo de nuevo.')
    }
    throw new Error(
      'No se pudo contactar con la API. Revisa que el backend esté en línea y que ' +
      `VITE_API_URL (${API_URL}) sea correcta.`,
    )
  }

  if (response.status === 422) {
    const detail = await response.json().catch(() => null)
    const campos = detail?.detail?.map((d) => d.loc?.slice(-1)[0]).filter(Boolean)
    throw new Error(
      campos?.length
        ? `La API rechazó los datos. Revisa estos campos: ${[...new Set(campos)].join(', ')}.`
        : 'La API rechazó los datos enviados por no cumplir las validaciones.',
    )
  }

  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(
      detail?.detail
        ? `Error del servidor: ${detail.detail}`
        : `La API respondió con el estado HTTP ${response.status}.`,
    )
  }

  const data = await response.json()
  if (typeof data?.score !== 'number') {
    throw new Error('La respuesta de la API no contiene un campo "score" numérico.')
  }
  return data
}

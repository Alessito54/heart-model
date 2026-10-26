// Resolucion de la URL del backend.
//
// Modo A (por defecto): un solo backend que sirve las tres versiones.
//   VITE_API_URL=https://heart-model-api.onrender.com
//   -> POST {API_URL}/score?version=25
//
// Modo B: un despliegue de Render por version (una imagen por etiqueta).
//   VITE_API_URL_25=https://heart-model-25.onrender.com
//   VITE_API_URL_50=...   VITE_API_URL_100=...
//   -> POST {API_URL_25}/score   (sin parametro de version)
//
// Si hay URLs por version definidas se usa el modo B; si no, el modo A.

const clean = (value) => (value || '').trim().replace(/\/+$/, '')

export const API_URL = clean(import.meta.env.VITE_API_URL) || 'http://localhost:8000'

const PER_VERSION_URLS = Object.fromEntries(
  Object.entries({
    25: clean(import.meta.env.VITE_API_URL_25),
    50: clean(import.meta.env.VITE_API_URL_50),
    100: clean(import.meta.env.VITE_API_URL_100),
  }).filter(([, url]) => url !== ''),
)

export const MULTI_DEPLOY = Object.keys(PER_VERSION_URLS).length > 0

/** URL base que atiende una version concreta. */
export function baseUrlFor(version) {
  if (version != null && PER_VERSION_URLS[version]) return PER_VERSION_URLS[version]
  return API_URL
}

/** Lista de versiones conocidas por configuración, antes de consultar la API. */
export const CONFIGURED_VERSIONS = Object.keys(PER_VERSION_URLS).sort(
  (a, b) => Number(a) - Number(b),
)

const TIMEOUT_MS = 30000

async function request(url, options = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}

function networkError(url) {
  return new Error(
    'No se pudo contactar con la API. Revisa que el backend esté en línea y que ' +
    `la URL configurada (${url}) sea correcta.`,
  )
}

/** GET /health — comprueba que la API responde y que el modelo está cargado. */
export async function checkHealth(version = null) {
  const base = baseUrlFor(version)
  const response = await request(`${base}/health`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new Error(`La API respondió con el estado HTTP ${response.status}.`)
  }
  return response.json()
}

/**
 * GET /models — versiones servidas por el backend, con sus métricas.
 * Devuelve [] si el backend es una versión antigua que no expone el endpoint.
 */
export async function listModels(version = null) {
  const base = baseUrlFor(version)
  let response
  try {
    response = await request(`${base}/models`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
  } catch {
    throw networkError(base)
  }
  if (response.status === 404) return []
  if (!response.ok) {
    throw new Error(`La API respondió con el estado HTTP ${response.status}.`)
  }
  const data = await response.json()
  return Array.isArray(data) ? data : []
}

/**
 * POST /score — contrato real del backend:
 *   entrada: los 13 campos numéricos del dataset
 *   salida:  { "score": number, "version": string }
 *
 * En modo A la versión viaja como parámetro de consulta; en modo B está
 * implícita en la URL del despliegue.
 */
export async function predict(values, version = null) {
  const base = baseUrlFor(version)
  const useQuery = version != null && !PER_VERSION_URLS[version]
  const url = `${base}/score${useQuery ? `?version=${encodeURIComponent(version)}` : ''}`

  let response
  try {
    response = await request(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(values),
    })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('La solicitud tardó demasiado y se canceló. Inténtalo de nuevo.')
    }
    throw networkError(base)
  }

  if (response.status === 404) {
    const detail = await response.json().catch(() => null)
    throw new Error(
      detail?.detail ||
      `El backend no sirve la versión ${version}% del modelo.`,
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
  return { score: data.score, version: data.version ?? version ?? null, url }
}

/** Ejecuta el mismo payload contra todas las versiones indicadas. */
export async function predictAll(values, versions) {
  const results = await Promise.allSettled(
    versions.map((v) => predict(values, v)),
  )
  return versions.map((version, i) => {
    const r = results[i]
    return r.status === 'fulfilled'
      ? { version, ...r.value }
      : { version, error: r.reason?.message || 'Error desconocido' }
  })
}

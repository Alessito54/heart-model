// Cliente de la API de incidencia delictiva.
//
// Un solo backend sirve las tres versiones del modelo y se elige con el
// parametro de consulta ?version=25|50|100:
//   VITE_API_URL=https://incidencia-api.onrender.com
//   -> POST {API_URL}/predict?version=25

const clean = (value) => (value || '').trim().replace(/\/+$/, '')

export const API_URL = clean(import.meta.env.VITE_API_URL) || 'http://localhost:8000'

// El plan gratuito de Render duerme el servicio tras ~15 min sin trafico y la
// primera peticion puede tardar 30-60 s en responder. Con un limite de 30 s el
// arranque en frio se abortaba y la interfaz quedaba en 'API no disponible'.
export const COLD_START_MS = 75000
const TIMEOUT_MS = COLD_START_MS

async function request(url, options = {}, timeout = TIMEOUT_MS) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}

function networkError() {
  return new Error(
    'No se pudo contactar con la API. Revisa que el backend esté en línea y que ' +
    `la URL configurada (${API_URL}) sea correcta.`,
  )
}

/**
 * Traduce una respuesta no-OK al mensaje de error mas util que haya.
 * El error lleva .status con el codigo HTTP, para poder distinguir casos
 * concretos (por ejemplo, un 404 de /catalog = backend desactualizado).
 */
async function readError(response, fallback) {
  const detail = await response.json().catch(() => null)
  let mensaje
  if (response.status === 422 && Array.isArray(detail?.detail)) {
    const campos = detail.detail.map((d) => d.loc?.slice(-1)[0]).filter(Boolean)
    mensaje = campos.length
      ? `La API rechazó los datos. Revisa estos campos: ${[...new Set(campos)].join(', ')}.`
      : 'La API rechazó los datos enviados por no cumplir las validaciones.'
  } else if (typeof detail?.detail === 'string') {
    mensaje = detail.detail
  } else {
    mensaje = fallback || `La API respondió con el estado HTTP ${response.status}.`
  }
  const error = new Error(mensaje)
  error.status = response.status
  return error
}

async function getJson(path, { headers = {}, timeout = COLD_START_MS } = {}) {
  let response
  try {
    response = await request(`${API_URL}${path}`, {
      method: 'GET',
      headers: { Accept: 'application/json', ...headers },
    }, timeout)
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('La solicitud se canceló por tiempo.')
    throw networkError()
  }
  if (!response.ok) throw await readError(response)
  return response.json()
}

/** GET /health — comprueba que la API responde y que el modelo está cargado. */
export const checkHealth = () => getJson('/health')

/** GET /catalog — valores válidos de cada campo y la jerarquía del delito. */
export const getCatalog = () => getJson('/catalog')

/**
 * GET /models — las tres versiones del modelo, con sus métricas de regresión.
 * Devuelve [] si el backend es una versión antigua que no expone el endpoint.
 */
export async function listModels() {
  const data = await getJson('/models').catch((error) => {
    if (/404/.test(error.message)) return []
    throw error
  })
  return Array.isArray(data) ? data : []
}

/**
 * POST /predict — contrato real del backend:
 *   entrada: anio, mes, clave_ent y los cuatro niveles del delito
 *   salida:  { prediccion, prediccion_redondeada, version, label, entidad, periodo }
 */
export async function predict(values, version = null) {
  const url = `${API_URL}/predict${version != null ? `?version=${encodeURIComponent(version)}` : ''}`

  let response
  try {
    response = await request(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(values),
    })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error(
        'La solicitud tardó más de 75 s y se canceló. Si el backend está en el ' +
        'plan gratuito de Render puede estar despertando: vuelve a intentarlo.',
      )
    }
    throw networkError()
  }

  if (response.status === 404) {
    throw await readError(response, `El backend no sirve la versión ${version} % del modelo.`)
  }
  if (!response.ok) throw await readError(response)

  const data = await response.json()
  if (typeof data?.prediccion !== 'number') {
    throw new Error('La respuesta de la API no contiene un campo "prediccion" numérico.')
  }
  return { ...data, version: data.version ?? version ?? null, url }
}

/** Ejecuta el mismo payload contra todas las versiones indicadas. */
export async function predictAll(values, versions) {
  const results = await Promise.allSettled(versions.map((v) => predict(values, v)))
  return versions.map((version, i) => {
    const r = results[i]
    return r.status === 'fulfilled'
      ? { version, ...r.value }
      : { version, error: r.reason?.message || 'Error desconocido' }
  })
}

/**
 * POST /retrain — dispara el workflow de GitHub Actions, que reentrena las tres
 * versiones y publica una imagen de Docker nueva etiquetada con "tag".
 *
 * Requiere la cabecera X-Retrain-Token: el backend deja el endpoint
 * deshabilitado si no se configuro un token, para que nadie pueda lanzar
 * construcciones de imagenes desde fuera.
 */
export async function retrain(body, token) {
  let response
  try {
    response = await request(`${API_URL}/retrain`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-Retrain-Token': token || '',
      },
      body: JSON.stringify(body),
    }, 40000)
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('La solicitud de reentrenamiento se canceló por tiempo.')
    throw networkError()
  }
  if (!response.ok) throw await readError(response)
  return response.json()
}

/** GET /retrain/status — últimas corridas del workflow de reentrenamiento. */
export const retrainStatus = (token) =>
  getJson('/retrain/status', { headers: { 'X-Retrain-Token': token || '' }, timeout: 30000 })

import { useEffect, useState } from 'react'
import { retrain, retrainStatus } from './api.js'

// URLs publicas de los datasets en Cloudinary (solo lectura: son archivos
// 'raw/upload'). Se precargan para que reentrenar sea un clic, y se pueden
// sustituir por otras para entrenar con datos nuevos.
const CLOUDINARY = {
  dataseturl_25: 'https://res.cloudinary.com/dvkzq6c8a/raw/upload/v1793196213/incidencia_25_hmvvv6.csv',
  dataseturl_50: 'https://res.cloudinary.com/dvkzq6c8a/raw/upload/v1793196216/incidencia_50_hbf5b7.csv',
  dataseturl_100: 'https://res.cloudinary.com/dvkzq6c8a/raw/upload/v1793196218/incidencia_100_owtcfa.csv',
}

const URL_FIELDS = [
  { name: 'dataseturl_25', label: 'Dataset 25 %' },
  { name: 'dataseturl_50', label: 'Dataset 50 %' },
  { name: 'dataseturl_100', label: 'Dataset 100 %' },
]

// El token puede recordarse en este navegador (localStorage, sobrevive al
// cierre de la pestana) o solo durante la sesion (sessionStorage). Nunca se
// pone en una variable VITE_*: esas quedan incrustadas en el JavaScript
// publico, donde cualquiera podria leer el token y lanzar construcciones.
const TOKEN_KEY = 'retrain-token'
const REMEMBER_KEY = 'retrain-token-remember'

// Cada acceso va en try/catch: en modo privado o con el almacenamiento
// bloqueado, leer o escribir lanza una excepcion.
const safeGet = (store, key) => {
  try {
    return store.getItem(key)
  } catch {
    return null
  }
}

const readRemember = () => safeGet(localStorage, REMEMBER_KEY) !== 'no'

const readToken = () =>
  safeGet(localStorage, TOKEN_KEY) || safeGet(sessionStorage, TOKEN_KEY) || ''

/** Guarda el token donde corresponda y limpia el otro almacen. */
function persistToken(token, remember) {
  const destino = remember ? localStorage : sessionStorage
  const otro = remember ? sessionStorage : localStorage
  try {
    otro.removeItem(TOKEN_KEY)
    localStorage.setItem(REMEMBER_KEY, remember ? 'si' : 'no')
    if (token) destino.setItem(TOKEN_KEY, token)
    else destino.removeItem(TOKEN_KEY)
  } catch { /* almacenamiento no disponible: seguir sin guardar */ }
}

const RUN_LABEL = {
  queued: 'En cola', in_progress: 'En ejecución', completed: 'Terminada',
  waiting: 'Esperando', requested: 'Solicitada', pending: 'Pendiente',
}
const CONCLUSION_LABEL = {
  success: 'correcta', failure: 'falló', cancelled: 'cancelada',
  skipped: 'omitida', timed_out: 'expiró', action_required: 'requiere acción',
}

export default function RetrainPanel({ health, onDone }) {
  const [token, setToken] = useState(readToken)
  const [remember, setRemember] = useState(readRemember)
  const [urls, setUrls] = useState(CLOUDINARY)
  const [tag, setTag] = useState('')
  const [nota, setNota] = useState('')
  const [sending, setSending] = useState(false)
  const [launched, setLaunched] = useState(null)
  const [error, setError] = useState(null)
  const [runs, setRuns] = useState(null)
  const [loadingRuns, setLoadingRuns] = useState(false)

  const enabled = health?.retrain_enabled === true

  useEffect(() => { persistToken(token, remember) }, [token, remember])

  async function loadRuns() {
    setLoadingRuns(true)
    setError(null)
    try {
      const data = await retrainStatus(token)
      setRuns(data.runs || [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoadingRuns(false)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setLaunched(null)

    const definidas = URL_FIELDS.map((f) => urls[f.name]?.trim()).filter(Boolean)
    if (definidas.length > 0 && definidas.length !== 3) {
      setError('Indica las tres URLs de dataset, o deja las tres vacías para usar ' +
               'las que tiene configuradas el workflow.')
      return
    }

    setSending(true)
    try {
      const body = {}
      if (definidas.length === 3) {
        for (const f of URL_FIELDS) body[f.name] = urls[f.name].trim()
      }
      if (tag.trim()) body.tag = tag.trim()
      if (nota.trim()) body.nota = nota.trim()

      const data = await retrain(body, token.trim())
      setLaunched(data)
      // El workflow tarda varios minutos; se consulta el estado enseguida para
      // que la corrida aparezca en la lista, y luego se refresca a mano.
      loadRuns()
      onDone?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setSending(false)
    }
  }

  return (
    <section className="card retrain-card" aria-labelledby="retrain-title">
      <div className="card-head">
        <h2 id="retrain-title">Reentrenar el modelo</h2>
        <span className={`pill${enabled ? ' pill-ok' : ' pill-off'}`}>
          {enabled ? 'disponible' : 'no configurado'}
        </span>
      </div>

      <p className="help">
        Lanza el workflow de GitHub Actions: descarga los datasets, entrena las
        tres versiones (25&nbsp;%, 50&nbsp;% y 100&nbsp;%), corre las pruebas y
        publica <strong>una imagen de Docker nueva</strong> etiquetada con la
        etiqueta de abajo. El entrenamiento no ocurre en este servidor, así que la
        API sigue respondiendo con el modelo actual hasta que redespliegues con la
        imagen nueva.
      </p>

      {!enabled && (
        <div className="alert alert-info" role="status">
          <strong>El reentrenamiento está deshabilitado en este despliegue</strong>
          <p>
            Para activarlo, define en el servicio del backend las variables de
            entorno <code>RETRAIN_TOKEN</code> (el token que se escribe aquí),
            <code> GITHUB_TOKEN</code> (con permiso de escritura en{' '}
            <em>contents</em>) y <code>GITHUB_REPOSITORY</code> (formato{' '}
            <code>usuario/repo</code>). Sin <code>RETRAIN_TOKEN</code> el endpoint
            queda cerrado a propósito: si estuviera abierto, cualquiera podría
            lanzar construcciones de imágenes.
          </p>
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <div className="grid">
          <div className="field field-wide">
            <label htmlFor="retrain-token">Token de reentrenamiento</label>
            <input
              id="retrain-token" type="password" autoComplete="off"
              placeholder="el valor de RETRAIN_TOKEN del backend"
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
            {token !== token.trim() && (
              <p className="help">
                El token tiene espacios al principio o al final. Se ignoran al
                enviarlo.
              </p>
            )}
            <label className="compare compare-inline">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
              />
              <span>Recordar en este navegador</span>
            </label>
            <p className="help">
              Se envía en la cabecera <code>X-Retrain-Token</code>. Es el valor de
              la variable <code>RETRAIN_TOKEN</code> del backend, no la clave de
              Cloudinary ni la de GitHub. Si marcas la casilla queda guardado en
              este navegador; si no, se olvida al cerrar la pestaña. No lo pongas
              en una variable <code>VITE_*</code>: esas quedan incrustadas en el
              JavaScript público.
            </p>
          </div>

          <div className="field">
            <label htmlFor="retrain-tag">Etiqueta de la imagen</label>
            <input
              id="retrain-tag" type="text" placeholder="se genera automáticamente"
              value={tag}
              onChange={(e) => setTag(e.target.value)}
            />
            <p className="help">
              Si la dejas vacía se usa <code>retrain-AAAAMMDD-HHMMSS</code>.
            </p>
          </div>

          <div className="field">
            <label htmlFor="retrain-nota">Nota</label>
            <input
              id="retrain-nota" type="text" maxLength={200}
              placeholder="opcional, para identificar la corrida"
              value={nota}
              onChange={(e) => setNota(e.target.value)}
            />
            <p className="help">Viaja en el payload del workflow.</p>
          </div>
        </div>

        <details className="retrain-datasets">
          <summary>Datasets de entrenamiento (Cloudinary)</summary>
          <p className="help">
            Las tres versiones ya codificadas, con la columna <code>id_delito</code>.
            Cámbialas para entrenar con datos nuevos; déjalas tal cual para repetir
            el entrenamiento con los actuales.
          </p>
          <div className="grid">
            {URL_FIELDS.map(({ name, label }) => (
              <div className="field field-wide" key={name}>
                <label htmlFor={name}>{label}</label>
                <input
                  id={name} type="url" value={urls[name]}
                  onChange={(e) => setUrls((prev) => ({ ...prev, [name]: e.target.value }))}
                />
              </div>
            ))}
          </div>
          <button type="button" className="btn-ghost"
                  onClick={() => setUrls(CLOUDINARY)}>
            Restablecer URLs
          </button>
        </details>

        <div className="actions">
          <button type="submit" className="btn-primary" disabled={sending || !enabled}>
            {sending
              ? (<><span className="spinner" aria-hidden="true" /> Lanzando…</>)
              : 'Reentrenar y publicar imagen'}
          </button>
          <button type="button" className="btn-ghost"
                  onClick={loadRuns} disabled={!enabled || loadingRuns}>
            {loadingRuns ? 'Consultando…' : 'Ver últimas corridas'}
          </button>
        </div>
      </form>

      {error && (
        <div className="alert" role="alert">
          <strong>No se pudo lanzar el reentrenamiento</strong>
          <p>{error}</p>
        </div>
      )}

      {launched && (
        <div className="alert alert-ok" role="status">
          <strong>Reentrenamiento lanzado</strong>
          <p>
            Etiqueta de la imagen: <code>{launched.tag}</code>. Datasets:{' '}
            {launched.datasets?.join(', ')}.{' '}
            <a href={launched.actions_url} target="_blank" rel="noreferrer">
              Seguir el progreso en GitHub Actions
            </a>
            . Cuando termine, apunta el servicio de Render a esa etiqueta (o a{' '}
            <code>latest</code>) y redespliega.
          </p>
        </div>
      )}

      {runs && (
        <>
          <p className="mono-label">Últimas corridas del workflow</p>
          {runs.length === 0 ? (
            <p className="help">Todavía no hay corridas registradas.</p>
          ) : (
            <table className="compare-table runs-table">
              <thead>
                <tr>
                  <th scope="col">Estado</th>
                  <th scope="col">Evento</th>
                  <th scope="col">Fecha</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <a href={run.url} target="_blank" rel="noreferrer">
                        {RUN_LABEL[run.status] || run.status}
                        {run.conclusion && ` · ${CONCLUSION_LABEL[run.conclusion] || run.conclusion}`}
                      </a>
                    </td>
                    <td>{run.event}</td>
                    <td>
                      {run.created_at
                        ? new Date(run.created_at).toLocaleString('es-MX')
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  )
}

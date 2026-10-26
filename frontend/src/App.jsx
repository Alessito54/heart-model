import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  API_URL, CONFIGURED_VERSIONS, MULTI_DEPLOY,
  baseUrlFor, checkHealth, listModels, predict, predictAll,
} from './api.js'
import { DEFAULT_VALUES, EXAMPLES, FIELDS } from './fields.js'

const STATUS_LABEL = {
  checking: 'Comprobando conexión…',
  online: 'API en línea',
  offline: 'API no disponible',
}

const VERSION_LABEL = {
  25: '25 % del dataset',
  50: '50 % del dataset',
  100: '100 % del dataset',
}

const labelFor = (v) => VERSION_LABEL[v] || `Versión ${v}`

/** Valida un campo contra los mismos límites que aplica el backend. */
function validateField(field, raw) {
  const text = String(raw ?? '').trim()
  if (text === '') return 'Este campo es obligatorio.'
  const value = Number(text)
  if (Number.isNaN(value)) return 'Introduce un número válido.'
  if (!field.decimal && !Number.isInteger(value)) return 'Debe ser un número entero.'
  if (value < field.min) return `El valor mínimo es ${field.min}.`
  if (value > field.max) return `El valor máximo es ${field.max}.`
  return null
}

export default function App() {
  const [values, setValues] = useState(DEFAULT_VALUES)
  const [errors, setErrors] = useState({})
  const [status, setStatus] = useState('checking')
  const [models, setModels] = useState([])
  const [version, setVersion] = useState(null)
  const [compareAll, setCompareAll] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [comparison, setComparison] = useState(null)
  const [apiError, setApiError] = useState(null)

  const versions = useMemo(() => models.map((m) => m.version), [models])

  /** Descubre qué versiones sirve el despliegue. */
  const refreshHealth = useCallback(async () => {
    setStatus('checking')
    try {
      if (MULTI_DEPLOY) {
        // Un backend por versión: se consulta cada uno por separado.
        const found = await Promise.allSettled(
          CONFIGURED_VERSIONS.map(async (v) => {
            const [health, list] = await Promise.all([checkHealth(v), listModels(v)])
            const info = list.find((m) => m.is_default) || list[0] || {}
            return { version: v, ...info, version_label: v, health }
          }),
        )
        const ok = found.filter((r) => r.status === 'fulfilled').map((r) => r.value)
        if (ok.length === 0) throw new Error('ningún backend respondió')
        setModels(ok.map((m) => ({ ...m, version: m.version_label })))
        setVersion((prev) => (prev && ok.some((m) => m.version_label === prev)
          ? prev : ok[ok.length - 1].version_label))
      } else {
        const [health, list] = await Promise.all([checkHealth(), listModels()])
        const resolved = list.length > 0
          ? list
          : (health.model_versions || ['default']).map((v) => ({
              version: v, is_default: v === health.default_version, path: health.model_path,
            }))
        setModels(resolved)
        const fallback = resolved.find((m) => m.is_default) || resolved[resolved.length - 1]
        setVersion((prev) => (prev && resolved.some((m) => m.version === prev)
          ? prev : fallback?.version ?? null))
      }
      setStatus('online')
    } catch {
      setModels([])
      setStatus('offline')
    }
  }, [])

  useEffect(() => { refreshHealth() }, [refreshHealth])

  function handleChange(field, raw) {
    setValues((prev) => ({ ...prev, [field.name]: raw }))
    setErrors((prev) => ({ ...prev, [field.name]: validateField(field, raw) }))
  }

  function clearOutput() {
    setResult(null)
    setComparison(null)
    setApiError(null)
  }

  function applyExample(example) {
    setValues(Object.fromEntries(
      Object.entries(example.values).map(([k, v]) => [k, String(v)]),
    ))
    setErrors({})
    clearOutput()
  }

  function resetForm() {
    setValues(DEFAULT_VALUES)
    setErrors({})
    clearOutput()
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setApiError(null)

    const nextErrors = {}
    for (const field of FIELDS) {
      const message = validateField(field, values[field.name])
      if (message) nextErrors[field.name] = message
    }
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) {
      setResult(null)
      setComparison(null)
      setApiError('Corrige los campos marcados antes de ejecutar la predicción.')
      return
    }

    const payload = Object.fromEntries(
      FIELDS.map((f) => [f.name, f.decimal ? Number(values[f.name]) : parseInt(values[f.name], 10)]),
    )

    setLoading(true)
    setResult(null)
    setComparison(null)
    try {
      if (compareAll && versions.length > 1) {
        const rows = await predictAll(payload, versions)
        if (rows.every((r) => r.error)) throw new Error(rows[0].error)
        setComparison({ rows, payload })
      } else {
        const data = await predict(payload, version)
        setResult({ ...data, payload })
      }
      setStatus('online')
    } catch (error) {
      setApiError(error.message)
      if (/no se pudo contactar/i.test(error.message)) setStatus('offline')
    } finally {
      setLoading(false)
    }
  }

  const selected = models.find((m) => m.version === version)
  const canCompare = versions.length > 1

  return (
    <div className="page">
      <header className="header">
        <div className="header-inner">
          <div>
            <p className="eyebrow">MLOps · GitHub Actions · FastAPI</p>
            <h1>Predicción de enfermedad cardíaca</h1>
            <p className="lede">
              Interfaz de prueba del modelo <code>heart-disease</code>, un clasificador
              Random&nbsp;Forest entrenado con el conjunto de datos UCI Heart Disease.
              Puedes enviar el mismo paciente a las versiones entrenadas con el
              25&nbsp;%, 50&nbsp;% y 100&nbsp;% del dataset y comparar sus salidas.
            </p>
          </div>
          <div className={`status status-${status}`} role="status" aria-live="polite">
            <span className="status-dot" aria-hidden="true" />
            <div className="status-text">
              <strong>{STATUS_LABEL[status]}</strong>
              <span className="status-url">
                {MULTI_DEPLOY ? `${CONFIGURED_VERSIONS.length} despliegues` : API_URL}
              </span>
              {status === 'online' && versions.length > 0 && (
                <span className="status-url">
                  versiones: {versions.map((v) => `${v}%`).join(' · ')}
                </span>
              )}
            </div>
            <button type="button" className="btn-ghost" onClick={refreshHealth}>
              Reintentar
            </button>
          </div>
        </div>
      </header>

      <main className="layout">
        <section className="card" aria-labelledby="form-title">
          <div className="card-head">
            <h2 id="form-title">Datos del paciente</h2>
            <div className="examples">
              {EXAMPLES.map((example) => (
                <button key={example.id} type="button" className="btn-ghost"
                        onClick={() => applyExample(example)}>
                  {example.label.split(' (')[0]}
                </button>
              ))}
              <button type="button" className="btn-ghost" onClick={resetForm}>
                Restablecer
              </button>
            </div>
          </div>

          <form onSubmit={handleSubmit} noValidate>
            <fieldset className="versions">
              <legend>Versión del modelo</legend>
              {status === 'offline' && (
                <p className="help">
                  No se pudo consultar el backend, por lo que no se conocen las
                  versiones disponibles.
                </p>
              )}
              {status === 'online' && versions.length === 0 && (
                <p className="help">El backend no reportó ninguna versión.</p>
              )}
              <div className="version-options">
                {models.map((m) => (
                  <label
                    key={m.version}
                    className={`version-option${version === m.version && !compareAll ? ' is-active' : ''}${compareAll ? ' is-disabled' : ''}`}
                  >
                    <input
                      type="radio"
                      name="model-version"
                      value={m.version}
                      checked={version === m.version}
                      disabled={compareAll}
                      onChange={() => { setVersion(m.version); clearOutput() }}
                    />
                    <span className="version-main">
                      {labelFor(m.version)}
                      {m.is_default && !MULTI_DEPLOY && <span className="pill">por defecto</span>}
                    </span>
                    <span className="version-meta">
                      {m.n_rows != null ? `${m.n_rows} registros` : 'registros n/d'}
                      {m.accuracy != null && ` · accuracy ${m.accuracy.toFixed(4)}`}
                    </span>
                  </label>
                ))}
              </div>

              {canCompare && (
                <label className="compare">
                  <input
                    type="checkbox"
                    checked={compareAll}
                    onChange={(e) => { setCompareAll(e.target.checked); clearOutput() }}
                  />
                  <span>
                    Comparar las {versions.length} versiones con el mismo paciente
                  </span>
                </label>
              )}
            </fieldset>

            <div className="grid">
              {FIELDS.map((field) => {
                const error = errors[field.name]
                const describedBy = `${field.name}-help${error ? ` ${field.name}-error` : ''}`
                return (
                  <div className="field" key={field.name}>
                    <label htmlFor={field.name}>
                      {field.label}
                      {field.unit && <span className="unit"> ({field.unit})</span>}
                    </label>

                    {field.type === 'select' ? (
                      <select
                        id={field.name}
                        name={field.name}
                        value={values[field.name]}
                        aria-describedby={describedBy}
                        aria-invalid={Boolean(error)}
                        onChange={(e) => handleChange(field, e.target.value)}
                      >
                        {field.options.map((option) => (
                          <option key={option.value} value={String(option.value)}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        id={field.name}
                        name={field.name}
                        type="number"
                        inputMode={field.decimal ? 'decimal' : 'numeric'}
                        min={field.min}
                        max={field.max}
                        step={field.step}
                        value={values[field.name]}
                        aria-describedby={describedBy}
                        aria-invalid={Boolean(error)}
                        onChange={(e) => handleChange(field, e.target.value)}
                      />
                    )}

                    <p className="help" id={`${field.name}-help`}>{field.help}</p>
                    {error && (
                      <p className="error" id={`${field.name}-error`} role="alert">{error}</p>
                    )}
                  </div>
                )
              })}
            </div>

            <div className="actions">
              <button type="submit" className="btn-primary"
                      disabled={loading || status !== 'online' || versions.length === 0}>
                {loading ? (<><span className="spinner" aria-hidden="true" /> Calculando…</>)
                         : compareAll ? 'Comparar versiones' : 'Ejecutar predicción'}
              </button>
              <span className="actions-note">
                {compareAll
                  ? `Se enviará el mismo payload a ${versions.length} versiones`
                  : <>Se enviará <code>POST {baseUrlFor(version)}/score
                      {!MULTI_DEPLOY && version ? `?version=${version}` : ''}</code></>}
              </span>
            </div>
          </form>
        </section>

        <aside className="side">
          <section className="card result-card" aria-labelledby="result-title" aria-live="polite">
            <h2 id="result-title">Resultado</h2>

            {loading && (
              <div className="placeholder">
                <span className="spinner spinner-lg" aria-hidden="true" />
                <p>Consultando el modelo…</p>
              </div>
            )}

            {!loading && apiError && (
              <div className="alert" role="alert">
                <strong>No se pudo obtener la predicción</strong>
                <p>{apiError}</p>
              </div>
            )}

            {!loading && !apiError && !result && !comparison && (
              <p className="placeholder-text">
                Completa el formulario y pulsa <em>Ejecutar predicción</em> para ver la
                salida real del modelo.
              </p>
            )}

            {!loading && result && (
              <>
                <p className="score-label">
                  Salida del modelo · campo <code>score</code> · versión{' '}
                  <strong>{labelFor(result.version)}</strong>
                </p>
                <p className="score">{result.score.toFixed(6)}</p>
                <p className="score-note">
                  Corresponde a <code>predict_proba</code> de la clase&nbsp;1
                  («presencia de enfermedad») del clasificador Random&nbsp;Forest. Es la
                  proporción de árboles del bosque que votan por esa clase, no un riesgo
                  clínico calibrado.
                </p>
                <details>
                  <summary>Ver el JSON enviado y recibido</summary>
                  <p className="mono-label">Petición · {result.url}</p>
                  <pre>{JSON.stringify(result.payload, null, 2)}</pre>
                  <p className="mono-label">Respuesta</p>
                  <pre>{JSON.stringify({ score: result.score, version: result.version }, null, 2)}</pre>
                </details>
              </>
            )}

            {!loading && comparison && (
              <>
                <p className="score-label">
                  Mismo paciente, {comparison.rows.length} versiones del modelo
                </p>
                <table className="compare-table">
                  <caption className="sr-only">
                    Salida del campo score por versión del dataset
                  </caption>
                  <thead>
                    <tr><th scope="col">Versión</th><th scope="col">score</th></tr>
                  </thead>
                  <tbody>
                    {comparison.rows.map((row) => (
                      <tr key={row.version}>
                        <th scope="row">{row.version}%</th>
                        <td>
                          {row.error
                            ? <span className="cell-error">{row.error}</span>
                            : row.score.toFixed(6)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="score-note">
                  Las diferencias entre filas provienen únicamente del tamaño del
                  conjunto de entrenamiento. No indican cuál versión es «mejor»: para
                  eso están las métricas de cada modelo en el selector.
                </p>
                <details>
                  <summary>Ver el JSON enviado y recibido</summary>
                  <p className="mono-label">Petición (idéntica para todas las versiones)</p>
                  <pre>{JSON.stringify(comparison.payload, null, 2)}</pre>
                  <p className="mono-label">Respuestas</p>
                  <pre>{JSON.stringify(
                    comparison.rows.map(({ version, score, error }) =>
                      error ? { version, error } : { version, score }), null, 2)}</pre>
                </details>
              </>
            )}
          </section>

          <section className="card info-card" aria-labelledby="info-title">
            <h2 id="info-title">Sobre el modelo</h2>
            <dl>
              <dt>Qué hace</dt>
              <dd>
                Un <code>RandomForestClassifier</code> (10 árboles, profundidad máxima 2)
                entrenado sobre el conjunto UCI Heart Disease con 13 variables.
                Devuelve un único valor <code>score</code> entre 0 y 1.
              </dd>
              <dt>Las tres versiones</dt>
              <dd>
                Cada versión es un modelo independiente, entrenado con el 25&nbsp;%,
                50&nbsp;% o 100&nbsp;% de los registros (muestreo estratificado, que
                conserva la proporción de la etiqueta). Comparten el mismo
                preprocesado y los mismos hiperparámetros, así que la única
                diferencia es el volumen de datos de entrenamiento.
              </dd>
              <dt>Cómo se entrena</dt>
              <dd>
                <code>model/train.py</code> se ejecuta en GitHub Actions. Los datasets
                pueden sustituirse en cada ejecución mediante
                <code>client_payload</code>, y la imagen resultante se etiqueta con el
                <code>sha</code> recibido.
              </dd>
              <dt>Limitaciones</dt>
              <dd>
                No es un dispositivo médico ni sustituye un diagnóstico profesional. El
                conjunto de datos es pequeño, antiguo y contiene registros duplicados; el
                modelo no está calibrado, por lo que <code>score</code> no debe leerse como
                una probabilidad clínica ni como un porcentaje de riesgo.
              </dd>
              <dt>API</dt>
              <dd>
                <code>GET /health</code> · <code>GET /models</code> ·{' '}
                <code>POST /score</code> ·{' '}
                <a href={`${baseUrlFor(version)}/docs`} target="_blank" rel="noreferrer">
                  documentación interactiva
                </a>
                {selected?.path && <> · artefacto <code>{selected.path}</code></>}
              </dd>
            </dl>
          </section>
        </aside>
      </main>

      <footer className="footer">
        <p>
          Práctica de MLOps — reentrenamiento de un modelo con GitHub Actions.
          Uso académico y demostrativo únicamente.
        </p>
      </footer>
    </div>
  )
}

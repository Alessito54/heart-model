import { useCallback, useEffect, useState } from 'react'
import { API_URL, checkHealth, predict } from './api.js'
import { DEFAULT_VALUES, EXAMPLES, FIELDS } from './fields.js'

const STATUS_LABEL = {
  checking: 'Comprobando conexión…',
  online: 'API en línea',
  offline: 'API no disponible',
}

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
  const [healthInfo, setHealthInfo] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [apiError, setApiError] = useState(null)

  const refreshHealth = useCallback(async () => {
    setStatus('checking')
    try {
      const info = await checkHealth()
      setHealthInfo(info)
      setStatus('online')
    } catch {
      setHealthInfo(null)
      setStatus('offline')
    }
  }, [])

  useEffect(() => { refreshHealth() }, [refreshHealth])

  function handleChange(field, raw) {
    setValues((prev) => ({ ...prev, [field.name]: raw }))
    setErrors((prev) => ({ ...prev, [field.name]: validateField(field, raw) }))
  }

  function applyExample(example) {
    const next = Object.fromEntries(
      Object.entries(example.values).map(([k, v]) => [k, String(v)]),
    )
    setValues(next)
    setErrors({})
    setResult(null)
    setApiError(null)
  }

  function resetForm() {
    setValues(DEFAULT_VALUES)
    setErrors({})
    setResult(null)
    setApiError(null)
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
      setApiError('Corrige los campos marcados antes de ejecutar la predicción.')
      return
    }

    const payload = Object.fromEntries(
      FIELDS.map((f) => [f.name, f.decimal ? Number(values[f.name]) : parseInt(values[f.name], 10)]),
    )

    setLoading(true)
    setResult(null)
    try {
      const data = await predict(payload)
      setResult({ score: data.score, payload })
      setStatus('online')
    } catch (error) {
      setApiError(error.message)
      if (/no se pudo contactar/i.test(error.message)) setStatus('offline')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <header className="header">
        <div className="header-inner">
          <div>
            <p className="eyebrow">MLOps · GitHub Actions · FastAPI</p>
            <h1>Predicción de enfermedad cardíaca</h1>
            <p className="lede">
              Interfaz de prueba del modelo <code>heart-disease-v1</code>, un clasificador
              Random&nbsp;Forest entrenado con el conjunto de datos UCI Heart Disease.
              Introduce las 13 variables clínicas y la API devolverá la salida del modelo.
            </p>
          </div>
          <div className={`status status-${status}`} role="status" aria-live="polite">
            <span className="status-dot" aria-hidden="true" />
            <div className="status-text">
              <strong>{STATUS_LABEL[status]}</strong>
              <span className="status-url">{API_URL}</span>
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
              <button type="submit" className="btn-primary" disabled={loading}>
                {loading ? (<><span className="spinner" aria-hidden="true" /> Calculando…</>)
                         : 'Ejecutar predicción'}
              </button>
              <span className="actions-note">
                Se enviará <code>POST {API_URL}/score</code>
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

            {!loading && !apiError && !result && (
              <p className="placeholder-text">
                Completa el formulario y pulsa <em>Ejecutar predicción</em> para ver la
                salida real del modelo.
              </p>
            )}

            {!loading && result && (
              <>
                <p className="score-label">
                  Salida del modelo · campo <code>score</code>
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
                  <p className="mono-label">Petición</p>
                  <pre>{JSON.stringify(result.payload, null, 2)}</pre>
                  <p className="mono-label">Respuesta</p>
                  <pre>{JSON.stringify({ score: result.score }, null, 2)}</pre>
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
                entrenado sobre el conjunto UCI Heart Disease (1025 registros, 13 variables).
                Devuelve un único valor <code>score</code> entre 0 y 1.
              </dd>
              <dt>Cómo se entrena</dt>
              <dd>
                <code>model/train.py</code> se ejecuta en GitHub Actions. El dataset puede
                sustituirse en cada ejecución mediante <code>client_payload.dataseturl</code>,
                lo que permite reentrenar con versiones al 25&nbsp;%, 50&nbsp;% y 100&nbsp;%.
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
                <code>GET /health</code> · <code>POST /score</code> ·{' '}
                <a href={`${API_URL}/docs`} target="_blank" rel="noreferrer">
                  documentación interactiva
                </a>
                {healthInfo?.model_path && (
                  <> · artefacto <code>{healthInfo.model_path}</code></>
                )}
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

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  API_URL, checkHealth, getCatalog, listModels, predict, predictAll,
} from './api.js'
import {
  EXAMPLES, HIERARCHY, METRICS,
  cascade, defaultValues, formatMetric, formatNumber, optionsFor, toPayload, validate,
} from './catalog.js'
import RetrainPanel from './RetrainPanel.jsx'

const STATUS_LABEL = {
  checking: 'Comprobando conexión…',
  waking: 'Despertando el servicio…',
  online: 'API en línea',
  offline: 'API no disponible',
}

// Reintentos al cargar: en el plan gratuito de Render el backend puede estar
// dormido y tardar hasta un minuto en atender la primera peticion.
const HEALTH_ATTEMPTS = 3

const labelFor = (v) => (/^\d+$/.test(v) ? `${v} % del dataset` : `Versión ${v}`)

export default function App() {
  const [catalog, setCatalog] = useState(null)
  const [values, setValues] = useState(null)
  const [errors, setErrors] = useState({})
  const [status, setStatus] = useState('checking')
  const [health, setHealth] = useState(null)
  const [models, setModels] = useState([])
  const [version, setVersion] = useState(null)
  const [compareAll, setCompareAll] = useState(true)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [comparison, setComparison] = useState(null)
  const [apiError, setApiError] = useState(null)

  const versions = useMemo(() => models.map((m) => m.version), [models])

  /** Carga el catálogo y las versiones, reintentando si el servicio está dormido. */
  const refresh = useCallback(async () => {
    const probe = async () => {
      const [salud, cat, list] = await Promise.all([
        checkHealth(), getCatalog(), listModels(),
      ])
      setHealth(salud)
      setCatalog(cat)
      setValues((prev) => prev ?? defaultValues(cat))

      const resolved = list.length > 0
        ? list
        : (salud.model_versions || ['default']).map((v) => ({
            version: v, is_default: v === salud.default_version, path: salud.model_path,
          }))
      setModels(resolved)
      const fallback = resolved.find((m) => m.is_default) || resolved[resolved.length - 1]
      setVersion((prev) => (prev && resolved.some((m) => m.version === prev)
        ? prev : fallback?.version ?? null))
    }

    for (let attempt = 1; attempt <= HEALTH_ATTEMPTS; attempt += 1) {
      setStatus(attempt === 1 ? 'checking' : 'waking')
      try {
        await probe()
        setStatus('online')
        return
      } catch {
        if (attempt < HEALTH_ATTEMPTS) {
          await new Promise((resolve) => setTimeout(resolve, 2000))
        }
      }
    }
    setStatus('offline')
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const options = useMemo(
    () => (catalog && values ? optionsFor(catalog.jerarquia, values) : null),
    [catalog, values],
  )
  const { warning } = useMemo(
    () => (values ? validate(values, catalog) : { errors: {}, warning: null }),
    [values, catalog],
  )

  function clearOutput() {
    setResult(null)
    setComparison(null)
    setApiError(null)
  }

  function handleChange(name, raw) {
    setValues((prev) => {
      const next = { ...prev, [name]: raw }
      // Al tocar un nivel de la jerarquía, los de abajo se recalculan.
      return HIERARCHY.some((f) => f.name === name)
        ? cascade(catalog.jerarquia, next)
        : next
    })
    setErrors((prev) => ({ ...prev, [name]: null }))
    clearOutput()
  }

  function applyExample(example) {
    setValues(cascade(catalog.jerarquia, { ...values, ...example.values }))
    setErrors({})
    clearOutput()
  }

  function resetForm() {
    setValues(defaultValues(catalog))
    setErrors({})
    clearOutput()
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setApiError(null)

    const { errors: nextErrors } = validate(values, catalog)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) {
      clearOutput()
      setApiError('Corrige los campos marcados antes de ejecutar la predicción.')
      return
    }

    const payload = toPayload(values)
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
  const listo = Boolean(catalog && values && options)

  return (
    <div className="page">
      <header className="header">
        <div className="header-inner">
          <div>
            <p className="eyebrow">MLOps · GitHub Actions · Docker · FastAPI</p>
            <h1>Incidencia delictiva estatal</h1>
            <p className="lede">
              Interfaz de prueba del modelo <code>incidencia-delictiva</code>, una
              regresión de conteos entrenada con los datos abiertos del SESNSP
              (2015&ndash;2025, 413&nbsp;952 registros). Estima las carpetas de
              investigación de un estado, un mes y una modalidad de delito.
              Están desplegadas las tres versiones &mdash; 25&nbsp;%, 50&nbsp;% y
              100&nbsp;% del dataset &mdash; y puedes reentrenarlas, lo que publica
              una imagen de Docker nueva.
            </p>
          </div>
          <div className={`status status-${status}`} role="status" aria-live="polite">
            <span className="status-dot" aria-hidden="true" />
            <div className="status-text">
              <strong>{STATUS_LABEL[status]}</strong>
              <span className="status-url">{API_URL}</span>
              {status === 'online' && versions.length > 0 && (
                <span className="status-url">
                  versiones: {versions.map((v) => `${v} %`).join(' · ')}
                </span>
              )}
            </div>
            <button type="button" className="btn-ghost" onClick={refresh}>
              Reintentar
            </button>
          </div>
        </div>
      </header>

      <main className="layout">
        <div className="main-col">
          {/* --- Los tres modelos entrenados, siempre visibles ------------- */}
          <section className="card models-card" aria-labelledby="models-title">
            <div className="card-head">
              <h2 id="models-title">Modelos entrenados</h2>
              <span className="actions-note">
                {versions.length > 0
                  ? `${versions.length} versiones cargadas en este despliegue`
                  : 'sin versiones'}
              </span>
            </div>

            {status === 'offline' && (
              <p className="help">
                No se pudo consultar el backend tras {HEALTH_ATTEMPTS} intentos. En
                el plan gratuito de Render el servicio se duerme tras unos minutos
                sin uso: espera un momento y pulsa <em>Reintentar</em>.
              </p>
            )}

            {models.length > 0 && (
              <>
                <div className="model-cards">
                  {models.map((m) => (
                    <article
                      key={m.version}
                      className={`model-card${version === m.version ? ' is-active' : ''}`}
                    >
                      <header>
                        <h3>{labelFor(m.version)}</h3>
                        {m.is_default && <span className="pill">por defecto</span>}
                      </header>
                      <p className="model-rows">
                        {formatNumber(m.n_rows)} registros de entrenamiento
                      </p>
                      <dl className="model-metrics">
                        {METRICS.map(({ key, label, help }) => (
                          <div key={key}>
                            <dt title={help}>{label}</dt>
                            <dd>{formatMetric(key, m[key])}</dd>
                          </div>
                        ))}
                      </dl>
                      {m.baseline_mae != null && m.mae != null && (
                        <p className="model-baseline">
                          Mejora un {((1 - m.mae / m.baseline_mae) * 100).toFixed(0)} % sobre
                          predecir siempre la media ({m.baseline_mae.toFixed(1)}).
                        </p>
                      )}
                      {m.path && <p className="model-path"><code>{m.path}</code></p>}
                    </article>
                  ))}
                </div>
                <p className="score-note">
                  Las tres comparten preprocesado e hiperparámetros: la única
                  diferencia es el volumen de datos de entrenamiento. MAE y RMSE
                  están en carpetas de investigación, así que son directamente
                  comparables entre versiones.
                </p>
              </>
            )}
          </section>

          {/* --- Formulario de predicción ---------------------------------- */}
          <section className="card" aria-labelledby="form-title">
            <div className="card-head">
              <h2 id="form-title">Consulta</h2>
              <div className="examples">
                {listo && EXAMPLES.map((example) => (
                  <button key={example.id} type="button" className="btn-ghost"
                          onClick={() => applyExample(example)}>
                    {example.label}
                  </button>
                ))}
                {listo && (
                  <button type="button" className="btn-ghost" onClick={resetForm}>
                    Restablecer
                  </button>
                )}
              </div>
            </div>

            {!listo && status !== 'offline' && (
              <div className="placeholder">
                <span className="spinner spinner-lg" aria-hidden="true" />
                <p>Cargando el catálogo del modelo…</p>
              </div>
            )}

            {listo && (
              <form onSubmit={handleSubmit} noValidate>
                <fieldset className="versions">
                  <legend>Versión del modelo a consultar</legend>
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
                        <span className="version-main">{labelFor(m.version)}</span>
                        <span className="version-meta">
                          {formatNumber(m.n_rows)} registros
                          {m.mae != null && ` · MAE ${m.mae.toFixed(2)}`}
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
                        Consultar las {versions.length} versiones con los mismos datos
                      </span>
                    </label>
                  )}
                </fieldset>

                <div className="grid">
                  <div className="field">
                    <label htmlFor="anio">Año</label>
                    <input
                      id="anio" name="anio" type="number" inputMode="numeric"
                      min={1990} max={2100} step={1}
                      value={values.anio}
                      aria-invalid={Boolean(errors.anio)}
                      aria-describedby="anio-help"
                      onChange={(e) => handleChange('anio', e.target.value)}
                    />
                    <p className="help" id="anio-help">
                      El dataset cubre {catalog.anios[0]}&ndash;{catalog.anios[1]}.
                    </p>
                    {errors.anio && <p className="error" role="alert">{errors.anio}</p>}
                  </div>

                  <div className="field">
                    <label htmlFor="mes">Mes</label>
                    <select
                      id="mes" name="mes" value={values.mes}
                      onChange={(e) => handleChange('mes', e.target.value)}
                    >
                      {catalog.meses.map((m) => (
                        <option key={m.numero} value={String(m.numero)}>{m.nombre}</option>
                      ))}
                    </select>
                    <p className="help">Mes del periodo consultado.</p>
                  </div>

                  <div className="field">
                    <label htmlFor="clave_ent">Entidad federativa</label>
                    <select
                      id="clave_ent" name="clave_ent" value={values.clave_ent}
                      onChange={(e) => handleChange('clave_ent', e.target.value)}
                    >
                      {catalog.entidades.map((e) => (
                        <option key={e.clave_ent} value={String(e.clave_ent)}>
                          {e.entidad}
                        </option>
                      ))}
                    </select>
                    <p className="help">Los 32 estados del país.</p>
                  </div>

                  {HIERARCHY.map(({ name, label, help }) => (
                    <div className={`field${name === 'modalidad' || name === 'subtipo_delito' ? ' field-wide' : ''}`} key={name}>
                      <label htmlFor={name}>{label}</label>
                      <select
                        id={name} name={name} value={values[name]}
                        aria-invalid={Boolean(errors[name])}
                        disabled={options[name].length === 0}
                        onChange={(e) => handleChange(name, e.target.value)}
                      >
                        {options[name].map((option) => (
                          <option key={option} value={option}>{option}</option>
                        ))}
                      </select>
                      <p className="help">
                        {help}
                        {options[name].length > 1 && ` ${options[name].length} opciones.`}
                      </p>
                      {errors[name] && <p className="error" role="alert">{errors[name]}</p>}
                    </div>
                  ))}
                </div>

                {warning && <p className="warning" role="status">{warning}</p>}

                <div className="actions">
                  <button type="submit" className="btn-primary"
                          disabled={loading || versions.length === 0}>
                    {loading
                      ? (<><span className="spinner" aria-hidden="true" /> Calculando…</>)
                      : compareAll && canCompare ? 'Comparar las 3 versiones' : 'Predecir'}
                  </button>
                  <span className="actions-note">
                    {compareAll && canCompare
                      ? `Se enviará el mismo payload a ${versions.length} versiones`
                      : <>Se enviará <code>POST {API_URL}/predict
                          {version ? `?version=${version}` : ''}</code></>}
                  </span>
                </div>
              </form>
            )}
          </section>

          {/* --- Reentrenamiento ------------------------------------------- */}
          <RetrainPanel health={health} onDone={refresh} />
        </div>

        <aside className="side">
          <section className="card result-card" aria-labelledby="result-title" aria-live="polite">
            <h2 id="result-title">Resultado</h2>

            {loading && (
              <div className="placeholder">
                <span className="spinner spinner-lg" aria-hidden="true" />
                <p>Consultando el modelo…</p>
                <p className="placeholder-hint">
                  Si el backend está en el plan gratuito de Render y llevaba rato
                  inactivo, la primera respuesta puede tardar hasta un minuto.
                </p>
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
                Completa la consulta y pulsa <em>Predecir</em> para ver la salida
                real del modelo.
              </p>
            )}

            {!loading && result && (
              <>
                <p className="score-label">
                  Carpetas de investigación estimadas · versión{' '}
                  <strong>{labelFor(result.version)}</strong>
                </p>
                <p className="score">{formatNumber(result.prediccion_redondeada)}</p>
                <p className="score-note">
                  {result.entidad} · {result.periodo} · valor exacto{' '}
                  <code>{result.prediccion.toFixed(4)}</code>. Es el número de
                  carpetas de investigación que el modelo espera para ese estado,
                  mes y modalidad de delito, no un pronóstico oficial.
                </p>
                <details>
                  <summary>Ver el JSON enviado y recibido</summary>
                  <p className="mono-label">Petición · {result.url}</p>
                  <pre>{JSON.stringify(result.payload, null, 2)}</pre>
                  <p className="mono-label">Respuesta</p>
                  <pre>{JSON.stringify({
                    prediccion: result.prediccion,
                    prediccion_redondeada: result.prediccion_redondeada,
                    version: result.version,
                    entidad: result.entidad,
                    periodo: result.periodo,
                  }, null, 2)}</pre>
                </details>
              </>
            )}

            {!loading && comparison && (
              <>
                <p className="score-label">
                  Mismos datos, {comparison.rows.length} versiones del modelo
                </p>
                <table className="compare-table">
                  <caption className="sr-only">
                    Carpetas de investigación estimadas por versión del dataset
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Versión</th>
                      <th scope="col">Estimación</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.rows.map((row) => (
                      <tr key={row.version}>
                        <th scope="row">{row.version} %</th>
                        <td>
                          {row.error
                            ? <span className="cell-error">{row.error}</span>
                            : formatNumber(row.prediccion_redondeada)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="score-note">
                  Las diferencias entre filas provienen únicamente del tamaño del
                  conjunto de entrenamiento. Para saber cuál es mejor, mira el MAE
                  de cada versión en <em>Modelos entrenados</em>.
                </p>
                <details>
                  <summary>Ver el JSON enviado y recibido</summary>
                  <p className="mono-label">Petición (idéntica para todas las versiones)</p>
                  <pre>{JSON.stringify(comparison.payload, null, 2)}</pre>
                  <p className="mono-label">Respuestas</p>
                  <pre>{JSON.stringify(
                    comparison.rows.map(({ version, prediccion, error }) =>
                      error ? { version, error } : { version, prediccion }), null, 2)}</pre>
                </details>
              </>
            )}
          </section>

          <section className="card info-card" aria-labelledby="info-title">
            <h2 id="info-title">Sobre el modelo</h2>
            <dl>
              <dt>Qué hace</dt>
              <dd>
                Un <code>HistGradientBoostingRegressor</code> que estima
                <code> incidencia_delictiva</code>: las carpetas de investigación
                abiertas en un estado, un mes y una modalidad de delito. Es una
                regresión de conteos, así que la salida es un número, no una
                probabilidad.
              </dd>
              <dt>Los datos</dt>
              <dd>
                Datos abiertos del SESNSP, 2015&ndash;2025: 413&nbsp;952 registros
                y 7 variables. El 43&nbsp;% de los registros vale 0 y la cola llega
                a casi 10&nbsp;000, por eso las métricas se leen junto al MAE de
                referencia (predecir siempre la media).
              </dd>
              <dt>Las tres versiones</dt>
              <dd>
                Cada versión es un modelo independiente, entrenado con el 25&nbsp;%,
                50&nbsp;% o 100&nbsp;% de los registros (muestreo estratificado por
                tipo de delito, que conserva la mezcla de delitos). La única
                diferencia es el volumen de datos.
              </dd>
              <dt>Cómo se reentrena</dt>
              <dd>
                El panel de reentrenamiento dispara el workflow de GitHub Actions,
                que descarga los datasets de Cloudinary, entrena las tres
                versiones, corre las pruebas y publica una imagen de Docker nueva
                con su propia etiqueta.
              </dd>
              <dt>Limitaciones</dt>
              <dd>
                Uso académico. El modelo aprende el histórico de carpetas
                <em> registradas</em>, que no es lo mismo que el delito real: la
                cifra negra y los cambios en la forma de registrar quedan dentro de
                los datos. Fuera de {catalog?.anios?.[0] ?? 2015}&ndash;
                {catalog?.anios?.[1] ?? 2025} extrapola.
              </dd>
              <dt>API</dt>
              <dd>
                <code>GET /health</code> · <code>GET /models</code> ·{' '}
                <code>GET /catalog</code> · <code>POST /predict</code> ·{' '}
                <code>POST /retrain</code> ·{' '}
                <a href={`${API_URL}/docs`} target="_blank" rel="noreferrer">
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
          Práctica de MLOps — reentrenamiento de un modelo con GitHub Actions y
          publicación de la imagen en Docker Hub. Uso académico y demostrativo
          únicamente.
        </p>
      </footer>
    </div>
  )
}

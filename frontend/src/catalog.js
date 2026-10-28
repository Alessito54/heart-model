// Logica del formulario, derivada del catalogo que publica GET /catalog.
//
// Los cuatro niveles del delito forman una jerarquia:
//   bien juridico -> tipo -> subtipo -> modalidad
// Cada nivel acota al siguiente, asi que las listas se encadenan: al cambiar
// uno, los de abajo se recalculan. Eso hace imposible enviar una combinacion
// que no exista en el dataset (el backend tambien la rechazaria con un 422).

export const HIERARCHY = [
  { name: 'bien_juridico_afectado', label: 'Bien jurídico afectado',
    help: 'La categoría más general: qué derecho vulnera el delito.' },
  { name: 'tipo_delito', label: 'Tipo de delito',
    help: 'Clasificación principal dentro del bien jurídico.' },
  { name: 'subtipo_delito', label: 'Subtipo de delito',
    help: 'Desglose del tipo de delito.' },
  { name: 'modalidad', label: 'Modalidad',
    help: 'El nivel más específico: cómo se cometió el delito.' },
]

/** Opciones validas de cada nivel dadas las selecciones de los niveles superiores. */
export function optionsFor(jerarquia, values) {
  const bienes = Object.keys(jerarquia).sort()
  const tipos = Object.keys(jerarquia[values.bien_juridico_afectado] || {}).sort()
  const subtipos = Object.keys(
    jerarquia[values.bien_juridico_afectado]?.[values.tipo_delito] || {},
  ).sort()
  const modalidades =
    jerarquia[values.bien_juridico_afectado]?.[values.tipo_delito]?.[values.subtipo_delito] || []
  return {
    bien_juridico_afectado: bienes,
    tipo_delito: tipos,
    subtipo_delito: subtipos,
    modalidad: [...modalidades],
  }
}

/**
 * Repara la cadena del delito tras un cambio: si un nivel dejo de ser valido
 * por lo que se eligio arriba, se sustituye por la primera opcion disponible.
 */
export function cascade(jerarquia, values) {
  const fixed = { ...values }
  for (const { name } of HIERARCHY) {
    const options = optionsFor(jerarquia, fixed)[name]
    if (!options.includes(fixed[name])) fixed[name] = options[0] ?? ''
  }
  return fixed
}

/** Primera combinacion valida del catalogo, para arrancar el formulario. */
export function firstValidSelection(jerarquia) {
  return cascade(jerarquia, {
    bien_juridico_afectado: Object.keys(jerarquia).sort()[0],
    tipo_delito: '', subtipo_delito: '', modalidad: '',
  })
}

/** Valores iniciales del formulario a partir del catalogo de la API. */
export function defaultValues(catalog) {
  const [, maxAnio] = catalog.anios
  // Se busca una rama conocida y representativa; si no existe en este
  // catalogo, se cae en la primera combinacion valida que haya.
  const preferida = cascade(catalog.jerarquia, {
    bien_juridico_afectado: 'El patrimonio',
    tipo_delito: 'Robo',
    subtipo_delito: 'Robo de vehículo automotor',
    modalidad: 'Robo de coche de 4 ruedas Con violencia',
  })
  const delito = preferida.modalidad
    ? preferida
    : firstValidSelection(catalog.jerarquia)

  // Se arranca en la Ciudad de Mexico (clave 9), que es tambien el valor por
  // defecto de la API: asi la primera pantalla muestra una cifra representativa
  // en lugar de un estado pequenio donde casi todo vale 0.
  const entidades = catalog.entidades.map((e) => e.clave_ent)
  const clave = entidades.includes(9) ? 9 : entidades[0] ?? 1

  return {
    anio: String(maxAnio),
    mes: '6',
    clave_ent: String(clave),
    ...delito,
  }
}

/** Convierte los valores del formulario (texto) al payload que espera la API. */
export function toPayload(values) {
  return {
    anio: parseInt(values.anio, 10),
    mes: parseInt(values.mes, 10),
    clave_ent: parseInt(values.clave_ent, 10),
    bien_juridico_afectado: values.bien_juridico_afectado,
    tipo_delito: values.tipo_delito,
    subtipo_delito: values.subtipo_delito,
    modalidad: values.modalidad,
  }
}

/** Valida el anio y el mes con los mismos limites que aplica el backend. */
export function validate(values, catalog) {
  const errors = {}
  const anio = Number(values.anio)
  if (!Number.isInteger(anio)) errors.anio = 'Introduce un año entero.'
  else if (anio < 1990 || anio > 2100) errors.anio = 'El año debe estar entre 1990 y 2100.'

  const mes = Number(values.mes)
  if (!Number.isInteger(mes) || mes < 1 || mes > 12) errors.mes = 'Elige un mes válido.'

  for (const { name, label } of HIERARCHY) {
    if (!values[name]) errors[name] = `Elige un valor para ${label.toLowerCase()}.`
  }
  if (!values.clave_ent) errors.clave_ent = 'Elige una entidad federativa.'

  // Aviso, no error: el modelo extrapola fuera del rango entrenado.
  const [minAnio, maxAnio] = catalog?.anios || []
  const warning = (anio > maxAnio || anio < minAnio)
    ? `El modelo se entrenó con datos de ${minAnio} a ${maxAnio}. ` +
      `Para ${anio} la predicción es una extrapolación.`
    : null

  return { errors, warning }
}

/** Escenarios de ejemplo, utiles para comparar las tres versiones de golpe. */
export const EXAMPLES = [
  {
    id: 'robo-vehiculo-cdmx',
    label: 'Robo de vehículo · CDMX',
    values: {
      clave_ent: '9', anio: '2025', mes: '6',
      bien_juridico_afectado: 'El patrimonio',
      tipo_delito: 'Robo',
      subtipo_delito: 'Robo de vehículo automotor',
      modalidad: 'Robo de coche de 4 ruedas Con violencia',
    },
  },
  {
    id: 'violencia-familiar-jalisco',
    label: 'Violencia familiar · Jalisco',
    values: {
      clave_ent: '14', anio: '2025', mes: '6',
      bien_juridico_afectado: 'La familia',
      tipo_delito: 'Violencia familiar',
      subtipo_delito: 'Violencia familiar',
      modalidad: 'Violencia familiar',
    },
  },
  {
    id: 'homicidio-doloso-guanajuato',
    label: 'Homicidio doloso · Guanajuato',
    values: {
      clave_ent: '11', anio: '2025', mes: '6',
      bien_juridico_afectado: 'La vida y la Integridad corporal',
      tipo_delito: 'Homicidio',
      subtipo_delito: 'Homicidio doloso',
      modalidad: 'Con arma de fuego',
    },
  },
]

/** Métricas que se muestran por versión, con su formato y su lectura. */
export const METRICS = [
  { key: 'mae', label: 'MAE', help: 'Error absoluto medio, en carpetas de investigación. Más bajo es mejor.' },
  { key: 'rmse', label: 'RMSE', help: 'Raíz del error cuadrático medio: penaliza los fallos grandes.' },
  { key: 'r2', label: 'R²', help: 'Proporción de la varianza explicada. 1 es perfecto.' },
]

export const formatMetric = (key, value) => {
  if (value == null) return '—'
  return key === 'r2' ? value.toFixed(4) : value.toFixed(2)
}

export const formatNumber = (value) =>
  value == null ? '—' : value.toLocaleString('es-MX')

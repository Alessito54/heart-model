// Definicion de los 13 campos que exige POST /score del backend real.
// Los limites (min/max) replican las validaciones de app.py (pydantic Field ge/le).
export const FIELDS = [
  {
    name: 'age', label: 'Edad', unit: 'años', type: 'number',
    min: 1, max: 120, step: 1, default: 64,
    help: 'Edad del paciente en años.',
  },
  {
    name: 'sex', label: 'Sexo', type: 'select', default: 1,
    options: [{ value: 0, label: 'Mujer' }, { value: 1, label: 'Hombre' }],
    help: 'Sexo biológico registrado en el estudio.',
  },
  {
    name: 'cp', label: 'Tipo de dolor torácico', type: 'select', default: 3,
    options: [
      { value: 0, label: '0 — Angina típica' },
      { value: 1, label: '1 — Angina atípica' },
      { value: 2, label: '2 — Dolor no anginoso' },
      { value: 3, label: '3 — Asintomático' },
    ],
    help: 'Categoría del dolor torácico reportado.',
  },
  {
    name: 'trestbps', label: 'Presión arterial en reposo', unit: 'mm Hg', type: 'number',
    min: 50, max: 250, step: 1, default: 120,
    help: 'Presión arterial sistólica medida al ingreso.',
  },
  {
    name: 'chol', label: 'Colesterol sérico', unit: 'mg/dl', type: 'number',
    min: 100, max: 700, step: 1, default: 267,
    help: 'Colesterol total en suero.',
  },
  {
    name: 'fbs', label: 'Glucosa en ayunas > 120 mg/dl', type: 'select', default: 0,
    options: [{ value: 0, label: 'No' }, { value: 1, label: 'Sí' }],
    help: 'Indica si la glucemia en ayunas supera 120 mg/dl.',
  },
  {
    name: 'restecg', label: 'Electrocardiograma en reposo', type: 'select', default: 0,
    options: [
      { value: 0, label: '0 — Normal' },
      { value: 1, label: '1 — Anomalía de la onda ST-T' },
      { value: 2, label: '2 — Hipertrofia ventricular izquierda' },
    ],
    help: 'Resultado del ECG en reposo.',
  },
  {
    name: 'thalach', label: 'Frecuencia cardíaca máxima', unit: 'lpm', type: 'number',
    min: 50, max: 250, step: 1, default: 99,
    help: 'Frecuencia cardíaca máxima alcanzada durante la prueba de esfuerzo.',
  },
  {
    name: 'exang', label: 'Angina inducida por ejercicio', type: 'select', default: 1,
    options: [{ value: 0, label: 'No' }, { value: 1, label: 'Sí' }],
    help: 'Aparición de angina durante el ejercicio.',
  },
  {
    name: 'oldpeak', label: 'Depresión ST (oldpeak)', unit: 'mm', type: 'number',
    min: 0, max: 10, step: 0.1, default: 1.8, decimal: true,
    help: 'Depresión del segmento ST inducida por ejercicio respecto al reposo.',
  },
  {
    name: 'slope', label: 'Pendiente del segmento ST', type: 'select', default: 1,
    options: [
      { value: 0, label: '0 — Ascendente' },
      { value: 1, label: '1 — Plana' },
      { value: 2, label: '2 — Descendente' },
    ],
    help: 'Pendiente del segmento ST en el pico del ejercicio.',
  },
  {
    name: 'ca', label: 'Vasos principales (fluoroscopia)', type: 'select', default: 2,
    options: [0, 1, 2, 3, 4].map((v) => ({ value: v, label: String(v) })),
    help: 'Número de vasos principales coloreados por fluoroscopia.',
  },
  {
    name: 'thal', label: 'Talasemia (thal)', type: 'select', default: 2,
    options: [
      { value: 0, label: '0 — No registrado' },
      { value: 1, label: '1 — Defecto fijo' },
      { value: 2, label: '2 — Normal' },
      { value: 3, label: '3 — Defecto reversible' },
    ],
    help: 'Resultado de la prueba de talasemia.',
  },
]

export const DEFAULT_VALUES = Object.fromEntries(
  FIELDS.map((f) => [f.name, String(f.default)]),
)

// Casos de ejemplo tomados de registros reales de data/heart-disease.csv.
export const EXAMPLES = [
  {
    id: 'ejemplo-a',
    label: 'Ejemplo A (registro del dataset, target = 0)',
    values: { age: 52, sex: 1, cp: 0, trestbps: 125, chol: 212, fbs: 0, restecg: 1,
      thalach: 168, exang: 0, oldpeak: 1, slope: 2, ca: 2, thal: 3 },
  },
  {
    id: 'ejemplo-b',
    label: 'Ejemplo B (registro del dataset, target = 1)',
    values: { age: 58, sex: 0, cp: 0, trestbps: 100, chol: 248, fbs: 0, restecg: 0,
      thalach: 122, exang: 0, oldpeak: 1, slope: 1, ca: 0, thal: 2 },
  },
]

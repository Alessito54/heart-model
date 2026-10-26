from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import pandas as pd
from joblib import load
import pathlib
import os

origins = ["*"]

app = FastAPI(
    title='Heart Disease Prediction',
    description='API de inferencia del modelo de prediccion de enfermedad cardiaca.',
    version='1.0.0',
)

app.add_middleware(
   CORSMiddleware,
   allow_origins=origins,
   allow_credentials=True,
   allow_methods=["*"],
   allow_headers=["*"]
)

MODEL_PATH = pathlib.Path(os.getenv('MODEL_PATH', 'model/heart-disease-v1.joblib'))

# Orden exacto de las columnas con las que se entreno el modelo (data/heart-disease.csv
# sin la columna 'target'). No cambiar: predict_proba depende de este orden.
FEATURES = ['age', 'sex', 'cp', 'trestbps', 'chol', 'fbs', 'restecg',
            'thalach', 'exang', 'oldpeak', 'slope', 'ca', 'thal']

model = load(MODEL_PATH)

class InputData(BaseModel):
    age:int=Field(64, ge=1, le=120, description='Edad en anios')
    sex:int=Field(1, ge=0, le=1, description='0 = mujer, 1 = hombre')
    cp:int=Field(3, ge=0, le=3, description='Tipo de dolor toracico (0-3)')
    trestbps:int=Field(120, ge=50, le=250, description='Presion arterial en reposo (mm Hg)')
    chol:int=Field(267, ge=100, le=700, description='Colesterol serico (mg/dl)')
    fbs:int=Field(0, ge=0, le=1, description='Glucosa en ayunas > 120 mg/dl (0/1)')
    restecg:int=Field(0, ge=0, le=2, description='Electrocardiograma en reposo (0-2)')
    thalach:int=Field(99, ge=50, le=250, description='Frecuencia cardiaca maxima alcanzada (lpm)')
    exang:int=Field(1, ge=0, le=1, description='Angina inducida por ejercicio (0/1)')
    oldpeak:float=Field(1.8, ge=0.0, le=10.0, description='Depresion ST inducida por ejercicio')
    slope:int=Field(1, ge=0, le=2, description='Pendiente del segmento ST (0-2)')
    ca:int=Field(2, ge=0, le=4, description='Vasos principales coloreados por fluoroscopia (0-4)')
    thal:int=Field(2, ge=0, le=3, description='Talasemia (0-3)')

class OutputData(BaseModel):
    score:float=0.80318881046519

@app.get('/')
def root():
    return {
        'service': 'Heart Disease Prediction',
        'version': app.version,
        'docs': '/docs',
        'endpoints': ['/score', '/health'],
    }

@app.get('/health')
def health():
    return {
        'status': 'ok',
        'model_loaded': model is not None,
        'model_path': str(MODEL_PATH),
        'features': FEATURES,
    }

@app.post('/score', response_model = OutputData)
def score(data:InputData):
    payload = data.dict()
    model_input = pd.DataFrame([[payload[f] for f in FEATURES]], columns=FEATURES)
    try:
        result = model.predict_proba(model_input)[:, -1]
    except Exception as exc:  # modelo incompatible con la entrada
        raise HTTPException(
            status_code=500,
            detail=f'No fue posible calcular la prediccion: {exc}',
        )

    return {'score': float(result[0])}

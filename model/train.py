from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, roc_auc_score
from joblib import dump
import pandas as pd
import pathlib
import json
import os

DATA_PATH = pathlib.Path(os.getenv('DATASET_PATH', 'data/heart-disease.csv'))
MODEL_PATH = pathlib.Path(os.getenv('MODEL_PATH', 'model/heart-disease-v1.joblib'))
METRICS_PATH = pathlib.Path(os.getenv('METRICS_PATH', 'model/metrics.json'))
RANDOM_STATE = int(os.getenv('RANDOM_STATE', '0'))

if not DATA_PATH.exists():
    raise SystemExit(f'ERROR: no se encontro el dataset en {DATA_PATH}')

df = pd.read_csv(DATA_PATH)

if 'target' not in df.columns:
    raise SystemExit(
        f"ERROR: el dataset {DATA_PATH} no contiene la columna 'target'. "
        f'Columnas encontradas: {list(df.columns)}'
    )

print(f'Dataset: {DATA_PATH} -> {df.shape[0]} registros, {df.shape[1]} columnas')

y = df.pop('target')
X = df

print(f'Distribucion de clases: {y.value_counts().to_dict()}')

# Muestreo estratificado: conserva la proporcion de clases en train y test.
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
)

print('Training model.. ')
clf = RandomForestClassifier(n_estimators = 10,
                            max_depth=2,
                            random_state=0)
clf.fit(X_train, y_train)

y_pred = clf.predict(X_test)
y_proba = clf.predict_proba(X_test)[:, -1]

print('\nclassification_report (conjunto de prueba):')
print(classification_report(y_test, y_pred))

metrics = {
    'dataset': str(DATA_PATH),
    'n_rows': int(len(df) + 0),
    'n_train': int(len(X_train)),
    'n_test': int(len(X_test)),
    'accuracy': float(accuracy_score(y_test, y_pred)),
    'roc_auc': float(roc_auc_score(y_test, y_proba)),
    'features': list(X.columns),
}
print(f"accuracy={metrics['accuracy']:.4f}  roc_auc={metrics['roc_auc']:.4f}")

print('Saving model..')
MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
dump(clf, MODEL_PATH)
METRICS_PATH.write_text(json.dumps(metrics, indent=2))
print(f'Modelo guardado en {MODEL_PATH}')
print(f'Metricas guardadas en {METRICS_PATH}')

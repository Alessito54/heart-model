"""Entrena el clasificador de enfermedad cardiaca para una version del dataset.

La "version" identifica el porcentaje del dataset original usado (25, 50, 100)
y determina el nombre de los artefactos, de modo que las tres versiones pueden
convivir en el mismo directorio sin sobrescribirse.

Uso:
    python model/train.py                                   # version por defecto
    python model/train.py --version 25 --dataset data/versions/heart-disease_25.csv
    DATASET_PATH=... MODEL_VERSION=50 python model/train.py
"""
import argparse
import json
import os
import pathlib

import pandas as pd
from joblib import dump
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score
from sklearn.model_selection import train_test_split

DEFAULT_VERSION = os.getenv('MODEL_VERSION', '100')
MODEL_DIR = pathlib.Path(os.getenv('MODEL_DIR', 'model'))


def artifact_paths(version: str) -> tuple[pathlib.Path, pathlib.Path]:
    """Rutas de los artefactos de una version. MODEL_PATH/METRICS_PATH las anulan."""
    model_path = pathlib.Path(
        os.getenv('MODEL_PATH', MODEL_DIR / f'heart-disease-{version}.joblib'))
    metrics_path = pathlib.Path(
        os.getenv('METRICS_PATH', MODEL_DIR / f'metrics-{version}.json'))
    return model_path, metrics_path


def train(dataset: pathlib.Path, version: str, random_state: int = 0) -> dict:
    if not dataset.exists():
        raise SystemExit(f'ERROR: no se encontro el dataset en {dataset}')

    df = pd.read_csv(dataset)
    if 'target' not in df.columns:
        raise SystemExit(
            f"ERROR: el dataset {dataset} no contiene la columna 'target'. "
            f'Columnas encontradas: {list(df.columns)}'
        )

    print(f'Version {version} | dataset: {dataset} -> '
          f'{df.shape[0]} registros, {df.shape[1]} columnas')

    y = df.pop('target')
    X = df
    print(f'Distribucion de clases: {y.value_counts().to_dict()}')

    # Muestreo estratificado: conserva la proporcion de clases en train y test.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=random_state, stratify=y
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
        'version': version,
        'dataset': str(dataset),
        'n_rows': int(len(X)),
        'n_train': int(len(X_train)),
        'n_test': int(len(X_test)),
        'accuracy': float(accuracy_score(y_test, y_pred)),
        'roc_auc': float(roc_auc_score(y_test, y_proba)),
        'features': list(X.columns),
    }
    print(f"accuracy={metrics['accuracy']:.4f}  roc_auc={metrics['roc_auc']:.4f}")

    model_path, metrics_path = artifact_paths(version)
    print('Saving model..')
    model_path.parent.mkdir(parents=True, exist_ok=True)
    dump(clf, model_path)
    metrics['model_path'] = str(model_path)
    metrics_path.write_text(json.dumps(metrics, indent=2))
    print(f'Modelo guardado en {model_path}')
    print(f'Metricas guardadas en {metrics_path}')
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', default=os.getenv('DATASET_PATH', 'data/heart-disease.csv'),
                        help='CSV de entrenamiento')
    parser.add_argument('--version', default=DEFAULT_VERSION,
                        help='Identificador de la version (25, 50, 100)')
    parser.add_argument('--random-state', type=int, default=int(os.getenv('RANDOM_STATE', '0')))
    args = parser.parse_args()
    train(pathlib.Path(args.dataset), args.version, args.random_state)


if __name__ == '__main__':
    main()

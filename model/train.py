"""Entrena el modelo de incidencia delictiva para una version del dataset.

La "version" identifica el porcentaje del dataset usado (25, 50, 100) y
determina el nombre de los artefactos, de modo que las tres versiones pueden
convivir en el mismo directorio sin sobrescribirse.

Es un problema de regresion de conteos: la etiqueta 'incidencia_delictiva' es el
numero de carpetas de investigacion abiertas en un estado, un mes y una
modalidad de delito. El 43 % de los registros vale 0 y la cola llega a ~10 000.
Se usa HistGradientBoostingRegressor con perdida cuadratica: la perdida de
Poisson, que seria la natural para conteos, divergia en los datasets de 50 % y
100 % (la cola pesada hace explotar el enlace logaritmico). Las predicciones se
recortan en 0, porque un conteo negativo no tiene sentido.

Uso:
    python model/train.py                                   # version por defecto
    python model/train.py --version 25 --dataset data/versions/incidencia_25.csv
    DATASET_PATH=... MODEL_VERSION=50 python model/train.py
"""
import argparse
import json
import os
import pathlib
import sys

import numpy as np
import pandas as pd
from joblib import dump
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    median_absolute_error,
    r2_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from model.schema import (  # noqa: E402
    CAT_FEATURES, FEATURES, LABEL, NUM_FEATURES,
    build_catalog_json, load_catalogs, rehydrate,
)

DEFAULT_VERSION = os.getenv('MODEL_VERSION', '100')
MODEL_DIR = pathlib.Path(os.getenv('MODEL_DIR', 'model'))
DATA_DIR = pathlib.Path(os.getenv('DATA_DIR', 'data'))
# Estratificar por el delito mantiene la misma mezcla en entrenamiento y prueba.
STRATIFY_ON = 'modalidad'


def artifact_paths(version: str) -> tuple[pathlib.Path, pathlib.Path]:
    """Rutas de los artefactos de una version. MODEL_PATH/METRICS_PATH las anulan."""
    model_path = pathlib.Path(
        os.getenv('MODEL_PATH', MODEL_DIR / f'incidencia-{version}.joblib'))
    metrics_path = pathlib.Path(
        os.getenv('METRICS_PATH', MODEL_DIR / f'metrics-{version}.json'))
    return model_path, metrics_path


def build_pipeline(random_state: int) -> Pipeline:
    """OrdinalEncoder + boosting de histogramas con soporte nativo de categoricas.

    Las categorias no vistas se codifican como NaN; HistGradientBoosting trata
    los NaN como valores ausentes, asi que un valor desconocido no rompe la
    inferencia (importante: el catalogo puede crecer entre reentrenamientos).
    """
    pre = ColumnTransformer(
        [
            ('cat',
             OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=np.nan),
             CAT_FEATURES),
            ('num', 'passthrough', NUM_FEATURES),
        ],
        remainder='drop',
    )
    regressor = HistGradientBoostingRegressor(
        loss='squared_error',
        max_iter=400,
        learning_rate=0.1,
        max_depth=None,
        max_leaf_nodes=63,
        min_samples_leaf=20,
        l2_regularization=1.0,
        # Indices tras el ColumnTransformer: las categoricas van primero.
        categorical_features=list(range(len(CAT_FEATURES))),
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=30,
        random_state=random_state,
    )
    return Pipeline([('pre', pre), ('reg', regressor)])


def train(dataset: pathlib.Path, version: str, random_state: int = 0) -> dict:
    if not dataset.exists():
        raise SystemExit(f'ERROR: no se encontro el dataset en {dataset}')

    delitos, entidades = load_catalogs(DATA_DIR)
    raw = pd.read_csv(dataset)
    df = rehydrate(raw, delitos)

    faltantes = [c for c in FEATURES + [LABEL] if c not in df.columns]
    if faltantes:
        raise SystemExit(
            f'ERROR: el dataset {dataset} no contiene las columnas {faltantes}. '
            f'Columnas encontradas: {list(df.columns)}'
        )

    print(f'Version {version} | dataset: {dataset} -> '
          f'{len(raw):,} registros, {len(FEATURES)} variables')

    y = df[LABEL].astype(float)
    X = df[FEATURES]
    print(f'Etiqueta: media {y.mean():.2f} | mediana {y.median():.0f} | '
          f'max {y.max():.0f} | ceros {(y == 0).mean():.1%}')

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=random_state, stratify=X[STRATIFY_ON]
    )

    print('Training model.. ')
    pipeline = build_pipeline(random_state)
    pipeline.fit(X_train, y_train)

    # Recorte en 0: la regresion puede devolver valores levemente negativos y
    # un numero de delitos negativo no existe. app.py aplica el mismo recorte.
    y_pred = np.clip(pipeline.predict(X_test), 0, None)
    # La media del conjunto de entrenamiento como referencia: cualquier modelo
    # util debe batirla.
    baseline = np.full_like(y_test, y_train.mean(), dtype=float)

    metrics = {
        'version': version,
        'dataset': str(dataset),
        'task': 'regression',
        'label': LABEL,
        'n_rows': int(len(X)),
        'n_train': int(len(X_train)),
        'n_test': int(len(X_test)),
        'mae': float(mean_absolute_error(y_test, y_pred)),
        'median_ae': float(median_absolute_error(y_test, y_pred)),
        'rmse': float(mean_squared_error(y_test, y_pred, squared=False)),
        'r2': float(r2_score(y_test, y_pred)),
        'baseline_mae': float(mean_absolute_error(y_test, baseline)),
        'baseline_rmse': float(mean_squared_error(y_test, baseline, squared=False)),
        'label_mean': float(y.mean()),
        'label_max': float(y.max()),
        'n_iter': int(pipeline.named_steps['reg'].n_iter_),
        'features': FEATURES,
    }
    print(f"\nmae={metrics['mae']:.3f} (baseline {metrics['baseline_mae']:.3f})  "
          f"rmse={metrics['rmse']:.3f} (baseline {metrics['baseline_rmse']:.3f})  "
          f"r2={metrics['r2']:.4f}  iteraciones={metrics['n_iter']}")

    model_path, metrics_path = artifact_paths(version)
    print('Saving model..')
    model_path.parent.mkdir(parents=True, exist_ok=True)
    dump(pipeline, model_path)
    metrics['model_path'] = str(model_path)
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))

    # Catalogo de valores validos para GET /catalog. Se escribe en cada version
    # porque la jerarquia es identica en las tres (muestreo estratificado).
    catalog_path = MODEL_DIR / 'catalog.json'
    catalog_path.write_text(
        json.dumps(build_catalog_json(df, entidades), indent=2, ensure_ascii=False))

    print(f'Modelo guardado en {model_path} ({model_path.stat().st_size / 1e6:.1f} MB)')
    print(f'Metricas guardadas en {metrics_path}')
    print(f'Catalogo guardado en {catalog_path}')
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',
                        default=os.getenv('DATASET_PATH',
                                          'data/versions/incidencia_100.csv'),
                        help='CSV de entrenamiento (codificado con id_delito)')
    parser.add_argument('--version', default=DEFAULT_VERSION,
                        help='Identificador de la version (25, 50, 100)')
    parser.add_argument('--random-state', type=int,
                        default=int(os.getenv('RANDOM_STATE', '0')))
    args = parser.parse_args()
    train(pathlib.Path(args.dataset), args.version, args.random_state)


if __name__ == '__main__':
    main()

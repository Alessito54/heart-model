"""Entrena las tres versiones del modelo (25 %, 50 %, 100 %) en un solo paso.

Cada version produce artefactos independientes:
    model/heart-disease-25.joblib   + model/metrics-25.json
    model/heart-disease-50.joblib   + model/metrics-50.json
    model/heart-disease-100.joblib  + model/metrics-100.json

Ademas copia la version por defecto a model/heart-disease-v1.joblib, que es la
ruta historica que siguen usando el Dockerfile y la variable MODEL_PATH.

Uso:
    python scripts/train_all_versions.py
    python scripts/train_all_versions.py --versions-dir data/versions --default 100
"""
import argparse
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from model.train import train  # noqa: E402

VERSIONS = ('25', '50', '100')
COMPAT_PATH = pathlib.Path('model/heart-disease-v1.joblib')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--versions-dir', default='data/versions')
    parser.add_argument('--default', default='100', choices=VERSIONS,
                        help='Version que se copia a heart-disease-v1.joblib')
    parser.add_argument('--random-state', type=int, default=0)
    args = parser.parse_args()

    versions_dir = pathlib.Path(args.versions_dir)
    missing = [v for v in VERSIONS
               if not (versions_dir / f'heart-disease_{v}.csv').exists()]
    if missing:
        print(
            f'ERROR: faltan los datasets {missing} en {versions_dir}.\n'
            'Genera las versiones primero:  python scripts/make_datasets.py',
            file=sys.stderr,
        )
        return 1

    resumen = []
    for version in VERSIONS:
        print(f'\n{"=" * 62}\n  Version {version} %\n{"=" * 62}')
        metrics = train(
            versions_dir / f'heart-disease_{version}.csv', version, args.random_state
        )
        resumen.append(metrics)

    default_model = pathlib.Path(f'model/heart-disease-{args.default}.joblib')
    shutil.copyfile(default_model, COMPAT_PATH)
    print(f'\nCompatibilidad: {default_model} -> {COMPAT_PATH}')

    print(f'\n{"=" * 62}\n  Resumen\n{"=" * 62}')
    print(f'{"version":>8} {"registros":>10} {"accuracy":>10} {"roc_auc":>9}')
    for m in resumen:
        print(f'{m["version"]:>7}% {m["n_rows"]:>10} '
              f'{m["accuracy"]:>10.4f} {m["roc_auc"]:>9.4f}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Entrena las tres versiones del modelo (25 %, 50 %, 100 %) en un solo paso.

Cada version produce artefactos independientes:
    model/incidencia-25.joblib   + model/metrics-25.json
    model/incidencia-50.joblib   + model/metrics-50.json
    model/incidencia-100.joblib  + model/metrics-100.json

Ademas copia la version por defecto a model/incidencia-v1.joblib, que es la
ruta de respaldo que usa la variable MODEL_PATH.

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
PREFIX = 'incidencia'
COMPAT_PATH = pathlib.Path(f'model/{PREFIX}-v1.joblib')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--versions-dir', default='data/versions')
    parser.add_argument('--default', default='100', choices=VERSIONS,
                        help=f'Version que se copia a {COMPAT_PATH}')
    parser.add_argument('--random-state', type=int, default=0)
    args = parser.parse_args()

    versions_dir = pathlib.Path(args.versions_dir)
    missing = [v for v in VERSIONS
               if not (versions_dir / f'{PREFIX}_{v}.csv').exists()]
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
            versions_dir / f'{PREFIX}_{version}.csv', version, args.random_state
        )
        resumen.append(metrics)

    default_model = pathlib.Path(f'model/{PREFIX}-{args.default}.joblib')
    shutil.copyfile(default_model, COMPAT_PATH)
    print(f'\nCompatibilidad: {default_model} -> {COMPAT_PATH}')

    print(f'\n{"=" * 62}\n  Resumen\n{"=" * 62}')
    print(f'{"version":>8} {"registros":>10} {"MAE":>9} {"RMSE":>9} {"R2":>8}')
    for m in resumen:
        print(f'{m["version"]:>7}% {m["n_rows"]:>10} '
              f'{m["mae"]:>9.3f} {m["rmse"]:>9.3f} {m["r2"]:>8.4f}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

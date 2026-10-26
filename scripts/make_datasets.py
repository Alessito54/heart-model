"""Genera versiones del dataset al 25%, 50% y 100% con muestreo estratificado.

Uso:
    python scripts/make_datasets.py
    python scripts/make_datasets.py --source data/heart-disease.csv --outdir data/versions

Conserva encabezado, columnas, tipos y la proporcion de la etiqueta 'target'.
"""
import argparse
import pathlib
import sys

import pandas as pd
from sklearn.model_selection import train_test_split

FRACTIONS = (25, 50, 100)
LABEL = 'target'


def build_subset(df: pd.DataFrame, percent: int, random_state: int) -> pd.DataFrame:
    if percent >= 100:
        return df.copy()
    # train_test_split con stratify conserva la proporcion de clases en el subconjunto.
    subset, _ = train_test_split(
        df,
        train_size=percent / 100,
        random_state=random_state,
        stratify=df[LABEL],
    )
    return subset.sort_index()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='data/heart-disease.csv')
    parser.add_argument('--outdir', default='data/versions')
    parser.add_argument('--random-state', type=int, default=42)
    args = parser.parse_args()

    source = pathlib.Path(args.source)
    if not source.exists():
        print(f'ERROR: no se encontro el dataset de origen: {source}', file=sys.stderr)
        return 1

    df = pd.read_csv(source)
    if LABEL not in df.columns:
        print(f"ERROR: el dataset no contiene la columna '{LABEL}'.", file=sys.stderr)
        return 1

    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    base = df[LABEL].value_counts(normalize=True).sort_index()
    print(f'Origen: {source} -> {len(df)} registros')
    print(f'Proporcion original: {base.round(4).to_dict()}\n')

    for percent in FRACTIONS:
        subset = build_subset(df, percent, args.random_state)
        destination = outdir / f'heart-disease_{percent}.csv'
        subset.to_csv(destination, index=False)
        proportion = subset[LABEL].value_counts(normalize=True).sort_index()
        print(
            f'{percent:>3}% -> {destination} | {len(subset)} registros '
            f'| proporcion {proportion.round(4).to_dict()}'
        )

    return 0


if __name__ == '__main__':
    raise SystemExit(main())

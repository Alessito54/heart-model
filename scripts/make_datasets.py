"""Genera las tablas de consulta y las versiones del dataset (25 %, 50 %, 100 %).

Fuente: data/INM_estatal_dic25.csv (incidencia delictiva estatal del SESNSP,
2015-2025, 413 952 registros). La etiqueta a predecir es 'incidencia_delictiva'
(un conteo), asi que la estratificacion no se hace sobre la etiqueta sino sobre
'id_delito', la combinacion mas fina de la jerarquia del delito (98 clases). Eso
garantiza que los tres subconjuntos contengan todos los tipos de delito y en la
misma proporcion.

Cloudinary limita los archivos raw a 10 MB, asi que los CSV se escriben con
identificadores en lugar de texto (ver model/schema.py): el dataset completo
baja de 47 MB a 6.4 MB y los tres archivos entran en el limite. Si aun asi la
version del 100 % superara --max-bytes, se recorta con muestreo estratificado
hasta que entre, y los porcentajes se calculan sobre ese archivo.

Salidas:
    data/catalogo_delitos.csv      98 filas  (id_delito -> jerarquia en texto)
    data/catalogo_entidades.csv    32 filas  (clave_ent -> nombre del estado)
    data/versions/incidencia_100.csv
    data/versions/incidencia_50.csv
    data/versions/incidencia_25.csv

Uso:
    python scripts/make_datasets.py
    python scripts/make_datasets.py --max-bytes 9000000
    python scripts/make_datasets.py --gzip        # ademas, copias .csv.gz
"""
import argparse
import pathlib
import sys

import pandas as pd
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from model.schema import (  # noqa: E402
    CATALOGO_DELITOS, CATALOGO_ENTIDADES, HIERARCHY, ID_COLUMNS, LABEL,
    MES_A_NUMERO,
)

FRACTIONS = (50, 25)
STRATIFY_ON = 'id_delito'
# Limite de Cloudinary para archivos raw: 10 MB. Se deja margen.
DEFAULT_MAX_BYTES = 9_000_000


def encode(source: pathlib.Path, outdir_data: pathlib.Path) -> pd.DataFrame:
    """Lee el CSV original, escribe las tablas de consulta y devuelve el dataset
    codificado con identificadores."""
    df = pd.read_csv(source)
    requeridas = HIERARCHY + ['anio', 'mes', 'clave_ent', LABEL]
    faltantes = [c for c in requeridas if c not in df.columns]
    if faltantes:
        raise SystemExit(f'ERROR: el dataset de origen no contiene {faltantes}.')

    # Catalogo de delitos: una fila por combinacion completa de la jerarquia.
    delitos = (df[HIERARCHY].drop_duplicates()
               .sort_values(HIERARCHY).reset_index(drop=True))
    delitos.insert(0, 'id_delito', range(len(delitos)))

    # Catalogo de entidades: clave_ent -> nombre. Se usa el nombre largo y
    # oficial de 'entidad'; 'entidad_federativa' es un alias abreviado.
    entidades = (df[['clave_ent', 'entidad']].drop_duplicates()
                 .sort_values('clave_ent').reset_index(drop=True))
    if entidades.clave_ent.duplicated().any():
        raise SystemExit('ERROR: una clave_ent apunta a mas de un nombre de entidad.')

    outdir_data.mkdir(parents=True, exist_ok=True)
    delitos.to_csv(outdir_data / CATALOGO_DELITOS, index=False)
    entidades.to_csv(outdir_data / CATALOGO_ENTIDADES, index=False)
    print(f'{CATALOGO_DELITOS:28} {len(delitos):>3} filas '
          f'({(outdir_data / CATALOGO_DELITOS).stat().st_size / 1024:.1f} KB)')
    print(f'{CATALOGO_ENTIDADES:28} {len(entidades):>3} filas '
          f'({(outdir_data / CATALOGO_ENTIDADES).stat().st_size / 1024:.1f} KB)')

    encoded = df.merge(delitos, on=HIERARCHY, how='left', validate='many_to_one')
    desconocidos = int(encoded.id_delito.isna().sum())
    if desconocidos:
        raise SystemExit(f'ERROR: {desconocidos} registros no se pudieron codificar.')

    meses_desconocidos = sorted(set(encoded.mes) - set(MES_A_NUMERO))
    if meses_desconocidos:
        raise SystemExit(f'ERROR: meses no reconocidos: {meses_desconocidos}.')
    encoded['mes'] = encoded.mes.map(MES_A_NUMERO).astype(int)
    encoded['id_delito'] = encoded.id_delito.astype(int)
    return encoded[ID_COLUMNS]


def subset(df: pd.DataFrame, percent: int, random_state: int) -> pd.DataFrame:
    if percent >= 100:
        return df.copy()
    sample, _ = train_test_split(
        df,
        train_size=percent / 100,
        random_state=random_state,
        stratify=df[STRATIFY_ON],
    )
    return sample.sort_index()


def write(df: pd.DataFrame, path: pathlib.Path, gzip: bool) -> list[pathlib.Path]:
    df.to_csv(path, index=False)
    escritos = [path]
    if gzip:
        gz = path.with_suffix('.csv.gz')
        df.to_csv(gz, index=False, compression='gzip')
        escritos.append(gz)
    return escritos


def fit_budget(df: pd.DataFrame, path: pathlib.Path, max_bytes: int,
               random_state: int) -> pd.DataFrame:
    """Recorta el dataset hasta que su CSV quepa en max_bytes.

    Con la codificacion por identificadores el dataset completo pesa ~6.4 MB y
    normalmente no entra aqui; es una red de seguridad para datasets mas grandes.
    """
    actual = df
    for intento in range(1, 6):
        actual.to_csv(path, index=False)
        size = path.stat().st_size
        if size <= max_bytes:
            if intento > 1:
                print(f'  ajuste: {len(actual):,} filas caben en {max_bytes / 1e6:.1f} MB')
            return actual
        # Margen del 3 % para no quedarse justo en el limite.
        objetivo = len(actual) * (max_bytes / size) * 0.97
        fraccion = objetivo / len(df)
        print(f'  intento {intento}: {size / 1e6:.2f} MB > {max_bytes / 1e6:.1f} MB, '
              f'recortando a {fraccion:.1%} del origen')
        actual, _ = train_test_split(
            df, train_size=fraccion, random_state=random_state,
            stratify=df[STRATIFY_ON])
        actual = actual.sort_index()
    raise SystemExit(f'ERROR: no se logro ajustar el dataset a {max_bytes} bytes.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='data/INM_estatal_dic25.csv')
    parser.add_argument('--outdir', default='data/versions')
    parser.add_argument('--data-dir', default='data',
                        help='donde se escriben las tablas de consulta')
    parser.add_argument('--prefix', default='incidencia')
    parser.add_argument('--random-state', type=int, default=42)
    parser.add_argument('--max-bytes', type=int, default=DEFAULT_MAX_BYTES,
                        help='tamanio maximo del CSV del 100 %% (limite de Cloudinary)')
    parser.add_argument('--gzip', action='store_true',
                        help='escribe tambien <archivo>.csv.gz')
    args = parser.parse_args()

    source = pathlib.Path(args.source)
    if not source.exists():
        print(f'ERROR: no se encontro el dataset de origen: {source}', file=sys.stderr)
        return 1

    print(f'Origen: {source}')
    encoded = encode(source, pathlib.Path(args.data_dir))
    print(f'\nCodificado: {len(encoded):,} registros, {len(encoded.columns)} columnas '
          f'({", ".join(encoded.columns)})')
    print(f'Estratificado por: {STRATIFY_ON} ({encoded[STRATIFY_ON].nunique()} clases)')
    print(f'Etiqueta: {LABEL} (media {encoded[LABEL].mean():.2f}, '
          f'max {encoded[LABEL].max()}, ceros {(encoded[LABEL] == 0).mean():.1%})\n')

    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # El 100 % se escribe primero y se ajusta al presupuesto; el 50 % y el 25 %
    # se derivan de ese archivo, no del origen.
    path_100 = outdir / f'{args.prefix}_100.csv'
    base = fit_budget(encoded, path_100, args.max_bytes, args.random_state)
    write(base, path_100, args.gzip)

    filas = {100: base}
    for percent in FRACTIONS:
        filas[percent] = subset(base, percent, args.random_state)
        write(filas[percent], outdir / f'{args.prefix}_{percent}.csv', args.gzip)

    print(f'{"version":>8} {"registros":>10} {"% del origen":>13} '
          f'{"CSV":>9} {"CSV.gz":>9} {"media":>8}')
    for percent in (100, 50, 25):
        d = filas[percent]
        path = outdir / f'{args.prefix}_{percent}.csv'
        gz = path.with_suffix('.csv.gz')
        tamanio_gz = f'{gz.stat().st_size / 1e6:.2f} MB' if gz.exists() else '-'
        print(f'{percent:>7}% {len(d):>10,} {len(d) / len(encoded):>12.1%} '
              f'{path.stat().st_size / 1e6:>6.2f} MB {tamanio_gz:>9} '
              f'{d[LABEL].mean():>8.2f}')

    if any((outdir / f'{args.prefix}_{p}.csv').stat().st_size > args.max_bytes
           for p in (100, 50, 25)):
        print('\nADVERTENCIA: algun archivo supera el limite.', file=sys.stderr)
        return 1
    print(f'\nTodos los archivos caben en {args.max_bytes / 1e6:.1f} MB: '
          'listos para subir a Cloudinary.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

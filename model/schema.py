"""Esquema compartido del dataset de incidencia delictiva.

Lo importan model/train.py (entrenamiento) y app.py (inferencia), para que
ambos coincidan en el orden de las columnas y en como se reconstruyen las
categorias. Si cambia FEATURES hay que reentrenar: el pipeline indexa por
nombre de columna.

Los CSV que viajan a Cloudinary estan codificados con identificadores en lugar
de texto ('id_delito' en vez de las cuatro columnas de la jerarquia del delito,
'clave_ent' en vez del nombre del estado). Asi el dataset completo de 413 952
registros ocupa 6.4 MB y entra en el limite de 10 MB de Cloudinary, en lugar de
los 47 MB que ocupaba con las categorias en texto. Las tablas de consulta
(data/catalogo_delitos.csv y data/catalogo_entidades.csv) viven en el
repositorio: pesan 9 KB entre las dos.
"""
import pathlib

import pandas as pd

LABEL = 'incidencia_delictiva'

# Jerarquia del delito, de lo general a lo especifico. Cada nivel acota al
# siguiente; 'modalidad' por si sola NO identifica al padre (el mismo nombre de
# modalidad aparece bajo 12 subtipos distintos), por eso el catalogo guarda las
# 98 combinaciones completas.
HIERARCHY = ['bien_juridico_afectado', 'tipo_delito', 'subtipo_delito', 'modalidad']

NUM_FEATURES = ['anio']
CAT_FEATURES = ['mes', 'clave_ent'] + HIERARCHY
# Orden exacto de las columnas de entrada del modelo. No cambiar sin reentrenar.
FEATURES = NUM_FEATURES + CAT_FEATURES

# Columnas de los CSV versionados, en este orden.
ID_COLUMNS = ['anio', 'mes', 'clave_ent', 'id_delito', LABEL]

MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio',
         'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
MES_A_NUMERO = {nombre: i + 1 for i, nombre in enumerate(MESES)}

CATALOGO_DELITOS = 'catalogo_delitos.csv'
CATALOGO_ENTIDADES = 'catalogo_entidades.csv'


def load_catalogs(data_dir: pathlib.Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carga las dos tablas de consulta que decodifican los CSV versionados."""
    delitos_path = data_dir / CATALOGO_DELITOS
    entidades_path = data_dir / CATALOGO_ENTIDADES
    for path in (delitos_path, entidades_path):
        if not path.exists():
            raise SystemExit(
                f'ERROR: falta la tabla de consulta {path}. '
                'Generala con: python scripts/make_datasets.py'
            )
    return pd.read_csv(delitos_path), pd.read_csv(entidades_path)


def rehydrate(df: pd.DataFrame, delitos: pd.DataFrame) -> pd.DataFrame:
    """Devuelve el dataset con las cuatro columnas de la jerarquia en texto."""
    if 'id_delito' not in df.columns:
        raise SystemExit(
            f"ERROR: el dataset no contiene la columna 'id_delito'. "
            f'Columnas encontradas: {list(df.columns)}'
        )
    merged = df.merge(delitos, on='id_delito', how='left', validate='many_to_one')
    desconocidos = merged[HIERARCHY[0]].isna().sum()
    if desconocidos:
        ids = sorted(df.loc[merged[HIERARCHY[0]].isna(), 'id_delito'].unique())
        raise SystemExit(
            f'ERROR: {desconocidos} registros traen id_delito fuera del catalogo: {ids[:10]}. '
            f'El dataset y {CATALOGO_DELITOS} no corresponden a la misma version.'
        )
    return merged


def build_catalog_json(df: pd.DataFrame, entidades: pd.DataFrame) -> dict:
    """Valores validos de cada campo, con la jerarquia de delitos anidada.

    El frontend lo consume en GET /catalog para poblar listas desplegables
    encadenadas, de modo que no se pueda enviar una combinacion inexistente.
    """
    jerarquia: dict = {}
    for bien, tipo, subtipo, modalidad in (
            df[HIERARCHY].drop_duplicates().itertuples(index=False)):
        (jerarquia
         .setdefault(bien, {})
         .setdefault(tipo, {})
         .setdefault(subtipo, set())
         .add(modalidad))
    jerarquia = {
        bien: {
            tipo: {sub: sorted(mods) for sub, mods in sorted(subs.items())}
            for tipo, subs in sorted(tipos.items())
        }
        for bien, tipos in sorted(jerarquia.items())
    }

    presentes = set(df['clave_ent'].unique())
    return {
        'anios': [int(df.anio.min()), int(df.anio.max())],
        'meses': [{'numero': i + 1, 'nombre': n} for i, n in enumerate(MESES)],
        'entidades': [
            {'clave_ent': int(r.clave_ent), 'entidad': r.entidad}
            for r in entidades.sort_values('clave_ent').itertuples(index=False)
            if int(r.clave_ent) in presentes
        ],
        'jerarquia': jerarquia,
        'label': LABEL,
        'features': FEATURES,
    }

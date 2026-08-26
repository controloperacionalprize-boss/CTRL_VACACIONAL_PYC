from __future__ import annotations

import re
import pandas as pd

def norm_col(x) -> str:
    x = str(x).strip().upper()
    x = re.sub(r"\s+", "_", x)
    x = re.sub(r"[^A-Z0-9_ÁÉÍÓÚÑ]", "", x)
    return x


def parse_date_column(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce")
    mixed = pd.to_datetime(series, errors="coerce")
    if mixed.notna().all():
        return mixed
    dayfirst = pd.to_datetime(series, errors="coerce", dayfirst=True)
    return dayfirst.where(mixed.isna(), mixed)


def normalize_workers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [norm_col(c) for c in df.columns]
    aliases = {
        "NOMBRE_COMPLETO": "NOMBRE",
        "NOMBRE_Y_APELLIDO": "NOMBRE",
        "JEFE": "JEFATURA",
        "JEFATURA_RESPONSABLE": "JEFATURA",
        "TIPO": "TIPO_PERSONAL",
        "TIPO_EMPLEADO": "TIPO_PERSONAL",
        "CARGO_TIPO": "TIPO_PERSONAL",
        "DIVISIÓN": "DIVISION",
        "DIVISION_": "DIVISION",
        "F_INGRESO": "FECHA_INGRESO",
        "F_DE_INGRESO": "FECHA_INGRESO",
        "FECHA_DE_INGRESO": "FECHA_INGRESO",
        "FECHA_ING": "FECHA_INGRESO",
        "CARGO": "CARGO_ACTUAL",
        "CARGO_ACTUAL_": "CARGO_ACTUAL",
        "ESTADO": "VIGENCIA",
        "ESTADO_VIGENCIA": "VIGENCIA",
        "SITUACION": "VIGENCIA",
        "F_CESE": "FECHA_CESE",
        "FECHA_DE_CESE": "FECHA_CESE",
        "FECHA_RETIRO": "FECHA_CESE",
        "F_RETIRO": "FECHA_CESE",
        "FECHA_BAJA": "FECHA_CESE",
        "F_BAJA": "FECHA_CESE",
    }
    for old, new in aliases.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]

    base_required = [
        "NOMBRE",
        "DNI",
        "GERENCIA",
        "AREA",
        "EMPRESA",
        "DIVISION",
        "FECHA_INGRESO",
        "CARGO_ACTUAL",
    ]
    missing = [c for c in base_required if c not in df.columns]
    if missing:
        raise ValueError(
            "Faltan columnas obligatorias en MASTER_EMPLEADO: " + ", ".join(missing)
        )

    if "JEFATURA" not in df.columns:
        df["JEFATURA"] = df["AREA"]
    if "TIPO_PERSONAL" not in df.columns:
        df["TIPO_PERSONAL"] = "ADMINISTRATIVO"

    text_cols = [
        "NOMBRE",
        "DNI",
        "GERENCIA",
        "AREA",
        "JEFATURA",
        "TIPO_PERSONAL",
        "EMPRESA",
        "DIVISION",
        "CARGO_ACTUAL",
    ]
    for c in text_cols:
        df[c] = df[c].fillna("").astype(str).str.strip()
    df.loc[df["JEFATURA"].eq(""), "JEFATURA"] = df.loc[df["JEFATURA"].eq(""), "AREA"]
    df["DNI"] = df["DNI"].str.replace(r"\.0$", "", regex=True)
    df["TIPO_PERSONAL"] = df["TIPO_PERSONAL"].str.upper().replace(
        {"OPERARIO": "OPERATIVO", "OBRERO": "OPERATIVO", "CAMPO": "OPERATIVO"}
    )
    df["FECHA_INGRESO"] = parse_date_column(df["FECHA_INGRESO"]).dt.date
    if "VIGENCIA" not in df.columns:
        df["VIGENCIA"] = ""
    df["VIGENCIA"] = df["VIGENCIA"].fillna("").astype(str).str.strip()
    if "FECHA_CESE" not in df.columns:
        df["FECHA_CESE"] = pd.NaT
    else:
        df["FECHA_CESE"] = parse_date_column(df["FECHA_CESE"]).dt.date
    return df[text_cols + ["FECHA_INGRESO", "VIGENCIA", "FECHA_CESE"]].drop_duplicates(subset=["DNI"]).reset_index(drop=True)


def normalize_cronograma(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["DNI", "FECHA_INICIO", "FECHA_FIN"])
    df = df.copy()
    df.columns = [norm_col(c) for c in df.columns]
    aliases = {
        "FECHA_DE_INICIO": "FECHA_INICIO",
        "FECHA_INICIO_VACACIONES": "FECHA_INICIO",
        "F_INICIO": "FECHA_INICIO",
        "FECHA_DE_TERMINO": "FECHA_FIN",
        "FECHA_TERMINO": "FECHA_FIN",
        "FECHA_FIN_VACACIONES": "FECHA_FIN",
        "F_TERMINO": "FECHA_FIN",
        "F_FIN": "FECHA_FIN",
        "N_DE_DÍAS": "N_DIAS",
        "N_DE_DIAS": "N_DIAS",
        "NÚMERO_DE_DÍAS": "N_DIAS",
        "NUMERO_DE_DIAS": "N_DIAS",
        "DIAS": "N_DIAS",
        "RECORD": "RECORD_VACACIONAL",
        "OBSERVACIÓN": "OBSERVACION",
        "OBSERVACIONES": "OBSERVACION",
        "OBS": "OBSERVACION",
        "OBS_PAGOS": "OBS_PAGOS",
        "OBS__PAGOS": "OBS_PAGOS",
    }
    for old, new in aliases.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]
    required = ["DNI", "FECHA_INICIO", "FECHA_FIN"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("La hoja CRONOGRAMA no tiene las columnas: " + ", ".join(missing))
    df["DNI"] = df["DNI"].fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    df["FECHA_INICIO"] = parse_date_column(df["FECHA_INICIO"]).dt.date
    df["FECHA_FIN"] = parse_date_column(df["FECHA_FIN"]).dt.date
    if "NOMBRE" not in df.columns:
        df["NOMBRE"] = ""
    if "N_DIAS" not in df.columns:
        df["N_DIAS"] = None
    if "RECORD_VACACIONAL" not in df.columns:
        df["RECORD_VACACIONAL"] = ""
    if "OBSERVACION" not in df.columns:
        df["OBSERVACION"] = ""
    if "OBS_PAGOS" not in df.columns:
        df["OBS_PAGOS"] = ""
    df["NOMBRE"] = df["NOMBRE"].fillna("").astype(str).str.strip()
    df["RECORD_VACACIONAL"] = df["RECORD_VACACIONAL"].fillna("").astype(str).str.strip()
    df["OBSERVACION"] = df["OBSERVACION"].fillna("").astype(str).str.strip()
    df["OBS_PAGOS"] = df["OBS_PAGOS"].fillna("").astype(str).str.strip()
    df = df[df["DNI"].ne("")]
    df = df.dropna(subset=["FECHA_INICIO", "FECHA_FIN"])
    cols = ["DNI", "NOMBRE", "FECHA_INICIO", "FECHA_FIN", "N_DIAS", "RECORD_VACACIONAL", "OBSERVACION", "OBS_PAGOS"]
    return df[cols].reset_index(drop=True)


def normalize_users(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [norm_col(c) for c in df.columns]
    aliases = {
        "USERNAME": "USUARIO",
        "LOGIN": "USUARIO",
        "NOMBRE": "NOMBRE_PERSONA",
        "NOMBRE_COMPLETO": "NOMBRE_PERSONA",
        "PERSONA": "NOMBRE_PERSONA",
        "EMAIL": "CORREO",
        "E_MAIL": "CORREO",
        "MAIL": "CORREO",
        "CORREO_CORPORATIVO": "CORREO",
        "GERENCIA_USUARIO": "GERENCIA",
        "ROL_USUARIO": "ROL",
        "ESTADO": "ACTIVO",
    }
    for old, new in aliases.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]
    required = [
        "USUARIO",
        "NOMBRE_USUARIO",
        "GERENCIA",
        "ROL",
        "ACTIVO",
        "NOMBRE_PERSONA",
        "CORREO",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("El maestro de usuarios no tiene las columnas: " + ", ".join(missing))
    for c in required:
        df[c] = df[c].fillna("").astype(str).str.strip()
    df["USUARIO"] = df["USUARIO"].str.lower()
    df["CORREO"] = df["CORREO"].str.lower()
    df["ACTIVO"] = df["ACTIVO"].str.upper()
    df["ROL"] = df["ROL"].str.upper()
    return df[required].drop_duplicates("CORREO").reset_index(drop=True)


def normalize_vacation_records(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df = df.copy()
    df.columns = [norm_col(c) for c in df.columns]
    aliases = {
        "NOMBRES_Y_APELLIDOS": "NOMBRE",
        "NOMBRES": "NOMBRE",
        "FECHA_DE_INGRESO": "FECHA_INGRESO",
        "SUB_AREA": "SUB_AREA",
        "SUBAREA": "SUB_AREA",
        "DESDE_PERIODO": "DESDE_PERIODO",
        "HASTA_PERIODO": "HASTA_PERIODO",
        "CUMPLE_RECORD": "CUMPLE_RECORD",
        "DIAS_PENDIENTES": "DIAS_PENDIENTES",
        "DIAS_GOZADOS": "DIAS_GOZADOS",
        "PROGRAMADO_SINO": "PROGRAMADO",
        "PROGRAMADO": "PROGRAMADO",
        "FECHA_VEN": "FECHA_VENCIMIENTO",
        "FECHA_VENCIMIENTO": "FECHA_VENCIMIENTO",
        "FECHA_LÍMITE": "FECHA_LIMITE",
        "FECHA_LIMITE": "FECHA_LIMITE",
    }
    for old, new in aliases.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]
    if "DNI" not in df.columns:
        return pd.DataFrame()
    df["DNI"] = df["DNI"].fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    for col in ["EMPRESA", "NOMBRE", "DIVISION", "SUB_AREA", "RECORD_VACACIONAL", "PROGRAMADO", "OBS1"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()
    for col in ["FECHA_INGRESO", "CUMPLE_RECORD", "FECHA_VENCIMIENTO", "FECHA_LIMITE"]:
        if col in df.columns:
            df[col] = parse_date_column(df[col]).dt.date
        else:
            df[col] = None
    for col in ["DESDE_PERIODO", "HASTA_PERIODO", "DIAS_PENDIENTES", "DIAS_GOZADOS"]:
        if col not in df.columns:
            df[col] = None
    df = df[df["DNI"].ne("")]
    return df.reset_index(drop=True)


def is_user_active(activo: str | bool) -> bool:
    if isinstance(activo, bool):
        return activo
    return str(activo).upper() in {"SI", "SÍ", "1", "TRUE", "ACTIVO", "T"}


_NO_VIGENTE = {
    "NO",
    "N",
    "0",
    "FALSE",
    "CESADO",
    "CESADA",
    "INACTIVO",
    "BAJA",
    "RETIRADO",
    "RETIRADA",
    "NO VIGENTE",
    "NO_VIGENTE",
    "F",
}


def is_worker_vigente(value) -> bool:
    if value is None or value is True:
        return True
    if value is False:
        return False
    text = str(value).strip().upper()
    if text == "" or text in {"NAN", "NONE", "NAT"}:
        return True
    if text in _NO_VIGENTE or text.startswith("CESAD") or text.startswith("INACTIV") or text.startswith("RETIR"):
        return False
    return True


def read_master_and_cronograma(path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    xls = pd.ExcelFile(path)
    names = xls.sheet_names
    if "MASTER_EMPLEADO" in names:
        master = xls.parse("MASTER_EMPLEADO")
    else:
        master = xls.parse(names[0])
    cronograma = xls.parse("CRONOGRAMA") if "CRONOGRAMA" in names else pd.DataFrame()
    record = pd.DataFrame()
    for candidate in ("RECORD_VACACIONALES", "RECORD_VACACIONAL", "RECORD"):
        if candidate in names:
            record = xls.parse(candidate)
            break
    return master, cronograma, record

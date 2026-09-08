"""Excel de flujo: una sola hoja según el rol (PERIODOS o FLUJO)."""
from __future__ import annotations

from datetime import date
from io import BytesIO

from openpyxl import load_workbook
import pandas as pd

from .calendar import parse_iso_date
from .excel_norm import norm_col, parse_date_column
from .export import _style_workbook
from .plan import group_periods
from .workflow import ESTADOS

FLUJO_COLS = [
    "DNI",
    "NOMBRE",
    "AREA",
    "GERENCIA",
    "FECHA_INGRESO",
    "CUMPLE_RECORD",
    "APTO",
    "DIAS_PROGRAMADOS",
    "ESTADO",
    "OBSERVACION",
    "ENVIADO_POR",
    "VALIDADO_POR",
    "RECEPCIONADO_POR",
]

PERIODOS_COLS = ["DNI", "NOMBRE", "AREA", "FECHA_INICIO", "FECHA_FIN"]

# Límites defensivos del Excel cargado (evitan filas/rangos absurdos que degraden el servicio).
MAX_FLUJO_ROWS = 500
MAX_PERIODOS_ROWS = 2000
MAX_PERIODO_DIAS = 60


def _fmt(d: date | str | None) -> str:
    if isinstance(d, date):
        return d.strftime("%d/%m/%Y")
    parsed = parse_iso_date(d)
    return parsed.strftime("%d/%m/%Y") if isinstance(parsed, date) else ""


def _periodos_rows(aptos: list[dict], daily_set, year: int) -> list[dict]:
    periods = group_periods(aptos, daily_set, year)
    emp = {str(w["dni"]): w for w in aptos}
    rows = []
    seen: set[str] = set()
    for p in periods:
        dni = str(p["dni"])
        seen.add(dni)
        w = emp.get(dni) or {}
        rows.append({
            "DNI": dni,
            "NOMBRE": w.get("nombre") or p.get("nombre") or "",
            "AREA": w.get("area") or "",
            "FECHA_INICIO": p["fecha_inicio"],
            "FECHA_FIN": p["fecha_fin"],
        })
    for w in sorted(aptos, key=lambda x: str(x.get("nombre") or "").casefold()):
        dni = str(w["dni"])
        if dni in seen:
            continue
        rows.append({
            "DNI": dni,
            "NOMBRE": w.get("nombre") or "",
            "AREA": w.get("area") or "",
            "FECHA_INICIO": "",
            "FECHA_FIN": "",
        })
    return rows


def build_flujo_excel(
    employees: list[dict],
    daily_set,
    targets,
    year: int,
    current_year: int,
    current_week: int,
    rol: str | None = None,
) -> bytes:
    from .workflow import programmed_days_for

    aptos = [w for w in employees if w.get("apto") or w.get("record_cumplido")]
    role = str(rol or "").upper()
    solo_flujo = role in {"GERENTE", "ADMIN"}

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if solo_flujo:
            flujo_rows = []
            for w in sorted(aptos, key=lambda x: str(x.get("nombre") or "").casefold()):
                dni = str(w["dni"])
                flujo_rows.append({
                    "DNI": dni,
                    "NOMBRE": w.get("nombre") or "",
                    "AREA": w.get("area") or "",
                    "GERENCIA": w.get("gerencia") or "",
                    "FECHA_INGRESO": _fmt(w.get("fecha_ingreso")),
                    "CUMPLE_RECORD": _fmt(w.get("cumple_record")),
                    "APTO": "SI" if w.get("apto") or w.get("record_cumplido") else "NO",
                    "DIAS_PROGRAMADOS": programmed_days_for(dni, daily_set, targets),
                    "ESTADO": w.get("flujo_estado") or "BORRADOR",
                    "OBSERVACION": w.get("flujo_observacion") or "",
                    "ENVIADO_POR": w.get("jefe_correo") or "",
                    "VALIDADO_POR": w.get("gerente_correo") or "",
                    "RECEPCIONADO_POR": w.get("admin_correo") or "",
                })
            pd.DataFrame(flujo_rows, columns=FLUJO_COLS).to_excel(writer, sheet_name="FLUJO", index=False)
        else:
            pd.DataFrame(_periodos_rows(aptos, daily_set, year), columns=PERIODOS_COLS).to_excel(
                writer, sheet_name="PERIODOS", index=False
            )
    output.seek(0)
    wb = load_workbook(output)
    _style_workbook(wb, year=year, current_year=current_year, current_week=current_week)
    out2 = BytesIO()
    wb.save(out2)
    out2.seek(0)
    return out2.getvalue()


def parse_flujo_upload(content: bytes) -> tuple[list[dict], list[dict]]:
    xl = pd.ExcelFile(BytesIO(content))
    names = {norm_col(n): n for n in xl.sheet_names}
    flujo_name = names.get("FLUJO")
    per_name = names.get("PERIODOS")
    if not flujo_name and not per_name:
        raise ValueError("El archivo debe tener la hoja PERIODOS (fechas) o FLUJO (estado).")

    flujo_rows = []
    if flujo_name:
        flujo_df = xl.parse(flujo_name)
        flujo_df.columns = [norm_col(c) for c in flujo_df.columns]
        if "DNI" not in flujo_df.columns:
            raise ValueError("La hoja FLUJO no tiene columna DNI.")
        flujo_df["DNI"] = flujo_df["DNI"].fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        if "ESTADO" not in flujo_df.columns:
            flujo_df["ESTADO"] = ""
        else:
            flujo_df["ESTADO"] = flujo_df["ESTADO"].fillna("").astype(str).str.strip().str.upper()
        if "OBSERVACION" not in flujo_df.columns:
            flujo_df["OBSERVACION"] = ""
        else:
            flujo_df["OBSERVACION"] = flujo_df["OBSERVACION"].fillna("").astype(str).str.strip()
        for r in flujo_df.to_dict("records"):
            dni = str(r["DNI"] or "").strip()
            if not dni:
                continue
            if len(flujo_rows) >= MAX_FLUJO_ROWS:
                raise ValueError(f"La hoja FLUJO tiene demasiadas filas (máximo {MAX_FLUJO_ROWS}).")
            estado = str(r.get("ESTADO") or "").strip().upper()
            if estado and estado not in ESTADOS:
                raise ValueError(
                    f"ESTADO no válido para {dni}: {estado}. Usa BORRADOR, ENVIADO, VALIDADO, RECEPCIONADO u OBSERVADO."
                )
            flujo_rows.append(
                {
                    "dni": dni,
                    "estado": estado,
                    "observacion": str(r.get("OBSERVACION") or "").strip(),
                }
            )

    periods: list[dict] = []
    if per_name:
        per_df = xl.parse(per_name)
        if len(per_df):
            per_df.columns = [norm_col(c) for c in per_df.columns]
            aliases = {
                "FECHA_DE_INICIO": "FECHA_INICIO",
                "F_INICIO": "FECHA_INICIO",
                "FECHA_DE_FIN": "FECHA_FIN",
                "F_FIN": "FECHA_FIN",
                "N_DE_DIAS": "N_DIAS",
            }
            for old, new in aliases.items():
                if old in per_df.columns and new not in per_df.columns:
                    per_df[new] = per_df[old]
            if "DNI" in per_df.columns and "FECHA_INICIO" in per_df.columns and "FECHA_FIN" in per_df.columns:
                per_df["DNI"] = per_df["DNI"].fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
                per_df["FECHA_INICIO"] = parse_date_column(per_df["FECHA_INICIO"]).dt.date
                per_df["FECHA_FIN"] = parse_date_column(per_df["FECHA_FIN"]).dt.date
                for r in per_df.to_dict("records"):
                    if not r["DNI"] or not r["FECHA_INICIO"] or not r["FECHA_FIN"]:
                        continue
                    if len(periods) >= MAX_PERIODOS_ROWS:
                        raise ValueError(f"La hoja PERIODOS tiene demasiadas filas (máximo {MAX_PERIODOS_ROWS}).")
                    dias = (r["FECHA_FIN"] - r["FECHA_INICIO"]).days + 1
                    if dias < 1:
                        raise ValueError(f"{r['DNI']}: FECHA_FIN no puede ser anterior a FECHA_INICIO.")
                    if dias > MAX_PERIODO_DIAS:
                        raise ValueError(
                            f"{r['DNI']}: el período {r['FECHA_INICIO']}–{r['FECHA_FIN']} son {dias} días "
                            f"(máximo {MAX_PERIODO_DIAS} por fila; usa varias filas si son varios períodos)."
                        )
                    periods.append(
                        {
                            "dni": r["DNI"],
                            "fecha_inicio": r["FECHA_INICIO"],
                            "fecha_fin": r["FECHA_FIN"],
                        }
                    )
    return flujo_rows, periods

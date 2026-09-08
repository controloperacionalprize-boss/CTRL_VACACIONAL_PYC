"""Flujo de validación: jefe envía aptos → gerente valida → admin recepciona."""
from __future__ import annotations

from datetime import date, datetime

from .calendar import (
    count_days_in_record,
    date_is_past,
    date_range,
    derecho_vigente,
    es_apto,
    fecha_record_cumplido,
    key_daily,
    parse_daily_key,
    parse_iso_date,
    record_cumplido,
    refresh_week_targets,
    reject_if_art8_invalido,
    reject_if_despues_de_vencimiento,
    reject_if_plan_not_completo,
    today_lima,
)
from ..org_scope import effective_role

BORRADOR = "BORRADOR"
ENVIADO = "ENVIADO"
VALIDADO = "VALIDADO"
RECEPCIONADO = "RECEPCIONADO"
OBSERVADO = "OBSERVADO"

ESTADOS = frozenset({BORRADOR, ENVIADO, VALIDADO, RECEPCIONADO, OBSERVADO})
EDITABLE = frozenset({BORRADOR, OBSERVADO})
CERRADO_JEFE = frozenset({ENVIADO, VALIDADO, RECEPCIONADO})

ESTADO_LABEL = {
    BORRADOR: "Borrador",
    ENVIADO: "Enviado al gerente",
    VALIDADO: "Validado por gerente",
    RECEPCIONADO: "Recepcionado",
    OBSERVADO: "Observado",
}


def norm_estado(valor: str | None) -> str:
    raw = str(valor or "").strip().upper()
    if raw in ESTADOS:
        return raw
    return BORRADOR


def flujo_from_row(row: dict | None) -> dict:
    if not row:
        return {
            "estado": BORRADOR,
            "apto": False,
            "cumple_record": None,
            "jefe_correo": "",
            "enviado_at": None,
            "gerente_correo": "",
            "validado_at": None,
            "admin_correo": "",
            "recepcionado_at": None,
            "observacion": "",
        }
    cumple = row.get("cumple_record")
    return {
        "estado": norm_estado(row.get("estado")),
        "apto": bool(row.get("apto")),
        "cumple_record": cumple.isoformat() if isinstance(cumple, date) else (str(cumple) if cumple else None),
        "jefe_correo": row.get("jefe_correo") or "",
        "enviado_at": _ts(row.get("enviado_at")),
        "gerente_correo": row.get("gerente_correo") or "",
        "validado_at": _ts(row.get("validado_at")),
        "admin_correo": row.get("admin_correo") or "",
        "recepcionado_at": _ts(row.get("recepcionado_at")),
        "observacion": row.get("observacion") or "",
    }


def _ts(value) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value:
        return str(value)
    return None


def cumple_record_de(emp: dict, today: date | None = None) -> date | None:
    ingreso = parse_iso_date(emp.get("fecha_ingreso"))
    if not isinstance(ingreso, date):
        return None
    return fecha_record_cumplido(ingreso)


def can_edit_days(user: dict, emp: dict, estado: str | None, today: date | None = None) -> bool:
    role = effective_role(user)
    estado = norm_estado(estado)
    if role == "ADMIN":
        return True
    if role == "GERENTE":
        return False
    if not es_apto(emp, today):
        return False
    return estado in EDITABLE


def reject_if_cannot_edit(user: dict, emp: dict, estado: str | None, today: date | None = None) -> None:
    role = effective_role(user)
    estado = norm_estado(estado)
    if role == "GERENTE":
        raise ValueError("El gerente no programa días: valida o observa en la bandeja.")
    if role != "ADMIN" and not es_apto(emp, today):
        raise ValueError(
            f"{emp.get('nombre') or 'Esta persona'} aún no cumple el año de servicio. "
            "Solo se programan trabajadores aptos."
        )
    if role != "ADMIN" and estado in CERRADO_JEFE:
        raise ValueError(
            f"El plan de {emp.get('nombre') or 'esta persona'} está {ESTADO_LABEL.get(estado, estado).lower()} "
            "y ya no se puede editar."
        )


def programmed_days_for(dni: str, daily_set, targets) -> int:
    n = 0
    if daily_set:
        prefix = f"{dni}|"
        n = sum(1 for item in daily_set if item.startswith(prefix))
    if n:
        return n
    return sum(int(dias) for (d, _w), dias in (targets or {}).items() if d == dni)


def goce_y_derecho(emp: dict, daily_set, targets, year: int, today: date | None = None) -> tuple[int, int, bool]:
    today = today or today_lima()
    ingreso = parse_iso_date(emp.get("fecha_ingreso"))
    adelanto = not record_cumplido(ingreso, today)
    derecho = derecho_vigente(ingreso, today)
    dni = str(emp["dni"])
    dias = count_days_in_record(daily_set, dni, year, today, ingreso)
    if not dias:
        dias = programmed_days_for(dni, daily_set, targets)
    return dias, derecho, adelanto


def reject_if_cannot_send(emp: dict, daily_set, targets, year: int, today: date | None = None) -> int:
    if not es_apto(emp, today):
        raise ValueError(
            f"{emp.get('nombre') or 'Esta persona'} aún no cumple el año y no se puede enviar."
        )
    dias, derecho, adelanto = goce_y_derecho(emp, daily_set, targets, year, today)
    reject_if_plan_not_completo(
        nombre=emp.get("nombre") or "",
        programados=dias,
        derecho=derecho,
        es_adelanto=adelanto,
    )
    reject_if_art8_invalido(daily_set, str(emp["dni"]), year)
    return dias


def allowed_transition(role: str, actual: str, destino: str) -> bool:
    actual = norm_estado(actual)
    destino = str(destino or "").strip().upper()
    if role == "JEFE" and actual in EDITABLE and destino == ENVIADO:
        return True
    if role == "GERENTE" and actual == ENVIADO and destino in {VALIDADO, OBSERVADO}:
        return True
    if role == "ADMIN" and actual == VALIDADO and destino in {RECEPCIONADO, OBSERVADO}:
        return True
    if role == "ADMIN" and actual in ESTADOS and destino == actual:
        return True
    return False


def apply_transition(row: dict, user: dict, destino: str, *, observacion: str = "", today: date | None = None) -> dict:
    role = effective_role(user)
    actual = norm_estado(row.get("estado"))
    destino = str(destino or "").strip().upper()
    if not allowed_transition(role, actual, destino):
        raise ValueError(
            f"No puedes pasar de {ESTADO_LABEL.get(actual, actual)} a {ESTADO_LABEL.get(destino, destino)}."
        )
    out = dict(row)
    out["estado"] = destino
    correo = user.get("correo") or ""
    if destino == ENVIADO:
        out["jefe_correo"] = correo
        out["enviado_at"] = "now"
        out["observacion"] = ""
        out["gerente_correo"] = ""
        out["validado_at"] = None
        out["admin_correo"] = ""
        out["recepcionado_at"] = None
    elif destino == VALIDADO:
        out["gerente_correo"] = correo
        out["validado_at"] = "now"
        out["observacion"] = ""
    elif destino == RECEPCIONADO:
        out["admin_correo"] = correo
        out["recepcionado_at"] = "now"
        out["observacion"] = ""
    elif destino == OBSERVADO:
        nota = (observacion or "").strip()
        if not nota:
            raise ValueError("Indica el motivo de la observación.")
        out["observacion"] = nota
        if role == "GERENTE":
            out["gerente_correo"] = correo
            out["validado_at"] = None
        else:
            out["admin_correo"] = correo
            out["recepcionado_at"] = None
    return out


def bandeja_estados_for(user: dict) -> list[str]:
    role = effective_role(user)
    if role == "GERENTE":
        return [ENVIADO]
    if role == "ADMIN":
        return [VALIDADO]
    if role == "JEFE":
        return [ENVIADO, VALIDADO, RECEPCIONADO, OBSERVADO]
    return []


def load_flujos(cur, year: int, dnis: list[str]) -> dict[str, dict]:
    if not dnis:
        return {}
    cur.execute(
        """SELECT anio, dni, estado, apto, cumple_record, jefe_correo, enviado_at,
                  gerente_correo, validado_at, admin_correo, recepcionado_at, observacion
           FROM plan_flujo WHERE anio = %s AND dni = ANY(%s)""",
        (year, [str(x) for x in dnis]),
    )
    return {str(r["dni"]): flujo_from_row(r) for r in cur.fetchall()}


def _stamp(flag) -> datetime | None:
    if flag == "now":
        return datetime.now()
    if isinstance(flag, datetime):
        return flag
    return None


def upsert_flujo(cur, year: int, dni: str, data: dict) -> None:
    cumple = data.get("cumple_record")
    if isinstance(cumple, str):
        cumple = parse_iso_date(cumple)
    enviado = _stamp(data.get("enviado_at"))
    validado = _stamp(data.get("validado_at"))
    recepcionado = _stamp(data.get("recepcionado_at"))
    cur.execute(
        """INSERT INTO plan_flujo (
               anio, dni, estado, apto, cumple_record, jefe_correo, enviado_at,
               gerente_correo, validado_at, admin_correo, recepcionado_at, observacion
           ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (anio, dni) DO UPDATE SET
               estado = EXCLUDED.estado,
               apto = EXCLUDED.apto,
               cumple_record = EXCLUDED.cumple_record,
               jefe_correo = EXCLUDED.jefe_correo,
               enviado_at = COALESCE(EXCLUDED.enviado_at, plan_flujo.enviado_at),
               gerente_correo = EXCLUDED.gerente_correo,
               validado_at = EXCLUDED.validado_at,
               admin_correo = EXCLUDED.admin_correo,
               recepcionado_at = EXCLUDED.recepcionado_at,
               observacion = EXCLUDED.observacion,
               actualizado = NOW()""",
        (
            year,
            str(dni),
            data["estado"],
            bool(data.get("apto")),
            cumple if isinstance(cumple, date) else None,
            data.get("jefe_correo") or "",
            enviado,
            data.get("gerente_correo") or "",
            validado,
            data.get("admin_correo") or "",
            recepcionado,
            data.get("observacion") or "",
        ),
    )


def enrich_workers(
    workers: list[dict],
    flujos: dict[str, dict],
    user: dict,
    today: date | None = None,
) -> list[dict]:
    today = today or today_lima()
    out = []
    for w in workers:
        dni = str(w["dni"])
        fl = flujos.get(dni) or flujo_from_row(None)
        apto = es_apto(w, today)
        cumple = cumple_record_de(w, today)
        out.append({
            **w,
            "jefe_correo": fl.get("jefe_correo") or "",
            "gerente_correo": fl.get("gerente_correo") or "",
            "admin_correo": fl.get("admin_correo") or "",
            "enviado_at": fl.get("enviado_at"),
            "validado_at": fl.get("validado_at"),
            "recepcionado_at": fl.get("recepcionado_at"),
            "flujo_estado": fl["estado"],
            "flujo_observacion": fl.get("observacion") or "",
            "apto": apto,
            "record_cumplido": apto,
            "cumple_record": cumple.isoformat() if cumple else None,
            "can_edit": can_edit_days(user, w, fl["estado"], today),
        })
    return out


def apply_uploaded_periods(
    daily_set: set[str],
    targets: dict,
    dni: str,
    year: int,
    periods: list[dict],
    today: date | None = None,
    fecha_ingreso: date | None = None,
    nombre: str = "",
) -> None:
    """Reemplaza días futuros del año con los tramos del Excel; conserva el pasado."""
    today = today or today_lima()
    prefix = f"{dni}|"
    keep = set()
    for item in list(daily_set):
        if not item.startswith(prefix):
            continue
        _, d = parse_daily_key(item)
        if d.isocalendar()[0] != year and d.year != year:
            continue
        if date_is_past(d, today):
            keep.add(item)
        daily_set.discard(item)
    daily_set.update(keep)
    nuevas: list[date] = []
    for per in periods:
        ini = per["fecha_inicio"]
        fin = per["fecha_fin"]
        if not isinstance(ini, date) or not isinstance(fin, date) or fin < ini:
            continue
        nuevas.extend(d for d in date_range(ini, fin) if not date_is_past(d, today))
    reject_if_despues_de_vencimiento(
        nuevas, fecha_ingreso, year, nombre=nombre, today=today
    )
    for d in nuevas:
        if d.isocalendar()[0] == year or d.year == year:
            daily_set.add(key_daily(dni, d))
    refresh_week_targets(daily_set, targets, dni, year, range(1, 54))

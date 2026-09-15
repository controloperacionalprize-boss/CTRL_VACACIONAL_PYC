"""Alertas de gestión vacacional: récord, mes siguiente y bandeja.

Se calculan sobre el plan real (empleados del alcance + días marcados + flujo).
No generan avisos genéricos: cada ítem dice quién, cuándo, quién actúa y a dónde ir.
"""
from __future__ import annotations

import calendar
from datetime import date

from .calendar import MESES_ES, parse_iso_date
from .workflow import (
    BORRADOR,
    ENVIADO,
    ESTADO_LABEL,
    OBSERVADO,
    VALIDADO,
)
from ..org_scope import fold_label

RECORD_WINDOW_DAYS = 93  # ~3 meses calendario
PRIORIDAD_RANK = {"informativa": 0, "proxima": 1, "importante": 2, "critica": 3}

TIPO_RECORD = "record_vence"
TIPO_MES = "mes_siguiente"
TIPO_SIN_PROGRAMAR = "sin_programar"
TIPO_PENDIENTES = "pendientes_flujo"

TIPOS = (TIPO_RECORD, TIPO_MES, TIPO_SIN_PROGRAMAR, TIPO_PENDIENTES)


def next_calendar_month(today: date) -> tuple[int, int]:
    if today.month == 12:
        return today.year + 1, 1
    return today.year, today.month + 1


def is_last_week_of_month(today: date) -> bool:
    last = calendar.monthrange(today.year, today.month)[1]
    return today.day >= last - 6


def month_label(year: int, month: int) -> str:
    return f"{MESES_ES.get(month, str(month))} {year}"


def format_fecha(d: date | None) -> str:
    if not isinstance(d, date):
        return "—"
    return d.strftime("%d/%m/%Y")


def _label_keys(*labels: str) -> set[str]:
    """Claves de área para cruzar jefe ↔ trabajador, sin mezclar áreas hermanas del mismo código."""
    keys: set[str] = set()
    for lab in labels:
        folded = fold_label(lab)
        if not folded:
            continue
        low = folded.lower()
        keys.add(low)
        compact = low.replace(" ", "")
        if compact:
            keys.add(compact)
    return keys


def attach_jefe_nombres(
    workers: list[dict],
    jefes: list[dict] | None,
    extras: list[dict] | None = None,
) -> list[dict]:
    """Completa jefe_nombre cruzando área/jefatura con jefes del maestro y, si falta, usuarios JEFE."""

    def indexed(rows: list[dict] | None) -> list[tuple[set[str], str, str]]:
        out: list[tuple[set[str], str, str]] = []
        for j in rows or []:
            nombre = (
                j.get("nombre")
                or j.get("nombre_persona")
                or j.get("nombre_usuario")
                or j.get("correo")
                or ""
            )
            nombre = str(nombre).strip()
            if not nombre:
                continue
            keys = _label_keys(j.get("area") or "", j.get("jefatura") or "")
            if keys:
                out.append((keys, nombre, str(j.get("dni") or "").strip()))
        return out

    def match_names(
        worker_keys: set[str],
        source: list[tuple[set[str], str, str]],
        *,
        skip_dni: str = "",
        skip_nombre: str = "",
    ) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        skip_fold = fold_label(skip_nombre)
        for jkeys, nombre, dni in source:
            if skip_dni and dni and dni == skip_dni:
                continue
            if skip_fold and fold_label(nombre) == skip_fold:
                continue
            if worker_keys & jkeys and nombre not in seen:
                seen.add(nombre)
                names.append(nombre)
        return names

    primary = indexed(jefes)
    secondary = indexed(extras)
    for w in workers:
        keys = _label_keys(w.get("area") or "", w.get("jefatura") or "")
        skip_dni = str(w.get("dni") or "").strip()
        skip_nombre = str(w.get("nombre") or "").strip()
        names = match_names(keys, primary, skip_dni=skip_dni, skip_nombre=skip_nombre) or match_names(
            keys, secondary, skip_dni=skip_dni, skip_nombre=skip_nombre
        )
        w["jefe_nombre"] = " · ".join(names)
    return workers


def _rank(p: str) -> int:
    return PRIORIDAD_RANK.get(p, 0)


def max_prioridad(*values: str) -> str:
    best = "informativa"
    for v in values:
        if _rank(v) > _rank(best):
            best = v
    return best


def prioridad_record(dias_restantes: int, total_dias: int, tope_dias: int) -> str:
    incompleto = total_dias < max(1, tope_dias)
    if dias_restantes < 0 and incompleto:
        return "critica"
    if dias_restantes <= 30 and incompleto:
        return "critica"
    if dias_restantes <= 45 and incompleto:
        return "importante"
    if dias_restantes <= 60:
        return "proxima"
    return "informativa"


def estado_planificacion(total_dias: int, tope_dias: int, flujo_estado: str) -> str:
    tope = max(0, tope_dias)
    if total_dias <= 0:
        base = "Sin programación"
    elif tope and total_dias >= tope:
        base = f"Completo ({total_dias}/{tope})"
    else:
        base = f"Parcial ({total_dias}/{tope or '—'})"
    flujo = ESTADO_LABEL.get(flujo_estado or BORRADOR, flujo_estado or BORRADOR)
    if flujo_estado in (None, "", BORRADOR) and total_dias <= 0:
        return base
    if flujo_estado in (None, "", BORRADOR):
        return f"{base} · Borrador"
    return f"{base} · {flujo}"


def responsable_texto(role: str, jefatura: str, area: str) -> str:
    lugar = (jefatura or area or "").strip() or "su área"
    if role == "JEFE":
        return f"Tú (jefatura {lugar})"
    if role == "GERENTE":
        return f"Jefatura de {lugar} programa; tú das seguimiento"
    return f"Jefatura de {lugar} programa; Personas y Cultura supervisa"


def accion_grupo(tipo: str, n: int, *, role: str = "", mes_label: str = "") -> str:
    """CTA del grupo completo: el listado, no un caso suelto."""
    if tipo == TIPO_PENDIENTES:
        if role == "GERENTE":
            return "Abrir bandeja para validar"
        if role == "ADMIN":
            return "Abrir bandeja para recepcionar"
        return "Abrir bandeja"
    if tipo == TIPO_MES and mes_label:
        return f"Ver listado de {mes_label.lower()}"
    if n == 1:
        return "Ver en Planificación"
    return f"Ver las {n} personas en Planificación"


def href_plan(tipo: str, dni: str = "", mes: str = "") -> str:
    q = [f"alerta={tipo}"]
    if mes:
        q.append(f"mes={mes}")
    if dni:
        q.append(f"dni={dni}")
    return "/?" + "&".join(q)


def href_detalle(tipo: str, mes: str = "") -> str:
    path = f"/alertas?tipo={tipo}"
    if mes:
        path += f"&mes={mes}"
    return path


def _persona_base(w: dict, role: str, tipo: str, extra: dict | None = None) -> dict:
    dni = str(w.get("dni") or "")
    jefatura = (w.get("jefatura") or "").strip()
    area = (w.get("area") or "").strip()
    flujo = w.get("flujo_estado") or BORRADOR
    total = int(w.get("total_dias") or 0)
    tope = int(w.get("tope_dias") or 0)
    vence = w.get("fecha_vencimiento")
    if isinstance(vence, str):
        vence = parse_iso_date(vence)
    dias_rest = w.get("dias_restantes")
    row = {
        "dni": dni,
        "nombre": w.get("nombre") or "",
        "area": area,
        "jefatura": jefatura,
        "gerencia": (w.get("gerencia") or w.get("division") or "").strip(),
        "division": (w.get("division") or w.get("gerencia") or "").strip(),
        "jefe_nombre": (w.get("jefe_nombre") or "").strip(),
        "fecha_vencimiento": vence.isoformat() if isinstance(vence, date) else None,
        "dias_restantes": dias_rest,
        "total_dias": total,
        "tope_dias": tope,
        "flujo_estado": flujo,
        "estado_plan": estado_planificacion(total, tope, flujo),
        "responsable": responsable_texto(role, jefatura, area),
        "href": href_plan(tipo, dni=dni, mes=(extra or {}).get("mes") or ""),
    }
    if extra:
        row.update(extra)
    return row


def _item(
    *,
    tipo: str,
    prioridad: str,
    titulo: str,
    descripcion: str,
    accion: str,
    responsable: str,
    responsable_rol: str,
    href: str,
    href_plan_vista: str,
    fecha_relevante: date | None,
    dias_restantes: int | None,
    personas: list[dict],
    extra: dict | None = None,
) -> dict:
    mes = (extra or {}).get("mes")
    payload = {
        "id": f"{tipo}:{mes}" if mes else tipo,
        "tipo": tipo,
        "prioridad": prioridad,
        "titulo": titulo,
        "descripcion": descripcion,
        "accion": accion,
        "responsable": responsable,
        "responsable_rol": responsable_rol,
        "href": href,
        "href_plan": href_plan_vista,
        "fecha_relevante": fecha_relevante.isoformat() if isinstance(fecha_relevante, date) else None,
        "dias_restantes": dias_restantes,
        "count": len(personas),
        "personas": personas,
        "en_inbox": True,
    }
    if extra:
        payload.update(extra)
    return payload


def collect_record_workers(workers: list[dict], today: date, window: int = RECORD_WINDOW_DAYS) -> list[dict]:
    out = []
    for w in workers:
        if w.get("apto") is False:
            continue
        vence = w.get("fecha_vencimiento")
        if isinstance(vence, str):
            vence = parse_iso_date(vence)
        if not isinstance(vence, date):
            continue
        dias = (vence - today).days
        if dias > window:
            continue
        row = dict(w)
        row["dias_restantes"] = dias
        row["_vence"] = vence
        out.append(row)
    out.sort(key=lambda r: (r["dias_restantes"], (r.get("nombre") or "").casefold()))
    return out


def collect_sin_programar(workers: list[dict]) -> list[dict]:
    out = []
    for w in workers:
        if w.get("apto") is False:
            continue
        if int(w.get("total_dias") or 0) > 0:
            continue
        out.append(w)
    out.sort(key=lambda r: (r.get("nombre") or "").casefold())
    return out


def collect_pendientes_flujo(workers: list[dict], role: str) -> list[dict]:
    if role == "GERENTE":
        wanted = {ENVIADO}
    elif role == "ADMIN":
        wanted = {VALIDADO}
    elif role == "JEFE":
        wanted = {OBSERVADO}
    else:
        return []
    out = [w for w in workers if (w.get("flujo_estado") or BORRADOR) in wanted]
    out.sort(key=lambda r: (r.get("nombre") or "").casefold())
    return out


def build_record_item(workers: list[dict], today: date, role: str) -> dict | None:
    if not workers:
        return None
    personas = []
    pris = []
    criticos = 0
    for w in workers:
        dias = int(w.get("dias_restantes") or 0)
        total = int(w.get("total_dias") or 0)
        tope = int(w.get("tope_dias") or 0)
        pri = prioridad_record(dias, total, tope)
        pris.append(pri)
        if pri == "critica":
            criticos += 1
        personas.append(_persona_base(w, role, TIPO_RECORD))
    n = len(personas)
    min_dias = min(int(w.get("dias_restantes") or 0) for w in workers)
    vence_min = min((w["_vence"] for w in workers if isinstance(w.get("_vence"), date)), default=None)
    sin_plan = sum(1 for w in workers if int(w.get("total_dias") or 0) == 0)
    if n == 1:
        p = personas[0]
        if min_dias < 0:
            desc = (
                f"{p['nombre']} tiene el récord vacacional vencido desde el {format_fecha(vence_min)} "
                f"y su planificación está {p['estado_plan'].lower()}."
            )
        else:
            desc = (
                f"{p['nombre']} tiene su récord vacacional próximo a cumplir "
                f"el {format_fecha(vence_min)} ({min_dias} día{'s' if min_dias != 1 else ''} restante"
                f"{'s' if min_dias != 1 else ''})."
            )
    else:
        if min_dias < 0:
            desc = (
                f"{n} trabajadores tienen el récord vacacional vencido o por vencer en los siguientes 3 meses."
            )
        else:
            desc = (
                f"{n} trabajadores tienen su récord vacacional próximo a vencer en los siguientes 3 meses."
            )
        if sin_plan:
            desc += f" {sin_plan} aún sin días programados."
        if criticos and criticos != n:
            desc += f" {criticos} caso{'s' if criticos != 1 else ''} crítico{'s' if criticos != 1 else ''}."
    return _item(
        tipo=TIPO_RECORD,
        prioridad=max_prioridad(*pris),
        titulo="Próximo vencimiento de récord",
        descripcion=desc,
        accion=accion_grupo(TIPO_RECORD, n, role=role),
        responsable="Jefatura programa · Gerencia sigue · Personas y Cultura supervisa",
        responsable_rol="JEFE",
        href=href_detalle(TIPO_RECORD),
        href_plan_vista=href_plan(TIPO_RECORD),
        fecha_relevante=vence_min,
        dias_restantes=min_dias,
        personas=personas,
    )


def build_mes_item(
    workers: list[dict],
    today: date,
    role: str,
    *,
    next_year: int,
    next_month: int,
    dias_por_dni: dict[str, list[date]],
) -> dict | None:
    if role not in {"JEFE", "GERENTE", "ADMIN"}:
        return None
    mes_key = f"{next_year:04d}-{next_month:02d}"
    label = month_label(next_year, next_month)
    last_week = is_last_week_of_month(today)
    personas = []
    for w in workers:
        dni = str(w.get("dni") or "")
        fechas = sorted(dias_por_dni.get(dni) or [])
        if not fechas:
            continue
        tramos = _group_ranges(fechas)
        resumen = " · ".join(f"{a.strftime('%d/%m')}–{b.strftime('%d/%m')}" for a, b in tramos[:3])
        extra = {
            "mes": mes_key,
            "dias_mes": len(fechas),
            "periodos_mes": resumen,
        }
        personas.append(_persona_base(w, role, TIPO_MES, extra))
    if not personas:
        return None
    n = len(personas)
    desc = (
        f"{n} trabajador{'es' if n != 1 else ''} tiene{'n' if n != 1 else ''} periodo vacacional "
        f"programado para {label.lower()}."
    )
    item = _item(
        tipo=TIPO_MES,
        prioridad="importante" if last_week else "informativa",
        titulo=f"Planificación de {label.lower()}",
        descripcion=desc,
        accion=accion_grupo(TIPO_MES, n, role=role, mes_label=label),
        responsable="Jefatura y Gerencia revisan el mes siguiente",
        responsable_rol="JEFE" if role == "JEFE" else "GERENTE",
        href=href_detalle(TIPO_MES, mes_key),
        href_plan_vista=href_plan(TIPO_MES, mes=mes_key),
        fecha_relevante=date(next_year, next_month, 1),
        dias_restantes=None,
        personas=personas,
        extra={"mes": mes_key, "mes_label": label},
    )
    item["en_inbox"] = last_week
    return item


def build_sin_programar_item(workers: list[dict], role: str, year: int) -> dict | None:
    if not workers:
        return None
    personas = [_persona_base(w, role, TIPO_SIN_PROGRAMAR) for w in workers]
    n = len(personas)
    if n == 1:
        p = personas[0]
        desc = (
            f"{p['nombre']} ({p['area'] or 'sin área'}) es apto y aún no tiene días "
            f"programados en {year}."
        )
    else:
        desc = f"{n} trabajadores aptos no tienen ningún día programado en {year}."
    return _item(
        tipo=TIPO_SIN_PROGRAMAR,
        prioridad="importante" if n >= 3 else "proxima",
        titulo="Casos sin programación",
        descripcion=desc,
        accion=accion_grupo(TIPO_SIN_PROGRAMAR, n, role=role),
        responsable=responsable_texto(role, "", ""),
        responsable_rol="JEFE",
        href=href_detalle(TIPO_SIN_PROGRAMAR),
        href_plan_vista=href_plan(TIPO_SIN_PROGRAMAR),
        fecha_relevante=None,
        dias_restantes=None,
        personas=personas,
    )


def build_pendientes_item(workers: list[dict], role: str) -> dict | None:
    if not workers:
        return None
    personas = [_persona_base(w, role, TIPO_PENDIENTES) for w in workers]
    n = len(personas)
    if role == "GERENTE":
        titulo = "Planes por validar"
        if n == 1:
            desc = (
                f"{personas[0]['nombre']} fue enviado por jefatura y espera tu validación "
                f"({personas[0]['area'] or 'sin área'})."
            )
        else:
            desc = f"{n} trabajadores enviados por jefatura esperan tu validación."
    elif role == "ADMIN":
        titulo = "Planes por recepcionar"
        if n == 1:
            desc = (
                f"{personas[0]['nombre']} ya fue validado por gerencia y espera recepción "
                f"de Personas y Cultura ({personas[0]['area'] or 'sin área'})."
            )
        else:
            desc = f"{n} trabajadores validados por gerencia esperan recepción de Personas y Cultura."
    else:
        titulo = "Planes observados"
        if n == 1:
            desc = (
                f"{personas[0]['nombre']} volvió con observación. "
                f"Corrige las fechas en Planificación y reenvía."
            )
        else:
            desc = (
                f"{n} trabajadores volvieron con observación. "
                f"Corrige las fechas en Planificación y reenvía."
            )
    return _item(
        tipo=TIPO_PENDIENTES,
        prioridad="importante",
        titulo=titulo,
        descripcion=desc,
        accion=accion_grupo(TIPO_PENDIENTES, n, role=role),
        responsable="Tú debes actuar ahora",
        responsable_rol=role,
        href="/validaciones",
        href_plan_vista="/validaciones",
        fecha_relevante=None,
        dias_restantes=None,
        personas=personas,
    )


def count_mes_siguiente(workers: list[dict], dias_por_dni: dict[str, list[date]]) -> int:
    n = 0
    for w in workers:
        dni = str(w.get("dni") or "")
        if dias_por_dni.get(dni):
            n += 1
    return n


def build_alerts(
    *,
    today: date,
    year: int,
    role: str,
    workers: list[dict],
    dias_mes_siguiente: dict[str, list[date]] | None = None,
) -> dict:
    """Arma el sobre de alertas para el alcance ya filtrado del usuario."""
    ny, nm = next_calendar_month(today)
    dias_mes = dias_mes_siguiente or {}
    record = collect_record_workers(workers, today)
    sin_prog = collect_sin_programar(workers)
    pendientes = collect_pendientes_flujo(workers, role)
    vac_mes = count_mes_siguiente(workers, dias_mes)

    items: list[dict] = []
    for builder in (
        build_pendientes_item(pendientes, role),
        build_record_item(record, today, role),
        build_mes_item(
            workers, today, role, next_year=ny, next_month=nm, dias_por_dni=dias_mes
        ),
        build_sin_programar_item(sin_prog, role, year),
    ):
        if builder:
            items.append(builder)

    items.sort(key=lambda it: (-_rank(it["prioridad"]), it["titulo"]))
    return {
        "today": today.isoformat(),
        "year": year,
        "rol": role,
        "ultima_semana_mes": is_last_week_of_month(today),
        "mes_siguiente": f"{ny:04d}-{nm:02d}",
        "mes_siguiente_label": month_label(ny, nm),
        "resumen": {
            "records_90": len(record),
            "vacaciones_mes_siguiente": vac_mes,
            "pendientes_plan": len(pendientes),
            "sin_programar": len(sin_prog),
        },
        "items": items,
    }


def dates_in_month(daily_set: set[str], year: int, month: int) -> dict[str, list[date]]:
    from .calendar import parse_daily_key

    out: dict[str, list[date]] = {}
    for item in daily_set:
        dni, d = parse_daily_key(item)
        if d.year == year and d.month == month:
            out.setdefault(dni, []).append(d)
    for fechas in out.values():
        fechas.sort()
    return out


def _group_ranges(fechas: list[date]) -> list[tuple[date, date]]:
    if not fechas:
        return []
    ranges = []
    start = prev = fechas[0]
    for d in fechas[1:]:
        if (d - prev).days == 1:
            prev = d
            continue
        ranges.append((start, prev))
        start = prev = d
    ranges.append((start, prev))
    return ranges

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

# Exclusiones futuras: DNIs que saltan   (solo lun–vie).
DNI_SOLO_DIAS_HABILES: frozenset[str] = frozenset()
MIN_DIAS = 0
MAX_DIAS = 7
# Derecho legal/planificado por año calendario ISO (misma cifra que UI calendario).
DERECHO_ANUAL = 30
# Acumulación mensual para adelanto (30 días ÷ 12 meses) antes de cumplir el récord anual.
DIAS_POR_MES_ADELANTO = DERECHO_ANUAL / 12
TOTAL_SEMANAS = 53
DIAS_SEMANA_CORTOS = ["L", "M", "M", "J", "V", "S", "D"]
DIAS_ES = {
    "Monday": "lun",
    "Tuesday": "mar",
    "Wednesday": "mie",
    "Thursday": "jue",
    "Friday": "vie",
    "Saturday": "sab",
    "Sunday": "dom",
}
MESES_ES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
}


def now_lima() -> str:
    return datetime.now(ZoneInfo("America/Lima")).strftime("%Y-%m-%d %H:%M:%S")


def today_lima() -> date:
    """Fecha de negocio (Lima); evita desfase UTC en servidores cloud."""
    return datetime.now(ZoneInfo("America/Lima")).date()


def iso_monday(year: int, week: int) -> date | None:
    try:
        return date.fromisocalendar(year, week, 1)
    except ValueError:
        return None


def week_dates(year: int, week: int) -> list[date]:
    monday = iso_monday(year, week)
    if monday is None:
        return []
    return [monday + timedelta(days=i) for i in range(7)]


def week_label(year: int, week: int) -> str:
    dates = week_dates(year, week)
    if not dates:
        return f"S{week}"
    return f"S{week} | {dates[0].strftime('%d/%m')} - {dates[-1].strftime('%d/%m')}"


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def is_business_day(d: date) -> bool:
    return d.weekday() < 5


def key_daily(dni: str, d: date) -> str:
    return f"{dni}|{d.isoformat()}"


def parse_daily_key(item: str) -> tuple[str, date]:
    dni, fecha = item.split("|", 1)
    return dni, date.fromisoformat(fecha)


def allowed_type(_tipo: str = "", dni: str | None = None) -> str:
    """Todos: días corridos. Si dni ∈ DNI_SOLO_DIAS_HABILES → solo lun–vie."""
    if dni is not None and str(dni).strip() in DNI_SOLO_DIAS_HABILES:
        return "HABIL"
    return "CALENDARIO"


def add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(month=2, day=28, year=d.year + years)


def selected_count(daily_set: set[str], dni: str, dates: Iterable[date]) -> int:
    return sum(key_daily(dni, d) in daily_set for d in dates)


def count_year_days(daily_set: set[str], dni: str, year: int) -> int:
    """Días de vacaciones del trabajador en el año ISO del plan."""
    prefix = f"{dni}|"
    n = 0
    for item in daily_set:
        if not item.startswith(prefix):
            continue
        _, d = parse_daily_key(item)
        if d.isocalendar()[0] == year:
            n += 1
    return n


def mensaje_sin_saldo(
    nombre: str,
    pedidas: int,
    programados: int,
    derecho: int = DERECHO_ANUAL,
    *,
    es_adelanto: bool = False,
) -> str:
    """Texto de error cuando el pedido supera el saldo del año (o el acumulado de adelanto)."""
    quien = (nombre or "").strip() or "Este trabajador"
    disponibles = max(derecho - programados, 0)
    etiqueta = "acumulado para adelanto" if es_adelanto else "derecho anual"
    if disponibles <= 0:
        extra = " (aún no cumple el año)" if es_adelanto else ""
        return (
            f"No se puede programar {pedidas} día(s) para {quien}: "
            f"ya tiene los {derecho} días de {etiqueta} programados{extra}."
        )
    return (
        f"No se puede programar {pedidas} día(s) para {quien}: "
        f"solo le quedan {disponibles} día(s) disponible(s) "
        f"({etiqueta} {derecho}, ya programados {programados})."
    )


def saldo_disponible(programados: int, derecho: int = DERECHO_ANUAL) -> int:
    return max(0, derecho - max(0, programados))


def reject_if_exceeds_saldo(
    *,
    nombre: str,
    pedidas: int,
    programados_base: int,
    derecho: int = DERECHO_ANUAL,
    es_adelanto: bool = False,
) -> None:
    """Rechazo rápido antes de mutar el plan (misma regla que ensure_within_derecho)."""
    if pedidas > saldo_disponible(programados_base, derecho):
        raise ValueError(mensaje_sin_saldo(nombre, pedidas, programados_base, derecho, es_adelanto=es_adelanto))


def ensure_within_derecho(
    daily_set: set[str],
    dni: str,
    year: int,
    *,
    nombre: str,
    pedidas: int,
    programados_base: int,
    derecho: int = DERECHO_ANUAL,
    es_adelanto: bool = False,
) -> None:
    """Falla si tras el cambio el año supera el derecho (30, o el acumulado si es adelanto)."""
    if count_year_days(daily_set, dni, year) > derecho:
        raise ValueError(mensaje_sin_saldo(nombre, pedidas, programados_base, derecho, es_adelanto=es_adelanto))


def parse_iso_date(value: object) -> date | None:
    """Convierte 'YYYY-MM-DD' (o date) a date; None si no es válido."""
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def meses_completos(fecha_ingreso: date | None, ref_date: date | None = None) -> int:
    """Meses calendario completos trabajados desde el ingreso (0 si aún no cumple 1 mes)."""
    ref_date = ref_date or today_lima()
    if not isinstance(fecha_ingreso, date) or fecha_ingreso > ref_date:
        return 0
    years = ref_date.year - fecha_ingreso.year
    months = ref_date.month - fecha_ingreso.month
    if ref_date.day < fecha_ingreso.day:
        months -= 1
    return max(0, years * 12 + months)


def fecha_record_cumplido(fecha_ingreso: date) -> date:
    """Fecha (aniversario) en la que el trabajador adquiere el derecho a los 30 días."""
    return add_years(fecha_ingreso, 1)


def record_cumplido(fecha_ingreso: date | None, ref_date: date | None = None) -> bool:
    """True si ya tiene un año de servicio (derecho completo). Sin fecha de ingreso: no se restringe."""
    if not isinstance(fecha_ingreso, date):
        return True
    ref_date = ref_date or today_lima()
    return ref_date >= fecha_record_cumplido(fecha_ingreso)


def dias_acumulados_adelanto(fecha_ingreso: date | None, ref_date: date | None = None) -> int:
    """Días ganados a razón de 2.5 por mes completo, antes de cumplir el récord anual (D.L. 1405)."""
    if not isinstance(fecha_ingreso, date):
        return DERECHO_ANUAL
    ref_date = ref_date or today_lima()
    meses = meses_completos(fecha_ingreso, ref_date)
    return min(DERECHO_ANUAL, int(meses * DIAS_POR_MES_ADELANTO))


def derecho_vigente(fecha_ingreso: date | None, ref_date: date | None = None) -> int:
    """Tope de días programables: 30 si ya cumplió el récord; si no, lo acumulado (adelanto)."""
    ref_date = ref_date or today_lima()
    if record_cumplido(fecha_ingreso, ref_date):
        return DERECHO_ANUAL
    return dias_acumulados_adelanto(fecha_ingreso, ref_date)


def vacation_record_for(
    fecha_ingreso: date | None,
    programmed: Iterable[date],
    view_year: int,
    today: date | None = None,
) -> dict:
    """Récord vacacional vivo: maestro (fecha_ingreso) + cronograma/plan (días marcados).

    El período es de aniversario a aniversario. En el año de vista se muestra el récord
    que se cumple ese año (o el primero, si aún no llega).
    """
    today = today or today_lima()
    programmed = [d for d in programmed if d.year == view_year or d.isocalendar()[0] == view_year]
    programados = len(programmed)
    gozados = sum(1 for d in programmed if d < today)
    if not isinstance(fecha_ingreso, date):
        return {
            "record_vacacional": "",
            "cumple_record": None,
            "fecha_vencimiento": None,
            "dias_programados": programados,
            "dias_gozados": gozados,
            "dias_pendientes": max(0, DERECHO_ANUAL - programados),
            "record_cumplido": False,
        }
    n = max(1, view_year - fecha_ingreso.year)
    cumple = add_years(fecha_ingreso, n)
    inicio = add_years(fecha_ingreso, n - 1)
    vencimiento = add_years(cumple, 1) - timedelta(days=1)
    return {
        "record_vacacional": f"{inicio.year}-{cumple.year}",
        "cumple_record": cumple,
        "fecha_vencimiento": vencimiento,
        "dias_programados": programados,
        "dias_gozados": gozados,
        "dias_pendientes": max(0, DERECHO_ANUAL - programados),
        "record_cumplido": today >= cumple,
    }


def clear_dates_for_week(
    daily_set: set[str],
    dni: str,
    year: int,
    week: int,
    *,
    today: date | None = None,
    keep_past: bool = False,
) -> None:
    today = today or today_lima()
    for d in week_dates(year, week):
        if keep_past and date_is_past(d, today):
            continue
        daily_set.discard(key_daily(dni, d))


def reject_if_fuera_de_anio_iso(fechas: list[date], year: int) -> None:
    """El tramo pedido debe caber entero en el año ISO del plan."""
    if not fechas:
        return
    fuera = [d for d in fechas if d.isocalendar()[0] != year]
    if not fuera:
        return
    last = fechas[-1]
    raise ValueError(
        f"Esos {len(fechas)} días corridos no caben en el año {year} "
        f"(llegarían hasta el {last.strftime('%d/%m/%Y')}). "
        f"Reduce los días o elige una fecha de inicio más temprana."
    )


def compute_consecutive_dates(
    tipo: str, start_date: date, number_of_days: int, dni: str | None = None
) -> list[date]:
    number_of_days = int(number_of_days)
    if number_of_days <= 0:
        return []
    modo = allowed_type(tipo, dni)
    d = start_date
    dates: list[date] = []
    while len(dates) < number_of_days:
        if modo == "CALENDARIO" or is_business_day(d):
            dates.append(d)
        d += timedelta(days=1)
    return dates


def reconcile_targets_with_daily(
    daily_set: set[str], targets: dict[tuple[str, int], int], year: int
) -> tuple[dict[tuple[str, int], int], bool]:
    counts: dict[tuple[str, int], int] = {}
    for item in daily_set:
        dni, d = parse_daily_key(item)
        iso_year, iso_week, _ = d.isocalendar()
        if iso_year != year:
            continue
        key = (dni, iso_week)
        counts[key] = counts.get(key, 0) + 1

    changed = False
    new_targets = dict(targets)
    for key in set(counts) | set(targets):
        real = min(counts.get(key, 0), 7)
        current = int(targets.get(key, 0))
        if real != current:
            changed = True
        if real > 0:
            new_targets[key] = real
        else:
            new_targets.pop(key, None)
    return new_targets, changed


def format_antiguedad(fecha_ingreso: date | None, ref_date: date | None = None) -> str:
    if not isinstance(fecha_ingreso, date):
        return "—"
    ref_date = ref_date or today_lima()
    if fecha_ingreso > ref_date:
        return "—"
    years = ref_date.year - fecha_ingreso.year
    months = ref_date.month - fecha_ingreso.month
    if ref_date.day < fecha_ingreso.day:
        months -= 1
    if months < 0:
        years -= 1
        months += 12
    parts = []
    if years:
        parts.append(f"{years} año" + ("s" if years != 1 else ""))
    parts.append(f"{months} mes" + ("es" if months != 1 else ""))
    return " ".join(parts)


def group_consecutive_dates(dates_sorted: list[date]) -> list[tuple[date, date]]:
    """Tramos de días corridos (Art. 8): solo fechas seguidas (gap = 1).

    No une lunes–viernes de semanas distintas saltando sáb/dom no gozados:
    eso no son 15 días corridos.
    """
    dates_sorted = sorted(dates_sorted)
    periods: list[tuple[date, date]] = []
    if not dates_sorted:
        return periods
    start = prev = dates_sorted[0]
    for d in dates_sorted[1:]:
        if (d - prev).days == 1:
            prev = d
            continue
        periods.append((start, prev))
        start = prev = d
    periods.append((start, prev))
    return periods


def reject_if_start_in_past(start_date: date, today: date | None = None) -> None:
    """No se programa vacaciones con inicio anterior a hoy."""
    today = today or today_lima()
    if start_date < today:
        raise ValueError(
            f"No se puede programar desde el {start_date.strftime('%d/%m/%Y')}: "
            f"solo desde hoy ({today.strftime('%d/%m/%Y')}) hacia adelante."
        )


def apply_consecutive_span(
    daily_set: set[str],
    targets: dict[tuple[str, int], int],
    dni: str,
    tipo: str,
    start_date: date,
    number_of_days: int,
    year: int,
    clear_week: int | None = None,
    today: date | None = None,
) -> tuple[list[date], list[tuple[int, int, int]]]:
    """Marca N días seguidos y actualiza el número de cada semana tocada."""
    today = today or today_lima()
    reject_if_start_in_past(start_date, today)
    if clear_week is not None:
        clear_dates_for_week(daily_set, dni, year, clear_week, today=today, keep_past=True)
    fechas = compute_consecutive_dates(tipo, start_date, number_of_days, dni)
    reject_if_fuera_de_anio_iso(fechas, year)
    in_year = [d for d in fechas if d.isocalendar()[0] == year]
    weeks = sorted({d.isocalendar()[1] for d in in_year})
    if clear_week is not None and clear_week not in weeks:
        weeks = sorted([clear_week, *weeks])
    locked = [wk for wk in weeks if week_is_locked(year, wk, today)]
    if locked:
        raise ValueError(
            f"La semana {locked[0]} ya pasó y no se puede cambiar."
            if len(locked) == 1
            else f"Las semanas {', '.join(str(w) for w in locked)} ya pasaron y no se pueden cambiar."
        )
    ignore = (
        {d for d in week_dates(year, clear_week) if not date_is_past(d, today)}
        if clear_week is not None
        else set()
    )
    reject_if_span_overlaps(daily_set, dni, in_year, ignore=ignore)
    for d in in_year:
        daily_set.add(key_daily(dni, d))
    deltas = refresh_week_targets(daily_set, targets, dni, year, weeks)
    reject_if_art8_invalido(daily_set, dni, year)
    return fechas, deltas


def dates_for_dni_year(daily_set: set[str], dni: str, year: int) -> list[date]:
    prefix = f"{dni}|"
    out: list[date] = []
    for item in daily_set:
        if not item.startswith(prefix):
            continue
        _, d = parse_daily_key(item)
        if d.isocalendar()[0] == year:
            out.append(d)
    return sorted(out)


def period_estado(ini: date, fin: date, today: date) -> str:
    if fin < today:
        return "gozado"
    if ini <= today:
        return "en_curso"
    return "programado"


def vacation_periods(
    daily_set: set[str], dni: str, year: int, today: date | None = None
) -> list[dict]:
    """Tramos corridos del trabajador en el año ISO del plan."""
    today = today or today_lima()
    dates = dates_for_dni_year(daily_set, dni, year)
    periods: list[dict] = []
    for ini, fin in group_consecutive_dates(dates):
        n = sum(1 for d in dates if ini <= d <= fin)
        estado = period_estado(ini, fin, today)
        periods.append({
            "inicio": ini,
            "fin": fin,
            "dias": n,
            "estado": estado,
            "editable": estado == "programado",
        })
    return periods


def art8_fraccion_ok(sizes: list[int]) -> bool:
    """D.S. 002-2019-TR Art. 8: un solo tramo, o ≥15 corridos, o dos tramos ≥7 y ≥8."""
    if len(sizes) <= 1:
        return True
    if any(s >= 15 for s in sizes):
        return True
    for i, a in enumerate(sizes):
        for j, b in enumerate(sizes):
            if i != j and a >= 7 and b >= 8:
                return True
    return False


def reject_if_art8_invalido(daily_set: set[str], dni: str, year: int) -> None:
    sizes = [p["dias"] for p in vacation_periods(daily_set, dni, year)]
    if art8_fraccion_ok(sizes):
        return
    raise ValueError(
        "El fraccionamiento no cumple el Art. 8 (D.S. 002-2019-TR): "
        "hace falta un bloque de al menos 15 días corridos, "
        "o dos bloques de al menos 7 y 8 días. El resto puede ser desde 1 día."
    )


def reject_if_span_overlaps(
    daily_set: set[str],
    dni: str,
    nuevas: Iterable[date],
    ignore: Iterable[date] | None = None,
) -> None:
    skip = {d.isoformat() for d in (ignore or [])}
    clash = [
        d for d in nuevas
        if d.isoformat() not in skip and key_daily(dni, d) in daily_set
    ]
    if not clash:
        return
    a, b = clash[0], clash[-1]
    rango = a.strftime("%d/%m/%Y") if a == b else f"{a.strftime('%d/%m/%Y')}–{b.strftime('%d/%m/%Y')}"
    raise ValueError(f"Esas fechas se cruzan con un período ya programado ({rango}).")


def refresh_week_targets(
    daily_set: set[str],
    targets: dict[tuple[str, int], int],
    dni: str,
    year: int,
    weeks: Iterable[int],
) -> list[tuple[int, int, int]]:
    deltas: list[tuple[int, int, int]] = []
    for wk in weeks:
        old = int(targets.get((dni, wk), 0))
        total = selected_count(daily_set, dni, week_dates(year, wk))
        new = min(total, 7) if total else 0
        if new:
            targets[(dni, wk)] = new
        else:
            targets.pop((dni, wk), None)
        deltas.append((wk, old, new))
    return deltas


def clear_period_dates(daily_set: set[str], dni: str, ini: date, fin: date) -> None:
    d = ini
    while d <= fin:
        daily_set.discard(key_daily(dni, d))
        d += timedelta(days=1)


def move_vacation_period(
    daily_set: set[str],
    targets: dict[tuple[str, int], int],
    dni: str,
    tipo: str,
    year: int,
    old_start: date,
    new_start: date,
    days: int | None = None,
    today: date | None = None,
) -> tuple[list[date], list[tuple[int, int, int]], dict]:
    """Reprograma un tramo futuro (mismos días salvo que se pida otro número). No descuenta dos veces."""
    today = today or today_lima()
    periods = vacation_periods(daily_set, dni, year, today)
    found = next((p for p in periods if p["inicio"] == old_start), None)
    if not found:
        raise ValueError("No se encontró ese período de vacaciones.")
    if not found["editable"]:
        raise ValueError(
            "Ese período ya comenzó o ya fue gozado; no se puede cambiar la fecha."
        )
    n = int(days) if days is not None else int(found["dias"])
    if n < 1:
        raise ValueError("Indica cuántos días tiene el período.")
    old_weeks = sorted({
        d.isocalendar()[1]
        for d in dates_for_dni_year(daily_set, dni, year)
        if found["inicio"] <= d <= found["fin"]
    })
    clear_period_dates(daily_set, dni, found["inicio"], found["fin"])
    nuevas, deltas_new = apply_consecutive_span(
        daily_set, targets, dni, tipo, new_start, n, year, today=today
    )
    extra_weeks = [wk for wk in old_weeks if wk not in {d[0] for d in deltas_new}]
    deltas_old = refresh_week_targets(daily_set, targets, dni, year, extra_weeks)
    merged = {wk: (wk, old, new) for wk, old, new in deltas_old}
    for wk, old, new in deltas_new:
        prev = merged.get(wk)
        merged[wk] = (wk, prev[1] if prev else old, new)
    return nuevas, list(merged.values()), found


def week_is_locked(year: int, week: int, today: date | None = None) -> bool:
    today = today or today_lima()
    current_year, current_week, _ = today.isocalendar()
    if year < current_year:
        return True
    if year == current_year and week < current_week:
        return True
    return False


def date_is_past(d: date, today: date | None = None) -> bool:
    """True si el día ya pasó (hoy sí se puede programar)."""
    today = today or today_lima()
    return d < today

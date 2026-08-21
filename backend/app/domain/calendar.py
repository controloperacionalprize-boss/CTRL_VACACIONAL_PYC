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


def mensaje_sin_saldo(nombre: str, pedidas: int, programados: int, derecho: int = DERECHO_ANUAL) -> str:
    """Texto de error cuando el pedido supera el saldo del año."""
    quien = (nombre or "").strip() or "Este trabajador"
    disponibles = max(derecho - programados, 0)
    if disponibles <= 0:
        return (
            f"No se puede programar {pedidas} día(s) para {quien}: "
            f"ya tiene los {derecho} días del derecho anual programados."
        )
    return (
        f"No se puede programar {pedidas} día(s) para {quien}: "
        f"solo le quedan {disponibles} día(s) disponible(s) "
        f"(derecho {derecho}, ya programados {programados})."
    )


def saldo_disponible(programados: int, derecho: int = DERECHO_ANUAL) -> int:
    return max(0, derecho - max(0, programados))


def reject_if_exceeds_saldo(
    *,
    nombre: str,
    pedidas: int,
    programados_base: int,
) -> None:
    """Rechazo rápido antes de mutar el plan (misma regla que ensure_within_derecho)."""
    if pedidas > saldo_disponible(programados_base):
        raise ValueError(mensaje_sin_saldo(nombre, pedidas, programados_base))


def ensure_within_derecho(
    daily_set: set[str],
    dni: str,
    year: int,
    *,
    nombre: str,
    pedidas: int,
    programados_base: int,
) -> None:
    """Falla si tras el cambio el año supera DERECHO_ANUAL."""
    if count_year_days(daily_set, dni, year) > DERECHO_ANUAL:
        raise ValueError(mensaje_sin_saldo(nombre, pedidas, programados_base))


def clear_dates_for_week(daily_set: set[str], dni: str, year: int, week: int) -> None:
    for d in week_dates(year, week):
        daily_set.discard(key_daily(dni, d))


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
    ref_date = ref_date or date.today()
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
    dates_sorted = sorted(dates_sorted)
    periods: list[tuple[date, date]] = []
    if not dates_sorted:
        return periods
    start = prev = dates_sorted[0]
    for d in dates_sorted[1:]:
        gap = (d - prev).days
        gap_dates = [prev + timedelta(days=i) for i in range(1, gap)]
        if gap == 1 or (gap_dates and all(is_weekend(g) for g in gap_dates)):
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
        clear_dates_for_week(daily_set, dni, year, clear_week)
    fechas = compute_consecutive_dates(tipo, start_date, number_of_days, dni)
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
    for d in in_year:
        daily_set.add(key_daily(dni, d))
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
    return fechas, deltas


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

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

TIPOS_CALENDARIO = {"OPERATIVO"}
TIPOS_HABILES = {"ADMINISTRATIVO", "SUBGERENCIA", "GERENCIA"}
MIN_DIAS = 0
MAX_DIAS = 7
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


def allowed_type(tipo: str) -> str:
    # Oficina (admin / gerencia): lun–vie. El resto, incluido operativo y tipos
    # no catalogados, toma sábados y domingo como días de vacaciones.
    if str(tipo).upper().strip() in TIPOS_HABILES:
        return "HABIL"
    return "CALENDARIO"


def add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(month=2, day=28, year=d.year + years)


def selected_count(daily_set: set[str], dni: str, dates: Iterable[date]) -> int:
    return sum(key_daily(dni, d) in daily_set for d in dates)


def clear_dates_for_week(daily_set: set[str], dni: str, year: int, week: int) -> None:
    for d in week_dates(year, week):
        daily_set.discard(key_daily(dni, d))


def compute_consecutive_dates(tipo: str, start_date: date, number_of_days: int) -> list[date]:
    number_of_days = int(number_of_days)
    if number_of_days <= 0:
        return []
    modo = allowed_type(tipo)
    d = start_date
    dates: list[date] = []
    while len(dates) < number_of_days:
        if modo == "CALENDARIO" or is_business_day(d):
            dates.append(d)
        d += timedelta(days=1)
    return dates


def apply_week_number(
    daily_set: set[str],
    dni: str,
    tipo: str,
    week: int,
    value: int,
    year: int,
) -> None:
    value = max(MIN_DIAS, min(MAX_DIAS, int(value)))
    clear_dates_for_week(daily_set, dni, year, week)
    dates = week_dates(year, week)
    if not dates or value == 0:
        return
    modo = allowed_type(tipo)
    if value < 7:
        return
    if modo == "CALENDARIO":
        for d in dates:
            daily_set.add(key_daily(dni, d))
    else:
        for d in dates:
            if is_business_day(d):
                daily_set.add(key_daily(dni, d))


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


def apply_consecutive_span(
    daily_set: set[str],
    targets: dict[tuple[str, int], int],
    dni: str,
    tipo: str,
    start_date: date,
    number_of_days: int,
    year: int,
    clear_week: int | None = None,
) -> tuple[list[date], list[tuple[int, int, int]]]:
    """Marca N días seguidos (según tipo) y actualiza el número de cada semana tocada."""
    if clear_week is not None:
        clear_dates_for_week(daily_set, dni, year, clear_week)
    fechas = compute_consecutive_dates(tipo, start_date, number_of_days)
    in_year = [d for d in fechas if d.isocalendar()[0] == year]
    weeks = sorted({d.isocalendar()[1] for d in in_year})
    if clear_week is not None and clear_week not in weeks:
        weeks = sorted([clear_week, *weeks])
    locked = [wk for wk in weeks if week_is_locked(year, wk)]
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
    today = today or date.today()
    current_year, current_week, _ = today.isocalendar()
    if year < current_year:
        return True
    if year == current_year and week < current_week:
        return True
    return False

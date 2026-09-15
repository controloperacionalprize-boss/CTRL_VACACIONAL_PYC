export const SEM_COLORS: Record<number, string> = {
  0: "transparent",
  1: "#F8696B",
  2: "#F8696B",
  3: "#F9C47A",
  4: "#FFEB84",
  5: "#FFEB84",
  6: "#9ED17A",
  7: "#63BE7B",
};

/** Lunes (YYYY-MM-DD) de la semana ISO. */
export function isoWeekMonday(year: number, week: number) {
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const day = jan4.getUTCDay() || 7;
  const monday = new Date(jan4);
  monday.setUTCDate(jan4.getUTCDate() - day + 1 + (week - 1) * 7);
  return monday.toISOString().slice(0, 10);
}

/** Lunes (YYYY-MM-DD) de la semana que contiene la fecha. */
export function mondayOf(iso: string) {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() || 7) - 1));
  return d.toISOString().slice(0, 10);
}

/**
 * Semana no editable: ya pasó, o empieza antes de la semana de `primerInicio`
 * (para la jefatura la semana cierra el viernes anterior; el backend envía ese día).
 */
export function weekLocked(
  year: number,
  week: number,
  currentYear: number,
  currentWeek: number,
  primerInicio?: string
) {
  if (year < currentYear) return true;
  if (year === currentYear && week < currentWeek) return true;
  return Boolean(primerInicio) && isoWeekMonday(year, week) < mondayOf(primerInicio!);
}

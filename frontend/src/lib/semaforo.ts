export const SEM_COLORS: Record<number, string> = {
  0: "transparent",
  1: "#E8F5E9",
  2: "#C8E6C9",
  3: "#FFF9C4",
  4: "#FFE082",
  5: "#FFCC80",
  6: "#FFAB91",
  7: "#EF9A9A",
};

export function weekLocked(year: number, week: number, currentYear: number, currentWeek: number) {
  if (year < currentYear) return true;
  if (year === currentYear && week < currentWeek) return true;
  return false;
}

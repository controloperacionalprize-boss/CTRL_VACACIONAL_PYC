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

export function weekLocked(year: number, week: number, currentYear: number, currentWeek: number) {
  if (year < currentYear) return true;
  if (year === currentYear && week < currentWeek) return true;
  return false;
}

/** Derecho anual (mismo tope que backend DERECHO_ANUAL). */
export const MAX_VAC_DAYS = 30;

export function topeDe(w: { tope_dias?: number } | null | undefined) {
  return w?.tope_dias ?? MAX_VAC_DAYS;
}

export function esAdelanto<T extends { record_cumplido?: boolean }>(
  w: T | null | undefined
): w is T & { record_cumplido: false } {
  return w != null && w.record_cumplido === false;
}

/** Días que aún puede pedir: tope − ya programados. */
export function diasDisponibles(programadosBase: number, tope: number = MAX_VAC_DAYS) {
  return Math.max(0, tope - Math.max(0, programadosBase));
}

/** Alerta de saldo insuficiente (misma lógica/texto que el backend). */
export function msgSinSaldo(
  nombre: string,
  pedidas: number,
  programadosBase: number,
  tope: number = MAX_VAC_DAYS,
  adelanto = false
) {
  const quien = nombre.trim() || "Este trabajador";
  const disponibles = diasDisponibles(programadosBase, tope);
  const etiqueta = adelanto ? "acumulado para adelanto" : "derecho anual";
  if (disponibles <= 0) {
    const extra = adelanto ? " (aún no cumple el año)" : "";
    return `No se puede programar ${pedidas} día(s) para ${quien}: ya tiene los ${tope} días de ${etiqueta} programados${extra}.`;
  }
  return `No se puede programar ${pedidas} día(s) para ${quien}: solo le quedan ${disponibles} día(s) disponible(s) (${etiqueta} ${tope}, ya programados ${programadosBase}).`;
}

export function etiquetaEstado(estado: string) {
  if (estado === "gozado") return "Gozado";
  if (estado === "en_curso") return "En curso";
  return "Programado";
}

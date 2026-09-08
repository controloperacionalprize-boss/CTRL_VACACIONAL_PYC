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

export function goceCompleto(programados: number, tope: number = MAX_VAC_DAYS) {
  return Math.max(0, programados) === Math.max(0, tope) && tope > 0;
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

export type Rol = "ADMIN" | "GERENTE" | "JEFE";

/** `rol` viene tal cual del backend (string); se compara por valor, sin forzar el tipo Rol aquí. */
export function flujoEstadoLabel(estado: string, rol?: Rol | string) {
  if (estado === "ENVIADO") {
    if (rol === "GERENTE") return "Por validar";
    if (rol === "ADMIN") return "Pendiente de gerente";
    return "Enviado al gerente";
  }
  if (estado === "VALIDADO") {
    if (rol === "ADMIN") return "Por recepcionar";
    if (rol === "GERENTE") return "Validado";
    return "Validado por el gerente";
  }
  if (estado === "RECEPCIONADO") return "Recepcionado";
  if (estado === "OBSERVADO") return "Observado";
  return "Borrador";
}

export function etiquetaEstado(estado: string) {
  if (estado === "gozado") return "Gozado";
  if (estado === "en_curso") return "En curso";
  return "Programado";
}

/** Mismos escenarios que el Word (memorando / fraccionamiento / adelanto). */
export function escenarioDe(adelanto: boolean, sizes: number[], tope: number = MAX_VAC_DAYS) {
  if (adelanto) {
    return {
      n: 4,
      titulo: "Adelanto de goce de vacaciones",
      detalle: "Aún no cumple el año: solo el acumulado. Puedes fraccionarlo en períodos.",
    };
  }
  if (sizes.length === 0) {
    return {
      n: 0,
      titulo: "Sin períodos aún",
      detalle: "Un solo período de 30 días es memorando. Varios períodos es fraccionamiento (Art. 8: 15 corridos, o 7 y 8).",
    };
  }
  if (sizes.length === 1 && sizes[0] === tope) {
    return {
      n: 1,
      titulo: "Memorando de vacaciones",
      detalle: "Goce continuo de todo el derecho.",
    };
  }
  return {
    n: 2,
    titulo: "Fraccionamiento de descanso vacacional",
    detalle: "Varios períodos. Art. 8: un bloque de al menos 15 días corridos, o uno de 7 y otro de 8 (u 8 y 7).",
  };
}

const FIELD: Record<string, string> = {
  start_date: "fecha de inicio",
  dni: "trabajador",
  days: "días",
  week: "semana",
  year: "año",
  dates: "fechas",
};

function fieldName(loc: unknown): string {
  if (!Array.isArray(loc) || loc.length === 0) return "el dato";
  const key = String(loc[loc.length - 1]);
  return FIELD[key] || key.replace(/_/g, " ");
}

function pydanticMsg(item: { type?: string; loc?: unknown; msg?: string; input?: unknown }): string {
  const field = fieldName(item.loc);
  const t = item.type || "";
  const raw = (item.msg || "").replace(/^Value error,\s*/i, "");
  if (t.includes("value_error") && raw && !raw.startsWith("Input should")) return raw;
  if (t.includes("date") || t.includes("datetime")) {
    if (item.input === "" || item.input == null) return `Indica la ${field}.`;
    return `La ${field} no es válida. Usa el formato AAAA-MM-DD.`;
  }
  if (t.includes("missing")) return `Falta ${field}.`;
  if (t.includes("int") || t.includes("number") || t.includes("type_error")) {
    return `${field.charAt(0).toUpperCase() + field.slice(1)} debe ser un número válido.`;
  }
  if (t.includes("less_than") || t.includes("greater_than") || t.includes("range")) {
    return item.msg ? `${field.charAt(0).toUpperCase() + field.slice(1)}: ${item.msg}` : `Revisa ${field}.`;
  }
  if (item.msg && !item.msg.startsWith("Input should") && !item.msg.startsWith("value is")) {
    return item.msg.replace(/^Value error,\s*/i, "");
  }
  return `Revisa ${field}.`;
}

function translateKnown(msg: string): string {
  if (/trabajador no visible/i.test(msg)) return "Esa persona no aparece con el filtro actual.";
  if (/es histórica y está bloqueada/i.test(msg)) {
    return msg.replace(/es histórica y está bloqueada/gi, "ya pasó y no se puede cambiar");
  }
  if (/sesión inválida|falta el token/i.test(msg)) return "La sesión caducó. Vuelve a iniciar sesión.";
  return msg;
}

export function formatApiError(detail: unknown, fallback = "No se pudo completar la operación."): string {
  if (detail == null || detail === "") return fallback;
  if (typeof detail === "string") return translateKnown(detail);
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => (item && typeof item === "object" ? pydanticMsg(item as never) : String(item)));
    return [...new Set(parts.filter(Boolean))].join(" ");
  }
  if (typeof detail === "object" && "msg" in (detail as object)) {
    return pydanticMsg(detail as never);
  }
  try {
    return translateKnown(JSON.stringify(detail));
  } catch {
    return fallback;
  }
}

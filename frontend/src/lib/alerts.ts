export type AlertPrioridad = "informativa" | "proxima" | "importante" | "critica";
export type AlertTipo = "record_vence" | "mes_siguiente" | "sin_programar" | "pendientes_flujo";
export type InboxStatus = "nueva" | "pendiente" | "atendida";

export type AlertPersona = {
  dni: string;
  nombre: string;
  area: string;
  jefatura: string;
  gerencia: string;
  division?: string;
  jefe_nombre?: string;
  fecha_vencimiento: string | null;
  dias_restantes: number | null;
  total_dias: number;
  tope_dias: number;
  flujo_estado: string;
  estado_plan: string;
  responsable: string;
  href: string;
  dias_mes?: number;
  periodos_mes?: string;
  mes?: string;
};

export type AlertItem = {
  id: string;
  tipo: AlertTipo;
  prioridad: AlertPrioridad;
  titulo: string;
  descripcion: string;
  accion: string;
  responsable: string;
  responsable_rol: string;
  href: string;
  href_plan: string;
  fecha_relevante: string | null;
  dias_restantes: number | null;
  count: number;
  personas: AlertPersona[];
  mes?: string;
  mes_label?: string;
  en_inbox?: boolean;
};

export type AlertsPayload = {
  today: string;
  year: number;
  rol: string;
  ultima_semana_mes: boolean;
  mes_siguiente: string;
  mes_siguiente_label: string;
  resumen: {
    records_90: number;
    vacaciones_mes_siguiente: number;
    pendientes_plan: number;
    sin_programar: number;
  };
  items: AlertItem[];
};

export type InboxEntry = {
  status: InboxStatus;
  firstSeenAt: number;
  attendedAt?: number;
};

type InboxMap = Record<string, InboxEntry>;

const PRIORIDAD_LABEL: Record<AlertPrioridad, string> = {
  informativa: "Informativa",
  proxima: "Próxima",
  importante: "Importante",
  critica: "Crítica",
};

export function prioridadLabel(p: AlertPrioridad) {
  return PRIORIDAD_LABEL[p] || p;
}

export function prioridadClass(p: AlertPrioridad) {
  if (p === "critica") return "bg-error-muted text-error";
  if (p === "importante") return "bg-warning-muted text-warning";
  if (p === "proxima") return "bg-[var(--primary-soft)] text-primary";
  return "bg-info-muted text-info";
}

function inboxKey(correo: string, year: number) {
  return `vac_alerts_inbox:${correo}:${year}`;
}

function pushKey(correo: string) {
  return `vac_alerts_push:${correo}`;
}

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function loadInbox(correo: string, year: number): InboxMap {
  return readJson<InboxMap>(inboxKey(correo, year), {});
}

export function saveInbox(correo: string, year: number, map: InboxMap) {
  localStorage.setItem(inboxKey(correo, year), JSON.stringify(map));
}

export function syncInbox(correo: string, year: number, items: AlertItem[]): InboxMap {
  const prev = loadInbox(correo, year);
  const now = Date.now();
  const next: InboxMap = {};
  const live = new Set(items.map((i) => i.id));
  for (const item of items) {
    const old = prev[item.id];
    next[item.id] = old
      ? { ...old, status: old.status === "atendida" ? "atendida" : old.status === "pendiente" ? "pendiente" : "nueva" }
      : { status: "nueva", firstSeenAt: now };
  }
  for (const [id, entry] of Object.entries(prev)) {
    if (!live.has(id) && entry.status === "atendida") next[id] = entry;
  }
  saveInbox(correo, year, next);
  return next;
}

export function markSeen(correo: string, year: number, ids: string[]): InboxMap {
  const map = loadInbox(correo, year);
  for (const id of ids) {
    const cur = map[id];
    if (!cur || cur.status !== "nueva") continue;
    map[id] = { ...cur, status: "pendiente" };
  }
  saveInbox(correo, year, map);
  return map;
}

export function markAttended(correo: string, year: number, id: string): InboxMap {
  const map = loadInbox(correo, year);
  const cur = map[id] || { status: "pendiente" as InboxStatus, firstSeenAt: Date.now() };
  map[id] = { ...cur, status: "atendida", attendedAt: Date.now() };
  saveInbox(correo, year, map);
  return map;
}

export function markPending(correo: string, year: number, id: string): InboxMap {
  const map = loadInbox(correo, year);
  const cur = map[id] || { status: "nueva" as InboxStatus, firstSeenAt: Date.now() };
  map[id] = { ...cur, status: "pendiente", attendedAt: undefined };
  saveInbox(correo, year, map);
  return map;
}

export function inboxItems(items: AlertItem[]) {
  return items.filter((i) => i.en_inbox !== false);
}

export function pendingBadgeCount(items: AlertItem[], inbox: InboxMap) {
  return inboxItems(items).filter((i) => inbox[i.id]?.status !== "atendida").length;
}

export function relativeFrom(ts: number, now = Date.now()) {
  const mins = Math.max(0, Math.round((now - ts) / 60000));
  if (mins < 1) return "Ahora";
  if (mins < 60) return `Hace ${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `Hace ${hours} hora${hours === 1 ? "" : "s"}`;
  const days = Math.round(hours / 24);
  if (days === 1) return "Ayer";
  if (days < 7) return `Hace ${days} días`;
  return new Date(ts).toLocaleDateString("es-PE");
}

export function browserNotificationsSupported() {
  return typeof window !== "undefined" && "Notification" in window;
}

export function browserPermission(): NotificationPermission | "unsupported" {
  if (!browserNotificationsSupported()) return "unsupported";
  return Notification.permission;
}

export async function requestBrowserPermission(): Promise<NotificationPermission | "unsupported"> {
  if (!browserNotificationsSupported()) return "unsupported";
  try {
    return await Notification.requestPermission();
  } catch {
    return Notification.permission;
  }
}

export function maybePushBrowserAlerts(correo: string, items: AlertItem[]) {
  if (!correo || !items.length) return;
  if (!browserNotificationsSupported()) return;
  if (Notification.permission !== "granted") return;
  if (typeof document !== "undefined" && document.visibilityState === "visible") return;

  const today = new Date().toISOString().slice(0, 10);
  const sent = readJson<Record<string, string>>(pushKey(correo), {});
  let changed = false;
  for (const item of inboxItems(items)) {
    if (item.prioridad !== "importante" && item.prioridad !== "critica") continue;
    if (sent[item.id] === today) continue;
    try {
      const n = new Notification("Control Vacacional", {
        body: item.descripcion,
        tag: item.id,
        data: { href: item.href },
      });
      n.onclick = () => {
        window.focus();
        const href = item.href || "/alertas";
        window.location.assign(href);
        n.close();
      };
      sent[item.id] = today;
      changed = true;
    } catch {
      /* el navegador puede bloquear el constructor aunque el permiso figure granted */
    }
  }
  if (changed) localStorage.setItem(pushKey(correo), JSON.stringify(sent));
}

export function findAlert(payload: AlertsPayload | null, tipo: string | null, mes?: string | null) {
  if (!payload || !tipo) return null;
  return (
    payload.items.find((i) => i.tipo === tipo && (!mes || i.mes === mes || tipo !== "mes_siguiente")) || null
  );
}

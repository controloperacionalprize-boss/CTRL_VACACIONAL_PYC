import { formatApiError } from "./lib/apiError";

export const API = import.meta.env.VITE_API_URL || "";

// Evita que la UI quede "colgada" para siempre si el backend no responde
// (caída, red lenta, etc.). Las exportaciones a Excel / PDF necesitan más margen.
const DEFAULT_TIMEOUT_MS = 20_000;
const LONG_TIMEOUT_MS = 60_000;

export function authHeader(): HeadersInit {
  const token = localStorage.getItem("vac_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function timeoutFor(path: string) {
  return (
    path.includes("/export") ||
    path.includes("/documento") ||
    path.includes("/documentos") ||
    path.includes("/asistencia") ||
    path.includes("/flujo/excel")
  )
    ? LONG_TIMEOUT_MS
    : DEFAULT_TIMEOUT_MS;
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutFor(path));

  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      ...init,
      signal: init.signal ?? controller.signal,
      headers: {
        ...authHeader(),
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(init.headers || {}),
      },
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error("El servidor tardó demasiado en responder. Revisa tu conexión e inténtalo de nuevo.");
    }
    throw new Error("No se pudo conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.");
  } finally {
    clearTimeout(timer);
  }

  if (res.status === 401) {
    localStorage.removeItem("vac_token");
    if (!path.includes("/auth/")) window.location.href = "/login";
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body;
    } catch {
      /* ignore */
    }
    const statusHint =
      res.status === 401
        ? "La sesión caducó. Vuelve a iniciar sesión."
        : res.status === 403
          ? "No tienes permiso para esta acción."
          : res.status === 404
            ? "No encontramos esa información."
            : res.status === 413
              ? "El archivo es demasiado grande."
              : res.status === 429
                ? "Demasiados intentos. Espera un momento e inténtalo de nuevo."
            : res.status === 503
              ? "El servidor está muy ocupado. Inténtalo de nuevo en unos segundos."
              : res.status >= 500
                ? "El servidor no respondió. Inténtalo de nuevo."
                : "No se pudo completar la operación.";
    throw new Error(formatApiError(detail, statusHint));
  }
  return res;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await request(path, init);
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res as unknown as T;
}

function filenameFromDisposition(header: string | null, fallback: string) {
  if (!header) return fallback;
  const quoted = header.match(/filename="([^"]+)"/);
  if (quoted?.[1]) return quoted[1];
  const star = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (star?.[1]) return decodeURIComponent(star[1]);
  return fallback;
}

export async function fetchFile(path: string, init: RequestInit = {}, fallbackName = "descarga") {
  const res = await request(path, init);
  const blob = await res.blob();
  return {
    blob,
    filename: filenameFromDisposition(res.headers.get("content-disposition"), fallbackName),
  };
}

export async function downloadFile(path: string, init: RequestInit = {}, fallbackName = "descarga") {
  const { blob, filename } = await fetchFile(path, init, fallbackName);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  // Revocar en el mismo tick puede cancelar la descarga en Firefox/Safari.
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

export async function uploadFile<T>(path: string, file: File, field = "file"): Promise<T> {
  const form = new FormData();
  form.append(field, file);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutFor(path));
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      method: "POST",
      signal: controller.signal,
      headers: { ...authHeader() },
      body: form,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error("El servidor tardó demasiado en responder. Revisa tu conexión e inténtalo de nuevo.");
    }
    throw new Error("No se pudo conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.");
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 401) {
    localStorage.removeItem("vac_token");
    window.location.href = "/login";
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body;
    } catch {
      /* ignore */
    }
    throw new Error(formatApiError(detail, "No se pudo cargar el archivo."));
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res as unknown as T;
}

export function qs(params: Record<string, string | number | boolean | string[] | undefined>) {
  const u = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === "") return;
    if (Array.isArray(v)) v.forEach((item) => u.append(k, item));
    else if (typeof v === "boolean") u.set(k, v ? "true" : "false");
    else u.set(k, String(v));
  });
  const s = u.toString();
  return s ? `?${s}` : "";
}

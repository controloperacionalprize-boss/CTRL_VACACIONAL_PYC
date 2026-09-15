import { lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { api, qs } from "./api";
import { Login } from "./pages/Login";
import { Shell } from "./pages/Shell";
import { PlanPage } from "./pages/Plan";
import { AppCtx, type AppState, type Filters, type User } from "./state";
import { inboxItems, syncInbox, type AlertsPayload, type InboxEntry } from "./lib/alerts";

// Cada pantalla se descarga al abrirla: Dashboard trae recharts (la mayor parte del bundle),
// y no hace falta parsearlo para planificar.
const DashboardPage = lazy(() => import("./pages/Dashboard").then((m) => ({ default: m.DashboardPage })));
const CalendarPage = lazy(() => import("./pages/Calendar").then((m) => ({ default: m.CalendarPage })));
const ExportPage = lazy(() => import("./pages/Export").then((m) => ({ default: m.ExportPage })));
const ValidacionesPage = lazy(() => import("./pages/Validaciones").then((m) => ({ default: m.ValidacionesPage })));
const AdminPage = lazy(() => import("./pages/Admin").then((m) => ({ default: m.AdminPage })));
const AlertasPage = lazy(() => import("./pages/Alertas").then((m) => ({ default: m.AlertasPage })));
const DocumentosPage = lazy(() => import("./pages/Documentos").then((m) => ({ default: m.DocumentosPage })));

const yearNow = new Date().getFullYear();
// Volver a la pestaña recalcula alertas en el servidor; no más de una vez por minuto.
const ALERTS_FOCUS_MIN_MS = 60_000;
const ALERTS_POLL_MS = 5 * 60_000;

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [options, setOptions] = useState({ empresas: [] as string[], gerencias: [] as string[], areas: [] as string[] });
  const [filters, setFilters] = useState<Filters>({
    year: yearNow,
    empresas: ["TODAS"],
    gerencias: ["TODAS"],
    areas: ["TODAS"],
  });
  const [alerts, setAlerts] = useState<AlertsPayload | null>(null);
  const [alertsError, setAlertsError] = useState("");
  const [inbox, setInbox] = useState<Record<string, InboxEntry>>({});
  const alertsAt = useRef(0);

  const alertQuery = useMemo(
    () => ({
      year: filters.year,
      empresa: filters.empresas.includes("TODAS") ? undefined : filters.empresas,
      gerencia: filters.gerencias.includes("TODAS") ? undefined : filters.gerencias,
      area: filters.areas.includes("TODAS") ? undefined : filters.areas,
    }),
    [filters]
  );

  const logout = useCallback(() => {
    localStorage.removeItem("vac_token");
    setUser(null);
    setAlerts(null);
    setAlertsError("");
    setInbox({});
  }, []);

  const reloadAlerts = useCallback(() => {
    if (!user) {
      setAlerts(null);
      return;
    }
    alertsAt.current = Date.now();
    api<AlertsPayload>(`/api/alerts${qs(alertQuery)}`)
      .then((data) => {
        setAlerts(data);
        setAlertsError("");
        setInbox(syncInbox(user.correo, filters.year, inboxItems(data.items)));
      })
      .catch((e) => {
        setAlertsError(e instanceof Error ? e.message : "No se pudieron cargar las alertas.");
      });
  }, [user, alertQuery, filters.year]);

  useEffect(() => {
    const token = localStorage.getItem("vac_token");
    if (!token) {
      setReady(true);
      return;
    }
    api<User>("/api/auth/me")
      .then(setUser)
      .catch(() => localStorage.removeItem("vac_token"))
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    if (!user) return;
    const query = {
      empresa: filters.empresas.includes("TODAS") ? undefined : filters.empresas,
      gerencia: filters.gerencias.includes("TODAS") ? undefined : filters.gerencias,
      area: filters.areas.includes("TODAS") ? undefined : filters.areas,
    };
    api<{ empresas: string[]; gerencias: string[]; areas: string[] }>(`/api/filters${qs(query)}`).then((opts) => {
      setOptions(opts);
      setFilters((prev) => {
        const keep = (selected: string[], available: string[]) =>
          selected.includes("TODAS") || available.includes(selected[0] || "") ? selected : (["TODAS"] as string[]);
        const empresas = keep(prev.empresas, opts.empresas);
        const gerencias = keep(prev.gerencias, opts.gerencias);
        const areas = keep(prev.areas, opts.areas);
        if (
          empresas[0] === prev.empresas[0] &&
          gerencias[0] === prev.gerencias[0] &&
          areas[0] === prev.areas[0]
        ) {
          return prev;
        }
        return { ...prev, empresas, gerencias, areas };
      });
    });
  }, [user, filters.empresas, filters.gerencias, filters.areas]);

  useEffect(() => {
    if (!user) return;
    reloadAlerts();
  }, [user, reloadAlerts]);

  useEffect(() => {
    if (!user) return;
    const onFocus = () => {
      if (Date.now() - alertsAt.current >= ALERTS_FOCUS_MIN_MS) reloadAlerts();
    };
    window.addEventListener("focus", onFocus);
    // Sin la pestaña visible no se consulta: evita trabajo del servidor con la app olvidada abierta.
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") reloadAlerts();
    }, ALERTS_POLL_MS);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.clearInterval(timer);
    };
  }, [user, reloadAlerts]);

  // Un objeto nuevo en cada render hacía re-renderizar a todas las pantallas que usan useApp().
  const ctx = useMemo<AppState>(
    () => ({
      user,
      setUser,
      logout,
      filters,
      setFilters,
      options,
      setOptions,
      alerts,
      alertsError,
      inbox,
      setInbox,
      reloadAlerts,
    }),
    [user, logout, filters, options, alerts, alertsError, inbox, reloadAlerts]
  );

  if (!ready) return <div className="p-10 text-sm text-muted-foreground">Abriendo la aplicación…</div>;

  return (
    <AppCtx.Provider value={ctx}>
      {!user ? (
        <Login
          onLogin={(token, u) => {
            localStorage.setItem("vac_token", token);
            setUser(u);
          }}
        />
      ) : (
        <Routes>
          <Route element={<Shell />}>
            <Route path="/" element={<PlanPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/asistencia" element={<Navigate to="/" replace />} />
            <Route path="/record-vacacional" element={<CalendarPage />} />
            <Route path="/calendario" element={<Navigate to="/record-vacacional" replace />} />
            <Route path="/exportar" element={<ExportPage />} />
            <Route path="/validaciones" element={<ValidacionesPage />} />
            <Route path="/alertas" element={<AlertasPage />} />
            <Route path="/documentos" element={<DocumentosPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      )}
    </AppCtx.Provider>
  );
}

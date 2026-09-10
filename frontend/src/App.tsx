import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { api, qs } from "./api";
import { Login } from "./pages/Login";
import { Shell } from "./pages/Shell";
import { PlanPage } from "./pages/Plan";
import { DashboardPage } from "./pages/Dashboard";
import { CalendarPage } from "./pages/Calendar";
import { ExportPage } from "./pages/Export";
import { ValidacionesPage } from "./pages/Validaciones";
import { AdminPage } from "./pages/Admin";
import { AlertasPage } from "./pages/Alertas";
import { DocumentosPage } from "./pages/Documentos";
import { AppCtx, type Filters, type User } from "./state";
import { inboxItems, syncInbox, type AlertsPayload, type InboxEntry } from "./lib/alerts";

const yearNow = new Date().getFullYear();

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

  const alertQuery = useMemo(
    () => ({
      year: filters.year,
      empresa: filters.empresas.includes("TODAS") ? undefined : filters.empresas,
      gerencia: filters.gerencias.includes("TODAS") ? undefined : filters.gerencias,
      area: filters.areas.includes("TODAS") ? undefined : filters.areas,
    }),
    [filters]
  );

  function logout() {
    localStorage.removeItem("vac_token");
    setUser(null);
    setAlerts(null);
    setAlertsError("");
    setInbox({});
  }

  const reloadAlerts = useCallback(() => {
    if (!user) {
      setAlerts(null);
      return;
    }
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
    const onFocus = () => reloadAlerts();
    window.addEventListener("focus", onFocus);
    const timer = window.setInterval(reloadAlerts, 5 * 60 * 1000);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.clearInterval(timer);
    };
  }, [user, reloadAlerts]);

  if (!ready) return <div className="p-10 text-sm text-muted-foreground">Abriendo la aplicación…</div>;

  return (
    <AppCtx.Provider
      value={{
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
      }}
    >
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

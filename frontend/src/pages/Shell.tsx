import { NavLink, Outlet } from "react-router-dom";
import {
  Calendar,
  CalendarRange,
  FileSpreadsheet,
  LayoutDashboard,
  LogOut,
  Shield,
} from "lucide-react";
import { useApp } from "../state";
import { Button, cn, Field, Select } from "../components/ui";

function Multi({
  label,
  values,
  selected,
  onChange,
}: {
  label: string;
  values: string[];
  selected: string[];
  onChange: (v: string[]) => void;
}) {
  const all = selected.length === 0 || selected.includes("TODAS");
  return (
    <Field label={label}>
      <Select value={all ? "TODAS" : selected[0] || "TODAS"} onChange={(e) => onChange(e.target.value === "TODAS" ? ["TODAS"] : [e.target.value])}>
        <option value="TODAS">Todas</option>
        {values.map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </Select>
    </Field>
  );
}

const NAV = [
  { to: "/", end: true, label: "Planificación", Icon: CalendarRange },
  { to: "/dashboard", end: false, label: "Dashboard", Icon: LayoutDashboard },
  { to: "/calendario", end: false, label: "Calendario", Icon: Calendar },
  { to: "/exportar", end: false, label: "Exportar", Icon: FileSpreadsheet },
] as const;

export function Shell() {
  const { user, logout, filters, setFilters, options } = useApp();
  const yearNow = new Date().getFullYear();
  const years = Array.from({ length: 5 }, (_, i) => yearNow - 1 + i);
  const display = user?.nombre_persona || user?.nombre_usuario || "";
  const initials = display
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toUpperCase();

  return (
    <div className="flex h-full overflow-hidden bg-background">
      <aside className="flex h-full w-[260px] shrink-0 flex-col border-r border-border bg-sidebar">
        <div className="shrink-0 border-b border-border px-5 py-5">
          <p className="text-[10px] font-semibold tracking-[0.12em] text-muted-foreground">GTH · Prize / Aquanqa</p>
          <h1 className="text-lg font-semibold leading-tight text-foreground">Vacaciones</h1>
        </div>

        <nav className="flex shrink-0 flex-col gap-0.5 p-3">
          {NAV.map(({ to, end, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex h-auto w-full items-center gap-2.5 rounded-[10px] px-3 py-2.5 no-underline transition-colors",
                  isActive
                    ? "bg-[var(--primary-soft)] font-semibold text-primary"
                    : "bg-transparent font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={16} strokeWidth={1.75} className={isActive ? "text-primary" : "text-muted-foreground"} />
                  <span className="text-[13px] leading-none">{label}</span>
                </>
              )}
            </NavLink>
          ))}
          {user?.is_admin ? (
            <NavLink
              to="/admin"
              className={({ isActive }) =>
                cn(
                  "flex h-auto w-full items-center gap-2.5 rounded-[10px] px-3 py-2.5 no-underline transition-colors",
                  isActive
                    ? "bg-[var(--primary-soft)] font-semibold text-primary"
                    : "bg-transparent font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Shield size={16} strokeWidth={1.75} className={isActive ? "text-primary" : "text-muted-foreground"} />
                  <span className="text-[13px] leading-none">Admin</span>
                </>
              )}
            </NavLink>
          ) : null}
        </nav>

        <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto px-4 pt-1 pb-3">
          <Field label="AÑO">
            <Select value={filters.year} onChange={(e) => setFilters({ ...filters, year: Number(e.target.value) })}>
              {years.map((y) => (
                <option key={y}>{y}</option>
              ))}
            </Select>
          </Field>
          <Multi label="EMPRESA" values={options.empresas} selected={filters.empresas} onChange={(empresas) => setFilters({ ...filters, empresas })} />
          {user?.is_admin ? (
            <Multi label="GERENCIA" values={options.gerencias} selected={filters.gerencias} onChange={(gerencias) => setFilters({ ...filters, gerencias })} />
          ) : (
            <p className="text-[11px] text-muted-foreground">Gerencia: {user?.gerencia}</p>
          )}
          <Multi label="DIVISIÓN" values={options.divisiones} selected={filters.divisiones} onChange={(divisiones) => setFilters({ ...filters, divisiones })} />
        </div>

        <div className="flex shrink-0 items-center gap-2.5 border-t border-border bg-sidebar p-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">
            {initials || "—"}
          </div>
          <div className="min-w-0">
            <p className="truncate text-xs font-semibold">{display}</p>
            <p className="text-[11px] text-muted-foreground">{user?.is_admin ? "Admin · GTH" : user?.rol}</p>
          </div>
        </div>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-card px-6">
          <p className="truncate text-[13px] text-muted-foreground">
            {display} · {user?.correo} · {user?.rol}
            {user?.is_admin ? " · todas las gerencias" : ` · ${user?.gerencia}`}
          </p>
          <Button variant="ghost" onClick={logout} className="h-9">
            <LogOut size={16} strokeWidth={1.75} />
            Cerrar sesión
          </Button>
        </header>
        <main className="flex-1 space-y-6 overflow-auto p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

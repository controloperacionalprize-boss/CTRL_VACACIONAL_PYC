import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  Calendar,
  CalendarRange,
  FileSpreadsheet,
  LayoutDashboard,
  LogOut,
  Menu,
  Shield,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useApp } from "../state";
import { Button, cn, Field, Select } from "../components/ui";
import { EmpAvatar } from "../components/EmpAvatar";

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
  { to: "/", end: true, label: "Planificación", short: "Plan", Icon: CalendarRange },
  { to: "/dashboard", end: false, label: "Dashboard", short: "Dash", Icon: LayoutDashboard },
  { to: "/record-vacacional", end: false, label: "Récord vacacional", short: "Récord", Icon: Calendar },
  { to: "/exportar", end: false, label: "Exportar", short: "Excel", Icon: FileSpreadsheet },
] as const;

function FiltersBlock({
  years,
  compact,
}: {
  years: number[];
  compact?: boolean;
}) {
  const { user, filters, setFilters, options } = useApp();
  return (
    <div className={cn("flex flex-col gap-2.5", compact ? "" : "px-4 pt-1 pb-3")}>
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
  );
}

export function Shell() {
  const { user, logout, filters } = useApp();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const display = user?.nombre_persona || user?.nombre_usuario || "";
  const yearNow = new Date().getFullYear();
  const years = Array.from({ length: 5 }, (_, i) => yearNow - 1 + i);

  useEffect(() => {
    if (!filtersOpen && !moreOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [filtersOpen, moreOpen]);

  const filterHint = [
    String(filters.year),
    filters.empresas.includes("TODAS") ? null : filters.empresas[0],
    filters.divisiones.includes("TODAS") ? null : filters.divisiones[0],
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="flex h-full overflow-hidden bg-background">
      <aside className="hidden h-full w-[260px] shrink-0 flex-col border-r border-border bg-sidebar md:flex">
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

        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
          <FiltersBlock years={years} />
        </div>

        <div className="flex shrink-0 items-center gap-2.5 border-t border-border bg-sidebar p-4">
          <EmpAvatar nombre={display} fotoUrl={user?.foto_url} className="h-8 w-8 text-[11px]" />
          <div className="min-w-0">
            <p className="truncate text-xs font-semibold">{display}</p>
            <p className="text-[11px] text-muted-foreground">{user?.is_admin ? "Admin · GTH" : user?.rol}</p>
          </div>
        </div>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border bg-card px-4 md:px-6">
          <div className="min-w-0 md:hidden">
            <p className="text-[10px] font-semibold tracking-[0.08em] text-muted-foreground">GTH · Vacaciones</p>
            <p className="truncate text-[13px] font-semibold text-foreground">{display}</p>
          </div>
          <p className="hidden min-w-0 truncate text-[13px] text-muted-foreground md:block">
            {display} · {user?.correo} · {user?.rol}
            {user?.is_admin ? " · todas las gerencias" : ` · ${user?.gerencia}`}
          </p>
          <div className="flex shrink-0 items-center gap-1.5">
            <Button
              variant="outline"
              className="h-9 px-2.5 md:hidden"
              onClick={() => setFiltersOpen(true)}
              aria-label="Filtros"
            >
              <SlidersHorizontal size={16} strokeWidth={1.75} />
              <span className="hidden xs:inline sm:inline">Filtros</span>
            </Button>
            <Button variant="ghost" onClick={logout} className="h-9 px-2.5 md:px-4">
              <LogOut size={16} strokeWidth={1.75} />
              <span className="hidden sm:inline">Cerrar sesión</span>
            </Button>
          </div>
        </header>

        <div className="flex items-center justify-between gap-2 border-b border-border bg-muted/60 px-4 py-2 text-[11px] text-muted-foreground md:hidden">
          <span className="truncate">{filterHint}</span>
          <button type="button" className="shrink-0 font-semibold text-primary" onClick={() => setFiltersOpen(true)}>
            Cambiar
          </button>
        </div>

        <main className="flex-1 space-y-5 overflow-auto p-4 pb-[calc(5.5rem+env(safe-area-inset-bottom))] md:space-y-6 md:p-8 md:pb-8">
          <Outlet />
        </main>

        <nav className="pointer-events-none fixed inset-x-0 bottom-0 z-40 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] md:hidden">
          <div className="pointer-events-auto mx-auto flex h-14 max-w-lg items-center justify-around rounded-full border border-border bg-card/95 px-1.5 shadow-[0_4px_20px_#0f1c2e1a] backdrop-blur">
            {NAV.map(({ to, end, short, Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  cn(
                    "flex h-11 w-14 flex-col items-center justify-center gap-0.5 rounded-full no-underline transition-colors",
                    isActive ? "bg-[var(--primary-soft)] text-primary" : "text-muted-foreground"
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon size={18} strokeWidth={isActive ? 2 : 1.75} />
                    <span className={cn("text-[10px] leading-none", isActive ? "font-semibold" : "font-medium")}>{short}</span>
                  </>
                )}
              </NavLink>
            ))}
            <button
              type="button"
              onClick={() => setMoreOpen(true)}
              className="flex h-11 w-14 flex-col items-center justify-center gap-0.5 rounded-full text-muted-foreground"
            >
              <Menu size={18} strokeWidth={1.75} />
              <span className="text-[10px] font-medium leading-none">Más</span>
            </button>
          </div>
        </nav>
      </div>

      {filtersOpen ? (
        <div className="fixed inset-0 z-50 md:hidden">
          <button type="button" className="absolute inset-0 bg-[var(--overlay)]" aria-label="Cerrar filtros" onClick={() => setFiltersOpen(false)} />
          <div className="absolute inset-x-0 bottom-0 max-h-[85vh] overflow-auto rounded-t-[20px] border border-border bg-card px-5 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-3 shadow-[0_-8px_24px_#0f1c2e14]">
            <div className="mb-3 flex justify-center">
              <span className="h-1 w-10 rounded-full bg-border" />
            </div>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold">Filtros</h3>
              <button type="button" className="rounded-[10px] p-2 text-muted-foreground hover:bg-muted" onClick={() => setFiltersOpen(false)} aria-label="Cerrar">
                <X size={18} strokeWidth={1.75} />
              </button>
            </div>
            <FiltersBlock years={years} compact />
            <Button className="mt-4 w-full" onClick={() => setFiltersOpen(false)}>
              Aplicar filtros
            </Button>
          </div>
        </div>
      ) : null}

      {moreOpen ? (
        <div className="fixed inset-0 z-50 md:hidden">
          <button type="button" className="absolute inset-0 bg-[var(--overlay)]" aria-label="Cerrar menú" onClick={() => setMoreOpen(false)} />
          <div className="absolute inset-x-0 bottom-0 rounded-t-[20px] border border-border bg-card px-5 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-3 shadow-[0_-8px_24px_#0f1c2e14]">
            <div className="mb-3 flex justify-center">
              <span className="h-1 w-10 rounded-full bg-border" />
            </div>
            <div className="mb-3 flex items-center gap-3">
              <EmpAvatar nombre={display} fotoUrl={user?.foto_url} className="h-10 w-10 text-xs" />
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{display}</p>
                <p className="truncate text-[12px] text-muted-foreground">{user?.correo}</p>
              </div>
            </div>
            {user?.is_admin ? (
              <NavLink
                to="/admin"
                onClick={() => setMoreOpen(false)}
                className="mb-2 flex items-center gap-2.5 rounded-[10px] bg-[var(--primary-soft)] px-3 py-3 text-[13px] font-semibold text-primary no-underline"
              >
                <Shield size={16} strokeWidth={1.75} />
                Administración
              </NavLink>
            ) : null}
            <Button
              variant="outline"
              className="w-full"
              onClick={() => {
                setMoreOpen(false);
                logout();
              }}
            >
              <LogOut size={16} strokeWidth={1.75} />
              Cerrar sesión
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

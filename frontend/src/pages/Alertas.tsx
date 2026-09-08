import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";
import { useApp } from "../state";
import { Alert, Button, EmptyState, Field, PageHeader, Select, cn } from "../components/ui";
import { formatFechaIso } from "../lib/dates";
import { findAlert, prioridadClass, prioridadLabel, type AlertItem, type AlertPersona } from "../lib/alerts";
import { flujoEstadoLabel } from "../lib/vacaciones";

const PAGE_SIZES = [10, 25, 50] as const;
const FLUJO_FILTRO = ["BORRADOR", "ENVIADO", "VALIDADO", "RECEPCIONADO", "OBSERVADO"] as const;

function pageItems(current: number, total: number): Array<number | "…"> {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  if (current <= 3) return [1, 2, 3, 4, 5, "…", total];
  if (current >= total - 2) return [1, "…", total - 4, total - 3, total - 2, total - 1, total];
  return [1, "…", current - 1, current, current + 1, "…", total];
}

function personaHref(p: AlertPersona, item: AlertItem) {
  if (item.tipo === "pendientes_flujo") return "/validaciones";
  return p.href || item.href_plan;
}

function uniqueSorted(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b, "es"));
}

function personaJefe(p: AlertPersona) {
  return (p.jefe_nombre || p.jefatura || "").trim();
}

type PersonaFiltro = "area" | "jefe" | "flujo";

export function AlertasPage() {
  const { alerts, alertsError, user } = useApp();
  const [params, setParams] = useSearchParams();
  const tipo = params.get("tipo");
  const mes = params.get("mes");
  const selected = findAlert(alerts, tipo, mes) || alerts?.items[0] || null;

  if (alertsError) {
    return (
      <Alert tone="error" title="No se pudieron cargar las alertas">
        {alertsError}
      </Alert>
    );
  }
  if (!alerts) return <p className="text-sm text-muted-foreground">Cargando alertas…</p>;

  const items = alerts.items;
  if (!items.length) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Alertas"
          help="Situaciones de tu alcance: récords por vencer, vacaciones del mes siguiente y lo que te toca en bandeja."
        />
        <EmptyState
          title="Nada requiere tu acción ahora"
          body="No hay récords por vencer en 3 meses, ni vacaciones el próximo mes en la última semana, ni planes esperándote en bandeja."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Alertas"
        help="Elige un grupo y abre el listado completo. El botón de arriba lleva a todas las personas de esa alerta, no a un caso suelto."
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {items.map((item) => {
          const active = selected?.id === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => {
                const next = new URLSearchParams();
                next.set("tipo", item.tipo);
                if (item.mes) next.set("mes", item.mes);
                setParams(next, { replace: true });
              }}
              className={cn(
                "rounded-xl border bg-card p-4 text-left shadow-[var(--shadow-card)]",
                active ? "border-primary ring-2 ring-[var(--primary-soft)]" : "border-border"
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-[13px] font-semibold leading-snug">{item.titulo}</p>
                <span className={cn("shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium", prioridadClass(item.prioridad))}>
                  {prioridadLabel(item.prioridad)}
                </span>
              </div>
              <p className="font-data mt-2 text-[22px] font-semibold tabular-nums">{item.count}</p>
              <p className="mt-1 text-[12px] leading-snug text-muted-foreground">{item.descripcion}</p>
            </button>
          );
        })}
      </div>

      {selected ? <AlertDetail key={selected.id} item={selected} rol={alerts.rol || user?.rol || ""} /> : null}
    </div>
  );
}

function AlertDetail({ item, rol }: { item: AlertItem; rol: string }) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZES)[number]>(10);
  const [area, setArea] = useState("");
  const [jefe, setJefe] = useState("");
  const [flujo, setFlujo] = useState("");
  const personas = item.personas;

  const matches = useMemo(() => {
    return (p: AlertPersona, skip?: PersonaFiltro) => {
      if (skip !== "area" && area && (p.area || "").trim() !== area) return false;
      if (skip !== "jefe" && jefe && personaJefe(p) !== jefe) return false;
      if (skip !== "flujo" && flujo && (p.flujo_estado || "BORRADOR") !== flujo) return false;
      return true;
    };
  }, [area, jefe, flujo]);

  const areaOpts = useMemo(
    () => uniqueSorted(personas.filter((p) => matches(p, "area")).map((p) => (p.area || "").trim())),
    [personas, matches]
  );
  const jefeOpts = useMemo(
    () => uniqueSorted(personas.filter((p) => matches(p, "jefe")).map(personaJefe)),
    [personas, matches]
  );
  const flujoCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const p of personas.filter((row) => matches(row, "flujo"))) {
      const key = p.flujo_estado || "BORRADOR";
      counts[key] = (counts[key] || 0) + 1;
    }
    return counts;
  }, [personas, matches]);
  const filtered = useMemo(() => personas.filter((p) => matches(p)), [personas, matches]);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const slice = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, page, pageSize]);
  const numbers = useMemo(() => pageItems(page, pages), [page, pages]);
  const hayFiltro = Boolean(area || jefe || flujo);

  useEffect(() => {
    setPage(1);
    setArea("");
    setJefe("");
    setFlujo("");
  }, [item.id]);

  useEffect(() => {
    if (area && !areaOpts.includes(area)) setArea("");
  }, [area, areaOpts]);
  useEffect(() => {
    if (jefe && !jefeOpts.includes(jefe)) setJefe("");
  }, [jefe, jefeOpts]);

  useEffect(() => {
    setPage(1);
  }, [pageSize, area, jefe, flujo]);

  useEffect(() => {
    if (page > pages) setPage(pages);
  }, [page, pages]);

  const showVence = item.tipo === "record_vence";
  const showMes = item.tipo === "mes_siguiente";
  const from = filtered.length ? (page - 1) * pageSize + 1 : 0;
  const to = Math.min(page * pageSize, filtered.length);
  const headers = showMes
    ? ["Trabajador", "Área", "Jefe", "Días en el mes", "Períodos", "Estado de planificación"]
    : showVence
      ? ["Trabajador", "Área", "Jefe", "Fecha de vencimiento", "Días restantes", "Estado de planificación"]
      : ["Trabajador", "Área", "Jefe", "Estado de planificación", "Flujo"];

  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card shadow-[var(--shadow-card)]">
      <div className="flex flex-col gap-3 border-b border-border px-4 py-4 sm:flex-row sm:items-start sm:justify-between sm:px-5">
        <div className="min-w-0">
          <p className="text-[15px] font-semibold">{item.titulo}</p>
          <p className="mt-1 text-[13px] text-muted-foreground">{item.descripcion}</p>
        </div>
        <div className="flex w-full shrink-0 flex-col gap-2 sm:w-auto sm:items-end">
          <Link to={item.href_plan || item.href} className="no-underline">
            <Button className="w-full sm:w-auto">{item.accion}</Button>
          </Link>
        </div>
      </div>
      <div className="grid gap-3 border-b border-border px-4 py-3 sm:grid-cols-3 sm:px-5">
        <Field label="ÁREA">
          <Select value={area} onChange={(e) => setArea(e.target.value)}>
            <option value="">Todas</option>
            {areaOpts.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="JEFE">
          <Select value={jefe} onChange={(e) => setJefe(e.target.value)}>
            <option value="">Todos</option>
            {jefeOpts.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="ESTADO">
          <Select value={flujo} onChange={(e) => setFlujo(e.target.value)}>
            <option value="">Todos ({personas.filter((p) => matches(p, "flujo")).length})</option>
            {FLUJO_FILTRO.map((estado) => (
              <option key={estado} value={estado}>
                {flujoEstadoLabel(estado, rol)} ({flujoCounts[estado] || 0})
              </option>
            ))}
          </Select>
        </Field>
      </div>
      {filtered.length === 0 ? (
        <p className="px-4 py-8 text-center text-[13px] text-muted-foreground sm:px-5">
          Nadie de este grupo coincide con los filtros.
        </p>
      ) : (
        <>
      <div className="divide-y divide-border md:hidden">
        {slice.map((p) => (
          <PersonaCard key={p.dni} p={p} item={item} showVence={showVence} showMes={showMes} />
        ))}
      </div>
      <div className="hidden overflow-auto md:block">
        <table className="w-full text-sm">
          <thead className="bg-muted/60 text-left">
            <tr>
              {headers.map((h) => (
                <th key={h} className="px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {slice.map((p) => (
              <tr key={p.dni} className="border-t border-border">
                <td className="px-4 py-2.5">
                  <Link to={personaHref(p, item)} className="font-medium text-foreground no-underline hover:text-primary hover:underline">
                    {p.nombre}
                  </Link>
                  <p className="font-data text-[11px] text-muted-foreground">{p.dni}</p>
                </td>
                <td className="max-w-[160px] truncate px-4 py-2.5 text-[13px]">{p.area || "—"}</td>
                <td className="max-w-[180px] px-4 py-2.5">
                  <p className="truncate text-[13px]">{p.jefe_nombre || p.jefatura || "—"}</p>
                  {p.jefe_nombre && p.jefatura && p.jefe_nombre !== p.jefatura ? (
                    <p className="truncate text-[11px] text-muted-foreground">{p.jefatura}</p>
                  ) : null}
                </td>
                {showVence ? (
                  <>
                    <td className="px-4 py-2.5 font-data text-[12px]">{formatFechaIso(p.fecha_vencimiento)}</td>
                    <td className="px-4 py-2.5 tabular-nums">
                      {p.dias_restantes == null
                        ? "—"
                        : p.dias_restantes < 0
                          ? `Vencido (${Math.abs(p.dias_restantes)} d)`
                          : `${p.dias_restantes} d`}
                    </td>
                  </>
                ) : null}
                {showMes ? (
                  <>
                    <td className="px-4 py-2.5 tabular-nums">{p.dias_mes ?? "—"}</td>
                    <td className="px-4 py-2.5 text-[12px]">{p.periodos_mes || "—"}</td>
                  </>
                ) : null}
                <td className="px-4 py-2.5 text-[12px]">{p.estado_plan}</td>
                {!showVence && !showMes ? (
                  <td className="px-4 py-2.5">
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium">
                      {flujoEstadoLabel(p.flujo_estado, rol)}
                    </span>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length ? (
        <div className="flex flex-col gap-3 border-t border-border px-4 py-3 sm:px-5 lg:flex-row lg:items-center lg:justify-between">
          <label className="flex items-center gap-2 text-[12px] text-muted-foreground">
            Resultados por página
            <span className="relative">
              <select
                value={pageSize}
                onChange={(e) => setPageSize(Number(e.target.value) as (typeof PAGE_SIZES)[number])}
                className="h-9 appearance-none rounded-[10px] border border-border bg-card py-0 pl-3 pr-8 text-[13px] text-foreground outline-none"
              >
                {PAGE_SIZES.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={14}
                className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground"
              />
            </span>
          </label>
          {pages > 1 ? (
            <div className="flex flex-wrap items-center justify-center gap-1">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="inline-flex h-9 items-center gap-1 rounded-md px-2 text-[13px] text-muted-foreground hover:text-foreground disabled:opacity-40"
              >
                <ChevronLeft size={16} />
                Anterior
              </button>
              {numbers.map((n, i) =>
                n === "…" ? (
                  <span key={`e${i}`} className="px-1 text-[13px] text-muted-foreground">
                    …
                  </span>
                ) : (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setPage(n)}
                    className={cn(
                      "inline-flex h-8 min-w-8 items-center justify-center rounded-md px-2 text-[13px] font-medium",
                      n === page ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-muted"
                    )}
                  >
                    {n}
                  </button>
                )
              )}
              <button
                type="button"
                disabled={page >= pages}
                onClick={() => setPage((p) => p + 1)}
                className="inline-flex h-9 items-center gap-1 rounded-md px-2 text-[13px] text-muted-foreground hover:text-foreground disabled:opacity-40"
              >
                Siguiente
                <ChevronRight size={16} />
              </button>
            </div>
          ) : (
            <span className="hidden lg:block" />
          )}
          <p className="text-[12px] text-muted-foreground lg:text-right">
            {from}–{to} de {filtered.length} personas
            {hayFiltro ? ` (${personas.length} en el grupo)` : ""}
          </p>
        </div>
      ) : null}
        </>
      )}
    </section>
  );
}

function PersonaCard({
  p,
  item,
  showVence,
  showMes,
}: {
  p: AlertPersona;
  item: AlertItem;
  showVence: boolean;
  showMes: boolean;
}) {
  return (
    <div className="px-4 py-3">
      <Link to={personaHref(p, item)} className="text-[14px] font-semibold text-foreground no-underline hover:text-primary hover:underline">
        {p.nombre}
      </Link>
      <p className="text-[12px] text-muted-foreground">
        {p.dni} · {p.area || "—"} · {p.jefe_nombre || p.jefatura || "—"}
      </p>
      {showVence ? (
        <p className="mt-1 text-[12px]">
          Vence {formatFechaIso(p.fecha_vencimiento)}
          {p.dias_restantes != null
            ? p.dias_restantes < 0
              ? ` · vencido hace ${Math.abs(p.dias_restantes)} día(s)`
              : ` · ${p.dias_restantes} día(s) restantes`
            : ""}
        </p>
      ) : null}
      {showMes ? (
        <p className="mt-1 text-[12px]">
          {p.dias_mes || 0} día(s) · {p.periodos_mes || "—"}
        </p>
      ) : null}
      <p className="mt-1 text-[12px]">{p.estado_plan}</p>
    </div>
  );
}

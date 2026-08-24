import { useDeferredValue, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { CalendarCheck, CalendarClock, CalendarRange, Layers, PenLine } from "lucide-react";
import { api, qs } from "../api";
import { useApp } from "../state";
import { Alert, EmptyState, Field, Input, PageHeader, Select, cn } from "../components/ui";
import { EmpAvatar } from "../components/EmpAvatar";

type Emp = { dni: string; nombre: string; foto_url?: string | null };
type DayKind = "vacacion" | "asistencia" | "falta" | "nolab" | "preingreso" | null;
type Cal = {
  empleado: {
    nombre: string;
    dni: string;
    empresa: string;
    area: string;
    cargo_actual: string;
    fecha_ingreso: string | null;
    gerencia: string;
    division?: string;
    jefatura?: string;
    tipo_personal?: string;
    foto_url?: string | null;
  };
  anio: number;
  antiguedad: string;
  consumido: number;
  disponible: number;
  fechas: string[];
  asistencia: string[];
  sin_marcacion: string[];
  no_laborables: string[];
  attendance_ok: boolean;
  periodos: { tipo: string; inicio: string; fin: string; dias: number }[];
  record?: {
    record_vacacional: string;
    cumple_record: string | null;
    fecha_vencimiento: string | null;
    dias_programados: number;
    dias_gozados: number;
    dias_pendientes: number;
    record_cumplido: boolean;
    derecho: number;
  };
};

const MESES = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];

const DAY_CLASS: Record<Exclude<DayKind, null>, string> = {
  vacacion: "bg-primary/15 font-semibold text-primary",
  asistencia: "bg-success-muted font-semibold text-success",
  falta: "bg-error-muted font-semibold text-error",
  nolab: "bg-muted text-muted-foreground",
  preingreso: "bg-muted/40 text-muted-foreground/55 opacity-45",
};

const LEGEND: { cls: string; label: string }[] = [
  { cls: "bg-primary/15 ring-1 ring-primary/30", label: "Vacaciones" },
  { cls: "bg-success-muted ring-1 ring-success/30", label: "Asistencia" },
  { cls: "bg-error-muted ring-1 ring-error/30", label: "Sin marcación" },
  { cls: "bg-muted ring-1 ring-border", label: "No laborable" },
  { cls: "bg-muted/40 opacity-45 ring-1 ring-border/60", label: "Antes del ingreso" },
];

function isoDay(year: number, month: number, day: number) {
  return `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function dayKind(
  iso: string,
  vac: Set<string>,
  asist: Set<string>,
  falta: Set<string>,
  nolab: Set<string>,
  ingresoIso: string | null
): DayKind {
  if (ingresoIso && iso < ingresoIso) return "preingreso";
  if (vac.has(iso)) return "vacacion";
  if (nolab.has(iso)) return "nolab";
  if (asist.has(iso)) return "asistencia";
  if (falta.has(iso)) return "falta";
  return null;
}

function formatFecha(iso: string | null | undefined) {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}

function MiniCal({
  year,
  month,
  vac,
  asist,
  falta,
  nolab,
  ingresoIso,
}: {
  year: number;
  month: number;
  vac: Set<string>;
  asist: Set<string>;
  falta: Set<string>;
  nolab: Set<string>;
  ingresoIso: string | null;
}) {
  const first = new Date(year, month, 1);
  const startPad = (first.getDay() + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: (number | null)[] = [
    ...Array(startPad).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  while (cells.length % 7) cells.push(null);

  const kindAt = (iso: string) => dayKind(iso, vac, asist, falta, nolab, ingresoIso);

  return (
    <div className="flex h-full min-h-0 flex-col rounded-lg border border-border/70 p-2">
      <div className="mb-1 shrink-0 text-[10px] font-semibold">{MESES[month]}</div>
      <div className="mb-0.5 grid shrink-0 grid-cols-7 text-center text-[7px] text-muted-foreground">
        {["L", "M", "X", "J", "V", "S", "D"].map((d, i) => (
          <div key={i}>{d}</div>
        ))}
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-7 auto-rows-fr">
        {cells.map((d, i) => {
          if (!d) return <div key={i} className="min-h-[18px]" />;
          const iso = isoDay(year, month, d);
          const kind = kindAt(iso);
          const prevKind = d > 1 ? kindAt(isoDay(year, month, d - 1)) : null;
          const nextKind = d < daysInMonth ? kindAt(isoDay(year, month, d + 1)) : null;
          const round =
            kind === "vacacion"
              ? `${prevKind === "vacacion" ? "" : "rounded-l-full"} ${nextKind === "vacacion" ? "" : "rounded-r-full"}`
              : "rounded-sm";
          const title =
            kind === "preingreso" && ingresoIso
              ? `${iso} · antes del ingreso (${formatFecha(ingresoIso)})`
              : iso;
          return (
            <div
              key={i}
              title={title}
              className={cn(
                "relative flex min-h-[18px] items-center justify-center text-[8px]",
                kind ? `${DAY_CLASS[kind]} ${round}` : "text-foreground"
              )}
            >
              {d}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SideCard({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-card px-3.5 py-3 shadow-[var(--shadow-card)]">
      {title ? <h3 className="mb-2 text-[12px] font-semibold">{title}</h3> : null}
      {children}
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 py-1.5 text-[11px]">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-right font-medium">{value || "—"}</span>
    </div>
  );
}

export function CalendarPage() {
  const { filters } = useApp();
  const [people, setPeople] = useState<Emp[]>([]);
  const [dni, setDni] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const deferredQ = useDeferredValue(q);
  const [year, setYear] = useState(filters.year);
  const [cal, setCal] = useState<Cal | null>(null);
  const [loadError, setLoadError] = useState("");
  const boxRef = useRef<HTMLDivElement>(null);
  const params = useMemo(
    () => ({
      empresa: filters.empresas.includes("TODAS") ? undefined : filters.empresas,
      gerencia: filters.gerencias.includes("TODAS") ? undefined : filters.gerencias,
      area: filters.areas.includes("TODAS") ? undefined : filters.areas,
    }),
    [filters]
  );

  useEffect(() => {
    setYear(filters.year);
  }, [filters.year]);

  useEffect(() => {
    let cancelled = false;
    api<{ items: Emp[] }>(`/api/employees${qs(params)}`)
      .then((r) => {
        if (cancelled) return;
        const items = r.items || [];
        setPeople(items);
        setDni((current) => {
          if (current && items.some((p) => p.dni === current)) return current;
          const first = items[0];
          if (first) {
            setQ(`${first.nombre} · ${first.dni}`);
            return first.dni;
          }
          setQ("");
          return "";
        });
      })
      .catch((e) => {
        if (cancelled) return;
        setPeople([]);
        setLoadError(e instanceof Error ? e.message : "No se pudo cargar el personal.");
      });
    return () => {
      cancelled = true;
    };
  }, [params]);

  useEffect(() => {
    if (!dni) {
      setCal(null);
      setLoadError("");
      return;
    }
    let cancelled = false;
    api<Cal>(`/api/calendar/${dni}${qs({ year })}`)
      .then((data) => {
        if (cancelled) return;
        setCal(data);
        setLoadError("");
      })
      .catch((e) => {
        if (cancelled) return;
        setCal(null);
        setLoadError(e instanceof Error ? e.message : "No se pudo cargar el récord.");
      });
    return () => {
      cancelled = true;
    };
  }, [dni, year]);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const matches = useMemo(() => {
    const terms = deferredQ
      .trim()
      .toLowerCase()
      .replace(/[·•|]/g, " ")
      .split(/\s+/)
      .filter(Boolean);
    if (!terms.length) return people.slice(0, 12);
    return people
      .filter((p) => {
        const hay = `${p.nombre} ${p.dni}`.toLowerCase();
        return terms.every((t) => hay.includes(t));
      })
      .slice(0, 12);
  }, [deferredQ, people]);

  function pick(p: Emp) {
    setDni(p.dni);
    setQ(`${p.nombre} · ${p.dni}`);
    setOpen(false);
  }

  const vac = useMemo(() => new Set(cal?.fechas || []), [cal?.fechas]);
  const asist = useMemo(() => new Set(cal?.asistencia || []), [cal?.asistencia]);
  const falta = useMemo(() => new Set(cal?.sin_marcacion || []), [cal?.sin_marcacion]);
  const nolab = useMemo(() => new Set(cal?.no_laborables || []), [cal?.no_laborables]);
  const ingresoIso = useMemo(() => {
    const raw = cal?.empleado?.fecha_ingreso;
    return raw ? raw.slice(0, 10) : null;
  }, [cal?.empleado?.fecha_ingreso]);

  const e = cal?.empleado;
  const rec = cal?.record;
  const derecho = rec?.derecho ?? 30;
  const usados = rec?.dias_programados ?? cal?.consumido ?? 0;
  const pendientes = rec?.dias_pendientes ?? Math.max(derecho - usados, 0);
  const gozados = rec?.dias_gozados ?? 0;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Récord vacacional"
        help="Se arma con la fecha de ingreso del maestro de trabajadores y los días que ya están en el cronograma / planificación."
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
        <Field label="EMPLEADO" className="min-w-0 w-full max-w-xl flex-1 sm:min-w-80">
          <div ref={boxRef} className="relative">
            <Input
              type="search"
              autoComplete="off"
              spellCheck={false}
              placeholder="Buscar nombre o DNI…"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setOpen(true);
                if (!e.target.value.trim()) {
                  setDni("");
                  setCal(null);
                }
              }}
              onFocus={() => setOpen(true)}
            />
            {open ? (
              <div className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-[10px] border border-border bg-card shadow-[var(--shadow-card)]">
                {people.length === 0 ? (
                  <p className="px-3 py-2.5 text-[13px] text-muted-foreground">No hay personas en este filtro.</p>
                ) : matches.length === 0 ? (
                  <p className="px-3 py-2.5 text-[13px] text-muted-foreground">Nadie coincide.</p>
                ) : (
                  matches.map((p) => (
                    <button
                      key={p.dni}
                      type="button"
                      className={cn(
                        "flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left text-[13px] hover:bg-muted",
                        p.dni === dni ? "bg-[var(--primary-soft)] text-primary" : "text-foreground"
                      )}
                      onClick={() => pick(p)}
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <EmpAvatar nombre={p.nombre} fotoUrl={p.foto_url} className="h-7 w-7 text-[9px]" />
                        <span className="min-w-0 truncate font-medium">{p.nombre}</span>
                      </span>
                      <span className="shrink-0 font-data text-[11px] text-muted-foreground">{p.dni}</span>
                    </button>
                  ))
                )}
              </div>
            ) : null}
          </div>
        </Field>
        <Field label="AÑO" className="w-full sm:w-36">
          <Select value={year} onChange={(e) => setYear(Number(e.target.value))}>
            {Array.from({ length: 5 }, (_, i) => new Date().getFullYear() - 1 + i).map((y) => (
              <option key={y}>{y}</option>
            ))}
          </Select>
        </Field>
      </div>

      {loadError ? (
        <Alert tone="error" title="No se pudo cargar">
          {loadError}
        </Alert>
      ) : null}

      {!dni ? (
        <EmptyState title="Elige a alguien" body="Busca por nombre o DNI." />
      ) : !cal ? (
        <p className="text-sm text-muted-foreground">Cargando…</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_280px] xl:items-stretch">
          <div className="flex h-full min-h-0 flex-col rounded-xl border border-border bg-card p-3 shadow-[var(--shadow-card)]">
            <div className="mb-2.5 flex shrink-0 flex-wrap items-center justify-between gap-2">
              <h3 className="text-[12px] font-semibold">Año {year}</h3>
              <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[10px] text-muted-foreground">
                {LEGEND.map((item) => (
                  <span key={item.label} className="inline-flex items-center gap-1">
                    <span className={cn("h-2 w-2 rounded-sm", item.cls)} />
                    {item.label}
                  </span>
                ))}
              </div>
            </div>

            <div className="grid min-h-0 flex-1 grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 lg:auto-rows-fr">
              {Array.from({ length: 12 }, (_, m) => (
                <MiniCal
                  key={m}
                  year={year}
                  month={m}
                  vac={vac}
                  asist={asist}
                  falta={falta}
                  nolab={nolab}
                  ingresoIso={ingresoIso}
                />
              ))}
            </div>

            {cal.periodos.length > 0 ? (
              <div className="mt-3 shrink-0 overflow-hidden rounded-lg border border-border">
                <table className="w-full text-[12px]">
                  <thead className="bg-muted text-left">
                    <tr>
                      {["Tipo", "Inicio", "Fin", "Días"].map((h) => (
                        <th key={h} className="px-2.5 py-1.5 text-[10px] font-semibold text-muted-foreground">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {cal.periodos.map((p, i) => (
                      <tr key={i} className="border-t border-border">
                        <td className="px-2.5 py-1.5">{p.tipo}</td>
                        <td className="px-2.5 py-1.5">{formatFecha(p.inicio)}</td>
                        <td className="px-2.5 py-1.5">{formatFecha(p.fin)}</td>
                        <td className="px-2.5 py-1.5">{p.dias}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>

          <aside className="flex h-full flex-col gap-2.5">
            <SideCard>
              <div className="flex items-center gap-2.5">
                <EmpAvatar nombre={e?.nombre || ""} fotoUrl={e?.foto_url} />
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-semibold leading-tight">{e?.nombre}</p>
                  <p className="font-data text-[11px] text-muted-foreground">{e?.dni}</p>
                </div>
              </div>
              <div className="mt-2 divide-y divide-border/80">
                <MetaRow label="Área" value={e?.area || "—"} />
                <MetaRow label="Cargo" value={e?.cargo_actual || "—"} />
                <MetaRow label="Antigüedad" value={cal.antiguedad} />
                <MetaRow label="Empresa" value={e?.empresa || "—"} />
                <MetaRow label="Gerencia" value={e?.gerencia || "—"} />
              </div>
            </SideCard>

            <SideCard title="Récord">
              <div className="divide-y divide-border/80">
                <MetaRow label="Período" value={rec?.record_vacacional || "—"} />
                <MetaRow label="Cumple récord" value={formatFecha(rec?.cumple_record)} />
                <MetaRow label="Vencimiento" value={formatFecha(rec?.fecha_vencimiento)} />
                <MetaRow label="Ingreso" value={formatFecha(e?.fecha_ingreso)} />
              </div>
            </SideCard>

            <SideCard title={`Vacaciones ${year}`}>
              <div className="grid grid-cols-2 gap-1.5">
                {[
                  { label: "Derecho", value: derecho, Icon: CalendarRange, tone: "text-primary bg-[var(--primary-soft)]" },
                  { label: "Programados", value: usados, Icon: CalendarCheck, tone: "text-success bg-success-muted" },
                  { label: "Gozados", value: gozados, Icon: CalendarClock, tone: "text-info bg-info-muted" },
                  { label: "Pendientes", value: pendientes, Icon: Layers, tone: "text-warning bg-warning-muted" },
                ].map(({ label, value, Icon, tone }) => (
                  <div
                    key={label}
                    className="flex h-[58px] items-center gap-2 rounded-lg border border-border bg-background/50 px-2"
                  >
                    <div className={cn("flex h-6 w-6 shrink-0 items-center justify-center rounded-md", tone)}>
                      <Icon size={12} strokeWidth={1.75} />
                    </div>
                    <div className="min-w-0">
                      <p className="text-[9px] leading-none text-muted-foreground">{label}</p>
                      <p className="font-data mt-0.5 text-[15px] font-semibold leading-none">{value}</p>
                    </div>
                  </div>
                ))}
              </div>
            </SideCard>

            <SideCard title="Datos">
              <div className="divide-y divide-border/80">
                <MetaRow label="Tipo" value={e?.tipo_personal || "—"} />
                <MetaRow label="División" value={e?.division || "—"} />
                <MetaRow label="Jefatura" value={e?.jefatura || "—"} />
                <MetaRow label="Ingreso" value={formatFecha(e?.fecha_ingreso)} />
              </div>
            </SideCard>

            <SideCard title="Firma">
              <div className="flex h-14 items-center justify-center rounded-md border border-dashed border-border bg-muted/30 text-muted-foreground">
                <PenLine size={14} strokeWidth={1.5} />
              </div>
              <p className="mt-1.5 truncate text-[11px] font-medium">{e?.nombre}</p>
            </SideCard>
          </aside>
        </div>
      )}
    </div>
  );
}

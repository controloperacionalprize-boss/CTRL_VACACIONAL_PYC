import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { CalendarCheck, CalendarClock, CalendarRange } from "lucide-react";
import { api, qs } from "../api";
import { useApp } from "../state";
import { EmptyState, Field, Input, Kpi, PageHeader, Select } from "../components/ui";

type Emp = { dni: string; nombre: string };
type Cal = {
  empleado: {
    nombre: string;
    dni: string;
    empresa: string;
    area: string;
    cargo_actual: string;
    fecha_ingreso: string | null;
    gerencia: string;
  };
  anio: number;
  antiguedad: string;
  consumido: number;
  disponible: number;
  fechas: string[];
  periodos: { tipo: string; inicio: string; fin: string; dias: number }[];
};
const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

function MiniCal({ year, month, marked }: { year: number; month: number; marked: Set<string> }) {
  const first = new Date(year, month, 1);
  const startPad = (first.getDay() + 6) % 7;
  const days = new Date(year, month + 1, 0).getDate();
  const cells: (number | null)[] = [...Array(startPad).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  while (cells.length % 7) cells.push(null);
  const today = new Date();
  const todayIso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;

  return (
    <div>
      <div className="mb-1.5 text-[11px] font-semibold">{MESES[month]}</div>
      <div className="mb-1 grid grid-cols-7 text-center text-[8px] text-muted-foreground">
        {["L", "M", "X", "J", "V", "S", "D"].map((d, i) => (
          <div key={i}>{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {cells.map((d, i) => {
          if (!d) return <div key={i} className="h-[20px]" />;
          const iso = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
          const on = marked.has(iso);
          const prev = marked.has(
            `${year}-${String(month + 1).padStart(2, "0")}-${String(d - 1).padStart(2, "0")}`
          );
          const next = marked.has(
            `${year}-${String(month + 1).padStart(2, "0")}-${String(d + 1).padStart(2, "0")}`
          );
          const isToday = iso === todayIso;
          return (
            <div
              key={i}
              className={`relative h-[20px] text-center text-[9px] leading-[20px] ${
                on
                  ? `bg-primary/15 font-semibold text-primary ${prev ? "" : "rounded-l-full"} ${next ? "" : "rounded-r-full"}`
                  : "text-foreground"
              }`}
            >
              {d}
              {isToday ? <span className="absolute bottom-0.5 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-success" /> : null}
            </div>
          );
        })}
      </div>
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
  const boxRef = useRef<HTMLDivElement>(null);
  const params = useMemo(
    () => ({
      empresa: filters.empresas.includes("TODAS") ? undefined : filters.empresas,
      gerencia: filters.gerencias.includes("TODAS") ? undefined : filters.gerencias,
      division: filters.divisiones.includes("TODAS") ? undefined : filters.divisiones,
    }),
    [filters]
  );

  useEffect(() => {
    api<{ items: Emp[] }>(`/api/employees${qs(params)}`).then((r) => {
      setPeople(r.items);
      if (!dni && r.items[0]) {
        setDni(r.items[0].dni);
        setQ(`${r.items[0].nombre} · ${r.items[0].dni}`);
      }
    });
  }, [params]);

  useEffect(() => {
    if (!dni) {
      setCal(null);
      return;
    }
    api<Cal>(`/api/calendar/${dni}${qs({ year })}`).then(setCal);
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

  const marked = new Set(cal?.fechas || []);

  return (
    <div className="space-y-6">
      <PageHeader title="Calendario del empleado" help="Busca por nombre o DNI. Luego ves los días y cuántos le quedan este año." />
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
                  <p className="px-3 py-2.5 text-[13px] text-muted-foreground">Nadie coincide. Prueba otro nombre o DNI.</p>
                ) : (
                  matches.map((p) => (
                    <button
                      key={p.dni}
                      type="button"
                      className={`flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left text-[13px] hover:bg-muted ${
                        p.dni === dni ? "bg-[var(--primary-soft)] text-primary" : "text-foreground"
                      }`}
                      onClick={() => pick(p)}
                    >
                      <span className="min-w-0 truncate font-medium">{p.nombre}</span>
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

      {!dni ? (
        <EmptyState title="Elige a alguien" body="Escribe el nombre o el DNI arriba para ver su calendario." />
      ) : cal ? (
        <div className="space-y-5">
          <div className="grid grid-cols-1 gap-4 rounded-xl border border-border bg-card p-4 text-sm shadow-[var(--shadow-card)] sm:grid-cols-2 md:grid-cols-4 md:gap-6">
            {[
              ["Empleado", cal.empleado.nombre],
              ["DNI", cal.empleado.dni],
              ["Área / cargo", `${cal.empleado.area} · ${cal.empleado.cargo_actual}`],
              ["Antigüedad", cal.antiguedad],
            ].map(([l, v]) => (
              <div key={l}>
                <div className="text-[11px] font-semibold text-muted-foreground">{l}</div>
                <div className="mt-1 font-medium">{v}</div>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Kpi label="Derecho anual" value={30} hint="Días que corresponden por año" icon={<CalendarRange size={18} strokeWidth={1.75} />} />
            <Kpi label="Usados" value={cal.consumido} hint="Ya programados" icon={<CalendarCheck size={18} strokeWidth={1.75} />} />
            <Kpi label="Disponibles" value={cal.disponible} hint={`Quedan para ${year}`} icon={<CalendarClock size={18} strokeWidth={1.75} />} />
          </div>
          <div className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)]">
            <h3 className="mb-4 text-[13px] font-semibold">Días programados en {year}</h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 md:gap-4">
              {Array.from({ length: 12 }, (_, m) => (
                <MiniCal key={m} year={year} month={m} marked={marked} />
              ))}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-4 border-t border-border pt-3 text-[11px] text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-primary" />
                Día programado
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-6 rounded-full bg-primary/15" />
                Rango de vacaciones
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-success" />
                Hoy
              </span>
            </div>
          </div>
          <div className="overflow-hidden rounded-[8px] border border-border bg-card shadow-[var(--shadow-card)]">
            <table className="w-full text-sm">
              <thead className="bg-muted text-left">
                <tr>
                  {["Tipo", "Inicio", "Fin", "Días"].map((h) => (
                    <th key={h} className="px-3 py-2 text-[11px] font-semibold text-muted-foreground">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {cal.periodos.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-3 py-2 text-muted-foreground">
                      Sin vacaciones programadas en este año.
                    </td>
                  </tr>
                ) : (
                  cal.periodos.map((p, i) => (
                    <tr key={i} className="border-t border-border">
                      <td className="px-3 py-2">{p.tipo}</td>
                      <td className="px-3 py-2">{p.inicio}</td>
                      <td className="px-3 py-2">{p.fin}</td>
                      <td className="px-3 py-2">{p.dias}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Cargando calendario…</p>
      )}
    </div>
  );
}

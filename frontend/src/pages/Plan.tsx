import { memo, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { api, qs } from "../api";
import { SEM_COLORS, weekLocked } from "../lib/semaforo";
import { useApp } from "../state";
import { Alert, Button, cn, EmptyState, Field, Input, Kpi, PageHeader } from "../components/ui";
import { EmpAvatar } from "../components/EmpAvatar";
import { CalendarClock, CalendarDays, CalendarPlus, CalendarRange, Users, UserCheck, UserX } from "lucide-react";

/** Derecho anual (mismo tope que backend DERECHO_ANUAL). */
const MAX_VAC_DAYS = 30;
const DAY_SHORT = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

type Worker = {
  dni: string;
  nombre: string;
  empresa: string;
  division: string;
  gerencia: string;
  area: string;
  cargo_actual: string;
  fecha_ingreso: string | null;
  tipo_personal: string;
  weeks: number[];
  total_dias: number;
  cambios: number;
  foto_url?: string | null;
  /** false = aún no cumple el año; solo puede pedir adelanto hasta tope_dias. */
  record_cumplido?: boolean;
  /** Tope real programable: 30 si ya cumplió el récord, o lo acumulado (adelanto) si no. */
  tope_dias?: number;
};

/** Tope real de un trabajador: 30 si ya cumplió el récord, o lo acumulado (adelanto). */
function topeDe(w: Pick<Worker, "tope_dias"> | null | undefined) {
  return w?.tope_dias ?? MAX_VAC_DAYS;
}

function esAdelanto<T extends Pick<Worker, "record_cumplido">>(
  w: T | null | undefined
): w is T & { record_cumplido: false } {
  return w != null && w.record_cumplido === false;
}

function formatFechaIso(iso: string | null | undefined) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}

function addDaysIso(iso: string, extra: number) {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + extra);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function etiquetaEstado(estado: string) {
  if (estado === "gozado") return "Gozado";
  if (estado === "en_curso") return "En curso";
  return "Programado";
}

type VacPeriod = {
  inicio: string;
  fin: string;
  dias: number;
  estado: string;
  editable: boolean;
};

type Plan = {
  year: number;
  today?: string;
  current_year: number;
  current_week: number;
  total_semanas: number;
  workers: Worker[];
  kpis: { trabajadores: number; programados: number; pendientes: number; dias: number };
};

type WeekDay = { fecha: string; weekday: number; selected: boolean; past?: boolean };

function scope(filters: ReturnType<typeof useApp>["filters"]) {
  return {
    year: filters.year,
    empresa: filters.empresas.includes("TODAS") ? undefined : filters.empresas,
    gerencia: filters.gerencias.includes("TODAS") ? undefined : filters.gerencias,
    area: filters.areas.includes("TODAS") ? undefined : filters.areas,
  };
}

function kpisFrom(workers: Worker[]) {
  return {
    trabajadores: workers.length,
    programados: workers.filter((w) => w.total_dias > 0).length,
    pendientes: workers.filter((w) => w.total_dias === 0).length,
    dias: workers.reduce((n, w) => n + w.total_dias, 0),
  };
}

function patchWorkerWeeks(workers: Worker[], dni: string, updates: Record<number, number>) {
  return workers.map((w) => {
    if (w.dni !== dni) return w;
    const weeks = w.weeks.map((v, i) => (i + 1 in updates ? updates[i + 1] : v));
    return { ...w, weeks, total_dias: weeks.reduce((a, b) => a + b, 0) };
  });
}

function cellColor(val: number) {
  if (!val) return "transparent";
  return SEM_COLORS[Math.min(val, 7)] || SEM_COLORS[7];
}

function formatDayLabel(iso: string) {
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

/** Días que aún puede pedir: tope (30, o acumulado si es adelanto) − ya programados. */
function diasDisponibles(programadosBase: number, tope: number = MAX_VAC_DAYS) {
  return Math.max(0, tope - Math.max(0, programadosBase));
}

/** Alerta de saldo insuficiente (misma lógica/texto que el backend). */
function msgSinSaldo(nombre: string, pedidas: number, programadosBase: number, tope: number = MAX_VAC_DAYS, adelanto = false) {
  const quien = nombre.trim() || "Este trabajador";
  const disponibles = diasDisponibles(programadosBase, tope);
  const etiqueta = adelanto ? "acumulado para adelanto" : "derecho anual";
  if (disponibles <= 0) {
    const extra = adelanto ? " (aún no cumple el año)" : "";
    return `No se puede programar ${pedidas} día(s) para ${quien}: ya tiene los ${tope} días de ${etiqueta} programados${extra}.`;
  }
  return `No se puede programar ${pedidas} día(s) para ${quien}: solo le quedan ${disponibles} día(s) disponible(s) (${etiqueta} ${tope}, ya programados ${programadosBase}).`;
}

function weeksFromApi(res: { weeks?: Record<string, number> }, fallbackWeek: number, fallbackDays: number) {
  if (!res.weeks) return { [fallbackWeek]: fallbackDays } as Record<number, number>;
  return Object.fromEntries(Object.entries(res.weeks).map(([k, v]) => [Number(k), v]));
}

/** YYYY-MM-DD local (calendario del navegador). */
function localTodayIso() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Edición local; confirma solo con Enter o al salir de la celda. */
const WeekInput = memo(function WeekInput({
  value,
  week,
  worker,
  onCommit,
  className,
}: {
  value: number;
  week: number;
  worker: Worker;
  onCommit: (w: Worker, week: number, days: number) => void;
  className: string;
}) {
  const [draft, setDraft] = useState(String(value));
  const committedRef = useRef(value);

  useEffect(() => {
    committedRef.current = value;
    setDraft(String(value));
  }, [value]);

  function commit(raw: string) {
    const prev = committedRef.current;
    if (raw.trim() === "") {
      setDraft(String(prev));
      return;
    }
    const n = Number(raw);
    if (!Number.isFinite(n)) {
      setDraft(String(prev));
      return;
    }
    const clamped = Math.max(0, Math.min(MAX_VAC_DAYS, Math.round(n)));
    if (clamped !== prev) {
      onCommit(worker, week, clamped);
      // >7 no se pinta en la celda hasta guardar (derrame); mantener valor anterior a la vista.
      if (clamped > 7) {
        setDraft(String(prev));
        return;
      }
    }
    setDraft(String(clamped));
  }

  return (
    <input
      type="number"
      min={0}
      max={MAX_VAC_DAYS}
      title={`0–${MAX_VAC_DAYS} días (más de 7 se reparte en semanas siguientes)`}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => {
        if (e.key !== "Enter") return;
        e.preventDefault();
        (e.target as HTMLInputElement).blur();
      }}
      onBlur={(e) => commit(e.target.value)}
      className={className}
      style={{ background: value ? cellColor(value) : "transparent" }}
    />
  );
});

const WorkerRow = memo(function WorkerRow({
  w,
  lockedWeeks,
  onDays,
}: {
  w: Worker;
  lockedWeeks: boolean[];
  onDays: (w: Worker, week: number, days: number) => void;
}) {
  return (
    <tr className="hover:bg-muted/60" style={{ contentVisibility: "auto", containIntrinsicSize: "auto 32px" }}>
      <td className="sticky left-0 z-10 whitespace-nowrap border-b border-border bg-card px-2.5 py-1 font-semibold">
        <span className="inline-flex max-w-[220px] items-center gap-2">
          <EmpAvatar nombre={w.nombre} fotoUrl={w.foto_url} className="h-7 w-7 text-[9px]" />
          <span className="truncate">{w.nombre}</span>
        </span>
      </td>
      <td className="border-b border-border px-2.5 py-1 text-muted-foreground">{w.dni}</td>
      <td className="border-b border-border px-2.5 py-1">{w.area}</td>
      <td className="border-b border-border px-2.5 py-1">{w.tipo_personal}</td>
      <td className="border-b border-border px-2.5 py-1 text-center">{w.total_dias}</td>
      {w.weeks.map((val, idx) => {
        const week = idx + 1;
        const locked = lockedWeeks[idx];
        const bg = val ? cellColor(val) : locked ? "var(--muted)" : "transparent";
        if (locked) {
          return (
            <td
              key={week}
              className="h-8 w-9 border-b border-border p-0 text-center text-[11px] font-medium text-muted-foreground"
              style={{ background: bg }}
            >
              {val || ""}
            </td>
          );
        }
        return (
          <td key={week} className="border-b border-border p-0">
            <WeekInput
              value={val}
              week={week}
              worker={w}
              onCommit={onDays}
              className="h-8 w-9 bg-transparent text-center text-[11px] font-medium outline-none"
            />
          </td>
        );
      })}
    </tr>
  );
});

const WorkerCard = memo(function WorkerCard({
  w,
  weekWindow,
  lockedWeeks,
  onDays,
}: {
  w: Worker;
  weekWindow: number[];
  lockedWeeks: boolean[];
  onDays: (w: Worker, week: number, days: number) => void;
}) {
  return (
    <article className="rounded-xl border border-border bg-card p-3.5 shadow-[var(--shadow-card)]">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <EmpAvatar nombre={w.nombre} fotoUrl={w.foto_url} className="h-9 w-9 text-[11px]" />
          <div className="min-w-0">
            <p className="truncate text-[14px] font-semibold">{w.nombre}</p>
            <p className="mt-0.5 text-[12px] text-muted-foreground">
              {w.dni} · {w.area || w.tipo_personal}
            </p>
          </div>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-lg px-2 py-1 text-[11px] font-semibold",
            w.total_dias === 0 ? "bg-warning-muted text-warning" : "bg-[var(--primary-soft)] text-primary"
          )}
        >
          {w.total_dias === 0 ? "Sin días" : `${w.total_dias} días`}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-6 gap-1.5">
        {weekWindow.map((week) => {
          const idx = week - 1;
          const val = w.weeks[idx] || 0;
          const locked = lockedWeeks[idx];
          const bg = val ? cellColor(val) : locked ? "var(--muted)" : "transparent";
          return (
            <label key={week} className="flex flex-col items-center gap-0.5">
              <span className="text-[9px] font-semibold text-muted-foreground">S{week}</span>
              {locked ? (
                <span
                  className="flex h-9 w-full items-center justify-center rounded-md border border-border text-[11px] font-medium text-muted-foreground"
                  style={{ background: bg }}
                >
                  {val || "—"}
                </span>
              ) : (
                <WeekInput
                  value={val}
                  week={week}
                  worker={w}
                  onCommit={onDays}
                  className="h-9 w-full rounded-md border border-border text-center text-[11px] font-medium outline-none"
                />
              )}
            </label>
          );
        })}
      </div>
    </article>
  );
});

export function PlanPage() {
  const { filters } = useApp();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [q, setQ] = useState("");
  const deferredQ = useDeferredValue(q);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [modal, setModal] = useState<{
    dni: string;
    nombre: string;
    foto_url?: string | null;
    week: number;
    days: number;
    prevDays: number;
    disponibles: number;
    tope: number;
  } | null>(null);
  const [start, setStart] = useState("");
  const [modalError, setModalError] = useState("");
  const [modalSaving, setModalSaving] = useState(false);
  const [weekDays, setWeekDays] = useState<WeekDay[]>([]);
  const [weekDaysLoading, setWeekDaysLoading] = useState(false);
  const [consec, setConsec] = useState({ dni: "", start: "", days: 6 });
  const [consecSaving, setConsecSaving] = useState(false);
  const [consecQ, setConsecQ] = useState("");
  const [consecOpen, setConsecOpen] = useState(false);
  const deferredConsecQ = useDeferredValue(consecQ);
  const consecBoxRef = useRef<HTMLDivElement>(null);
  const adelantoBoxRef = useRef<HTMLDivElement>(null);
  const [adelantoOpen, setAdelantoOpen] = useState(false);
  const [adelantoError, setAdelantoError] = useState("");
  const [modificarOpen, setModificarOpen] = useState(false);
  const [modificarError, setModificarError] = useState("");
  const [periodos, setPeriodos] = useState<VacPeriod[]>([]);
  const [periodosLoading, setPeriodosLoading] = useState(false);
  const [periodoSel, setPeriodoSel] = useState("");
  const [modStart, setModStart] = useState("");
  const [loadError, setLoadError] = useState("");

  const params = useMemo(() => scope(filters), [filters]);

  const load = useCallback(async () => {
    const data = await api<Plan>(`/api/plan${qs(params)}`);
    setPlan(data);
    setLoadError("");
    const first = data.workers[0];
    const minDay = data.today || localTodayIso();
    setConsec((c) => {
      const start = !c.start || c.start < minDay ? minDay : c.start;
      if (c.dni && data.workers.some((w) => w.dni === c.dni)) return { ...c, start };
      return { ...c, dni: first?.dni || "", start };
    });
    setConsecQ((q) => {
      if (q.trim()) return q;
      return first ? `${first.nombre} · ${first.dni}` : "";
    });
  }, [params]);

  useEffect(() => {
    load().catch((e) => setLoadError(e instanceof Error ? e.message : "No se pudo cargar el plan."));
  }, [load]);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      const t = e.target as Node;
      if (!consecBoxRef.current?.contains(t) && !adelantoBoxRef.current?.contains(t)) setConsecOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const lockedWeeks = useMemo(() => {
    if (!plan) return [];
    return Array.from({ length: plan.total_semanas }, (_, i) =>
      weekLocked(plan.year, i + 1, plan.current_year, plan.current_week)
    );
  }, [plan?.year, plan?.current_year, plan?.current_week, plan?.total_semanas]);

  const weekWindow = useMemo(() => {
    if (!plan) return [];
    const start = Math.max(1, (plan.current_week || 1) - 1);
    const end = Math.min(plan.total_semanas, start + 5);
    return Array.from({ length: end - start + 1 }, (_, i) => start + i);
  }, [plan?.current_week, plan?.total_semanas]);

  const searchIndex = useMemo(
    () =>
      (plan?.workers || []).map((w) => ({
        w,
        hay: `${w.nombre} ${w.dni} ${w.area} ${w.tipo_personal} ${w.division} ${w.gerencia}`.toLowerCase(),
      })),
    [plan?.workers]
  );

  const visible = useMemo(() => {
    const terms = deferredQ.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return plan?.workers || [];
    return searchIndex.filter((row) => terms.every((t) => row.hay.includes(t))).map((row) => row.w);
  }, [deferredQ, plan?.workers, searchIndex]);

  const consecMatches = useMemo(() => {
    const workers = plan?.workers || [];
    const terms = deferredConsecQ
      .trim()
      .toLowerCase()
      .replace(/[·•|]/g, " ")
      .split(/\s+/)
      .filter(Boolean);
    if (!terms.length) return workers.slice(0, 12);
    return workers
      .filter((w) => {
        const hay = `${w.nombre} ${w.dni}`.toLowerCase();
        return terms.every((t) => hay.includes(t));
      })
      .slice(0, 12);
  }, [deferredConsecQ, plan?.workers]);

  const consecWorker = useMemo(
    () => plan?.workers.find((w) => w.dni === consec.dni) || null,
    [plan?.workers, consec.dni]
  );

  function pickConsec(w: Worker) {
    setConsec((c) => ({ ...c, dni: w.dni }));
    setConsecQ(`${w.nombre} · ${w.dni}`);
    setConsecOpen(false);
    setPeriodoSel("");
  }

  useEffect(() => {
    if (!modificarOpen || !consec.dni) {
      setPeriodos([]);
      return;
    }
    let cancelled = false;
    setPeriodosLoading(true);
    api<{ periodos: VacPeriod[] }>(`/api/plan/periods${qs({ year: params.year, dni: consec.dni })}`)
      .then((r) => {
        if (cancelled) return;
        setPeriodos(r.periodos || []);
      })
      .catch(() => {
        if (!cancelled) setPeriodos([]);
      })
      .finally(() => {
        if (!cancelled) setPeriodosLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [modificarOpen, consec.dni, params.year]);

  const applyLocalWeeks = useCallback((dni: string, updates: Record<number, number>) => {
    setPlan((p) => {
      if (!p) return p;
      const workers = patchWorkerWeeks(p.workers, dni, updates);
      return { ...p, workers, kpis: kpisFrom(workers) };
    });
  }, []);

  const setWeek = useCallback(
    async (w: Worker, week: number, days: number, startDate?: string) => {
      setError("");
      setOk("");
      if (Number.isNaN(days) || days < 0 || days > MAX_VAC_DAYS) {
        const msg = `Indica entre 0 y ${MAX_VAC_DAYS} días.`;
        setError(msg);
        return msg;
      }
      if (weekLocked(plan?.year ?? params.year, week, plan?.current_year ?? 0, plan?.current_week ?? 0)) {
        const msg = `La semana ${week} ya pasó. Solo puedes editar la semana ${plan?.current_week ?? "en curso"} y las siguientes.`;
        setError(msg);
        return msg;
      }
      if (days > 0 && !startDate) {
        const msg = "Indica desde qué fecha empiezan las vacaciones.";
        setError(msg);
        return msg;
      }
      try {
        const res = await api<{ weeks?: Record<string, number> }>("/api/plan/week", {
          method: "PATCH",
          body: JSON.stringify({
            ...params,
            dni: w.dni,
            week,
            days,
            start_date: startDate || null,
          }),
        });
        const updates = weeksFromApi(res, week, days);
        applyLocalWeeks(w.dni, updates);
        const spill = Object.keys(updates).filter((k) => Number(k) !== week);
        setOk(
          days === 0
            ? "Listo: se quitaron las vacaciones de esa semana."
            : spill.length
              ? `Listo: ${days} día(s) repartidos — ${Object.entries(updates)
                  .sort((a, b) => Number(a[0]) - Number(b[0]))
                  .map(([wk, n]) => `S${wk}=${n}`)
                  .join(", ")}.`
              : `Listo: se guardaron ${days} día(s) en la semana ${week}.`
        );
        return "";
      } catch (e) {
        const msg = e instanceof Error ? e.message : "No se pudo guardar la semana.";
        setError(msg);
        return msg;
      }
    },
    [applyLocalWeeks, params, plan?.year, plan?.current_year, plan?.current_week]
  );

  const onDays = useCallback(
    (w: Worker, week: number, days: number) => {
      if (esAdelanto(w) && days > 0) {
        setOk("");
        setError(
          `${w.nombre} aún no cumple el año de servicio. Programa esos días con Adelanto vacacional.`
        );
        return;
      }
      if (Number.isNaN(days) || days < 0 || days > MAX_VAC_DAYS) {
        setError(`Indica entre 0 y ${MAX_VAC_DAYS} días.`);
        return;
      }
      const prevDays = w.weeks[week - 1] || 0;
      if (days === 0) {
        applyLocalWeeks(w.dni, { [week]: 0 });
        void setWeek(w, week, 0).then((msg) => {
          if (msg) applyLocalWeeks(w.dni, { [week]: prevDays });
        });
        return;
      }
      const programadosBase = Math.max(0, w.total_dias - prevDays);
      const disponibles = diasDisponibles(programadosBase, MAX_VAC_DAYS);
      if (days > disponibles) {
        setOk("");
        setError(msgSinSaldo(w.nombre, days, programadosBase, MAX_VAC_DAYS, false));
        return;
      }
      setModalError("");
      setStart("");
      setWeekDays([]);
      setError("");
      setOk("");
      // No pintar N>7 en una sola celda: el valor real llega al guardar (derrame).
      if (days <= 7) applyLocalWeeks(w.dni, { [week]: days });
      setModal({
        dni: w.dni,
        nombre: w.nombre,
        foto_url: w.foto_url,
        week,
        days,
        prevDays,
        disponibles,
        tope: MAX_VAC_DAYS,
      });
    },
    [applyLocalWeeks, setWeek]
  );

  useEffect(() => {
    if (!modal) return;
    const { dni, week } = modal;
    let cancelled = false;
    setWeekDaysLoading(true);
    api<{ dates: WeekDay[] }>(`/api/plan/week-detail${qs({ year: params.year, dni, week })}`)
      .then((r) => {
        if (cancelled) return;
        const dates = r.dates || [];
        setWeekDays(dates);
        const firstOk = dates.find((d) => !d.past && !d.selected) || dates.find((d) => !d.past);
        setStart(firstOk?.fecha || "");
      })
      .catch(() => {
        if (!cancelled) setWeekDays([]);
      })
      .finally(() => {
        if (!cancelled) setWeekDaysLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [modal?.dni, modal?.week, params.year]);

  function closeModal(revert: boolean) {
    if (modal && revert) applyLocalWeeks(modal.dni, { [modal.week]: modal.prevDays });
    setModal(null);
    setStart("");
    setModalError("");
    setModalSaving(false);
    setWeekDays([]);
  }

  async function programarConsec() {
    setError("");
    setOk("");
    if (!consec.dni) {
      setError("Selecciona a la persona.");
      return;
    }
    if (!consec.start) {
      setError("Indica desde qué día empiezan las vacaciones.");
      return;
    }
    const worker = plan?.workers.find((w) => w.dni === consec.dni);
    if (!worker) {
      setError("Esa persona ya no está en el filtro actual.");
      return;
    }
    if (esAdelanto(worker)) {
      setError(`${worker.nombre} aún no cumple el año de servicio. Usa Adelanto vacacional.`);
      return;
    }
    if (!Number.isFinite(consec.days) || consec.days < 1 || consec.days > MAX_VAC_DAYS) {
      setError(`Indica cuántos días son (entre 1 y ${MAX_VAC_DAYS}).`);
      return;
    }
    if (consec.days > diasDisponibles(worker.total_dias, MAX_VAC_DAYS)) {
      setError(msgSinSaldo(worker.nombre, consec.days, worker.total_dias, MAX_VAC_DAYS, false));
      return;
    }
    const startDt = new Date(`${consec.start}T00:00:00`);
    if (Number.isNaN(startDt.getTime())) {
      setError("La fecha de inicio no es válida.");
      return;
    }
    const todayIso = plan?.today || localTodayIso();
    if (consec.start < todayIso) {
      setError(
        `No se puede programar desde una fecha anterior a hoy (${todayIso.slice(8, 10)}/${todayIso.slice(5, 7)}/${todayIso.slice(0, 4)}).`
      );
      return;
    }
    setConsecSaving(true);
    try {
      const res = await api<{ fechas?: string[]; fin?: string }>("/api/plan/consecutive", {
        method: "POST",
        body: JSON.stringify({
          ...params,
          dni: consec.dni,
          start_date: consec.start,
          days: consec.days,
        }),
      });
      await load();
      const fin = res.fin || (res.fechas && res.fechas[res.fechas.length - 1]) || "";
      setOk(
        fin
          ? `Listo: se programaron ${consec.days} día(s) del ${formatFechaIso(consec.start)} al ${formatFechaIso(fin)}.`
          : `Listo: se programaron ${consec.days} día(s) desde el ${consec.start}.`
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron guardar esas vacaciones.");
    } finally {
      setConsecSaving(false);
    }
  }

  async function guardarAdelanto() {
    setAdelantoError("");
    if (!consec.dni) {
      setAdelantoError("Selecciona a la persona.");
      return;
    }
    if (!consec.start) {
      setAdelantoError("Indica desde qué día empiezan las vacaciones.");
      return;
    }
    const worker = plan?.workers.find((w) => w.dni === consec.dni);
    if (!worker) {
      setAdelantoError("Esa persona ya no está en el filtro actual.");
      return;
    }
    if (!esAdelanto(worker)) {
      setAdelantoError(
        `${worker.nombre} ya cumplió el año de servicio. Programa vacaciones normales (hasta ${MAX_VAC_DAYS} días).`
      );
      return;
    }
    const tope = topeDe(worker);
    if (!Number.isFinite(consec.days) || consec.days < 1 || consec.days > tope) {
      setAdelantoError(`Indica cuántos días son (entre 1 y ${tope}, según lo acumulado).`);
      return;
    }
    if (consec.days > diasDisponibles(worker.total_dias, tope)) {
      setAdelantoError(msgSinSaldo(worker.nombre, consec.days, worker.total_dias, tope, true));
      return;
    }
    const todayIso = plan?.today || localTodayIso();
    if (consec.start < todayIso) {
      setAdelantoError("No se puede programar desde una fecha anterior a hoy.");
      return;
    }
    setConsecSaving(true);
    try {
      await api("/api/plan/consecutive", {
        method: "POST",
        body: JSON.stringify({
          ...params,
          dni: consec.dni,
          start_date: consec.start,
          days: consec.days,
        }),
      });
      await load();
      setAdelantoOpen(false);
      setOk(
        `Listo: se adelantaron ${consec.days} día(s) para ${worker.nombre} desde el ${consec.start} (tope acumulado ${tope}).`
      );
      setError("");
    } catch (e) {
      setAdelantoError(e instanceof Error ? e.message : "No se pudo guardar el adelanto.");
    } finally {
      setConsecSaving(false);
    }
  }

  async function guardarModificar() {
    setModificarError("");
    if (!consec.dni) {
      setModificarError("Selecciona a la persona.");
      return;
    }
    if (!periodoSel) {
      setModificarError("Elige el período que quieres mover.");
      return;
    }
    if (!modStart) {
      setModificarError("Indica la nueva fecha de inicio.");
      return;
    }
    const periodo = periodos.find((p) => p.inicio === periodoSel);
    if (!periodo) {
      setModificarError("Ese período ya no está disponible.");
      return;
    }
    if (!periodo.editable) {
      setModificarError("Ese período ya comenzó o ya fue gozado; no se puede cambiar.");
      return;
    }
    const todayIso = plan?.today || localTodayIso();
    if (modStart < todayIso) {
      setModificarError("La nueva fecha no puede ser anterior a hoy.");
      return;
    }
    setConsecSaving(true);
    try {
      const res = await api<{ fin?: string }>("/api/plan/period-move", {
        method: "POST",
        body: JSON.stringify({
          year: params.year,
          dni: consec.dni,
          old_start: periodoSel,
          new_start: modStart,
          days: periodo.dias,
        }),
      });
      await load();
      setModificarOpen(false);
      setOk(
        `Listo: el período de ${periodo.dias} día(s) pasó del ${formatFechaIso(periodo.inicio)} al ${formatFechaIso(modStart)}` +
          (res.fin ? ` (termina ${formatFechaIso(res.fin)})` : "") +
          ". El saldo no se volvió a descontar."
      );
      setError("");
    } catch (e) {
      setModificarError(e instanceof Error ? e.message : "No se pudo modificar el período.");
    } finally {
      setConsecSaving(false);
    }
  }

  if (loadError && !plan) {
    return (
      <div className="space-y-6">
        <PageHeader title="Planificación" help="No se pudo abrir la grilla. Comprueba tu conexión e inténtalo de nuevo." />
        <Alert tone="error" title="No se pudo cargar el plan">
          {loadError}
        </Alert>
      </div>
    );
  }

  if (!plan) return <p className="text-sm text-muted-foreground">Cargando plan…</p>;

  const minProgramable = plan.today || localTodayIso();
  const finEstimado =
    consec.start && consec.days > 0 ? addDaysIso(consec.start, consec.days - 1) : "";

  return (
    <div className="space-y-6">
      <PageHeader
        title="Planificación"
        help={`Estás en la semana ${plan.current_week}. Solo se programan días desde hoy hacia adelante; semanas anteriores no se editan.`}
      />

      {error ? (
        <Alert tone="error" title="No se puede programar">
          {error}
        </Alert>
      ) : null}
      {ok ? (
        <Alert tone="success" title="Guardado">
          {ok}
        </Alert>
      ) : null}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
        <Kpi label="Trabajadores" value={plan.kpis.trabajadores} hint="Personas en este filtro" icon={<Users size={18} strokeWidth={1.75} />} />
        <Kpi label="Programados" value={plan.kpis.programados} hint="Ya tienen vacaciones" icon={<UserCheck size={18} strokeWidth={1.75} />} />
        <Kpi label="Sin programación" value={plan.kpis.pendientes} hint={`Aún sin días en ${plan.year}`} icon={<UserX size={18} strokeWidth={1.75} />} />
        <Kpi label="Días programados" value={plan.kpis.dias} hint="Suma de todas las semanas" icon={<CalendarDays size={18} strokeWidth={1.75} />} />
      </div>

      <div className="grid grid-cols-1 items-end gap-3 rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)] sm:grid-cols-2 md:grid-cols-[2fr_1fr_1fr]">
        <Field label="TRABAJADOR" className="sm:col-span-2 md:col-span-1">
          <div ref={consecBoxRef} className="relative">
            <Input
              type="search"
              autoComplete="off"
              spellCheck={false}
              placeholder="Buscar nombre o DNI…"
              value={consecQ}
              onChange={(e) => {
                setConsecQ(e.target.value);
                setConsecOpen(true);
                if (!e.target.value.trim()) setConsec((c) => ({ ...c, dni: "" }));
              }}
              onFocus={() => setConsecOpen(true)}
            />
            {consecOpen ? (
              <div className="absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-[10px] border border-border bg-card shadow-[var(--shadow-card)]">
                {plan.workers.length === 0 ? (
                  <p className="px-3 py-2.5 text-[13px] text-muted-foreground">No hay personas en este filtro.</p>
                ) : consecMatches.length === 0 ? (
                  <p className="px-3 py-2.5 text-[13px] text-muted-foreground">Nadie coincide. Prueba otro nombre o DNI.</p>
                ) : (
                  consecMatches.map((w) => (
                    <button
                      key={w.dni}
                      type="button"
                      className={`flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left text-[13px] hover:bg-muted ${
                        w.dni === consec.dni ? "bg-[var(--primary-soft)] text-primary" : "text-foreground"
                      }`}
                      onClick={() => pickConsec(w)}
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <EmpAvatar nombre={w.nombre} fotoUrl={w.foto_url} className="h-7 w-7 text-[9px]" />
                        <span className="min-w-0 truncate font-medium">{w.nombre}</span>
                      </span>
                      <span className="shrink-0 font-data text-[11px] text-muted-foreground">{w.dni}</span>
                    </button>
                  ))
                )}
              </div>
            ) : null}
          </div>
        </Field>
        <Field label="FECHA INICIO">
          <Input
            type="date"
            min={minProgramable}
            value={consec.start || minProgramable}
            onChange={(e) => {
              const v = e.target.value;
              setConsec({ ...consec, start: v && v < minProgramable ? minProgramable : v });
            }}
          />
        </Field>
        <Field label="DÍAS">
          <Input
            type="number"
            min={1}
            max={MAX_VAC_DAYS}
            value={consec.days}
            onChange={(e) => setConsec({ ...consec, days: Number(e.target.value) })}
          />
        </Field>
        <div className="flex flex-col gap-2 sm:col-span-2 sm:flex-row md:col-span-3">
          <Button onClick={programarConsec} disabled={consecSaving} className="w-full md:w-auto">
            <CalendarPlus size={16} strokeWidth={1.75} />
            {consecSaving && !adelantoOpen ? "Guardando…" : "Programar vacaciones"}
          </Button>
          <Button
            variant="outline"
            disabled={consecSaving}
            className="w-full md:w-auto"
            onClick={() => {
              setAdelantoError("");
              setError("");
              setOk("");
              setAdelantoOpen(true);
            }}
          >
            <CalendarClock size={16} strokeWidth={1.75} />
            Adelanto vacacional
          </Button>
          <Button
            variant="outline"
            disabled={consecSaving}
            className="w-full md:w-auto"
            onClick={() => {
              setModificarError("");
              setError("");
              setOk("");
              setPeriodoSel("");
              setModStart(minProgramable);
              setModificarOpen(true);
            }}
          >
            <CalendarRange size={16} strokeWidth={1.75} />
            Modificar período
          </Button>
        </div>
        {finEstimado ? (
          <p className="text-[12px] text-muted-foreground sm:col-span-2 md:col-span-3">
            Termina el {formatFechaIso(finEstimado)}
            {consec.days === MAX_VAC_DAYS ? " · goce completo" : " · fraccionamiento si ya hay otros tramos"}
          </p>
        ) : null}
        <p className="text-[11px] text-muted-foreground sm:col-span-2 md:col-span-3">
          Art. 8: un bloque de 15 días corridos, o 7+8. El resto, desde 1 día. Sin cruces de fechas.
        </p>
      </div>

      <div className="flex w-full max-w-sm items-center gap-2">
        <Input
          type="search"
          autoComplete="off"
          spellCheck={false}
          className="max-w-sm"
          placeholder="Buscar nombre, DNI, área…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {q ? (
          <span className="whitespace-nowrap text-xs text-muted-foreground">
            {visible.length} de {plan.workers.length}
          </span>
        ) : null}
      </div>

      {plan.workers.length === 0 ? (
        <EmptyState
          title="No hay trabajadores"
          body="Cambia el año, la empresa, la gerencia o el área. Con este filtro no aparece nadie."
        />
      ) : visible.length === 0 ? (
        <EmptyState title="Nadie coincide" body="Prueba con otro nombre, DNI o área." />
      ) : (
        <>
          <div className="space-y-3 md:hidden">
            <p className="text-[11px] text-muted-foreground">
              Semanas {weekWindow[0]}–{weekWindow[weekWindow.length - 1]} (alrededor de la actual). En escritorio ves el año completo.
            </p>
            {visible.map((w) => (
              <WorkerCard key={w.dni} w={w} weekWindow={weekWindow} lockedWeeks={lockedWeeks} onDays={onDays} />
            ))}
          </div>
          <div className="hidden max-h-[70vh] overflow-auto rounded-[8px] border border-border bg-card shadow-[var(--shadow-card)] md:block">
            <table className="border-collapse text-xs">
              <thead>
                <tr className="bg-muted">
                  {["Nombre", "DNI", "Área", "Tipo", "Total"].map((h) => (
                    <th
                      key={h}
                      className="sticky top-0 z-20 border-b border-border bg-muted px-2.5 py-2 text-left text-[11px] font-semibold text-muted-foreground"
                    >
                      {h}
                    </th>
                  ))}
                  {Array.from({ length: plan.total_semanas }, (_, i) => i + 1).map((w) => {
                    const locked = lockedWeeks[w - 1];
                    const current = plan.year === plan.current_year && w === plan.current_week;
                    return (
                      <th
                        key={w}
                        className={`sticky top-0 z-10 min-w-9 border-b border-border px-1 py-2 text-center text-[11px] font-semibold ${
                          current ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                        }`}
                      >
                        {locked ? <span className="opacity-60">S{w}</span> : `S${w}`}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {visible.map((w) => (
                  <WorkerRow key={w.dni} w={w} lockedWeeks={lockedWeeks} onDays={onDays} />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
        <span className="font-semibold text-foreground">Leyenda</span>
        {[
          [0, "0"],
          [1, "1–2"],
          [3, "3"],
          [4, "4–5"],
          [6, "6"],
          [7, "7"],
        ].map(([days, label]) => (
          <span key={label} className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-3.5 w-5 rounded-[3px] border border-border"
              style={{ background: SEM_COLORS[Number(days)] === "transparent" ? "#fff" : SEM_COLORS[Number(days)] }}
            />
            {label} días
          </span>
        ))}
      </div>

      {adelantoOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay)] p-4">
          <div className="w-full max-w-[480px] rounded-xl border border-border bg-card shadow-[0_8px_24px_#1E2C3A14]">
            <div className="space-y-1.5 px-5 pt-5">
              <h3 className="text-[15px] font-semibold">Adelanto vacacional</h3>
              <p className="text-[13px] text-muted-foreground">
                Solo si aún no cumple el año. El tope es 2.5 días por mes trabajado.
              </p>
            </div>
            <div className="space-y-3 px-5 py-3">
              <Field label="TRABAJADOR">
                <div ref={adelantoBoxRef} className="relative">
                  <Input
                    type="search"
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="Buscar nombre o DNI…"
                    value={consecQ}
                    onChange={(e) => {
                      setConsecQ(e.target.value);
                      setConsecOpen(true);
                      if (!e.target.value.trim()) setConsec((c) => ({ ...c, dni: "" }));
                    }}
                    onFocus={() => setConsecOpen(true)}
                  />
                  {consecOpen ? (
                    <div className="absolute z-30 mt-1 max-h-56 w-full overflow-auto rounded-[10px] border border-border bg-card shadow-[var(--shadow-card)]">
                      {consecMatches.length === 0 ? (
                        <p className="px-3 py-2.5 text-[13px] text-muted-foreground">Nadie coincide.</p>
                      ) : (
                        consecMatches.map((w) => (
                          <button
                            key={w.dni}
                            type="button"
                            className={`flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left text-[13px] hover:bg-muted ${
                              w.dni === consec.dni ? "bg-[var(--primary-soft)] text-primary" : "text-foreground"
                            }`}
                            onClick={() => pickConsec(w)}
                          >
                            <span className="flex min-w-0 items-center gap-2">
                              <EmpAvatar nombre={w.nombre} fotoUrl={w.foto_url} className="h-7 w-7 text-[9px]" />
                              <span className="min-w-0 truncate font-medium">{w.nombre}</span>
                            </span>
                            <span className="shrink-0 font-data text-[11px] text-muted-foreground">{w.dni}</span>
                          </button>
                        ))
                      )}
                    </div>
                  ) : null}
                </div>
              </Field>

              {consecWorker && esAdelanto(consecWorker) ? (
                <div className="rounded-lg border border-border bg-muted/40 px-3 py-2.5 text-[13px]">
                  <p>
                    Ingreso:{" "}
                    <span className="font-data font-medium">{formatFechaIso(consecWorker.fecha_ingreso)}</span>
                  </p>
                  <p className="mt-1">
                    Acumulado:{" "}
                    <span className="font-semibold text-foreground">{topeDe(consecWorker)} día(s)</span>
                    {" · "}
                    Ya programados: {consecWorker.total_dias}
                    {" · "}
                    Disponibles:{" "}
                    <span className="font-semibold text-foreground">
                      {diasDisponibles(consecWorker.total_dias, topeDe(consecWorker))}
                    </span>
                  </p>
                </div>
              ) : consecWorker ? (
                <Alert tone="warning" title="No aplica adelanto">
                  {consecWorker.nombre} ya cumplió el año. Usa Programar vacaciones (hasta {MAX_VAC_DAYS} días).
                </Alert>
              ) : (
                <p className="text-[13px] text-muted-foreground">Elige a la persona para ver cuánto tiene acumulado.</p>
              )}

              <div className="grid grid-cols-2 gap-3">
                <Field label="FECHA INICIO">
                  <Input
                    type="date"
                    min={minProgramable}
                    value={consec.start || minProgramable}
                    onChange={(e) => {
                      const v = e.target.value;
                      setConsec({ ...consec, start: v && v < minProgramable ? minProgramable : v });
                    }}
                  />
                </Field>
                <Field label="DÍAS A ADELANTAR">
                  <Input
                    type="number"
                    min={1}
                    max={consecWorker && esAdelanto(consecWorker) ? topeDe(consecWorker) : MAX_VAC_DAYS}
                    value={consec.days}
                    onChange={(e) => setConsec({ ...consec, days: Number(e.target.value) })}
                  />
                </Field>
              </div>

              {adelantoError ? (
                <Alert tone="error" title="No se puede adelantar">
                  {adelantoError}
                </Alert>
              ) : null}
            </div>
            <div className="flex justify-end gap-2 px-5 pb-5">
              <Button
                variant="outline"
                disabled={consecSaving}
                onClick={() => {
                  setAdelantoOpen(false);
                  setAdelantoError("");
                }}
              >
                Cancelar
              </Button>
              <Button disabled={consecSaving} onClick={() => void guardarAdelanto()}>
                {consecSaving && adelantoOpen ? "Guardando…" : "Guardar adelanto"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {modificarOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay)] p-4">
          <div className="w-full max-w-[520px] rounded-xl border border-border bg-card shadow-[0_8px_24px_#1E2C3A14]">
            <div className="space-y-1.5 px-5 pt-5">
              <h3 className="text-[15px] font-semibold">Modificar período</h3>
              <p className="text-[13px] text-muted-foreground">
                Solo tramos que aún no empiezan. Mismos días; el saldo no se descuenta otra vez.
              </p>
            </div>
            <div className="space-y-3 px-5 py-3">
              <p className="text-[13px] font-medium">
                {consecWorker ? consecWorker.nombre : "Selecciona a la persona arriba, en Planificación."}
              </p>
              {periodosLoading ? (
                <p className="text-[13px] text-muted-foreground">Cargando períodos…</p>
              ) : periodos.length === 0 ? (
                <p className="text-[13px] text-muted-foreground">Esta persona no tiene vacaciones programadas.</p>
              ) : (
                <div className="max-h-48 space-y-1 overflow-auto">
                  {periodos.map((p) => (
                    <button
                      key={p.inicio}
                      type="button"
                      disabled={!p.editable}
                      onClick={() => {
                        if (!p.editable) return;
                        setPeriodoSel(p.inicio);
                        setModStart(minProgramable);
                        setModificarError("");
                      }}
                      className={cn(
                        "flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-[13px]",
                        !p.editable
                          ? "cursor-not-allowed border-border/60 bg-muted/40 text-muted-foreground opacity-60"
                          : periodoSel === p.inicio
                            ? "border-primary bg-[var(--primary-soft)] text-primary"
                            : "border-border hover:bg-muted"
                      )}
                    >
                      <span>
                        {formatFechaIso(p.inicio)} – {formatFechaIso(p.fin)} · {p.dias} día{p.dias === 1 ? "" : "s"}
                      </span>
                      <span className="shrink-0 text-[11px]">{etiquetaEstado(p.estado)}</span>
                    </button>
                  ))}
                </div>
              )}
              <Field label="NUEVA FECHA INICIO">
                <Input
                  type="date"
                  min={minProgramable}
                  value={modStart || minProgramable}
                  onChange={(e) => {
                    const v = e.target.value;
                    setModStart(v && v < minProgramable ? minProgramable : v);
                  }}
                />
              </Field>
              {periodoSel && modStart ? (
                <p className="text-[12px] text-muted-foreground">
                  Nuevo tramo: {formatFechaIso(modStart)} –{" "}
                  {formatFechaIso(
                    addDaysIso(modStart, (periodos.find((p) => p.inicio === periodoSel)?.dias || 1) - 1)
                  )}
                </p>
              ) : null}
              {modificarError ? (
                <Alert tone="error" title="No se puede modificar">
                  {modificarError}
                </Alert>
              ) : null}
            </div>
            <div className="flex justify-end gap-2 px-5 pb-5">
              <Button
                variant="outline"
                disabled={consecSaving}
                onClick={() => {
                  setModificarOpen(false);
                  setModificarError("");
                }}
              >
                Cancelar
              </Button>
              <Button disabled={consecSaving} onClick={() => void guardarModificar()}>
                {consecSaving && modificarOpen ? "Guardando…" : "Guardar cambio"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {modal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay)] p-4">
          <div className="w-full max-w-[440px] rounded-xl border border-border bg-card shadow-[0_8px_24px_#1E2C3A14]">
            <div className="space-y-1.5 px-5 pt-5">
              <h3 className="flex items-center gap-2.5 text-[15px] font-semibold">
                <EmpAvatar nombre={modal.nombre} fotoUrl={modal.foto_url} className="h-8 w-8 text-[10px]" />
                <span className="min-w-0 truncate">
                  Semana {modal.week} · {modal.nombre}
                </span>
              </h3>
              <p className="text-[13px] text-muted-foreground">
                Elige el día de inicio ·{" "}
                <span className="font-semibold text-foreground">{modal.days}</span> día
                {modal.days === 1 ? "" : "s"} · saldo{" "}
                <span className="font-semibold text-foreground">{modal.disponibles}</span>/
                {modal.tope}
              </p>
            </div>
            <div className="space-y-3 px-5 py-3">
              <div>
                <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Día de inicio
                </p>
                {weekDaysLoading ? (
                  <p className="text-[13px] text-muted-foreground">Cargando días…</p>
                ) : weekDays.length === 0 ? (
                  <Field label="FECHA DE INICIO">
                    <Input
                      type="date"
                      min={minProgramable}
                      value={start}
                      onChange={(e) => {
                        const v = e.target.value;
                        setStart(v && v < minProgramable ? minProgramable : v);
                        setModalError("");
                      }}
                    />
                  </Field>
                ) : (
                  <div className="grid grid-cols-7 gap-1">
                    {weekDays.map((d) => {
                      const active = start === d.fecha;
                      const disabled = Boolean(d.past);
                      return (
                        <button
                          key={d.fecha}
                          type="button"
                          title={disabled ? undefined : d.fecha}
                          disabled={disabled}
                          onClick={() => {
                            if (disabled) return;
                            setStart(d.fecha);
                            setModalError("");
                          }}
                          className={cn(
                            "flex flex-col items-center rounded-lg border px-0.5 py-1.5 text-center transition-colors",
                            disabled
                              ? "cursor-not-allowed border-border/60 bg-muted/40 text-muted-foreground opacity-45"
                              : active
                                ? "border-primary bg-[var(--primary-soft)] text-primary"
                                : "border-border bg-background hover:bg-muted",
                            d.selected && !active && !disabled ? "ring-1 ring-success/40" : ""
                          )}
                        >
                          <span className="text-[9px] font-semibold text-muted-foreground">
                            {DAY_SHORT[d.weekday] || "?"}
                          </span>
                          <span className="font-data text-[12px] font-semibold leading-tight">
                            {formatDayLabel(d.fecha)}
                          </span>
                          {d.selected && !disabled ? (
                            <span className="mt-0.5 text-[8px] text-success">ya</span>
                          ) : (
                            <span className="mt-0.5 text-[8px] text-transparent">·</span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                )}
                {start ? (
                  <p className="mt-2 text-[12px] text-muted-foreground">
                    Inicio: <span className="font-data font-medium text-foreground">{formatDayLabel(start)}</span>
                  </p>
                ) : null}
              </div>
              {modalError ? (
                <Alert tone="error" title="No se pudo guardar">
                  {modalError}
                </Alert>
              ) : null}
            </div>
            <div className="flex justify-end gap-2 px-5 pb-5">
              <Button variant="outline" disabled={modalSaving} onClick={() => closeModal(true)}>
                Cancelar
              </Button>
              <Button
                disabled={modalSaving}
                onClick={async () => {
                  if (!start) {
                    setModalError("Elige un día de inicio.");
                    return;
                  }
                  if (weekDays.some((d) => d.fecha === start && d.past)) {
                    setModalError("Ese día no está disponible.");
                    return;
                  }
                  const w = plan.workers.find((x) => x.dni === modal.dni);
                  if (!w) {
                    setModalError("Esa persona ya no está en el filtro actual.");
                    return;
                  }
                  setModalSaving(true);
                  setModalError("");
                  const msg = await setWeek(w, modal.week, modal.days, start);
                  if (msg) {
                    setModalError(msg);
                    applyLocalWeeks(modal.dni, { [modal.week]: modal.prevDays });
                    setModalSaving(false);
                    return;
                  }
                  setModalSaving(false);
                  closeModal(false);
                }}
              >
                {modalSaving ? "Guardando…" : "Guardar"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

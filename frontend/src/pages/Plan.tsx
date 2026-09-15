import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, downloadFile, fetchFile, qs } from "../api";
import { addDaysIso, formatDayLabel, formatFechaIso, inclusiveDays, localTodayIso } from "../lib/dates";
import { SEM_COLORS, weekLocked } from "../lib/semaforo";
import {
  MAX_VAC_DAYS,
  diasDisponibles,
  esAdelanto,
  escenarioDe,
  etiquetaEstado,
  goceCompleto,
  msgSinSaldo,
  topeDe,
} from "../lib/vacaciones";
import { useApp } from "../state";
import { findAlert } from "../lib/alerts";
import { Alert, Button, cn, EmptyState, Field, Input, Kpi, PageHeader } from "../components/ui";
import { EmpAvatar } from "../components/EmpAvatar";
import { CalendarClock, CalendarDays, CalendarPlus, CalendarRange, Eye, FileDown, Users, UserCheck, UserX } from "lucide-react";
import { FlujoBadge, lockReasonFor, WorkerCard, WorkerRow } from "./plan/WorkerGrid";
import { JefeEquipo } from "./plan/JefeEquipo";
import type { CalendarioDoc, DocReady, DocumentoResp, Plan, VacPeriod, WeekDay, Worker } from "./plan/types";

const DAY_SHORT = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

function CamposFechas({
  start,
  end,
  min,
  max,
  onStart,
  onEnd,
}: {
  start: string;
  end: string;
  min: string;
  max?: string;
  onStart: (v: string) => void;
  onEnd: (v: string) => void;
}) {
  const startVal = start || min;
  return (
    <>
      <Field label="FECHA INICIO">
        <Input type="date" min={min} max={max} value={startVal} onChange={(e) => onStart(e.target.value)} />
      </Field>
      <Field label="FECHA FIN">
        <Input type="date" min={startVal} max={max} value={end} onChange={(e) => onEnd(e.target.value)} />
      </Field>
    </>
  );
}

function textoDiasCalculados(start: string, end: string, days: number) {
  if (!end) return "Elige la fecha de fin. Los días se cuentan solos (corridos, de inicio a fin).";
  if (days < 1) return "La fecha de fin no puede ser anterior al inicio.";
  return `${formatFechaIso(start)} → ${formatFechaIso(end)}: ${days} día${days === 1 ? "" : "s"} corrido${days === 1 ? "" : "s"}.`;
}

function ListaPeriodos({ periodos }: { periodos: VacPeriod[] }) {
  if (!periodos.length) return null;
  return (
    <div className="space-y-1.5">
      {periodos.map((p, i) => (
        <div
          key={p.inicio}
          className="flex items-center justify-between gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-[13px]"
        >
          <span>
            <span className="font-semibold text-muted-foreground">Período {i + 1} · </span>
            {formatFechaIso(p.inicio)} – {formatFechaIso(p.fin)}
          </span>
          <span className="shrink-0 tabular-nums font-medium">
            {p.dias} día{p.dias === 1 ? "" : "s"}
          </span>
        </div>
      ))}
    </div>
  );
}

function scope(filters: ReturnType<typeof useApp>["filters"]) {
  return {
    year: filters.year,
    empresa: filters.empresas.includes("TODAS") ? undefined : filters.empresas,
    gerencia: filters.gerencias.includes("TODAS") ? undefined : filters.gerencias,
    area: filters.areas.includes("TODAS") ? undefined : filters.areas,
  };
}

function densifyWeeks(raw: number[] | Record<string, number> | undefined, total = 53): number[] {
  const out = Array.from({ length: total }, () => 0);
  if (Array.isArray(raw)) {
    const n = Math.min(raw.length, total);
    for (let i = 0; i < n; i++) out[i] = Number(raw[i]) || 0;
    return out;
  }
  if (raw) {
    for (const [k, v] of Object.entries(raw)) {
      const week = Number(k);
      if (week >= 1 && week <= total) out[week - 1] = Number(v) || 0;
    }
  }
  return out;
}

function esAptoPlan(w: Worker) {
  return w.apto !== false && !esAdelanto(w);
}

/** Primer día programable para el usuario (jefatura: la semana cierra el viernes anterior). */
function primerDia(plan: Pick<Plan, "primer_inicio" | "today"> | null) {
  return plan?.primer_inicio || plan?.today || localTodayIso();
}

function kpisFrom(workers: Worker[]) {
  let trabajadores = 0;
  let programados = 0;
  let pendientes = 0;
  let dias = 0;
  for (const w of workers) {
    if (!esAptoPlan(w)) continue;
    trabajadores += 1;
    if (w.total_dias > 0) programados += 1;
    else pendientes += 1;
    dias += w.total_dias;
  }
  return { trabajadores, programados, pendientes, dias };
}

function patchWorkerWeeks(workers: Worker[], dni: string, updates: Record<number, number>) {
  return workers.map((w) => {
    if (w.dni !== dni) return w;
    const weeks = w.weeks.map((v, i) => (i + 1 in updates ? updates[i + 1] : v));
    return { ...w, weeks, total_dias: weeks.reduce((a, b) => a + b, 0) };
  });
}

function weeksFromApi(res: { weeks?: Record<string, number> }, fallbackWeek: number, fallbackDays: number) {
  if (!res.weeks) return { [fallbackWeek]: fallbackDays } as Record<number, number>;
  return Object.fromEntries(Object.entries(res.weeks).map(([k, v]) => [Number(k), v]));
}


export function PlanPage() {
  const { filters, user, alerts } = useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const alertaTipo = searchParams.get("alerta");
  const alertaMes = searchParams.get("mes");
  const alertaDni = searchParams.get("dni");
  const alertaActiva = findAlert(alerts, alertaTipo, alertaMes);
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
  const [consec, setConsec] = useState({ dni: "", start: "", end: "" });
  const [consecSaving, setConsecSaving] = useState(false);
  const [consecQ, setConsecQ] = useState("");
  const [consecOpen, setConsecOpen] = useState(false);
  const deferredConsecQ = useDeferredValue(consecQ);
  const consecBoxRef = useRef<HTMLDivElement>(null);
  const adelantoBoxRef = useRef<HTMLDivElement>(null);
  const programFormRef = useRef<HTMLDivElement>(null);
  const [adelantoOpen, setAdelantoOpen] = useState(false);
  const [adelantoError, setAdelantoError] = useState("");
  const [modificarOpen, setModificarOpen] = useState(false);
  const [modificarError, setModificarError] = useState("");
  const [periodos, setPeriodos] = useState<VacPeriod[]>([]);
  const [periodosLoading, setPeriodosLoading] = useState(false);
  const [savingCell, setSavingCell] = useState<{ dni: string; week: number } | null>(null);
  const savingCellRef = useRef<{ dni: string; week: number } | null>(null);
  savingCellRef.current = savingCell;
  const [periodosTick, setPeriodosTick] = useState(0);
  const [periodoSel, setPeriodoSel] = useState("");
  const [modStart, setModStart] = useState("");
  const [loadError, setLoadError] = useState("");
  const [docReady, setDocReady] = useState<DocReady | null>(null);
  const [docFalta, setDocFalta] = useState("");
  const [calendario, setCalendario] = useState<CalendarioDoc[]>([]);
  const [recepcionando, setRecepcionando] = useState(false);
  const [docBusy, setDocBusy] = useState(false);
  const [docError, setDocError] = useState("");
  const [docPreviewUrl, setDocPreviewUrl] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [jefeFormOpen, setJefeFormOpen] = useState(false);

  const params = useMemo(() => scope(filters), [filters]);

  const load = useCallback(async () => {
    const data = await api<Plan>(`/api/plan${qs(params)}`);
    const total = data.total_semanas || 53;
    setPlan({
      ...data,
      workers: data.workers.map((w) => ({
        ...w,
        weeks: densifyWeeks(w.weeks as number[] | Record<string, number>, total),
      })),
    });
    setLoadError("");
    const first = data.workers.find(esAptoPlan) || data.workers[0];
    const minDay = primerDia(data);
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

  useEffect(() => {
    return () => {
      if (docPreviewUrl) URL.revokeObjectURL(docPreviewUrl);
    };
  }, [docPreviewUrl]);

  const lockedWeeks = useMemo(() => {
    if (!plan) return [];
    return Array.from({ length: plan.total_semanas }, (_, i) =>
      weekLocked(plan.year, i + 1, plan.current_year, plan.current_week, plan.primer_inicio)
    );
  }, [plan?.year, plan?.current_year, plan?.current_week, plan?.total_semanas, plan?.primer_inicio]);

  const aplicarDocumento = useCallback(
    (res: DocumentoResp, dni: string) => {
      setDocError("");
      setDocReady(res.documento ? { ...res.documento, dni, year: params.year } : null);
      setDocFalta(res.documento ? "" : res.documento_falta || "");
      setCalendario(res.documento ? res.calendario_documentos || [] : []);
    },
    [params.year]
  );

  const weekWindow = useMemo(() => {
    if (!plan) return [];
    const start = Math.max(1, (plan.current_week || 1) - 1);
    const end = Math.min(plan.total_semanas, start + 5);
    return Array.from({ length: end - start + 1 }, (_, i) => start + i);
  }, [plan?.current_week, plan?.total_semanas]);

  const gridWorkers = useMemo(
    () => (plan?.workers || []).filter(esAptoPlan),
    [plan?.workers]
  );
  const ocultosSinAnio = (plan?.workers || []).filter((w) => !esAptoPlan(w)).length;

  const searchIndex = useMemo(
    () =>
      gridWorkers.map((w) => ({
        w,
        hay: `${w.nombre} ${w.dni} ${w.area} ${w.jefatura || ""} ${w.tipo_personal} ${w.division} ${w.gerencia}`.toLowerCase(),
      })),
    [gridWorkers]
  );

  const alertaDnis = useMemo(() => {
    if (!alertaTipo) return null;
    if (alertaDni) return new Set([alertaDni]);
    if (!alertaActiva) return null;
    return new Set(alertaActiva.personas.map((p) => p.dni));
  }, [alertaTipo, alertaDni, alertaActiva]);

  const visible = useMemo(() => {
    const base = alertaDnis ? gridWorkers.filter((w) => alertaDnis.has(w.dni)) : gridWorkers;
    const terms = deferredQ.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return base;
    const hay = new Set(base.map((w) => w.dni));
    return searchIndex.filter((row) => hay.has(row.w.dni) && terms.every((t) => row.hay.includes(t))).map((row) => row.w);
  }, [deferredQ, gridWorkers, searchIndex, alertaDnis]);

  const consecMatches = useMemo(() => {
    const workers = (plan?.workers || []).filter((w) => user?.is_admin || esAptoPlan(w));
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
  }, [deferredConsecQ, plan?.workers, user?.is_admin]);

  const consecWorker = useMemo(
    () => plan?.workers.find((w) => w.dni === consec.dni) || null,
    [plan?.workers, consec.dni]
  );

  function pickConsec(w: Worker) {
    setConsec((c) => ({ ...c, dni: w.dni }));
    setConsecQ(`${w.nombre} · ${w.dni}`);
    setConsecOpen(false);
    setPeriodoSel("");
    if (user?.is_jefe && !user?.is_admin) {
      setJefeFormOpen(true);
      return;
    }
    window.requestAnimationFrame(() => {
      programFormRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  useEffect(() => {
    if (!alertaDni || !plan) return;
    const w = plan.workers.find((x) => x.dni === alertaDni);
    if (w && consec.dni !== w.dni) pickConsec(w);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alertaDni, plan, consec.dni]);

  function patchFechas(partial: { start?: string; end?: string }) {
    const minDay = primerDia(plan);
    setConsec((c) => {
      let start = partial.start !== undefined ? partial.start : c.start;
      let end = partial.end !== undefined ? partial.end : c.end;
      if (start && start < minDay) start = minDay;
      if (end && start && end < start) end = start;
      return { ...c, start, end };
    });
  }

  useEffect(() => {
    if (!consec.dni) {
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
  }, [consec.dni, params.year, periodosTick]);

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
      if (weekLocked(plan?.year ?? params.year, week, plan?.current_year ?? 0, plan?.current_week ?? 0, plan?.primer_inicio)) {
        const msg = `La semana ${week} ya está cerrada. Puedes programar desde el ${formatFechaIso(primerDia(plan))}.`;
        setError(msg);
        return msg;
      }
      if (days > 0 && !startDate) {
        const msg = "Indica desde qué fecha empiezan las vacaciones.";
        setError(msg);
        return msg;
      }
      setSavingCell({ dni: w.dni, week });
      try {
        const res = await api<DocumentoResp & {
          weeks?: Record<string, number>;
          fin?: string;
          fechas?: string[];
        }>("/api/plan/week", {
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
        setPeriodosTick((n) => n + 1);
        const spill = Object.keys(updates).filter((k) => Number(k) !== week);
        aplicarDocumento(days > 0 ? res : {}, w.dni);
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
      } finally {
        setSavingCell(null);
      }
    },
    [applyLocalWeeks, aplicarDocumento, params, plan?.year, plan?.current_year, plan?.current_week, plan?.primer_inicio, plan?.today]
  );

  const onDays = useCallback(
    (w: Worker, week: number, days: number) => {
      if (savingCellRef.current) return;
      if (esAdelanto(w) || w.can_edit === false) {
        setOk("");
        setError(lockReasonFor(w) || `${w.nombre} aún no cumple el año de servicio. Solo se programan trabajadores aptos.`);
        return;
      }
      if (Number.isNaN(days) || days < 0 || days > MAX_VAC_DAYS) {
        setError(`Indica entre 0 y ${MAX_VAC_DAYS} días.`);
        return;
      }
      const prevDays = w.weeks[week - 1] || 0;
      if (days === prevDays) return;
      if (days === 0) {
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
    if (!consec.end) {
      setError("Indica hasta qué día terminan las vacaciones. Los días se calculan solos.");
      return;
    }
    const worker = plan?.workers.find((w) => w.dni === consec.dni);
    if (!worker) {
      setError("Esa persona ya no está en el filtro actual.");
      return;
    }
    if (esAdelanto(worker) || worker.can_edit === false) {
      setError(lockReasonFor(worker) || `${worker.nombre} aún no cumple el año de servicio. Solo se programan trabajadores aptos.`);
      return;
    }
    const days = inclusiveDays(consec.start, consec.end);
    if (days < 1) {
      setError("La fecha de fin no puede ser anterior al inicio.");
      return;
    }
    if (days > MAX_VAC_DAYS) {
      setError(`Ese rango son ${days} días. El máximo es ${MAX_VAC_DAYS}.`);
      return;
    }
    if (days > diasDisponibles(worker.total_dias, MAX_VAC_DAYS)) {
      setError(msgSinSaldo(worker.nombre, days, worker.total_dias, MAX_VAC_DAYS, false));
      return;
    }
    const startDt = new Date(`${consec.start}T00:00:00`);
    if (Number.isNaN(startDt.getTime())) {
      setError("La fecha de inicio no es válida.");
      return;
    }
    const todayIso = primerDia(plan);
    if (consec.start < todayIso) {
      setError(
        plan?.primer_inicio && plan.primer_inicio !== plan.today
          ? `Esa semana ya cerró: se puede programar desde el ${formatFechaIso(todayIso)} (la semana cierra el viernes anterior).`
          : `No se puede programar desde una fecha anterior a hoy (${formatFechaIso(todayIso)}).`
      );
      return;
    }
    if (worker.fecha_vencimiento && consec.end > worker.fecha_vencimiento) {
      setError(
        `${worker.nombre}: el récord se goza como máximo hasta el ${formatFechaIso(worker.fecha_vencimiento)}. No se puede programar hasta el ${formatFechaIso(consec.end)}.`
      );
      return;
    }
    setConsecSaving(true);
    try {
      const res = await api<DocumentoResp & { fechas?: string[]; fin?: string }>(
        "/api/plan/consecutive",
        {
          method: "POST",
          body: JSON.stringify({
            ...params,
            dni: consec.dni,
            start_date: consec.start,
            days,
          }),
        }
      );
      await load();
      setPeriodosTick((n) => n + 1);
      const fin = res.fin || (res.fechas && res.fechas[res.fechas.length - 1]) || consec.end || "";
      aplicarDocumento(res, consec.dni);
      setOk(
        fin
          ? `Listo: se programaron ${days} día(s) del ${formatFechaIso(consec.start)} al ${formatFechaIso(fin)}.`
          : `Listo: se programaron ${days} día(s) desde el ${consec.start}.`
      );
      const tope = topeDe(worker);
      const quedan = diasDisponibles(worker.total_dias + days, tope);
      const next = fin ? addDaysIso(fin, 1) : "";
      setConsec((c) => ({
        ...c,
        start: next && next >= todayIso ? next : todayIso,
        end: "",
      }));
      if (user?.is_jefe && !user?.is_admin) {
        setJefeFormOpen(true);
      }
      if (quedan <= 0) {
        setOk(
          fin
            ? `Listo: goce completo (${tope} días). Último período del ${formatFechaIso(consec.start)} al ${formatFechaIso(fin)}.`
            : `Listo: goce completo (${tope} días).`
        );
      }
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
    if (!consec.end) {
      setAdelantoError("Indica hasta qué día terminan. Los días se calculan solos.");
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
    const days = inclusiveDays(consec.start, consec.end);
    if (days < 1) {
      setAdelantoError("La fecha de fin no puede ser anterior al inicio.");
      return;
    }
    if (days > tope) {
      setAdelantoError(`Ese rango son ${days} días. El acumulado de adelanto es ${tope}.`);
      return;
    }
    if (days > diasDisponibles(worker.total_dias, tope)) {
      setAdelantoError(msgSinSaldo(worker.nombre, days, worker.total_dias, tope, true));
      return;
    }
    const todayIso = primerDia(plan);
    if (consec.start < todayIso) {
      setAdelantoError(`No se puede programar antes del ${formatFechaIso(todayIso)}.`);
      return;
    }
    if (worker.fecha_vencimiento && consec.end > worker.fecha_vencimiento) {
      setAdelantoError(
        `${worker.nombre}: el récord se goza como máximo hasta el ${formatFechaIso(worker.fecha_vencimiento)}. No se puede programar hasta el ${formatFechaIso(consec.end)}.`
      );
      return;
    }
    setConsecSaving(true);
    try {
      const res = await api<DocumentoResp & { fin?: string; fechas?: string[] }>(
        "/api/plan/consecutive",
        {
          method: "POST",
          body: JSON.stringify({
            ...params,
            dni: consec.dni,
            start_date: consec.start,
            days,
          }),
        }
      );
      await load();
      setPeriodosTick((n) => n + 1);
      setAdelantoOpen(false);
      const fin = res.fin || (res.fechas && res.fechas[res.fechas.length - 1]) || consec.end || "";
      aplicarDocumento(res, consec.dni);
      setOk(
        `Listo: se adelantaron ${days} día(s) para ${worker.nombre} del ${formatFechaIso(consec.start)} al ${formatFechaIso(fin || consec.end)} (tope acumulado ${tope}).`
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
    const worker = plan?.workers.find((w) => w.dni === consec.dni);
    if (!worker) {
      setModificarError("Esa persona ya no está en el filtro actual.");
      return;
    }
    if (worker.can_edit === false) {
      setModificarError(lockReasonFor(worker) || "Este plan ya no se puede editar.");
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
    const todayIso = primerDia(plan);
    if (modStart < todayIso) {
      setModificarError(`La nueva fecha no puede ser anterior al ${formatFechaIso(todayIso)}.`);
      return;
    }
    const nuevoFin = addDaysIso(modStart, periodo.dias - 1);
    if (worker.fecha_vencimiento && nuevoFin > worker.fecha_vencimiento) {
      setModificarError(
        `${worker.nombre}: el récord se goza como máximo hasta el ${formatFechaIso(worker.fecha_vencimiento)}. Ese período llegaría al ${formatFechaIso(nuevoFin)}.`
      );
      return;
    }
    setConsecSaving(true);
    try {
      const res = await api<DocumentoResp & { fin?: string }>("/api/plan/period-move", {
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
      setPeriodosTick((n) => n + 1);
      setModificarOpen(false);
      aplicarDocumento(res, consec.dni);
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

  async function enviarAlGerente() {
    setError("");
    setOk("");
    const falta = gridWorkers.filter((w) => !goceCompleto(w.total_dias, topeDe(w)));
    if (falta.length) {
      setError(
        `No puedes enviar al gerente: ${falta.length} persona${falta.length === 1 ? "" : "s"} no tiene${falta.length === 1 ? "" : "n"} el goce completo. Programa todos los días del derecho (puedes hacerlo en varios períodos) y luego envía.`
      );
      return;
    }
    setEnviando(true);
    try {
      const res = await api<{ enviados: number; rechazados: number; errors: string[] }>(
        `/api/flujo/enviar-aptos${qs(params)}`,
        { method: "POST" }
      );
      await load();
      const extra = res.errors?.length ? ` ${res.errors.slice(0, 3).join(" ")}` : "";
      setOk(
        res.enviados
          ? `Se enviaron ${res.enviados} plan(es) al gerente.${res.rechazados ? ` ${res.rechazados} no se pudieron enviar.` : ""}${extra}`
          : `No se envió nadie.${extra}`
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo enviar el plan.");
    } finally {
      setEnviando(false);
    }
  }

  async function recepcionarDirecto() {
    if (!docReady) return;
    setRecepcionando(true);
    setDocError("");
    try {
      const res = await api<{ recepcionados: number; errors: string[] }>("/api/flujo/recepcionar-directo", {
        method: "POST",
        body: JSON.stringify({ year: docReady.year, dnis: [docReady.dni] }),
      });
      if (!res.recepcionados) {
        setDocError(res.errors?.join(" ") || "No se pudo recepcionar el plan.");
        return;
      }
      await load();
      setOk("Plan recepcionado. Sus documentos ya están en Documentos: ahí se emite cada uno en su momento.");
      setDocReady(null);
      setCalendario([]);
    } catch (e) {
      setDocError(e instanceof Error ? e.message : "No se pudo recepcionar el plan.");
    } finally {
      setRecepcionando(false);
    }
  }

  function documentoRequest(doc: DocReady): RequestInit {
    return {
      method: "POST",
      body: JSON.stringify({ year: doc.year, dni: doc.dni, key: doc.key, formato: "pdf" }),
    };
  }

  async function descargarDocumento() {
    if (!docReady) return;
    setDocBusy(true);
    setDocError("");
    try {
      await downloadFile("/api/plan/documento", documentoRequest(docReady), "vacaciones.pdf");
    } catch (e) {
      setDocError(e instanceof Error ? e.message : "No se pudo descargar el PDF.");
    } finally {
      setDocBusy(false);
    }
  }

  async function verDocumento() {
    if (!docReady) return;
    setDocBusy(true);
    setDocError("");
    try {
      const { blob } = await fetchFile("/api/plan/documento", documentoRequest(docReady), "vacaciones.pdf");
      setDocPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return URL.createObjectURL(blob);
      });
    } catch (e) {
      setDocError(e instanceof Error ? e.message : "No se pudo abrir la vista previa.");
    } finally {
      setDocBusy(false);
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

  const isAdmin = Boolean(user?.is_admin);
  const docWorker = docReady ? plan.workers.find((w) => w.dni === docReady.dni) : undefined;
  // Recepción directa: plan completo en borrador/observado (el backend vuelve a validar 30 días y Art. 8).
  const recepcionable = Boolean(
    docWorker &&
      !esAdelanto(docWorker) &&
      goceCompleto(docWorker.total_dias, topeDe(docWorker)) &&
      ["BORRADOR", "OBSERVADO", "", undefined].includes(docWorker.flujo_estado)
  );
  const isJefe = Boolean(user?.is_jefe);
  const isGerente = Boolean(user?.is_gerente) && !isAdmin && !isJefe;
  const minProgramable = primerDia(plan);
  const maxGoce = consecWorker?.fecha_vencimiento || undefined;
  const startIso = consec.start || minProgramable;
  const consecDays = inclusiveDays(startIso, consec.end);
  const workerReady = Boolean(consecWorker);
  const workerEsAdelanto = esAdelanto(consecWorker);
  const saldoRestante = consecWorker
    ? diasDisponibles(consecWorker.total_dias, topeDe(consecWorker))
    : 0;
  const workerCanEdit = !isGerente && consecWorker?.can_edit !== false;
  const rangoOk = consecDays >= 1 && Boolean(consec.end);
  const canProgramar =
    workerReady &&
    !workerEsAdelanto &&
    saldoRestante > 0 &&
    workerCanEdit &&
    rangoOk &&
    consecDays <= saldoRestante;
  const canOpenAdelanto = isAdmin && workerReady && workerEsAdelanto && saldoRestante > 0;
  const canAdelanto = canOpenAdelanto && rangoOk && consecDays <= saldoRestante;
  const canModificar = workerReady && workerCanEdit && !periodosLoading && periodos.some((p) => p.editable);
  const topeWorker = topeDe(consecWorker);
  const escenario = escenarioDe(workerEsAdelanto, periodos.map((p) => p.dias), topeWorker);
  const pctGoce = topeWorker ? Math.min(100, Math.round((100 * (consecWorker?.total_dias || 0)) / topeWorker)) : 0;
  const programarTitle = isGerente
    ? "El gerente no programa: valida o observa en la bandeja."
    : !workerReady
    ? "Selecciona a la persona."
    : !workerCanEdit
      ? lockReasonFor(consecWorker!)
    : workerEsAdelanto
      ? "Aún no cumple el año. Usa Adelanto vacacional."
      : saldoRestante <= 0
        ? "Ya tiene todos los días programados."
        : !consec.end
          ? "Elige la fecha de fin; los días se calculan solos. Puedes hacerlo en varios períodos."
          : consecDays > saldoRestante
            ? `Ese rango son ${consecDays} días y solo quedan ${saldoRestante}.`
            : undefined;
  const adelantoTitle = !workerReady
    ? "Selecciona a la persona."
    : !workerEsAdelanto
      ? "Ya cumplió el año; debe gozar sus vacaciones con Programar."
      : saldoRestante <= 0
        ? "Ya usó el acumulado de adelanto."
        : undefined;
  const modificarTitle = !workerReady
    ? "Selecciona a la persona."
    : periodosLoading
      ? "Cargando períodos…"
      : !canModificar
        ? "No tiene un período futuro para mover."
        : undefined;

  const personaAlerta =
    alertaDni && alertaActiva ? alertaActiva.personas.find((p) => p.dni === alertaDni) || null : null;
  const kpisVista = alertaTipo ? kpisFrom(visible) : { ...plan.kpis, trabajadores: gridWorkers.length };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Planificación"
        help={
          isGerente
            ? "El gerente no programa días: revisa la bandeja para validar u observar lo que envió el jefe."
            : isJefe
              ? `Programa los 30 días de cada persona y envía el plan al gerente. Cada semana se programa o cambia hasta el viernes anterior: hoy puedes desde el ${formatFechaIso(minProgramable)}.`
              : `Estás en la semana ${plan.current_week}. Como Personas y Cultura puedes programar desde hoy y mover tramos de semanas ya cerradas (casos extraordinarios).`
        }
      />

      {alertaTipo ? (
        <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)] sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="text-[15px] font-semibold">{alertaActiva?.titulo || "Filtro de alerta"}</p>
            <p className="mt-1 text-[13px] text-muted-foreground">
              {personaAlerta
                ? `${personaAlerta.nombre} (${personaAlerta.area || "sin área"}): ${personaAlerta.estado_plan}.`
                : alertaActiva?.descripcion || "Mostrando las personas de esta alerta."}
            </p>
            {alertaActiva?.responsable ? (
              <p className="mt-1 text-[12px] text-muted-foreground">Quién actúa: {alertaActiva.responsable}</p>
            ) : null}
          </div>
          <Button
            variant="outline"
            className="shrink-0"
            onClick={() => setSearchParams({}, { replace: true })}
          >
            Quitar filtro
          </Button>
        </div>
      ) : null}

      {error ? (
        <Alert tone="error" title="No se puede programar">
          {error}
        </Alert>
      ) : null}
      {ok ? (
        <Alert tone="success" title="Guardado">
          <p>{ok}</p>
          {isAdmin && docFalta ? <p className="mt-2 text-[12px] text-warning">{docFalta}</p> : null}
          {isAdmin && docReady ? (
            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                variant="outline"
                className="h-9 bg-card"
                disabled={docBusy}
                onClick={() => void verDocumento()}
              >
                <Eye size={16} strokeWidth={1.75} />
                {docBusy ? "Preparando…" : "Ver PDF"}
              </Button>
              <Button
                variant="outline"
                className="h-9 bg-card"
                disabled={docBusy}
                onClick={() => void descargarDocumento()}
              >
                <FileDown size={16} strokeWidth={1.75} />
                {docBusy ? "Preparando PDF…" : `Descargar ${docReady.titulo}`}
              </Button>
              <p className="mt-1.5 w-full text-[11px] text-muted-foreground">
                Vista previa del documento que toca ahora. La emisión oficial se hace en Documentos, una vez
                recepcionado el plan.
              </p>
            </div>
          ) : null}
          {isAdmin && docReady && calendario.length ? (
            <div className="mt-3 rounded-lg border border-border bg-card px-3 py-2.5">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Documentos de este plan, por partes
              </p>
              <ol className="mt-1.5 space-y-1 text-[12px] text-foreground">
                {calendario.map((d, i) => (
                  <li key={`${d.tipo}-${d.tramo?.inicio || i}`} className="flex flex-wrap justify-between gap-x-3">
                    <span>
                      {i + 1}. {d.titulo}
                      {d.tramo
                        ? d.tipo === "memorando"
                          ? ` · ${formatFechaIso(d.tramo.inicio)}–${formatFechaIso(d.tramo.fin)} (${d.tramo.dias} días)`
                          : ` + memorando ${formatFechaIso(d.tramo.inicio)}–${formatFechaIso(d.tramo.fin)} (${d.tramo.dias} días)`
                        : ""}
                    </span>
                    <span className="text-muted-foreground">
                      {d.estado === "por_emitir"
                        ? "Ahora"
                        : `Desde el ${formatFechaIso(d.emitir_desde)}`}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
          {isAdmin && docReady && recepcionable ? (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button className="h-9" disabled={recepcionando} onClick={() => void recepcionarDirecto()}>
                {recepcionando ? "Recepcionando…" : "Recepcionar y pasar a Documentos"}
              </Button>
              <span className="text-[11px] text-muted-foreground">
                Plan completo programado por Personas y Cultura: queda recepcionado sin pasar por jefe ni gerente.
              </span>
            </div>
          ) : null}
          {docError ? <p className="mt-2 text-[12px] text-error">{docError}</p> : null}
        </Alert>
      ) : null}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
        <Kpi label="Trabajadores" value={kpisVista.trabajadores} hint={alertaTipo ? "En esta alerta" : "Aptos para vacaciones"} icon={<Users size={18} strokeWidth={1.75} />} />
        <Kpi label="Programados" value={kpisVista.programados} hint="Con al menos un día programado" icon={<UserCheck size={18} strokeWidth={1.75} />} />
        <Kpi label="Sin programación" value={kpisVista.pendientes} hint={`Aptos aún sin días en ${plan.year}`} icon={<UserX size={18} strokeWidth={1.75} />} />
        <Kpi label="Días programados" value={kpisVista.dias} hint="Suma de aptos" icon={<CalendarDays size={18} strokeWidth={1.75} />} />
      </div>

      {isJefe ? (
        <JefeEquipo
          workers={gridWorkers}
          selectedDni={consec.dni}
          enviando={enviando}
          onPick={pickConsec}
          onEnviar={() => void enviarAlGerente()}
        />
      ) : null}

      {isJefe || isGerente ? null : (
      <div
        ref={programFormRef}
        className="grid grid-cols-1 items-end gap-3 rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)] sm:grid-cols-2 md:grid-cols-[2fr_1fr_1fr]"
      >
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
                      <span className="flex shrink-0 items-center gap-2">
                        {esAdelanto(w) || w.apto === false ? (
                          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                            No cumple el año
                          </span>
                        ) : (
                          <FlujoBadge w={w} rol={isAdmin ? "ADMIN" : isGerente ? "GERENTE" : "JEFE"} />
                        )}
                        <span className="font-data text-[11px] text-muted-foreground">{w.dni}</span>
                      </span>
                    </button>
                  ))
                )}
              </div>
            ) : null}
          </div>
        </Field>
        <CamposFechas
          start={consec.start}
          end={consec.end}
          min={minProgramable}
          max={maxGoce}
          onStart={(v) => patchFechas({ start: v })}
          onEnd={(v) => patchFechas({ end: v })}
        />
        <div className="flex flex-col gap-2 sm:col-span-2 sm:flex-row md:col-span-3">
          <span title={programarTitle} className="w-full md:w-auto">
            <Button
              onClick={programarConsec}
              disabled={consecSaving || !canProgramar}
              className="w-full md:w-auto"
            >
              <CalendarPlus size={16} strokeWidth={1.75} />
              {consecSaving && !adelantoOpen && !modificarOpen ? "Guardando…" : "Programar vacaciones"}
            </Button>
          </span>
          <span title={adelantoTitle} className="w-full md:w-auto">
            <Button
              variant="outline"
              disabled={consecSaving || !canOpenAdelanto}
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
          </span>
          <span title={modificarTitle} className="w-full md:w-auto">
            <Button
              variant="outline"
              disabled={consecSaving || !canModificar}
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
          </span>
        </div>
        {consec.end ? (
          <p
            className={`text-[12px] sm:col-span-2 md:col-span-3 ${
              workerReady && consecDays > saldoRestante ? "text-warning" : "text-muted-foreground"
            }`}
          >
            {textoDiasCalculados(startIso, consec.end, consecDays)}
            {workerReady && saldoRestante > consecDays && consecDays > 0
              ? ` Quedan ${saldoRestante - consecDays} día(s).`
              : ""}
          </p>
        ) : null}
        <p className="text-[11px] text-muted-foreground sm:col-span-2 md:col-span-3">
          {workerReady
            ? workerEsAdelanto
              ? `Aún no cumple el año: solo Adelanto (acumulado ${topeDe(consecWorker)} día(s), quedan ${saldoRestante}).`
              : workerCanEdit
                ? `Ya cumplió el año: programa o modifica el goce. Quedan ${saldoRestante} día(s). En la grilla, Enter o clic fuera guarda.`
                : lockReasonFor(consecWorker!)
            : "Selecciona a la persona para habilitar Programar, Adelanto o Modificar período."}
        </p>
      </div>
      )}

      {isJefe ? (
        <p className="text-[13px] font-semibold">Detalle por semanas</p>
      ) : null}
      <div className="flex w-full max-w-xl flex-wrap items-center gap-2">
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
            {visible.length} de {gridWorkers.length}
          </span>
        ) : null}
        {ocultosSinAnio > 0 ? (
          <span className="text-[11px] text-muted-foreground">
            {ocultosSinAnio} persona{ocultosSinAnio === 1 ? "" : "s"} aún no cumplen el año: no aparecen en la tabla.
          </span>
        ) : null}
      </div>

      {plan.workers.length === 0 ? (
        <EmptyState
          title="No hay trabajadores"
          body="Cambia el año, la empresa, la división o el área."
        />
      ) : gridWorkers.length === 0 ? (
        <EmptyState
          title="No hay aptos para vacaciones"
          body="Nadie de este filtro cumple el año de servicio. No se listan en planificación."
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
              <WorkerCard
                key={w.dni}
                w={w}
                weekWindow={weekWindow}
                lockedWeeks={lockedWeeks}
                onDays={onDays}
                gridLocked={w.can_edit === false || isGerente}
                lockReason={lockReasonFor(w)}
                savingWeek={savingCell?.dni === w.dni ? savingCell.week : null}
              />
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
                  <WorkerRow
                    key={w.dni}
                    w={w}
                    lockedWeeks={lockedWeeks}
                    onDays={onDays}
                    gridLocked={w.can_edit === false || isGerente}
                    lockReason={lockReasonFor(w)}
                    savingWeek={savingCell?.dni === w.dni ? savingCell.week : null}
                  />
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

      {jefeFormOpen && consecWorker ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay)] p-4">
          <div className="flex max-h-[90vh] w-full max-w-[520px] flex-col overflow-hidden rounded-xl border border-border bg-card shadow-[0_8px_24px_#1E2C3A14]">
            <div className="flex items-start gap-3 px-5 pt-5">
              <EmpAvatar nombre={consecWorker.nombre} fotoUrl={consecWorker.foto_url} className="h-10 w-10 text-[11px]" />
              <div className="min-w-0 flex-1">
                <h3 className="truncate text-[15px] font-semibold">{consecWorker.nombre}</h3>
                <p className="text-[12px] text-muted-foreground">
                  {consecWorker.dni} · {consecWorker.total_dias} de {topeWorker} días
                  {consecWorker.fecha_vencimiento
                    ? ` · gozar hasta ${formatFechaIso(consecWorker.fecha_vencimiento)}`
                    : ""}
                </p>
                {consecWorker.record_vacacional ? (
                  <p className="text-[11px] text-muted-foreground">Récord {consecWorker.record_vacacional}</p>
                ) : null}
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div className="h-full rounded-full bg-primary" style={{ width: `${pctGoce}%` }} />
                </div>
              </div>
            </div>
            <div className="min-h-0 flex-1 space-y-4 overflow-auto px-5 py-4">
              <div className="rounded-lg border border-border bg-muted/40 px-3 py-2.5">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {escenario.n ? `Escenario ${escenario.n}` : "Escenario"}
                </p>
                <p className="mt-0.5 text-[13px] font-semibold">{escenario.titulo}</p>
                <p className="mt-0.5 text-[12px] leading-snug text-muted-foreground">{escenario.detalle}</p>
              </div>
              {periodos.length ? (
                <div>
                  <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Períodos guardados</p>
                  <ListaPeriodos periodos={periodos} />
                </div>
              ) : null}
              {saldoRestante > 0 ? (
                <div className="rounded-xl border border-border p-3">
                  <p className="text-[13px] font-semibold">Período {periodos.length + 1}</p>
                  <p className="mt-0.5 text-[12px] text-muted-foreground">
                    Quedan {saldoRestante} día{saldoRestante === 1 ? "" : "s"}.{" "}
                    {periodos.length === 0 && !workerEsAdelanto
                      ? "El primer período debe tener al menos 7 días (o 15 / 30 corridos). Al guardar se abre el siguiente."
                      : "Este período no tiene que ser todo: al guardar se abre el siguiente."}
                  </p>
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <CamposFechas
                      start={consec.start}
                      end={consec.end}
                      min={minProgramable}
                      max={maxGoce}
                      onStart={(v) => patchFechas({ start: v })}
                      onEnd={(v) => patchFechas({ end: v })}
                    />
                  </div>
                  <p className="mt-2 text-[12px] text-muted-foreground">
                    {textoDiasCalculados(startIso, consec.end, consecDays)}
                    {saldoRestante > consecDays && consecDays > 0
                      ? ` Después quedarán ${saldoRestante - consecDays}.`
                      : ""}
                  </p>
                </div>
              ) : (
                <Alert tone="success" title="Goce completo">
                  Ya tiene los {topeWorker} días. Escenario: {escenario.titulo}. Ya puedes enviar al gerente.
                </Alert>
              )}
              {error ? (
                <Alert tone="error" title="No se puede programar">
                  {error}
                </Alert>
              ) : null}
            </div>
            <div className="flex flex-col gap-2 border-t border-border px-5 py-4 sm:flex-row sm:justify-end">
              <Button
                variant="outline"
                className="w-full sm:w-[9.5rem] justify-center"
                disabled={consecSaving}
                onClick={() => {
                  setJefeFormOpen(false);
                  setError("");
                }}
              >
                {saldoRestante > 0 ? "Cerrar" : "Listo"}
              </Button>
              {canModificar ? (
                <Button
                  variant="outline"
                  className="w-full sm:w-[9.5rem] justify-center"
                  disabled={consecSaving}
                  onClick={() => {
                    setJefeFormOpen(false);
                    setModificarError("");
                    setPeriodoSel("");
                    setModStart(minProgramable);
                    setModificarOpen(true);
                  }}
                >
                  Modificar
                </Button>
              ) : null}
              {saldoRestante > 0 ? (
                <Button
                  className="w-full sm:w-[9.5rem] justify-center"
                  disabled={consecSaving || !canProgramar}
                  onClick={() => void programarConsec()}
                  title={programarTitle}
                >
                  {consecSaving && !adelantoOpen && !modificarOpen ? "Guardando…" : "Guardar período"}
                </Button>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

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
                <CamposFechas
                  start={consec.start}
                  end={consec.end}
                  min={minProgramable}
                  max={maxGoce}
                  onStart={(v) => patchFechas({ start: v })}
                  onEnd={(v) => patchFechas({ end: v })}
                />
              </div>
              <p className="text-[12px] text-muted-foreground">{textoDiasCalculados(startIso, consec.end, consecDays)}</p>

              {adelantoError ? (
                <Alert tone="error" title="No se puede adelantar">
                  {adelantoError}
                </Alert>
              ) : null}
            </div>
            <div className="flex flex-col gap-2 px-5 pb-5 sm:flex-row sm:justify-end">
              <Button
                variant="outline"
                className="w-full sm:w-[9.5rem] justify-center"
                disabled={consecSaving}
                onClick={() => {
                  setAdelantoOpen(false);
                  setAdelantoError("");
                }}
              >
                Cancelar
              </Button>
              <Button
                className="w-full sm:w-[9.5rem] justify-center"
                disabled={consecSaving || !canAdelanto}
                onClick={() => void guardarAdelanto()}
              >
                {consecSaving && adelantoOpen ? "Guardando…" : "Guardar"}
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
                Solo períodos que aún no empiezan. Mismos días; el saldo no se descuenta otra vez.
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
                  max={maxGoce}
                  value={modStart || minProgramable}
                  onChange={(e) => {
                    const v = e.target.value;
                    setModStart(v && v < minProgramable ? minProgramable : v);
                  }}
                />
              </Field>
              {periodoSel && modStart ? (
                <p className="text-[12px] text-muted-foreground">
                  Nuevo período: {formatFechaIso(modStart)} –{" "}
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
            <div className="flex flex-col gap-2 px-5 pb-5 sm:flex-row sm:justify-end">
              <Button
                variant="outline"
                className="w-full sm:w-[9.5rem] justify-center"
                disabled={consecSaving}
                onClick={() => {
                  setModificarOpen(false);
                  setModificarError("");
                }}
              >
                Cancelar
              </Button>
              <Button
                className="w-full sm:w-[9.5rem] justify-center"
                disabled={consecSaving || !periodoSel}
                onClick={() => void guardarModificar()}
              >
                {consecSaving && modificarOpen ? "Guardando…" : "Guardar"}
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
                {modal.tope}. Se escribe en la grilla al guardar.
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
                      max={plan.workers.find((w) => w.dni === modal.dni)?.fecha_vencimiento || undefined}
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

      {docPreviewUrl ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="flex h-[min(92vh,980px)] w-full max-w-4xl flex-col overflow-hidden rounded-xl border border-border bg-card shadow-[var(--shadow-card)]">
            <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
              <p className="text-sm font-semibold">{docReady?.titulo || "Documento de Personas y Cultura"}</p>
              <div className="flex gap-2">
                <Button variant="outline" className="h-9" disabled={docBusy} onClick={() => void descargarDocumento()}>
                  <FileDown size={16} strokeWidth={1.75} />
                  Descargar PDF
                </Button>
                <Button
                  variant="ghost"
                  className="h-9"
                  onClick={() =>
                    setDocPreviewUrl((prev) => {
                      if (prev) URL.revokeObjectURL(prev);
                      return null;
                    })
                  }
                >
                  Cerrar
                </Button>
              </div>
            </div>
            <iframe title="Vista previa del documento" className="min-h-0 flex-1 bg-muted" src={docPreviewUrl} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
import { memo, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { api, qs } from "../api";
import { SEM_COLORS, weekLocked } from "../lib/semaforo";
import { useApp } from "../state";
import { Alert, Button, cn, EmptyState, Field, Input, Kpi, PageHeader } from "../components/ui";
import { CalendarDays, CalendarPlus, Users, UserCheck, UserX } from "lucide-react";

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
};

type Plan = {
  year: number;
  current_year: number;
  current_week: number;
  total_semanas: number;
  workers: Worker[];
  kpis: { trabajadores: number; programados: number; pendientes: number; dias: number };
};

function scope(filters: ReturnType<typeof useApp>["filters"]) {
  return {
    year: filters.year,
    empresa: filters.empresas.includes("TODAS") ? undefined : filters.empresas,
    gerencia: filters.gerencias.includes("TODAS") ? undefined : filters.gerencias,
    division: filters.divisiones.includes("TODAS") ? undefined : filters.divisiones,
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
        {w.nombre}
      </td>
      <td className="border-b border-border px-2.5 py-1 text-muted-foreground">{w.dni}</td>
      <td className="border-b border-border px-2.5 py-1">{w.area}</td>
      <td className="border-b border-border px-2.5 py-1">{w.tipo_personal}</td>
      <td className="border-b border-border px-2.5 py-1 text-center">{w.total_dias}</td>
      {w.weeks.map((val, idx) => {
        const week = idx + 1;
        const locked = lockedWeeks[idx];
        const bg = val ? SEM_COLORS[val] : locked ? "var(--muted)" : "transparent";
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
            <input
              type="number"
              min={0}
              max={7}
              value={val}
              onChange={(e) => {
                const raw = e.target.value;
                if (raw === "") return;
                const n = Number(raw);
                onDays(w, week, n);
              }}
              className="h-8 w-9 bg-transparent text-center text-[11px] font-medium outline-none"
              style={{ background: bg }}
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
        <div className="min-w-0">
          <p className="truncate text-[14px] font-semibold">{w.nombre}</p>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            {w.dni} · {w.area || w.tipo_personal}
          </p>
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
          const bg = val ? SEM_COLORS[val] : locked ? "var(--muted)" : "transparent";
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
                <input
                  type="number"
                  min={0}
                  max={7}
                  value={val}
                  onChange={(e) => {
                    const raw = e.target.value;
                    if (raw === "") return;
                    onDays(w, week, Number(raw));
                  }}
                  className="h-9 w-full rounded-md border border-border text-center text-[11px] font-medium outline-none"
                  style={{ background: bg }}
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
  const [modal, setModal] = useState<{ dni: string; nombre: string; week: number; days: number; tipo: string } | null>(null);
  const [start, setStart] = useState("");
  const [modalError, setModalError] = useState("");
  const [consec, setConsec] = useState({ dni: "", start: "", days: 6 });
  const [consecQ, setConsecQ] = useState("");
  const [consecOpen, setConsecOpen] = useState(false);
  const deferredConsecQ = useDeferredValue(consecQ);
  const consecBoxRef = useRef<HTMLDivElement>(null);
  const [loadError, setLoadError] = useState("");

  const params = useMemo(() => scope(filters), [filters]);

  const load = useCallback(async () => {
    const data = await api<Plan>(`/api/plan${qs(params)}`);
    setPlan(data);
    setLoadError("");
    const first = data.workers[0];
    setConsec((c) => {
      if (c.dni && data.workers.some((w) => w.dni === c.dni)) return c;
      return { ...c, dni: first?.dni || "" };
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
      if (!consecBoxRef.current?.contains(e.target as Node)) setConsecOpen(false);
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

  function pickConsec(w: Worker) {
    setConsec((c) => ({ ...c, dni: w.dni }));
    setConsecQ(`${w.nombre} · ${w.dni}`);
    setConsecOpen(false);
  }

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
      if (Number.isNaN(days) || days < 0 || days > 7) {
        const msg = "Cada semana admite de 0 a 7 días.";
        setError(msg);
        return msg;
      }
      if (weekLocked(plan?.year ?? params.year, week, plan?.current_year ?? 0, plan?.current_week ?? 0)) {
        const msg = `La semana ${week} ya pasó. Solo puedes editar la semana ${plan?.current_week ?? "en curso"} y las siguientes.`;
        setError(msg);
        return msg;
      }
      if (days > 0 && days < 7 && !startDate) {
        const msg = "Si pones de 1 a 6 días, indica desde qué fecha empiezan.";
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
        const updates: Record<number, number> = res.weeks
          ? Object.fromEntries(Object.entries(res.weeks).map(([k, v]) => [Number(k), v]))
          : { [week]: days };
        applyLocalWeeks(w.dni, updates);
        const spill = Object.keys(updates).filter((k) => Number(k) !== week);
        setOk(
          days === 0
            ? "Se quitaron las vacaciones de esa semana."
            : spill.length
              ? `Se guardaron ${days} día(s): ${Object.entries(updates)
                  .sort((a, b) => Number(a[0]) - Number(b[0]))
                  .map(([wk, n]) => `S${wk} = ${n}`)
                  .join(", ")}.`
              : "Se guardaron los días de esa semana."
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
      if (Number.isNaN(days)) {
        setError("Cada semana admite de 0 a 7 días.");
        return;
      }
      const clamped = Math.max(0, Math.min(7, days));
      if (clamped !== days) setError("Cada semana admite de 0 a 7 días.");
      if (clamped > 0 && clamped < 7) {
        setModalError("");
        setStart("");
        setModal({ dni: w.dni, nombre: w.nombre, week, days: clamped, tipo: w.tipo_personal });
        return;
      }
      setWeek(w, week, clamped);
    },
    [setWeek]
  );

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
    if (!Number.isFinite(consec.days) || consec.days < 1 || consec.days > 90) {
      setError("Indica cuántos días son (entre 1 y 90).");
      return;
    }
    const startDt = new Date(`${consec.start}T00:00:00`);
    if (Number.isNaN(startDt.getTime())) {
      setError("La fecha de inicio no es válida.");
      return;
    }
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
      setOk(`Se programaron ${consec.days} día(s) desde el ${consec.start}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron guardar esas vacaciones.");
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

  return (
    <div className="space-y-6">
      <PageHeader
        title="Planificación"
        help={`Estás en la semana ${plan.current_week}. Las semanas anteriores no se pueden cambiar.`}
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
        <Kpi label="Trabajadores" value={plan.kpis.trabajadores} hint="Personas en este filtro" icon={<Users size={18} strokeWidth={1.75} />} />
        <Kpi label="Programados" value={plan.kpis.programados} hint="Ya tienen vacaciones" icon={<UserCheck size={18} strokeWidth={1.75} />} />
        <Kpi label="Sin programación" value={plan.kpis.pendientes} hint={`Aún sin días en ${plan.year}`} icon={<UserX size={18} strokeWidth={1.75} />} />
        <Kpi label="Días programados" value={plan.kpis.dias} hint="Suma de todas las semanas" icon={<CalendarDays size={18} strokeWidth={1.75} />} />
      </div>

      <div className="grid grid-cols-1 items-end gap-3 rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)] sm:grid-cols-2 md:grid-cols-[2fr_1fr_1fr_auto]">
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
                      <span className="min-w-0 truncate font-medium">{w.nombre}</span>
                      <span className="shrink-0 font-data text-[11px] text-muted-foreground">{w.dni}</span>
                    </button>
                  ))
                )}
              </div>
            ) : null}
          </div>
        </Field>
        <Field label="FECHA INICIO">
          <Input type="date" value={consec.start} onChange={(e) => setConsec({ ...consec, start: e.target.value })} />
        </Field>
        <Field label="DÍAS">
          <Input
            type="number"
            min={1}
            max={90}
            value={consec.days}
            onChange={(e) => setConsec({ ...consec, days: Number(e.target.value) })}
          />
        </Field>
        <Button onClick={programarConsec} className="w-full md:w-auto">
          <CalendarPlus size={16} strokeWidth={1.75} />
          Programar vacaciones
        </Button>
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

      {error ? (
        <Alert tone="error" title="No se pudo guardar">
          {error}
        </Alert>
      ) : null}
      {ok ? (
        <Alert tone="success" title="Guardado">
          {ok}
        </Alert>
      ) : null}

      {plan.workers.length === 0 ? (
        <EmptyState
          title="No hay trabajadores"
          body="Cambia el año, la empresa, la gerencia o la división. Con este filtro no aparece nadie."
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

      {modal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay)] p-4">
          <div className="w-full max-w-[400px] rounded-xl border border-border bg-card shadow-[0_8px_24px_#1E2C3A14]">
            <div className="space-y-1.5 px-5 pt-5">
              <h3 className="text-[15px] font-semibold">
                Primer día de vacaciones · {modal.nombre} · semana {modal.week}
              </h3>
              <p className="text-[13px] text-muted-foreground">
                Indica el primer día de esas vacaciones. Debe caer en la semana {modal.week}.
              </p>
            </div>
            <div className="space-y-3 px-5 py-3">
              <Field label="FECHA DE INICIO">
                <Input
                  type="date"
                  value={start}
                  onChange={(e) => {
                    setStart(e.target.value);
                    setModalError("");
                  }}
                />
              </Field>
              {modalError ? (
                <Alert tone="error" title="Falta la fecha">
                  {modalError}
                </Alert>
              ) : null}
            </div>
            <div className="flex justify-end gap-2 px-5 pb-5">
              <Button
                variant="outline"
                onClick={() => {
                  setModal(null);
                  setStart("");
                  setModalError("");
                }}
              >
                Cancelar
              </Button>
              <Button
                onClick={async () => {
                  if (!start) {
                    setModalError("Elige la fecha de inicio.");
                    return;
                  }
                  const w = plan.workers.find((x) => x.dni === modal.dni);
                  if (!w) {
                    setModalError("Esa persona ya no está en el filtro actual.");
                    return;
                  }
                  const msg = await setWeek(w, modal.week, modal.days, start);
                  if (msg) {
                    setModalError(msg);
                    return;
                  }
                  setModal(null);
                  setStart("");
                  setModalError("");
                }}
              >
                Guardar
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

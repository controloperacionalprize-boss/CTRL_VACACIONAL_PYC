import { memo, useEffect, useRef, useState } from "react";
import { SEM_COLORS } from "../../lib/semaforo";
import { MAX_VAC_DAYS } from "../../lib/vacaciones";
import { EmpAvatar } from "../../components/EmpAvatar";
import { cn } from "../../components/ui";
import type { Worker } from "./types";

function cellColor(val: number) {
  if (!val) return "transparent";
  return SEM_COLORS[Math.min(val, 7)] || SEM_COLORS[7];
}

/** Edición local; confirma solo con Enter o al salir de la celda. */
const WeekInput = memo(function WeekInput({
  value,
  week,
  worker,
  onCommit,
  className,
  disabled,
  saving,
}: {
  value: number;
  week: number;
  worker: Worker;
  onCommit: (w: Worker, week: number, days: number) => void;
  className: string;
  disabled?: boolean;
  saving?: boolean;
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
      setDraft(String(prev));
      return;
    }
    setDraft(String(clamped));
  }

  return (
    <input
      type="number"
      min={0}
      max={MAX_VAC_DAYS}
      disabled={disabled || saving}
      title={
        saving
          ? "Guardando…"
          : `0–${MAX_VAC_DAYS} días. Enter o clic fuera para guardar (más de 7 se reparte en semanas siguientes).`
      }
      value={saving ? "…" : draft}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => {
        if (e.key !== "Enter") return;
        e.preventDefault();
        (e.target as HTMLInputElement).blur();
      }}
      onBlur={(e) => {
        if (disabled || saving) return;
        commit(e.target.value);
      }}
      className={cn(className, saving && "animate-pulse")}
      style={{ background: value ? cellColor(value) : "transparent" }}
    />
  );
});

export const WorkerRow = memo(function WorkerRow({
  w,
  lockedWeeks,
  onDays,
  gridLocked,
  savingWeek,
}: {
  w: Worker;
  lockedWeeks: boolean[];
  onDays: (w: Worker, week: number, days: number) => void;
  gridLocked?: boolean;
  savingWeek?: number | null;
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
        const bg = val ? cellColor(val) : locked || gridLocked ? "var(--muted)" : "transparent";
        if (locked || gridLocked) {
          return (
            <td
              key={week}
              title={
                gridLocked && !locked
                  ? "Aún no cumple el año. Usa Adelanto vacacional o Modificar período."
                  : undefined
              }
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
              saving={savingWeek === week}
              className="h-8 w-9 bg-transparent text-center text-[11px] font-medium outline-none"
            />
          </td>
        );
      })}
    </tr>
  );
});

export const WorkerCard = memo(function WorkerCard({
  w,
  weekWindow,
  lockedWeeks,
  onDays,
  gridLocked,
  savingWeek,
}: {
  w: Worker;
  weekWindow: number[];
  lockedWeeks: boolean[];
  onDays: (w: Worker, week: number, days: number) => void;
  gridLocked?: boolean;
  savingWeek?: number | null;
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
          const bg = val ? cellColor(val) : locked || gridLocked ? "var(--muted)" : "transparent";
          return (
            <label key={week} className="flex flex-col items-center gap-0.5">
              <span className="text-[9px] font-semibold text-muted-foreground">S{week}</span>
              {locked || gridLocked ? (
                <span
                  title={
                    gridLocked && !locked
                      ? "Aún no cumple el año. Usa Adelanto vacacional o Modificar período."
                      : undefined
                  }
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
                  saving={savingWeek === week}
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

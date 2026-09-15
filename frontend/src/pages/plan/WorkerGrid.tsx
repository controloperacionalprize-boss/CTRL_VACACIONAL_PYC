import { memo, useEffect, useRef, useState } from "react";
import { SEM_COLORS } from "../../lib/semaforo";
import { flujoEstadoLabel, MAX_VAC_DAYS, type Rol } from "../../lib/vacaciones";
import { EmpAvatar } from "../../components/EmpAvatar";
import { cn } from "../../components/ui";
import type { Worker } from "./types";

function cellColor(val: number) {
  if (!val) return "transparent";
  return SEM_COLORS[Math.min(val, 7)] || SEM_COLORS[7];
}

export function FlujoBadge({ w, rol }: { w: Worker; rol?: Rol }) {
  if (w.apto === false) {
    return (
      <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
        No cumple el año
      </span>
    );
  }
  const estado = w.flujo_estado || "BORRADOR";
  if (estado === "BORRADOR") return null;
  const tone =
    estado === "OBSERVADO"
      ? "bg-warning-muted text-warning"
      : estado === "RECEPCIONADO" || estado === "VALIDADO"
        ? "bg-success-muted text-success"
        : estado === "ENVIADO"
          ? "bg-[var(--primary-soft)] text-primary"
          : "bg-muted text-muted-foreground";
  return (
    <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium", tone)} title={w.flujo_observacion || undefined}>
      {flujoEstadoLabel(estado, rol)}
    </span>
  );
}

export function lockReasonFor(w: Worker) {
  if (w.apto === false) return "No cumple el año de servicio. Solo se programan trabajadores aptos.";
  if (w.can_edit === false) {
    const estado = w.flujo_estado || "";
    if (estado === "ENVIADO") return "Enviado al gerente: ya no se puede editar.";
    if (estado === "VALIDADO") return "Validado por el gerente: ya no se puede editar.";
    if (estado === "RECEPCIONADO") return "Recepcionado: el plan queda bloqueado.";
    return "No puedes editar estos días.";
  }
  return "";
}

const CELL_TITLE = `0–${MAX_VAC_DAYS} días. Enter o clic fuera para guardar (más de 7 se reparte en semanas siguientes).`;

/**
 * Celda de semana. En reposo es un botón sin estado; el <input> solo existe mientras se edita.
 * Con cientos de filas × 53 semanas, montar un input con estado y efecto por celda era lo que
 * más CPU consumía al cargar o refrescar la grilla.
 */
const WeekInput = memo(function WeekInput({
  value,
  week,
  worker,
  onCommit,
  className,
  saving,
}: {
  value: number;
  week: number;
  worker: Worker;
  onCommit: (w: Worker, week: number, days: number) => void;
  className: string;
  saving?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const background = value ? cellColor(value) : "transparent";

  if (!editing || saving) {
    return (
      <button
        type="button"
        disabled={saving}
        title={saving ? "Guardando…" : CELL_TITLE}
        // onFocus cubre Tab; onClick hace falta porque Safari (Mac/iPhone) y Firefox en Mac
        // no enfocan un <button> al hacer clic o tocarlo.
        onFocus={() => setEditing(true)}
        onClick={() => setEditing(true)}
        className={cn(className, saving && "animate-pulse", !value && "text-muted-foreground/60")}
        style={{ background }}
      >
        {saving ? "…" : value}
      </button>
    );
  }
  return (
    <WeekEditor
      value={value}
      className={className}
      background={background}
      onDone={(days) => {
        setEditing(false);
        if (days !== null && days !== value) onCommit(worker, week, days);
      }}
    />
  );
});

function WeekEditor({
  value,
  className,
  background,
  onDone,
}: {
  value: number;
  className: string;
  background: string;
  onDone: (days: number | null) => void;
}) {
  const [draft, setDraft] = useState(String(value));
  const ref = useRef<HTMLInputElement>(null);
  // Algunos navegadores disparan blur al desmontar: sin esto, Escape terminaría guardando.
  const closed = useRef(false);

  useEffect(() => {
    ref.current?.focus();
    ref.current?.select();
  }, []);

  function finish(days: number | null) {
    if (closed.current) return;
    closed.current = true;
    onDone(days);
  }

  function parse(raw: string): number | null {
    if (raw.trim() === "") return null;
    const n = Number(raw);
    if (!Number.isFinite(n)) return null;
    return Math.max(0, Math.min(MAX_VAC_DAYS, Math.round(n)));
  }

  return (
    <input
      ref={ref}
      type="number"
      min={0}
      max={MAX_VAC_DAYS}
      title={CELL_TITLE}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          finish(null);
        } else if (e.key === "Enter") {
          e.preventDefault();
          e.currentTarget.blur();
        }
      }}
      onBlur={(e) => finish(parse(e.target.value))}
      className={className}
      style={{ background }}
    />
  );
}

export const WorkerRow = memo(function WorkerRow({
  w,
  lockedWeeks,
  onDays,
  gridLocked,
  savingWeek,
  lockReason,
}: {
  w: Worker;
  lockedWeeks: boolean[];
  onDays: (w: Worker, week: number, days: number) => void;
  gridLocked?: boolean;
  savingWeek?: number | null;
  lockReason?: string;
}) {
  return (
    <tr className="hover:bg-muted/60" style={{ contentVisibility: "auto", containIntrinsicSize: "auto 32px" }}>
      <td className="sticky left-0 z-10 whitespace-nowrap border-b border-border bg-card px-2.5 py-1 font-semibold">
        <span className="inline-flex max-w-[280px] items-center gap-2">
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
              title={gridLocked && !locked ? lockReason || lockReasonFor(w) : undefined}
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
  lockReason,
}: {
  w: Worker;
  weekWindow: number[];
  lockedWeeks: boolean[];
  onDays: (w: Worker, week: number, days: number) => void;
  gridLocked?: boolean;
  savingWeek?: number | null;
  lockReason?: string;
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
                  title={gridLocked && !locked ? lockReason || lockReasonFor(w) : undefined}
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

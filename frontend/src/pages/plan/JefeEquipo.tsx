import { useMemo, useState } from "react";
import { Send } from "lucide-react";
import { EmpAvatar } from "../../components/EmpAvatar";
import { Button, cn } from "../../components/ui";
import { MAX_VAC_DAYS, diasDisponibles, goceCompleto, topeDe } from "../../lib/vacaciones";
import type { Worker } from "./types";

type FilaKind = "sin" | "listo" | "observado" | "enviado" | "cerrado";
type Filtro = "todos" | "sin" | "listo" | "enviado";

function filaKind(w: Worker): FilaKind {
  const estado = w.flujo_estado || "BORRADOR";
  if (estado === "OBSERVADO") return "observado";
  if (estado === "ENVIADO") return "enviado";
  if (estado === "VALIDADO" || estado === "RECEPCIONADO") return "cerrado";
  if (goceCompleto(w.total_dias, topeDe(w))) return "listo";
  return "sin";
}

function filaLabel(kind: FilaKind, w: Worker) {
  if (kind === "sin") return w.total_dias > 0 ? "Incompleto" : "Sin programar";
  if (kind === "listo") return "Listo para enviar";
  if (kind === "observado") return "Observado";
  if (kind === "enviado") return "Enviado";
  if (w.flujo_estado === "RECEPCIONADO") return "Recepcionado";
  return "Validado";
}

function filaTone(kind: FilaKind) {
  if (kind === "sin" || kind === "observado") return "bg-warning-muted text-warning";
  if (kind === "listo") return "bg-[var(--primary-soft)] text-primary";
  if (kind === "enviado") return "bg-muted text-muted-foreground";
  return "bg-success-muted text-success";
}

const SORT: Record<FilaKind, number> = {
  observado: 0,
  sin: 1,
  listo: 2,
  enviado: 3,
  cerrado: 4,
};

export function JefeEquipo({
  workers,
  selectedDni,
  enviando,
  onPick,
  onEnviar,
}: {
  workers: Worker[];
  selectedDni?: string;
  enviando: boolean;
  onPick: (w: Worker) => void;
  onEnviar: () => void;
}) {
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const ranked = useMemo(
    () =>
      [...workers].sort((a, b) => {
        const d = SORT[filaKind(a)] - SORT[filaKind(b)];
        if (d) return d;
        return a.nombre.localeCompare(b.nombre, "es");
      }),
    [workers]
  );
  const sin = ranked.filter((w) => {
    const k = filaKind(w);
    return k === "sin" || k === "observado";
  }).length;
  const listos = ranked.filter((w) => filaKind(w) === "listo").length;
  const enviados = ranked.filter((w) => {
    const k = filaKind(w);
    return k === "enviado" || k === "cerrado";
  }).length;
  const faltaProgramar = ranked.filter((w) => !goceCompleto(w.total_dias, topeDe(w))).length;
  const porEnviar = ranked.filter((w) => {
    const k = filaKind(w);
    return goceCompleto(w.total_dias, topeDe(w)) && (k === "listo" || k === "observado");
  }).length;
  const puedeEnviar = faltaProgramar === 0 && porEnviar > 0;
  const visible = ranked.filter((w) => {
    const k = filaKind(w);
    if (filtro === "sin") return k === "sin" || k === "observado";
    if (filtro === "listo") return k === "listo";
    if (filtro === "enviado") return k === "enviado" || k === "cerrado";
    return true;
  });

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card shadow-[var(--shadow-card)]">
      <div className="space-y-4 px-4 py-4 sm:px-5">
        <div>
          <h2 className="text-[16px] font-semibold tracking-tight">Equipo de tu área</h2>
          <p className="mt-0.5 text-[12px] text-muted-foreground">{workers.length} personas aptas para vacaciones</p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="flex items-start gap-3 rounded-[10px] bg-muted/50 px-3 py-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-[12px] font-semibold text-primary-foreground">
              1
            </span>
            <div className="min-w-0">
              <p className="text-[13px] font-semibold">Programa</p>
              <p className="mt-0.5 text-[12px] leading-snug text-muted-foreground">
                Programa los 30 días de cada persona, en uno o varios períodos (Art. 8: 15 corridos, o primero 7 u 8 y luego el otro; el resto libre). Cada semana se programa o cambia hasta el viernes anterior.
              </p>
            </div>
          </div>
          <div className="flex items-start gap-3 rounded-[10px] bg-muted/50 px-3 py-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-[12px] font-semibold text-primary-foreground">
              2
            </span>
            <div className="min-w-0">
              <p className="text-[13px] font-semibold">Envía</p>
              <p className="mt-0.5 text-[12px] leading-snug text-muted-foreground">
                Cuando todo el equipo tenga el goce completo, envía el plan al gerente.
              </p>
            </div>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-[10px] border border-border px-3 py-2.5">
            <p className="text-[11px] font-medium text-muted-foreground">Falta</p>
            <p className="mt-0.5 text-[18px] font-semibold tabular-nums">{sin}</p>
          </div>
          <div className="rounded-[10px] border border-border px-3 py-2.5">
            <p className="text-[11px] font-medium text-muted-foreground">Listos</p>
            <p className="mt-0.5 text-[18px] font-semibold tabular-nums">{listos}</p>
          </div>
          <div className="rounded-[10px] border border-border px-3 py-2.5">
            <p className="text-[11px] font-medium text-muted-foreground">Enviados</p>
            <p className="mt-0.5 text-[18px] font-semibold tabular-nums">{enviados}</p>
          </div>
        </div>
        <div className="flex gap-1 rounded-[10px] bg-muted p-1">
          {(
            [
              ["todos", "Todos"],
              ["sin", "Falta"],
              ["listo", "Listos"],
              ["enviado", "Enviados"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setFiltro(id)}
              className={cn(
                "h-8 flex-1 rounded-lg text-[12px] font-semibold transition-colors",
                filtro === id ? "bg-card text-foreground shadow-[var(--shadow-card)]" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {visible.length === 0 ? (
        <p className="border-t border-border px-4 py-8 text-center text-[13px] text-muted-foreground">Nadie en este grupo.</p>
      ) : (
        <>
          <div className="divide-y divide-border border-t border-border md:hidden">
            {visible.map((w) => {
              const kind = filaKind(w);
              const saldo = diasDisponibles(w.total_dias, topeDe(w));
              const canPick = w.can_edit !== false && (kind === "sin" || kind === "listo" || kind === "observado");
              return (
                <div key={w.dni} className={cn("flex items-start gap-3 px-4 py-3", selectedDni === w.dni && "bg-[var(--primary-soft)]/35")}>
                  <EmpAvatar nombre={w.nombre} fotoUrl={w.foto_url} className="h-9 w-9 text-[11px]" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-semibold">{w.nombre}</p>
                    <p className="mt-0.5 text-[12px] text-muted-foreground">
                      {w.dni} · {w.total_dias} de {topeDe(w)} días
                      {saldo > 0 ? ` · quedan ${saldo}` : ""}
                    </p>
                    <span className={cn("mt-1 inline-block rounded px-1.5 py-0.5 text-[10px] font-medium", filaTone(kind))}>
                      {filaLabel(kind, w)}
                    </span>
                    {w.flujo_observacion ? <p className="mt-1 text-[11px] text-warning">{w.flujo_observacion}</p> : null}
                  </div>
                  {canPick ? (
                    <Button variant="outline" className="h-8 w-[7.25rem] shrink-0 justify-center px-2 text-xs" onClick={() => onPick(w)}>
                      {kind === "sin" ? "Programar" : "Modificar"}
                    </Button>
                  ) : null}
                </div>
              );
            })}
          </div>
          <div className="hidden overflow-auto border-t border-border md:block">
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-left">
                <tr>
                  {["Persona", "DNI", "Programados", "Quedan", "Estado", ""].map((h) => (
                    <th key={h || "accion"} className="px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((w) => {
                  const kind = filaKind(w);
                  const saldo = diasDisponibles(w.total_dias, topeDe(w));
                  const canPick = w.can_edit !== false && (kind === "sin" || kind === "listo" || kind === "observado");
                  return (
                    <tr
                      key={w.dni}
                      className={cn("border-t border-border", selectedDni === w.dni && "bg-[var(--primary-soft)]/35")}
                    >
                      <td className="px-4 py-2.5">
                        <span className="inline-flex max-w-[280px] items-center gap-2.5">
                          <EmpAvatar nombre={w.nombre} fotoUrl={w.foto_url} className="h-8 w-8 text-[10px]" />
                          <span className="truncate font-medium">{w.nombre}</span>
                        </span>
                      </td>
                      <td className="px-4 py-2.5 font-data text-[12px] text-muted-foreground">{w.dni}</td>
                      <td className="px-4 py-2.5 tabular-nums">{w.total_dias}</td>
                      <td className="px-4 py-2.5 tabular-nums text-muted-foreground">{saldo}</td>
                      <td className="px-4 py-2.5">
                        <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium", filaTone(kind))}>
                          {filaLabel(kind, w)}
                        </span>
                        {w.flujo_observacion ? (
                          <p className="mt-1 max-w-[220px] text-[11px] text-warning">{w.flujo_observacion}</p>
                        ) : null}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        {canPick ? (
                          <Button variant="outline" className="h-8 w-[7.25rem] justify-center px-2 text-xs" onClick={() => onPick(w)}>
                            {kind === "sin" ? "Programar" : "Modificar"}
                          </Button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="flex flex-col gap-3 border-t border-border px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <p className={cn("text-[13px] leading-snug", faltaProgramar > 0 ? "font-medium text-warning" : "text-muted-foreground")}>
          {faltaProgramar > 0
            ? `No puedes enviar al gerente: faltan ${faltaProgramar} persona${faltaProgramar === 1 ? "" : "s"} por completar sus ${MAX_VAC_DAYS} días. Programa a todo el equipo primero.`
            : puedeEnviar
              ? `Todo el equipo está programado. Puedes enviar ${porEnviar} plan${porEnviar === 1 ? "" : "es"} al gerente.`
              : "No hay planes pendientes de envío."}
        </p>
        <Button
          disabled={enviando || !puedeEnviar}
          onClick={onEnviar}
          className="shrink-0 sm:min-w-[200px]"
          title={
            faltaProgramar > 0
              ? "Programa a todas las personas antes de enviar."
              : !puedeEnviar
                ? "No hay planes pendientes de envío."
                : undefined
          }
        >
          <Send size={16} strokeWidth={1.75} />
          {enviando ? "Enviando…" : porEnviar && faltaProgramar === 0 ? `Enviar ${porEnviar} al gerente` : "Enviar al gerente"}
        </Button>
      </div>
    </div>
  );
}

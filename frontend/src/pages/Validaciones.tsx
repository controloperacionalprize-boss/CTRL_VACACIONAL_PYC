import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, Download, FileSpreadsheet, Inbox, Send, Upload } from "lucide-react";
import { api, downloadFile, qs, uploadFile } from "../api";
import { useApp } from "../state";
import { Alert, Button, cn, EmptyState, Field, PageHeader } from "../components/ui";
import { EmpAvatar } from "../components/EmpAvatar";
import { flujoEstadoLabel } from "../lib/vacaciones";
import { formatFechaIso } from "../lib/dates";

type PeriodoResumen = { inicio: string; fin: string; dias: number };

type FlujoItem = {
  dni: string;
  nombre: string;
  area: string;
  gerencia?: string;
  apto: boolean;
  cumple_record?: string | null;
  flujo_estado: string;
  flujo_observacion?: string;
  estado_label?: string;
  dias_programados: number;
  periodos?: PeriodoResumen[];
  jefe_correo?: string;
  gerente_correo?: string;
  admin_correo?: string;
  enviado_at?: string | null;
  validado_at?: string | null;
  recepcionado_at?: string | null;
  foto_url?: string | null;
};

type FlujoList = {
  year: number;
  rol: string;
  bandeja: boolean;
  items: FlujoItem[];
  pendientes: number;
};

type ActionResult = { ok: { dni: string }[]; errors: string[]; enviados?: number; rechazados?: number };

const BTN = "w-full sm:w-[12rem] justify-center";

function scope(filters: ReturnType<typeof useApp>["filters"]) {
  return {
    year: filters.year,
    empresa: filters.empresas.includes("TODAS") ? undefined : filters.empresas,
    gerencia: filters.gerencias.includes("TODAS") ? undefined : filters.gerencias,
    area: filters.areas.includes("TODAS") ? undefined : filters.areas,
  };
}

function copyFor(rol: string) {
  if (rol === "JEFE") {
    return {
      title: "Bandeja",
      emptyTitle: "Aún no hay nada enviado",
      emptyBody:
        "En Planificación programa vacaciones a todas las personas aptas y pulsa Enviar al gerente. Luego aparecen aquí, y también si te las observan.",
    };
  }
  if (rol === "GERENTE") {
    return {
      title: "Bandeja",
      emptyTitle: "Nadie te ha enviado planes todavía",
      emptyBody: "Cuando un jefe envíe a las personas aptas de su área, aparecerán aquí para que las valides o observes.",
    };
  }
  return {
    title: "Bandeja",
    emptyTitle: "Nada listo para recepcionar",
    emptyBody: "Cuando el gerente valide un plan, llegará aquí. Recíbelo o, si no corresponde, obsérvalo.",
  };
}

function estadoTone(estado: string) {
  if (estado === "OBSERVADO") return "bg-warning-muted text-warning";
  if (estado === "RECEPCIONADO" || estado === "VALIDADO") return "bg-success-muted text-success";
  return "bg-[var(--primary-soft)] text-primary";
}

function ExcelFechasJefe({
  year,
  busy,
  onDownload,
  onUpload,
}: {
  year: number;
  busy: boolean;
  onDownload: () => void;
  onUpload: () => void;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card shadow-[var(--shadow-card)]">
      <div className="flex flex-col gap-4 p-4 sm:flex-row sm:items-start sm:justify-between sm:p-5">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-[15px] font-semibold">
            <FileSpreadsheet size={18} strokeWidth={1.75} className="text-primary" />
            Excel opcional (fechas)
          </p>
          <p className="mt-1 text-[13px] text-muted-foreground">
            Lo más simple es programar en Planificación. Usa Excel solo si quieres cargar varias fechas de una vez.
          </p>
        </div>
        <div className="flex w-full shrink-0 flex-col gap-2 sm:w-auto sm:flex-row">
          <Button variant="outline" className={BTN} onClick={onDownload}>
            <Download size={16} strokeWidth={1.75} />
            Descargar plantilla
          </Button>
          <Button variant="outline" className={BTN} disabled={busy} onClick={onUpload}>
            <Upload size={16} strokeWidth={1.75} />
            {busy ? "Cargando…" : "Cargar Excel"}
          </Button>
        </div>
      </div>
      <div className="grid gap-px border-t border-border bg-border sm:grid-cols-3">
        {[
          ["1", "Descarga la plantilla", "Sale una sola hoja: PERIODOS, con tu equipo apto del año " + year + "."],
          ["2", "Completa las fechas", "Por cada persona, los períodos deben sumar todos los días del derecho (30, o lo que quede si ya hay goce pasado). Fechas dd/mm/aaaa. Varias filas del mismo DNI se suman."],
          ["3", "Carga el mismo archivo", "No cambies el nombre de la hoja ni de las columnas. Las filas sin fechas se ignoran."],
        ].map(([n, t, d]) => (
          <div key={n} className="flex gap-3 bg-card px-4 py-3.5 sm:px-5">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-[12px] font-semibold text-primary-foreground">
              {n}
            </span>
            <div>
              <p className="text-[13px] font-semibold">{t}</p>
              <p className="mt-0.5 text-[12px] leading-snug text-muted-foreground">{d}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="border-t border-border bg-muted/40 px-4 py-4 sm:px-5">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Formato que espera el sistema</p>
        <p className="mt-2 text-[13px]">
          Hoja <span className="font-data font-semibold">PERIODOS</span>. Columnas: DNI, NOMBRE, AREA, FECHA_INICIO, FECHA_FIN. Los días se calculan solos.
        </p>
        <div className="mt-3 overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full min-w-[480px] text-left text-[12px]">
            <thead className="bg-muted/70 text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr>
                {["DNI", "NOMBRE", "AREA", "FECHA_INICIO", "FECHA_FIN"].map((h) => (
                  <th key={h} className="px-3 py-2 font-semibold">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-border">
                <td className="px-3 py-2 font-data">12345678</td>
                <td className="px-3 py-2">Ana Pérez</td>
                <td className="px-3 py-2">T.I.</td>
                <td className="px-3 py-2 font-data">14/09/2026</td>
                <td className="px-3 py-2 font-data">18/09/2026</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[12px] text-muted-foreground">
          Solo DNI, inicio y fin. 14/09 al 18/09 son 5 días corridos. La suma por persona debe ser el derecho completo (p. ej. 30). Fechas en dd/mm/aaaa.
        </p>
      </div>
    </div>
  );
}

function PeriodosBandeja({ periodos, total }: { periodos: PeriodoResumen[]; total: number }) {
  if (!periodos.length) {
    return <span className="text-[12px] text-muted-foreground">{total ? `${total} día(s)` : "Sin períodos"}</span>;
  }
  return (
    <div className="space-y-1.5">
      {periodos.map((p, i) => (
        <div
          key={`${p.inicio}-${p.fin}`}
          className="flex items-center justify-between gap-2 rounded-lg border border-border bg-muted/40 px-2.5 py-1.5"
        >
          <span className="min-w-0 text-[12px] leading-snug">
            <span className="font-semibold text-muted-foreground">P{i + 1} · </span>
            {formatFechaIso(p.inicio)} – {formatFechaIso(p.fin)}
          </span>
          <span className="shrink-0 rounded-md bg-card px-1.5 py-0.5 text-[11px] font-semibold tabular-nums">
            {p.dias}d
          </span>
        </div>
      ))}
      <p className="text-[11px] text-muted-foreground">
        {total} día{total === 1 ? "" : "s"} en {periodos.length} período{periodos.length === 1 ? "" : "s"}
      </p>
    </div>
  );
}

function seguimientoDe(item: FlujoItem) {
  return [
    item.jefe_correo ? `Envió ${item.jefe_correo}` : "",
    item.gerente_correo ? `Validó ${item.gerente_correo}` : "",
    item.admin_correo ? `Recepcionó ${item.admin_correo}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

export function ValidacionesPage() {
  const { filters, user } = useApp();
  const params = useMemo(() => scope(filters), [filters]);
  const [data, setData] = useState<FlujoList | null>(null);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [nota, setNota] = useState("");
  const [busy, setBusy] = useState("");
  const [excelError, setExcelError] = useState("");
  const [excelOk, setExcelOk] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const rol = data?.rol || (user?.is_admin ? "ADMIN" : user?.is_jefe ? "JEFE" : "GERENTE");
  const copy = copyFor(rol);
  const puedeActuar = rol === "GERENTE" || rol === "ADMIN";

  const load = useCallback(async () => {
    const res = await api<FlujoList>(`/api/flujo${qs({ ...params, bandeja: true })}`);
    setData(res);
    setSelected([]);
  }, [params]);

  useEffect(() => {
    load().catch((e) => setError(e instanceof Error ? e.message : "No se pudo abrir la bandeja."));
  }, [load]);

  async function run(path: string, extra: Record<string, unknown> = {}) {
    if (!selected.length) {
      setError("Marca al menos una persona en la lista.");
      return;
    }
    setError("");
    setOk("");
    setBusy(path);
    try {
      const res = await api<ActionResult>(path, {
        method: "POST",
        body: JSON.stringify({ year: params.year, dnis: selected, observacion: nota, ...extra }),
      });
      await load();
      setNota("");
      const done = res.ok?.length || res.enviados || 0;
      const extras = res.errors?.length ? ` ${res.errors.slice(0, 4).join(" ")}` : "";
      if (path.includes("observar")) {
        setOk(done ? `Devolviste ${done} persona${done === 1 ? "" : "s"} al jefe.${extras}` : res.errors?.join(" ") || "No se observó a nadie.");
      } else if (path.includes("recepcionar")) {
        setOk(done ? `Recepcionaste ${done} persona${done === 1 ? "" : "s"}.${extras}` : res.errors?.join(" ") || "No se recepcionó a nadie.");
      } else {
        setOk(done ? `Validaste ${done} persona${done === 1 ? "" : "s"}.${extras}` : res.errors?.join(" ") || "No se validó a nadie.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo completar la acción.");
    } finally {
      setBusy("");
    }
  }

  async function descargarExcel() {
    setExcelError("");
    try {
      await downloadFile(`/api/flujo/excel${qs(params)}`, {}, `FLUJO_VACACIONES_${filters.year}.xlsx`);
    } catch (e) {
      setExcelError(e instanceof Error ? e.message : "No se pudo descargar la plantilla.");
    }
  }

  async function cargarExcel(file: File) {
    setExcelError("");
    setExcelOk("");
    setBusy("excel");
    try {
      const res = await uploadFile<{ aplicados: number; rechazados: number; errors: string[] }>(
        `/api/flujo/excel${qs({ year: params.year })}`,
        file
      );
      await load();
      const extras = res.errors?.length ? ` ${res.errors.slice(0, 5).join(" ")}` : "";
      setExcelOk(
        res.aplicados
          ? `Se actualizaron ${res.aplicados} fila${res.aplicados === 1 ? "" : "s"}.${
              res.rechazados ? ` ${res.rechazados} no se aplicaron.` : ""
            }${extras}`
          : `No se aplicó ninguna fila.${res.rechazados ? ` ${res.rechazados} rechazada${res.rechazados === 1 ? "" : "s"}.` : ""}${extras}`
      );
    } catch (e) {
      setExcelError(e instanceof Error ? e.message : "No se pudo cargar el Excel. Revisa que la hoja y las columnas coincidan con el instructivo.");
    } finally {
      setBusy("");
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const items = data?.items || [];
  const allSelected = items.length > 0 && selected.length === items.length;

  return (
    <div className="space-y-6">
      <PageHeader title={copy.title} />

      {error ? (
        <Alert tone="error" title="No se pudo completar">
          {error}
        </Alert>
      ) : null}
      {ok ? (
        <Alert tone="success" title="Listo">
          {ok}
        </Alert>
      ) : null}

      {rol === "JEFE" ? (
        <>
          <ExcelFechasJefe
            year={filters.year}
            busy={busy === "excel"}
            onDownload={() => void descargarExcel()}
            onUpload={() => fileRef.current?.click()}
          />
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xlsm"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void cargarExcel(f);
            }}
          />
          {excelError ? (
            <Alert tone="error" title="No se pudo usar el Excel">
              {excelError}
            </Alert>
          ) : null}
          {excelOk ? (
            <Alert tone="success" title="Excel aplicado">
              {excelOk}
            </Alert>
          ) : null}
        </>
      ) : null}

      {!data ? (
        <p className="text-sm text-muted-foreground">Cargando tu bandeja…</p>
      ) : items.length === 0 ? (
        <EmptyState title={copy.emptyTitle} body={copy.emptyBody} />
      ) : (
        <>
          {puedeActuar ? (
            <div className="space-y-4 rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)] sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[15px] font-semibold">
                    {rol === "GERENTE" ? "Validar o devolver" : "Recepcionar o devolver"}
                  </p>
                  <p className="mt-0.5 text-[12px] text-muted-foreground">
                    {selected.length} de {items.length} marcada{selected.length === 1 ? "" : "s"}
                    {data.pendientes
                      ? ` · ${data.pendientes} pendiente${data.pendientes === 1 ? "" : "s"} en esta vista`
                      : ""}
                  </p>
                </div>
                <label className="flex h-10 items-center gap-2 text-[13px] font-medium">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={(e) => setSelected(e.target.checked ? items.map((i) => i.dni) : [])}
                  />
                  Marcar todas
                </label>
              </div>
              <Field label="MOTIVO (obligatorio si observas)">
                <textarea
                  className="mt-1 min-h-[72px] w-full rounded-[10px] border border-border bg-card px-3 py-2 text-[13px] outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-soft)]"
                  value={nota}
                  onChange={(e) => setNota(e.target.value)}
                  placeholder="Ej. Falta el bloque de 15 días corridos. El jefe lo verá en Planificación."
                />
              </Field>
              <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
                {rol === "GERENTE" ? (
                  <Button className={BTN} disabled={Boolean(busy)} onClick={() => void run("/api/flujo/validar")}>
                    <CheckCircle2 size={16} strokeWidth={1.75} />
                    {busy === "/api/flujo/validar" ? "Validando…" : "Validar"}
                  </Button>
                ) : (
                  <Button className={BTN} disabled={Boolean(busy)} onClick={() => void run("/api/flujo/recepcionar")}>
                    <Send size={16} strokeWidth={1.75} />
                    {busy === "/api/flujo/recepcionar" ? "Recepcionando…" : "Recepcionar"}
                  </Button>
                )}
                <Button variant="outline" className={BTN} disabled={Boolean(busy)} onClick={() => void run("/api/flujo/observar")}>
                  <Inbox size={16} strokeWidth={1.75} />
                  {busy === "/api/flujo/observar" ? "Devolviendo…" : "Observar"}
                </Button>
              </div>
            </div>
          ) : (
            <p className="text-[13px] text-muted-foreground">
              Si alguien aparece como Observado, corrige las fechas en Planificación y vuelve a enviar al gerente.
            </p>
          )}

          <div className="overflow-hidden rounded-xl border border-border bg-card shadow-[var(--shadow-card)]">
            <div className="border-b border-border px-4 py-3 sm:px-5">
              <p className="text-[15px] font-semibold">Personas en tu bandeja</p>
              <p className="text-[12px] text-muted-foreground">{items.length} en el filtro actual</p>
            </div>
            <div className="divide-y divide-border md:hidden">
              {items.map((item) => (
                <label key={item.dni} className="flex items-start gap-3 px-4 py-3">
                  {puedeActuar ? (
                    <input
                      type="checkbox"
                      className="mt-2"
                      checked={selected.includes(item.dni)}
                      onChange={(e) =>
                        setSelected((prev) =>
                          e.target.checked ? [...prev, item.dni] : prev.filter((d) => d !== item.dni)
                        )
                      }
                    />
                  ) : null}
                  <EmpAvatar nombre={item.nombre} fotoUrl={item.foto_url} className="mt-0.5 h-9 w-9 text-[11px]" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-[14px] font-semibold">{item.nombre}</p>
                      <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium", estadoTone(item.flujo_estado))}>
                        {flujoEstadoLabel(item.flujo_estado, rol)}
                      </span>
                      {item.apto === false ? (
                        <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                          Ya no es apto
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-0.5 text-[12px] text-muted-foreground">
                      {item.dni} · {item.area || "—"}
                      {item.cumple_record ? ` · cumple ${formatFechaIso(item.cumple_record)}` : ""}
                    </p>
                    <div className="mt-1.5">
                      <PeriodosBandeja periodos={item.periodos || []} total={item.dias_programados} />
                    </div>
                    {item.flujo_observacion ? (
                      <p className="mt-1 text-[12px] text-warning">Observación: {item.flujo_observacion}</p>
                    ) : null}
                    {seguimientoDe(item) ? (
                      <p className="mt-1 text-[11px] text-muted-foreground">{seguimientoDe(item)}</p>
                    ) : null}
                  </div>
                </label>
              ))}
            </div>
            <div className="hidden overflow-auto md:block">
              <table className="w-full text-sm">
                <thead className="bg-muted/60 text-left">
                  <tr>
                    {puedeActuar ? <th className="w-10 px-4 py-2.5"></th> : null}
                    {["Persona", "DNI", "Área", "Períodos", "Estado", "Seguimiento"].map((h) => (
                      <th key={h} className="px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.dni} className="border-t border-border">
                      {puedeActuar ? (
                        <td className="px-4 py-2.5">
                          <input
                            type="checkbox"
                            checked={selected.includes(item.dni)}
                            onChange={(e) =>
                              setSelected((prev) =>
                                e.target.checked ? [...prev, item.dni] : prev.filter((d) => d !== item.dni)
                              )
                            }
                          />
                        </td>
                      ) : null}
                      <td className="px-4 py-2.5">
                        <span className="inline-flex max-w-[260px] items-center gap-2.5">
                          <EmpAvatar nombre={item.nombre} fotoUrl={item.foto_url} className="h-8 w-8 text-[10px]" />
                          <span className="truncate font-medium">{item.nombre}</span>
                        </span>
                      </td>
                      <td className="px-4 py-2.5 font-data text-[12px] text-muted-foreground">{item.dni}</td>
                      <td className="max-w-[160px] truncate px-4 py-2.5 text-[13px]" title={item.area}>
                        {item.area || "—"}
                      </td>
                      <td className="min-w-[220px] px-4 py-2.5 align-top">
                        <PeriodosBandeja periodos={item.periodos || []} total={item.dias_programados} />
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium", estadoTone(item.flujo_estado))}>
                          {flujoEstadoLabel(item.flujo_estado, rol)}
                        </span>
                        {item.apto === false ? (
                          <p className="mt-1 text-[11px] text-muted-foreground">Ya no es apto</p>
                        ) : null}
                        {item.flujo_observacion ? (
                          <p className="mt-1 max-w-[240px] text-[11px] text-warning">{item.flujo_observacion}</p>
                        ) : null}
                      </td>
                      <td className="max-w-[220px] px-4 py-2.5 text-[11px] leading-snug text-muted-foreground">
                        {seguimientoDe(item) || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

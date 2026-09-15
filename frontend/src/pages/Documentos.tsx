import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { ChevronLeft, ChevronRight, Download, FileArchive, Mail } from "lucide-react";
import { api, downloadFile, qs } from "../api";
import { useApp } from "../state";
import { Alert, Button, cn, EmptyState, Field, Kpi, PageHeader, Select } from "../components/ui";
import { formatFechaIso } from "../lib/dates";

type Tramo = { inicio: string; fin: string; dias: number };
type Tab = "por_emitir" | "proximo" | "emitido";

type Persona = {
  dni: string;
  nombre: string;
  area: string;
  jefatura: string;
  jefe_nombre: string;
  gerencia: string;
};

type Pendiente = Persona & {
  key: string;
  tipo: string;
  titulo: string;
  estado: "por_emitir" | "proximo";
  tramo: Tramo | null;
  incluye_memorando: boolean;
  periodos: Tramo[];
  emitir_desde: string | null;
};

type Emitido = Persona & {
  id: number;
  tipo: string;
  titulo: string;
  estado: "emitido";
  tramo: Tramo | null;
  periodos: Tramo[];
  emitido_at: string | null;
  emitido_por: string;
  descargas: number;
  enviado_at: string | null;
  enviado_a: string;
  envio_error: string;
};

type Fila = Pendiente | Emitido;

type DocList = {
  year: number;
  resumen: { por_emitir: number; proximo: number; emitido: number };
  max_zip: number;
  max_envio: number;
  correo_activo: boolean;
  items: Pendiente[];
  emitidos: Emitido[];
  /** Recepcionados que luego quedaron incompletos: no se emite nada hasta corregirlos. */
  bloqueados?: (Persona & { motivo: string })[];
};

type DocRef = { dni?: string; key?: string; id?: number };

const PAGE_SIZE = 25;

const TIPO_CORTO: Record<string, string> = {
  memorando: "Memorando",
  fraccionamiento: "Solicitud y convenio",
  modificacion: "Modificación de convenio",
  adelanto: "Adelanto",
};

function esEmitido(f: Fila): f is Emitido {
  return f.estado === "emitido";
}

function filaId(f: Fila) {
  return esEmitido(f) ? `id:${f.id}` : `${f.dni}|${f.key}`;
}

function refDe(f: Fila): DocRef {
  return esEmitido(f) ? { id: f.id } : { dni: f.dni, key: f.key };
}

function jefeDe(p: Persona) {
  return (p.jefe_nombre || p.jefatura || "").trim();
}

function uniqueSorted(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b, "es"));
}

function formatWhen(iso: string | null) {
  if (!iso) return "—";
  const day = formatFechaIso(iso.slice(0, 10));
  const time = iso.includes("T") ? iso.slice(11, 16) : "";
  return time ? `${day} ${time}` : day;
}

function rango(t: Tramo) {
  return `${formatFechaIso(t.inicio)} – ${formatFechaIso(t.fin)} (${t.dias} d)`;
}

function scope(filters: ReturnType<typeof useApp>["filters"]) {
  return {
    year: filters.year,
    empresa: filters.empresas.includes("TODAS") ? undefined : filters.empresas,
    gerencia: filters.gerencias.includes("TODAS") ? undefined : filters.gerencias,
    area: filters.areas.includes("TODAS") ? undefined : filters.areas,
  };
}

function DetalleDocumento({ f }: { f: Fila }) {
  return (
    <div className="space-y-0.5 text-[12px] leading-snug">
      <p className="font-medium text-foreground">{TIPO_CORTO[f.tipo] || f.titulo}</p>
      {f.tramo ? (
        <p className="font-data text-muted-foreground">
          {f.tipo === "memorando" || f.tipo === "adelanto" ? rango(f.tramo) : `+ memorando ${rango(f.tramo)}`}
        </p>
      ) : null}
      {f.tipo === "fraccionamiento" || f.tipo === "modificacion" ? (
        <p className="text-muted-foreground">
          {f.periodos.length} períodos · {f.periodos.reduce((a, p) => a + p.dias, 0)} días
        </p>
      ) : null}
    </div>
  );
}

function EstadoDocumento({ f }: { f: Fila }) {
  if (esEmitido(f)) {
    return (
      <div className="space-y-0.5 text-[11px] leading-snug text-muted-foreground">
        <span className="inline-flex rounded bg-success-muted px-1.5 py-0.5 text-[10px] font-medium text-success">
          Emitido
        </span>
        <p>
          {formatWhen(f.emitido_at)}
          {f.descargas > 1 ? ` · ${f.descargas} descargas` : ""}
        </p>
        {f.enviado_at ? <p className="text-success">Enviado a {f.enviado_a}</p> : null}
        {f.envio_error ? <p className="text-warning">Correo: {f.envio_error}</p> : null}
      </div>
    );
  }
  if (f.estado === "proximo") {
    return (
      <div className="text-[11px] leading-snug text-muted-foreground">
        <span className="inline-flex rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium">Próximo</span>
        {f.emitir_desde ? <p className="mt-0.5">Se emite desde el {formatFechaIso(f.emitir_desde)}</p> : null}
      </div>
    );
  }
  return (
    <span className="inline-flex rounded bg-[var(--primary-soft)] px-1.5 py-0.5 text-[10px] font-medium text-primary">
      Por emitir
    </span>
  );
}

export function DocumentosPage() {
  const { user, filters } = useApp();
  const params = useMemo(() => scope(filters), [filters]);
  const [data, setData] = useState<DocList | null>(null);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [busy, setBusy] = useState("");
  const [tab, setTab] = useState<Tab>("por_emitir");
  const [area, setArea] = useState("");
  const [jefe, setJefe] = useState("");
  const [tipo, setTipo] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [page, setPage] = useState(1);

  async function load() {
    try {
      setData(await api<DocList>(`/api/documentos${qs(params)}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron cargar los documentos.");
    }
  }

  useEffect(() => {
    if (!user?.is_admin) return;
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, params]);

  const filas: Fila[] = useMemo(() => {
    if (!data) return [];
    if (tab === "emitido") return data.emitidos;
    return data.items.filter((i) => i.estado === tab);
  }, [data, tab]);

  const areaOpts = useMemo(() => uniqueSorted(filas.map((f) => f.area)), [filas]);
  const jefeOpts = useMemo(() => uniqueSorted(filas.map(jefeDe)), [filas]);
  const tipoOpts = useMemo(() => uniqueSorted(filas.map((f) => f.tipo)), [filas]);

  const view = useMemo(
    () =>
      filas.filter(
        (f) => (!area || f.area === area) && (!jefe || jefeDe(f) === jefe) && (!tipo || f.tipo === tipo)
      ),
    [filas, area, jefe, tipo]
  );
  const pages = Math.max(1, Math.ceil(view.length / PAGE_SIZE));
  const slice = view.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const byId = useMemo(() => new Map(view.map((f) => [filaId(f), f])), [view]);
  const marcadas = selected.map((id) => byId.get(id)).filter((f): f is Fila => Boolean(f));
  const objetivo = marcadas.length ? marcadas : view;
  const maxZip = data?.max_zip || 40;
  const maxEnvio = data?.max_envio || 20;

  useEffect(() => {
    setPage(1);
    setSelected([]);
  }, [tab, area, jefe, tipo, filters.year]);

  useEffect(() => {
    if (page > pages) setPage(pages);
  }, [page, pages]);

  if (!user?.is_admin) return <Navigate to="/" replace />;

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label);
    setError("");
    setOk("");
    try {
      await action();
      setSelected([]);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo completar la acción.");
    } finally {
      setBusy("");
    }
  }

  function descargarUno(f: Fila) {
    return run(filaId(f), () =>
      downloadFile(
        "/api/documentos/descargar",
        { method: "POST", body: JSON.stringify({ year: params.year, doc: refDe(f) }) },
        "documento.pdf"
      )
    );
  }

  function descargarZip(targets: Fila[]) {
    if (targets.length > maxZip) {
      setError(`Como máximo ${maxZip} documentos por ZIP. Afina el filtro o marca menos.`);
      return;
    }
    return run("zip", () =>
      downloadFile(
        "/api/documentos/zip",
        { method: "POST", body: JSON.stringify({ year: params.year, docs: targets.map(refDe) }) },
        `documentos_gth_${params.year}.zip`
      )
    );
  }

  function enviar(targets: Fila[]) {
    if (targets.length > maxEnvio) {
      setError(`Como máximo ${maxEnvio} correos por envío. Marca menos documentos.`);
      return;
    }
    return run("correo", async () => {
      const res = await api<{ enviados: number; errores: string[] }>("/api/documentos/enviar", {
        method: "POST",
        body: JSON.stringify({ year: params.year, docs: targets.map(refDe) }),
      });
      const extra = res.errores.length ? ` No se pudo: ${res.errores.slice(0, 4).join(" ")}` : "";
      setOk(`${res.enviados === 1 ? "Se envió 1 documento" : `Se enviaron ${res.enviados} documentos`} por correo.${extra}`);
    });
  }

  const puedeEmitir = tab !== "proximo";

  return (
    <div className="space-y-6">
      <PageHeader
        title="Documentos"
        help="La solicitud y el convenio de fraccionamiento se emiten una sola vez. Después, cada salida lleva su memorando, que se emite el mes anterior."
      />

      {error ? (
        <Alert tone="error" title="No se completó">
          {error}
        </Alert>
      ) : null}
      {ok ? (
        <Alert tone="success" title="Listo">
          {ok}
        </Alert>
      ) : null}

      {!data ? (
        <p className="text-sm text-muted-foreground">Cargando documentos…</p>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Kpi
              label="Por emitir"
              value={data.resumen.por_emitir}
              hint="Convenios pendientes y memorandos de este mes y el siguiente"
              accent="info"
              onClick={() => setTab("por_emitir")}
            />
            <Kpi
              label="Próximos"
              value={data.resumen.proximo}
              hint="Memorandos de salidas más adelante"
              accent="warning"
              onClick={() => setTab("proximo")}
            />
            <Kpi
              label="Emitidos"
              value={data.resumen.emitido}
              hint="Registro de lo entregado; se puede reimprimir"
              accent="success"
              onClick={() => setTab("emitido")}
            />
          </div>

          {data.bloqueados?.length ? (
            <Alert
              tone="warning"
              title={
                data.bloqueados.length === 1
                  ? "1 plan recepcionado no puede emitir documentos"
                  : `${data.bloqueados.length} planes recepcionados no pueden emitir documentos`
              }
            >
              <ul className="mt-1 max-h-40 list-disc space-y-0.5 overflow-auto pl-4">
                {data.bloqueados.map((b) => (
                  <li key={b.dni}>
                    <span className="font-medium text-foreground">{b.nombre}</span>: {b.motivo}
                  </li>
                ))}
              </ul>
            </Alert>
          ) : null}

          {!data.correo_activo ? (
            <Alert tone="warning" title="Envío por correo no configurado">
              Mientras el servidor no tenga SMTP configurado, descarga el PDF y entrégalo. Al activarlo, cada
              documento llega al correo del trabajador con copia a Personas y Cultura.
            </Alert>
          ) : null}

          <div className="overflow-hidden rounded-xl border border-border bg-card shadow-[var(--shadow-card)]">
            <div className="flex flex-col gap-3 border-b border-border px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
              <div className="grid grid-cols-3 gap-1 rounded-[10px] bg-muted p-1 sm:flex">
                {(
                  [
                    ["por_emitir", `Por emitir (${data.resumen.por_emitir})`],
                    ["proximo", `Próximos (${data.resumen.proximo})`],
                    ["emitido", `Emitidos (${data.resumen.emitido})`],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setTab(id)}
                    className={cn(
                      "rounded-lg px-2 py-1.5 text-[12px] font-semibold leading-tight sm:whitespace-nowrap sm:px-3 sm:text-[13px]",
                      tab === id ? "bg-card text-foreground" : "text-muted-foreground"
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {puedeEmitir ? (
                <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
                  <Button
                    variant="outline"
                    className="w-full sm:w-auto"
                    disabled={Boolean(busy) || objetivo.length === 0}
                    onClick={() => void descargarZip(objetivo)}
                  >
                    <FileArchive size={16} strokeWidth={1.75} />
                    {busy === "zip" ? "Armando ZIP…" : marcadas.length ? `ZIP de ${marcadas.length}` : "ZIP de esta vista"}
                  </Button>
                  <span title={data.correo_activo ? undefined : "Falta configurar SMTP en el servidor."}>
                    <Button
                      className="w-full sm:w-auto"
                      disabled={Boolean(busy) || !data.correo_activo || marcadas.length === 0}
                      onClick={() => void enviar(marcadas)}
                    >
                      <Mail size={16} strokeWidth={1.75} />
                      {busy === "correo" ? "Enviando…" : `Enviar por correo${marcadas.length ? ` (${marcadas.length})` : ""}`}
                    </Button>
                  </span>
                </div>
              ) : null}
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
              <Field label="DOCUMENTO">
                <Select value={tipo} onChange={(e) => setTipo(e.target.value)}>
                  <option value="">Todos</option>
                  {tipoOpts.map((v) => (
                    <option key={v} value={v}>
                      {TIPO_CORTO[v] || v}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>

            {view.length === 0 ? (
              <EmptyState
                title={tab === "emitido" ? "Nada emitido todavía" : "Nada en esta vista"}
                body={
                  tab === "por_emitir"
                    ? "Cuando recepciones un plan en Bandeja, sus documentos aparecen aquí."
                    : tab === "proximo"
                      ? "Los memorandos de salidas más lejanas aparecerán aquí hasta el mes anterior."
                      : "Al descargar o enviar un documento queda registrado aquí."
                }
              />
            ) : (
              <>
                {puedeEmitir ? (
                  <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5 sm:px-5">
                    <label className="flex items-center gap-2 text-[13px] font-medium">
                      <input
                        type="checkbox"
                        checked={view.length > 0 && selected.length === view.length}
                        onChange={(e) => setSelected(e.target.checked ? view.map(filaId) : [])}
                      />
                      Marcar todo ({view.length})
                    </label>
                    <p className="text-[12px] text-muted-foreground">
                      ZIP hasta {maxZip} · correo hasta {maxEnvio}
                    </p>
                  </div>
                ) : null}
                <div className="divide-y divide-border md:hidden">
                  {slice.map((f) => {
                    const id = filaId(f);
                    return (
                      <div key={id} className="flex items-start gap-3 px-4 py-3">
                        {puedeEmitir ? (
                          <input
                            type="checkbox"
                            className="mt-1"
                            aria-label={`Marcar ${f.nombre}`}
                            checked={selected.includes(id)}
                            onChange={(e) =>
                              setSelected((prev) => (e.target.checked ? [...prev, id] : prev.filter((x) => x !== id)))
                            }
                          />
                        ) : null}
                        <div className="min-w-0 flex-1 space-y-1.5">
                          <div>
                            <p className="text-[14px] font-semibold leading-snug">{f.nombre}</p>
                            <p className="text-[12px] text-muted-foreground">
                              {f.dni} · {f.area || "—"}
                              {jefeDe(f) ? ` · ${jefeDe(f)}` : ""}
                            </p>
                          </div>
                          <DetalleDocumento f={f} />
                          <EstadoDocumento f={f} />
                          <Button
                            variant="outline"
                            className="h-9 w-full"
                            disabled={Boolean(busy)}
                            onClick={() => void descargarUno(f)}
                          >
                            <Download size={16} strokeWidth={1.75} />
                            {busy === id ? "Descargando…" : esEmitido(f) ? "Reimprimir PDF" : "Descargar PDF"}
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="hidden overflow-x-auto md:block">
                  <table className="w-full min-w-[900px] text-sm">
                    <thead className="bg-muted/60 text-left">
                      <tr>
                        {[puedeEmitir ? "" : null, "Trabajador", "Área · Jefe", "Documento", "Estado", ""]
                          .filter((h) => h !== null)
                          .map((h, i) => (
                            <th
                              key={`${h}-${i}`}
                              className="px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
                            >
                              {h}
                            </th>
                          ))}
                      </tr>
                    </thead>
                    <tbody>
                      {slice.map((f) => {
                        const id = filaId(f);
                        return (
                          <tr key={id} className="border-t border-border align-top">
                            {puedeEmitir ? (
                              <td className="w-10 px-3 py-2.5">
                                <input
                                  type="checkbox"
                                  checked={selected.includes(id)}
                                  onChange={(e) =>
                                    setSelected((prev) => (e.target.checked ? [...prev, id] : prev.filter((x) => x !== id)))
                                  }
                                />
                              </td>
                            ) : null}
                            <td className="px-3 py-2.5">
                              <p className="font-medium leading-snug">{f.nombre}</p>
                              <p className="font-data text-[11px] text-muted-foreground">{f.dni}</p>
                            </td>
                            <td className="px-3 py-2.5 text-[12px] leading-snug">
                              <p>{f.area || "—"}</p>
                              <p className="text-muted-foreground">{jefeDe(f) || "—"}</p>
                            </td>
                            <td className="px-3 py-2.5">
                              <DetalleDocumento f={f} />
                            </td>
                            <td className="px-3 py-2.5">
                              <EstadoDocumento f={f} />
                            </td>
                            <td className="whitespace-nowrap px-3 py-2.5 text-right">
                              <Button
                                variant="outline"
                                className="h-9 px-3"
                                disabled={Boolean(busy)}
                                title={tab === "proximo" ? "Todavía no toca; puedes adelantarlo si hace falta." : undefined}
                                onClick={() => void descargarUno(f)}
                              >
                                <Download size={16} strokeWidth={1.75} />
                                {busy === id ? "…" : esEmitido(f) ? "Reimprimir" : "PDF"}
                              </Button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="flex items-center justify-between gap-3 border-t border-border px-4 py-3 text-[12px] text-muted-foreground sm:px-5">
                  <span>
                    {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, view.length)} de {view.length}
                  </span>
                  {pages > 1 ? (
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        disabled={page <= 1}
                        onClick={() => setPage((n) => Math.max(1, n - 1))}
                        className="inline-flex h-8 items-center gap-1 rounded-md px-2 hover:text-foreground disabled:opacity-40"
                      >
                        <ChevronLeft size={16} /> Anterior
                      </button>
                      <span className="px-2">
                        {page} / {pages}
                      </span>
                      <button
                        type="button"
                        disabled={page >= pages}
                        onClick={() => setPage((n) => n + 1)}
                        className="inline-flex h-8 items-center gap-1 rounded-md px-2 hover:text-foreground disabled:opacity-40"
                      >
                        Siguiente <ChevronRight size={16} />
                      </button>
                    </div>
                  ) : null}
                </div>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}

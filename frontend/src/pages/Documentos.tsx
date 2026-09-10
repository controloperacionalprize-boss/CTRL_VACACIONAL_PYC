import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { ChevronDown, ChevronLeft, ChevronRight, Download, FileArchive } from "lucide-react";
import { api, downloadFile, qs } from "../api";
import { useApp } from "../state";
import { Alert, Button, cn, EmptyState, Field, Kpi, PageHeader, Select } from "../components/ui";
import { formatFechaIso } from "../lib/dates";

type Periodo = { inicio: string; fin: string; dias: number };
type EstadoEmision = "por_emitir" | "emitido" | "por_reemitir";

type DocItem = {
  dni: string;
  nombre: string;
  area: string;
  jefatura: string;
  jefe_nombre: string;
  gerencia: string;
  escenario: number;
  titulo: string;
  dias: number;
  periodos: Periodo[];
  inicio: string;
  fin: string;
  estado_emision: EstadoEmision;
  estado_emision_label: string;
  recepcionado_at: string | null;
  descargas: number;
  descargado_at: string | null;
  descargado_por: string;
};

type DocList = {
  year: number;
  resumen: { por_emitir: number; por_reemitir: number; emitido: number };
  max_zip: number;
  tipos: { escenario: number; titulo: string }[];
  items: DocItem[];
};

const PAGE_SIZES = [10, 25, 50] as const;

function pageItems(current: number, total: number): Array<number | "…"> {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  if (current <= 3) return [1, 2, 3, 4, 5, "…", total];
  if (current >= total - 2) return [1, "…", total - 4, total - 3, total - 2, total - 1, total];
  return [1, "…", current - 1, current, current + 1, "…", total];
}

function uniqueSorted(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b, "es"));
}

function personaJefe(p: DocItem) {
  return (p.jefe_nombre || p.jefatura || "").trim();
}

function formatWhen(iso: string | null) {
  if (!iso) return "—";
  const day = formatFechaIso(iso.slice(0, 10));
  const time = iso.includes("T") ? iso.slice(11, 16) : "";
  return time ? `${day} ${time}` : day;
}

function tipoCorto(escenario: number, titulo: string) {
  if (escenario === 1) return "Memorando";
  if (escenario === 2) return "Fraccionamiento";
  if (escenario === 3) return "Modificación";
  if (escenario === 4) return "Adelanto";
  return titulo;
}

function periodosDe(p: DocItem): Periodo[] {
  if (p.periodos?.length) return p.periodos;
  return [{ inicio: p.inicio, fin: p.fin, dias: p.dias }];
}

function emisionTone(estado: EstadoEmision) {
  if (estado === "por_reemitir") return "bg-warning-muted text-warning";
  if (estado === "emitido") return "bg-success-muted text-success";
  return "bg-[var(--primary-soft)] text-primary";
}

function scope(filters: ReturnType<typeof useApp>["filters"]) {
  return {
    year: filters.year,
    empresa: filters.empresas.includes("TODAS") ? undefined : filters.empresas,
    gerencia: filters.gerencias.includes("TODAS") ? undefined : filters.gerencias,
    area: filters.areas.includes("TODAS") ? undefined : filters.areas,
  };
}

export function DocumentosPage() {
  const { user, filters } = useApp();
  const params = scope(filters);
  const [data, setData] = useState<DocList | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [tab, setTab] = useState<"cola" | "emitidos">("cola");
  const [area, setArea] = useState("");
  const [jefe, setJefe] = useState("");
  const [tipo, setTipo] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZES)[number]>(10);

  async function load() {
    setError("");
    try {
      const next = await api<DocList>(`/api/documentos${qs(params)}`);
      setData(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron cargar los documentos.");
    }
  }

  useEffect(() => {
    if (!user?.is_admin) return;
    void load();
  }, [user, filters.year, filters.empresas, filters.gerencias, filters.areas]);

  const personas = data?.items || [];
  const matches = useMemo(() => {
    return (p: DocItem, skip?: "area" | "jefe" | "tipo") => {
      if (skip !== "area" && area && (p.area || "").trim() !== area) return false;
      if (skip !== "jefe" && jefe && personaJefe(p) !== jefe) return false;
      if (skip !== "tipo" && tipo && String(p.escenario) !== tipo) return false;
      return true;
    };
  }, [area, jefe, tipo]);

  const areaOpts = useMemo(
    () => uniqueSorted(personas.filter((p) => matches(p, "area")).map((p) => (p.area || "").trim())),
    [personas, matches]
  );
  const jefeOpts = useMemo(
    () => uniqueSorted(personas.filter((p) => matches(p, "jefe")).map(personaJefe)),
    [personas, matches]
  );
  const tipoOpts = useMemo(() => {
    const seen = new Map<number, string>();
    for (const p of personas.filter((row) => matches(row, "tipo"))) {
      seen.set(p.escenario, p.titulo);
    }
    return [...seen.entries()].sort((a, b) => a[0] - b[0]);
  }, [personas, matches]);

  const filtered = useMemo(() => personas.filter((p) => matches(p)), [personas, matches]);
  const cola = useMemo(
    () => filtered.filter((p) => p.estado_emision !== "emitido"),
    [filtered]
  );
  const emitidos = useMemo(
    () => filtered.filter((p) => p.estado_emision === "emitido"),
    [filtered]
  );
  const view = tab === "cola" ? cola : emitidos;
  const pages = Math.max(1, Math.ceil(view.length / pageSize));
  const slice = useMemo(() => {
    const start = (page - 1) * pageSize;
    return view.slice(start, start + pageSize);
  }, [view, page, pageSize]);
  const numbers = useMemo(() => pageItems(page, pages), [page, pages]);
  const from = view.length ? (page - 1) * pageSize + 1 : 0;
  const to = Math.min(page * pageSize, view.length);
  const allSelected = view.length > 0 && view.every((p) => selected.includes(p.dni));
  const maxZip = data?.max_zip || 40;

  useEffect(() => {
    setPage(1);
    setSelected([]);
  }, [tab, area, jefe, tipo, pageSize, filters.year]);

  useEffect(() => {
    if (page > pages) setPage(pages);
  }, [page, pages]);

  useEffect(() => {
    if (area && !areaOpts.includes(area)) setArea("");
  }, [area, areaOpts]);
  useEffect(() => {
    if (jefe && !jefeOpts.includes(jefe)) setJefe("");
  }, [jefe, jefeOpts]);

  if (!user?.is_admin) return <Navigate to="/" replace />;

  async function descargarUno(dni: string) {
    setBusy(dni);
    setError("");
    try {
      await downloadFile(
        `/api/documentos/descargar${qs(params)}`,
        { method: "POST", body: JSON.stringify({ year: params.year, dni }) },
        "vacaciones.pdf"
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo descargar el PDF.");
    } finally {
      setBusy("");
    }
  }

  async function descargarZip(dnis: string[]) {
    if (!dnis.length) {
      setError("Marca al menos una persona, o usa el ZIP de esta vista.");
      return;
    }
    if (dnis.length > maxZip) {
      setError(`Como máximo ${maxZip} documentos por ZIP. Afina el filtro o marca menos.`);
      return;
    }
    setBusy("zip");
    setError("");
    try {
      await downloadFile(
        `/api/documentos/zip${qs(params)}`,
        { method: "POST", body: JSON.stringify({ year: params.year, dnis }) },
        `documentos_gth_${params.year}.zip`
      );
      setSelected([]);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo armar el ZIP.");
    } finally {
      setBusy("");
    }
  }

  const zipTargets = selected.length ? selected.filter((dni) => view.some((p) => p.dni === dni)) : view.map((p) => p.dni);

  return (
    <div className="space-y-6">
      <PageHeader title="Documentos" />

      {error ? (
        <Alert tone="error" title="No se completó la descarga">
          {error}
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
              hint="Recepcionados sin PDF todavía"
              accent="info"
              onClick={() => setTab("cola")}
            />
            <Kpi
              label="Por reemitir"
              value={data.resumen.por_reemitir}
              hint="El plan cambió después de la última descarga"
              accent="warning"
              onClick={() => setTab("cola")}
            />
            <Kpi
              label="Emitidos"
              value={data.resumen.emitido}
              hint="Ya se descargó al menos una vez"
              accent="success"
              onClick={() => setTab("emitidos")}
            />
          </div>

          <div className="overflow-hidden rounded-xl border border-border bg-card shadow-[var(--shadow-card)]">
            <div className="flex flex-col gap-3 border-b border-border px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
              <div className="flex gap-1 rounded-[10px] bg-muted p-1">
                <button
                  type="button"
                  onClick={() => setTab("cola")}
                  className={cn(
                    "rounded-lg px-3 py-1.5 text-[13px] font-semibold",
                    tab === "cola" ? "bg-card text-foreground" : "text-muted-foreground"
                  )}
                >
                  Por emitir ({cola.length})
                </button>
                <button
                  type="button"
                  onClick={() => setTab("emitidos")}
                  className={cn(
                    "rounded-lg px-3 py-1.5 text-[13px] font-semibold",
                    tab === "emitidos" ? "bg-card text-foreground" : "text-muted-foreground"
                  )}
                >
                  Emitidos ({emitidos.length})
                </button>
              </div>
              <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
                <Button
                  variant="outline"
                  className="w-full sm:w-auto"
                  disabled={Boolean(busy) || view.length === 0}
                  onClick={() => void descargarZip(zipTargets)}
                >
                  <FileArchive size={16} strokeWidth={1.75} />
                  {busy === "zip" ? "Armando ZIP…" : selected.length ? `ZIP de ${selected.length}` : "ZIP de esta vista"}
                </Button>
              </div>
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
              <Field label="TIPO">
                <Select value={tipo} onChange={(e) => setTipo(e.target.value)}>
                  <option value="">Todos</option>
                  {tipoOpts.map(([n, titulo]) => (
                    <option key={n} value={String(n)}>
                      {tipoCorto(n, titulo)}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>

            {view.length === 0 ? (
              <EmptyState
                title={tab === "cola" ? "Nada por emitir en esta vista" : "Nadie emitido todavía"}
                body={
                  tab === "cola"
                    ? "Cuando recepciones un plan en Bandeja, el PDF aparece aquí. Los emitidos están en la otra pestaña."
                    : "Al descargar un PDF (uno o el ZIP) pasa a esta lista. Puedes reimprimir si lo necesitas."
                }
              />
            ) : (
              <>
                <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5 sm:px-5">
                  <label className="flex items-center gap-2 text-[13px] font-medium">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={(e) => setSelected(e.target.checked ? view.map((i) => i.dni) : [])}
                    />
                    Marcar visibles
                  </label>
                  <p className="text-[12px] text-muted-foreground">
                    {selected.length ? `${selected.length} marcada(s) · ` : ""}
                    máximo {maxZip} por ZIP
                  </p>
                </div>
                <div className="divide-y divide-border md:hidden">
                  {slice.map((p) => (
                    <div key={p.dni} className="flex items-start gap-3 px-4 py-3">
                      <input
                        type="checkbox"
                        className="mt-1"
                        checked={selected.includes(p.dni)}
                        onChange={(e) =>
                          setSelected((prev) =>
                            e.target.checked ? [...prev, p.dni] : prev.filter((d) => d !== p.dni)
                          )
                        }
                      />
                      <div className="min-w-0 flex-1">
                        <p className="text-[14px] font-semibold">{p.nombre}</p>
                        <p className="text-[12px] text-muted-foreground">
                          {p.dni} · {p.area || "—"} · {personaJefe(p) || "—"}
                        </p>
                        <p className="mt-1 text-[12px]">{tipoCorto(p.escenario, p.titulo)}</p>
                        <div className="mt-0.5 space-y-0.5 text-[12px] text-muted-foreground">
                          {periodosDe(p).map((x, i) => (
                            <p key={`${x.inicio}-${x.fin}-${i}`}>
                              {formatFechaIso(x.inicio)} – {formatFechaIso(x.fin)}
                            </p>
                          ))}
                        </div>
                        <span
                          className={cn(
                            "mt-1 inline-flex whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-medium",
                            emisionTone(p.estado_emision)
                          )}
                        >
                          {p.estado_emision_label}
                        </span>
                        <Button
                          className="mt-2 w-full"
                          variant="outline"
                          disabled={Boolean(busy)}
                          onClick={() => void descargarUno(p.dni)}
                        >
                          <Download size={16} strokeWidth={1.75} />
                          {busy === p.dni ? "Descargando…" : tab === "emitidos" ? "Reimprimir PDF" : "Descargar PDF"}
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="hidden overflow-x-auto md:block">
                  <table className="w-full min-w-[1080px] table-fixed text-sm">
                    <colgroup>
                      <col className="w-10" />
                      <col className="w-[22%]" />
                      <col className="w-[16%]" />
                      <col className="w-[18%]" />
                      <col className="w-[14%]" />
                      <col className="w-[16%]" />
                      <col className="w-[12%]" />
                      <col className="w-[110px]" />
                    </colgroup>
                    <thead className="bg-muted/60 text-left">
                      <tr>
                        {["", "Trabajador", "Área", "Jefe", "Tipo", "Períodos", "Estado", ""].map((h, i) => (
                          <th
                            key={h || `c${i}`}
                            className="px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
                          >
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {slice.map((p) => {
                        const jefe = (p.jefe_nombre || p.jefatura || "—").trim();
                        return (
                          <tr key={p.dni} className="border-t border-border align-top">
                            <td className="px-3 py-2.5">
                              <input
                                type="checkbox"
                                checked={selected.includes(p.dni)}
                                onChange={(e) =>
                                  setSelected((prev) =>
                                    e.target.checked ? [...prev, p.dni] : prev.filter((d) => d !== p.dni)
                                  )
                                }
                              />
                            </td>
                            <td className="px-3 py-2.5">
                              <p className="font-medium leading-snug">{p.nombre}</p>
                              <p className="font-data text-[11px] text-muted-foreground">{p.dni}</p>
                            </td>
                            <td className="px-3 py-2.5 text-[13px] leading-snug" title={p.area || undefined}>
                              {p.area || "—"}
                            </td>
                            <td className="px-3 py-2.5 text-[13px] leading-snug" title={jefe}>
                              {jefe}
                            </td>
                            <td className="whitespace-nowrap px-3 py-2.5 text-[13px]" title={p.titulo}>
                              {tipoCorto(p.escenario, p.titulo)}
                            </td>
                            <td className="px-3 py-2.5">
                              <div className="space-y-0.5">
                                {periodosDe(p).map((x, i) => (
                                  <p key={`${x.inicio}-${x.fin}-${i}`} className="whitespace-nowrap font-data text-[12px] text-muted-foreground">
                                    {formatFechaIso(x.inicio)} – {formatFechaIso(x.fin)}
                                  </p>
                                ))}
                              </div>
                            </td>
                            <td className="px-3 py-2.5">
                              <span
                                className={cn(
                                  "inline-flex whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-medium",
                                  emisionTone(p.estado_emision)
                                )}
                              >
                                {p.estado_emision_label}
                              </span>
                              {p.descargado_at ? (
                                <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
                                  {formatWhen(p.descargado_at)}
                                  {p.descargas > 1 ? ` · ${p.descargas} veces` : ""}
                                </p>
                              ) : null}
                            </td>
                            <td className="whitespace-nowrap px-3 py-2.5">
                              <Button
                                variant="outline"
                                className="h-9 px-3"
                                disabled={Boolean(busy)}
                                onClick={() => void descargarUno(p.dni)}
                              >
                                <Download size={16} strokeWidth={1.75} />
                                {busy === p.dni ? "…" : tab === "emitidos" ? "Reimprimir" : "PDF"}
                              </Button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="flex flex-col gap-3 border-t border-border px-4 py-3 sm:px-5 lg:flex-row lg:items-center lg:justify-between">
                  <label className="flex items-center gap-2 text-[12px] text-muted-foreground">
                    Resultados por página
                    <span className="relative">
                      <select
                        value={pageSize}
                        onChange={(e) => setPageSize(Number(e.target.value) as (typeof PAGE_SIZES)[number])}
                        className="h-9 appearance-none rounded-[10px] border border-border bg-card py-0 pl-3 pr-8 text-[13px] text-foreground outline-none"
                      >
                        {PAGE_SIZES.map((n) => (
                          <option key={n} value={n}>
                            {n}
                          </option>
                        ))}
                      </select>
                      <ChevronDown
                        size={14}
                        className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground"
                      />
                    </span>
                  </label>
                  {pages > 1 ? (
                    <div className="flex flex-wrap items-center justify-center gap-1">
                      <button
                        type="button"
                        disabled={page <= 1}
                        onClick={() => setPage((n) => Math.max(1, n - 1))}
                        className="inline-flex h-9 items-center gap-1 rounded-md px-2 text-[13px] text-muted-foreground hover:text-foreground disabled:opacity-40"
                      >
                        <ChevronLeft size={16} />
                        Anterior
                      </button>
                      {numbers.map((n, i) =>
                        n === "…" ? (
                          <span key={`e${i}`} className="px-1 text-[13px] text-muted-foreground">
                            …
                          </span>
                        ) : (
                          <button
                            key={n}
                            type="button"
                            onClick={() => setPage(n)}
                            className={cn(
                              "inline-flex h-8 min-w-8 items-center justify-center rounded-md px-2 text-[13px] font-medium",
                              n === page ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-muted"
                            )}
                          >
                            {n}
                          </button>
                        )
                      )}
                      <button
                        type="button"
                        disabled={page >= pages}
                        onClick={() => setPage((n) => n + 1)}
                        className="inline-flex h-9 items-center gap-1 rounded-md px-2 text-[13px] text-muted-foreground hover:text-foreground disabled:opacity-40"
                      >
                        Siguiente
                        <ChevronRight size={16} />
                      </button>
                    </div>
                  ) : (
                    <span className="hidden lg:block" />
                  )}
                  <p className="text-[12px] text-muted-foreground lg:text-right">
                    {from}–{to} de {view.length}
                  </p>
                </div>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}

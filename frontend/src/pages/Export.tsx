import { useEffect, useMemo, useState } from "react";
import { API, api, authHeader, qs } from "../api";
import { useApp } from "../state";
import { Alert, Button, Icon, PageHeader } from "../components/ui";

const SHEETS = [
  ["Resumen", "Totales y riesgos del equipo que estás viendo"],
  ["Vacaciones", "Las vacaciones de cada persona"],
  ["Detalle diario", "Un renglón por cada día de vacaciones"],
  ["Plan semanal", "Cuántos días hay en cada semana del año"],
  ["Historial", "Record vacacional: gozados, pendientes y vencimiento"],
  ["Cambios", "Quién modificó el plan y cuándo"],
] as const;

type Group = { code: string; title: string; hint: string; count: number; samples: string[] };

function isoWeek(d = new Date()) {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  return { year: t.getUTCFullYear(), week: Math.ceil(((t.getTime() - yearStart.getTime()) / 86400000 + 1) / 7) };
}

function weekFromText(text: string): number | null {
  const m = text.match(/SEM\s*0*(\d+)|semana\s+(\d+)/i);
  if (!m) return null;
  return Number(m[1] || m[2]);
}

function isLockedWeek(year: number, week: number) {
  const now = isoWeek();
  if (year < now.year) return true;
  if (year === now.year && week < now.week) return true;
  return false;
}

/** Semanas pasadas, sáb/dom de oficina y textos viejos del validador: no hay nada que corregir. */
function isNoise(text: string, year: number) {
  if (
    /histórica|historica|bloqueada|hábil|habil|fin de semana|s[aá]bado|domingo|weekend|se indic[oó].*seleccionad/i.test(
      text
    )
  ) {
    return true;
  }
  const week = weekFromText(text);
  if (week != null && isLockedWeek(year, week)) return true;
  return false;
}

function classifyErrors(errors: string[], year: number): Group[] {
  const live = errors.filter((e) => !isNoise(e, year));
  const range = live.filter((e) => /máximo|maximo|más de 7|mas de 7/i.test(e));
  const mismatch = live.filter((e) => /planificación|detalle|completa|están marcados|estan marcados|grilla/i.test(e));
  const groups: Group[] = [];
  if (mismatch.length) {
    groups.push({
      code: "mismatch",
      title: "El número de la semana no coincide con las fechas",
      hint: "El número que ves en planificación no coincide con las fechas guardadas día por día.",
      count: mismatch.length,
      samples: mismatch,
    });
  }
  if (range.length) {
    groups.push({
      code: "range",
      title: "Una semana tiene más de 7 días",
      hint: "En cada semana solo se pueden programar de 0 a 7 días.",
      count: range.length,
      samples: range,
    });
  }
  return groups;
}

function usableGroups(result: { errors?: string[]; groups?: Group[] }, year: number): Group[] {
  const cleaned = (result.groups || [])
    .filter((g) => g.code !== "weekend")
    .map((g) => {
      const samples = g.samples.filter((s) => !isNoise(s, year));
      return samples.length ? { ...g, samples, count: samples.length } : null;
    })
    .filter((g): g is Group => g != null);
  return cleaned.length ? cleaned : classifyErrors(result.errors || [], year);
}

function futureCoverage(warnings: string[]) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return warnings.filter((w) => {
    const m = w.match(/El (\d{2})\/(\d{2})\/(\d{4})/);
    if (!m) return true;
    const day = new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]));
    return day >= today;
  });
}

function labelList(values: string[]) {
  if (!values.length || values.includes("TODAS")) return "Todas";
  return values.join(", ");
}

export function ExportPage() {
  const { filters } = useApp();
  const [result, setResult] = useState<{
    errors: string[];
    groups?: Group[];
    warnings: string[];
    warning_count: number;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [downloadError, setDownloadError] = useState("");
  const params = useMemo(
    () => ({
      year: filters.year,
      empresa: filters.empresas.includes("TODAS") ? undefined : filters.empresas,
      gerencia: filters.gerencias.includes("TODAS") ? undefined : filters.gerencias,
      division: filters.divisiones.includes("TODAS") ? undefined : filters.divisiones,
    }),
    [filters]
  );

  useEffect(() => {
    api<{ errors: string[]; groups?: Group[]; warnings: string[]; warning_count: number }>(
      `/api/plan/validate${qs(params)}`
    ).then(setResult);
  }, [params]);

  async function download() {
    setBusy(true);
    setDownloadError("");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 60_000);
    try {
      const res = await fetch(`${API}/api/export${qs({ ...params, label: "PLAN" })}`, {
        headers: authHeader(),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error("No se pudo generar el Excel. Inténtalo de nuevo.");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `VACACIONES_${filters.year}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      const msg =
        e instanceof DOMException && e.name === "AbortError"
          ? "Generar el Excel tardó demasiado. Inténtalo de nuevo."
          : e instanceof Error
            ? e.message
            : "No se pudo generar el Excel. Inténtalo de nuevo.";
      setDownloadError(msg);
    } finally {
      clearTimeout(timer);
      setBusy(false);
    }
  }

  const groups = result ? usableGroups(result, filters.year) : [];
  const coverage = result ? futureCoverage(result.warnings || []) : [];
  const total = groups.reduce((n, g) => n + g.count, 0);
  const generatedAt = new Date().toLocaleString("es-PE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Exportar y validar"
        help="Descarga el plan en Excel. Si hay avisos, igual puedes bajar el archivo."
      />

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="order-2 overflow-hidden rounded-xl border border-border bg-card shadow-[var(--shadow-card)] lg:order-1">
          {SHEETS.map(([name, desc], i) => (
            <div key={name} className={`flex items-center gap-3 px-4 py-3 ${i < SHEETS.length - 1 ? "border-b border-border" : ""}`}>
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-[var(--primary-soft)] text-primary">
                <Icon name="file-spreadsheet" />
              </div>
              <div>
                <p className="text-xs font-semibold">{name}</p>
                <p className="text-xs text-muted-foreground">{desc}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="order-1 space-y-4 lg:order-2">
          {result ? (
            total === 0 ? (
              <Alert tone="success" title="El plan está en orden">
                Puedes descargar el Excel. No hay nada que debas corregir.
              </Alert>
            ) : (
              <Alert tone="warning" title={total === 1 ? "Hay 1 aviso en el plan" : `Hay ${total} avisos en el plan`}>
                Revisa estas semanas actuales o futuras. No impiden descargar.
              </Alert>
            )
          ) : (
            <p className="text-sm text-muted-foreground">Revisando el plan…</p>
          )}

          <div className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)]">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Resumen del filtro</p>
            <dl className="mt-3 space-y-2 text-[13px]">
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">Año</dt>
                <dd className="font-medium">{filters.year}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">Empresa</dt>
                <dd className="max-w-[60%] truncate text-right font-medium">{labelList(filters.empresas)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">Gerencia</dt>
                <dd className="max-w-[60%] truncate text-right font-medium">{labelList(filters.gerencias)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">División</dt>
                <dd className="max-w-[60%] truncate text-right font-medium">{labelList(filters.divisiones)}</dd>
              </div>
              <div className="flex justify-between gap-3 border-t border-border pt-2">
                <dt className="text-muted-foreground">Generado</dt>
                <dd className="font-data text-[12px]">{generatedAt}</dd>
              </div>
            </dl>
            <Button className="mt-4 w-full" disabled={busy} onClick={download}>
              <Icon name={busy ? "loader" : "download"} className={busy ? "animate-spin" : undefined} />
              {busy ? "Preparando el archivo…" : "Descargar Excel"}
            </Button>
            {downloadError ? (
              <Alert className="mt-3" tone="error" title="No se pudo descargar">
                {downloadError}
              </Alert>
            ) : null}
          </div>
        </div>
      </div>

      {result && total > 0 ? (
        <div className="space-y-3">
          {groups.map((g) => (
            <div key={g.code} className="rounded-[10px] border border-warning bg-warning-muted px-3.5 py-3.5">
              <p className="text-[13px] font-semibold text-foreground">
                {g.title} · {g.count}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">{g.hint}</p>
              <ul className="mt-2 max-h-40 list-disc space-y-0.5 overflow-auto pl-4 text-xs text-foreground">
                {g.samples.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : null}

      {coverage.length > 0 ? (
        <Alert
          tone="warning"
          title={
            coverage.length === 1
              ? "Un día con mucha gente de vacaciones"
              : `${coverage.length} días con mucha gente de vacaciones`
          }
        >
          <ul className="mt-1 max-h-32 list-disc space-y-0.5 overflow-auto pl-4">
            {coverage.slice(0, 12).map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Alert>
      ) : null}
    </div>
  );
}

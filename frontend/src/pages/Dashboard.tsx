import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  ArrowRight,
  CalendarDays,
  Clock3,
  Percent,
  Target,
  UserCheck,
  Users,
  UserX,
} from "lucide-react";
import { api, qs } from "../api";
import { useApp } from "../state";
import { Kpi, PageHeader, cn } from "../components/ui";

type Dash = {
  total_people: number;
  programados: number;
  pendientes: number;
  dias_totales: number;
  personas_hoy: number;
  cobertura_prom: number;
  agg_gerencia: Record<string, number>;
  agg_area: Record<string, number>;
  agg_tipo: Record<string, number>;
  heatmap: number[][];
  weekly_unique_absent: number[];
  week_risk: { semana: number; periodo: string; max_ausentes_dia: number; max_ausencia_pct: number }[];
  proximas_criticas: { periodo: string; max_ausentes_dia: number; max_ausencia_pct: number }[];
  current_week: number | null;
};

const TIPO_COLORS = ["var(--primary)", "var(--info)", "var(--success)", "var(--warning)"];
const AREA_COLORS = ["#1a56db", "#1d5fb8", "#047857", "#d97706", "#dc2626", "#5b6b7c"];
const DIAS = ["L", "M", "X", "J", "V", "S", "D"] as const;

function heatFill(v: number, maxH: number) {
  if (v === 0) return "var(--muted)";
  const t = v / maxH;
  if (t <= 0.25) return "#C8E6C9";
  if (t <= 0.45) return "#FFF9C4";
  if (t <= 0.7) return "#FFCC80";
  return "#EF9A9A";
}

function pctLabel(n: number, total: number) {
  if (!total) return "0%";
  return `${Math.round((n / total) * 100)}%`;
}

function Panel({
  title,
  children,
  className,
  bodyClassName,
}: {
  title?: string;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("rounded-xl border border-border bg-card shadow-[var(--shadow-card)]", className)}>
      {title ? (
        <h3 className="border-b border-border px-4 py-3 text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
          {title}
        </h3>
      ) : null}
      <div className={cn("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

function CoberturaGauge({ pct }: { pct: number }) {
  const value = Math.max(0, Math.min(100, Math.round(pct * 100)));
  const data = [
    { name: "ok", value },
    { name: "rest", value: 100 - value },
  ];
  const tone = value >= 85 ? "var(--success)" : value >= 70 ? "var(--warning)" : "var(--error)";
  return (
    <div className="relative mx-auto h-[180px] w-full max-w-[240px]">
      <ResponsiveContainer>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            startAngle={180}
            endAngle={0}
            innerRadius={58}
            outerRadius={78}
            paddingAngle={0}
            stroke="none"
          >
            <Cell fill={tone} />
            <Cell fill="var(--muted)" />
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-x-0 bottom-6 text-center">
        <div className="font-data text-[28px] font-semibold leading-none" style={{ color: tone }}>
          {value}%
        </div>
        <div className="mt-1 text-[11px] text-muted-foreground">Presencia promedio</div>
      </div>
    </div>
  );
}

export function DashboardPage() {
  const { filters } = useApp();
  const [data, setData] = useState<Dash | null>(null);
  const params = useMemo(
    () => ({
      year: filters.year,
      empresa: filters.empresas.includes("TODAS") ? undefined : filters.empresas,
      gerencia: filters.gerencias.includes("TODAS") ? undefined : filters.gerencias,
      area: filters.areas.includes("TODAS") ? undefined : filters.areas,
    }),
    [filters]
  );

  useEffect(() => {
    api<Dash>(`/api/dashboard${qs(params)}`).then(setData);
  }, [params]);

  if (!data) return <p className="text-sm text-muted-foreground">Cargando el dashboard…</p>;

  const totalDias = Math.max(1, data.dias_totales);
  const totalPeople = Math.max(1, data.total_people);
  const progPct = Math.round((data.programados / totalPeople) * 100);
  const coberturaPct = Math.round(data.cobertura_prom * 100);
  const critica = data.proximas_criticas[0];
  const criticaAlta = (critica?.max_ausencia_pct ?? 0) >= 0.25;

  const ger = Object.entries(data.agg_gerencia)
    .map(([name, value]) => ({
      name,
      short: name.length > 22 ? `${name.slice(0, 20)}…` : name,
      value,
      pct: Math.round((value / totalDias) * 100),
      label: `${Math.round((value / totalDias) * 100)}%`,
    }))
    .sort((a, b) => b.value - a.value);

  const areas = Object.entries(data.agg_area || {})
    .map(([name, value]) => ({
      name,
      short: name.length > 20 ? `${name.slice(0, 18)}…` : name,
      value,
      pct: Math.round((value / totalDias) * 100),
      label: `${Math.round((value / totalDias) * 100)}%`,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8);

  const tipo = Object.entries(data.agg_tipo).map(([name, value]) => ({
    name,
    value,
    pct: Math.round((value / totalDias) * 100),
  }));
  const tipoTotal = Math.max(1, tipo.reduce((s, r) => s + r.value, 0));

  const trend = data.weekly_unique_absent.map((v, i) => ({
    semana: i + 1,
    label: `S${i + 1}`,
    personas: v,
    pct: Math.round((v / totalPeople) * 100),
  }));

  const maxH = Math.max(1, ...data.heatmap.flat());
  const heatCols = Math.min(12, data.heatmap[0]?.length || 0);
  const heatStart = data.current_week
    ? Math.max(0, Math.min((data.heatmap[0]?.length || 1) - heatCols, data.current_week - 5))
    : 0;
  const heatWeeks = Array.from({ length: heatCols }, (_, i) => heatStart + i + 1);

  const topRisk = data.week_risk.slice(0, 8);
  const recomendaciones = [
    data.pendientes > 0
      ? {
          icon: Target,
          title: "Cerrar pendientes",
          body: `${data.pendientes} personas aún sin días programados en ${filters.year}.`,
        }
      : null,
    critica
      ? {
          icon: AlertTriangle,
          title: "Revisar pico de ausencias",
          body: `${critica.periodo}: hasta ${critica.max_ausentes_dia} personas el mismo día (${Math.round(critica.max_ausencia_pct * 100)}%).`,
        }
      : null,
    coberturaPct < 85
      ? {
          icon: Percent,
          title: "Mejorar cobertura",
          body: `La presencia promedio está en ${coberturaPct}%. Redistribuye semanas críticas.`,
        }
      : null,
    areas[0]
      ? {
          icon: Clock3,
          title: "Área con más días",
          body: `${areas[0].name} concentra ${areas[0].value} días (${areas[0].pct}% del plan).`,
        }
      : null,
  ].filter(Boolean) as { icon: typeof Target; title: string; body: string }[];

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <PageHeader
          title="Gestión de vacaciones"
          help={`Cobertura, avance del plan y semanas críticas · ${filters.year}`}
        />
        <div className="flex flex-wrap gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 py-1.5 text-[11px] font-semibold text-muted-foreground shadow-[var(--shadow-card)]">
            <CalendarDays size={14} strokeWidth={1.75} />
            Año {filters.year}
            {data.current_week ? ` · S${data.current_week}` : ""}
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 py-1.5 text-[11px] font-semibold text-muted-foreground shadow-[var(--shadow-card)]">
            <Users size={14} strokeWidth={1.75} />
            {data.total_people} colaboradores
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        <Kpi label="Plantilla" value={data.total_people} hint="Filtro actual" icon={<Users size={18} strokeWidth={1.75} />} accent="info" />
        <Kpi
          label="Programados"
          value={data.programados}
          hint={`${progPct}% del filtro`}
          icon={<UserCheck size={18} strokeWidth={1.75} />}
          accent="success"
        />
        <Kpi
          label="Sin programar"
          value={data.pendientes}
          hint="Aún sin días"
          icon={<UserX size={18} strokeWidth={1.75} />}
          accent={data.pendientes > 0 ? "error" : "success"}
        />
        <Kpi
          label="Días plan"
          value={data.dias_totales}
          hint="Suma de vacaciones"
          icon={<CalendarDays size={18} strokeWidth={1.75} />}
          accent="primary"
        />
        <Kpi
          label="Cobertura"
          value={`${coberturaPct}%`}
          hint="Promedio presente"
          icon={<Percent size={18} strokeWidth={1.75} />}
          accent={coberturaPct >= 85 ? "success" : coberturaPct >= 70 ? "warning" : "error"}
        />
        <Kpi
          label="Hoy"
          value={data.personas_hoy}
          hint="De vacaciones hoy"
          icon={<Clock3 size={18} strokeWidth={1.75} />}
          accent="warning"
        />
      </div>

      {critica && critica.max_ausentes_dia > 0 ? (
        <div
          className={cn(
            "flex flex-col gap-2 rounded-xl border px-4 py-3 sm:flex-row sm:items-center sm:justify-between",
            criticaAlta ? "border-error bg-error-muted" : "border-warning bg-warning-muted"
          )}
        >
          <div className="flex min-w-0 items-start gap-3">
            <AlertTriangle
              className={cn("mt-0.5 h-[18px] w-[18px] shrink-0", criticaAlta ? "text-error" : "text-warning")}
              strokeWidth={1.75}
            />
            <div className="min-w-0">
              <p className="text-[13px] font-semibold text-foreground">
                Atención: próximas semanas con mayor concentración de vacaciones
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {data.proximas_criticas
                  .map((c) => `${c.periodo}: hasta ${c.max_ausentes_dia} personas (${Math.round(c.max_ausencia_pct * 100)}%)`)
                  .join(" · ")}
              </p>
            </div>
          </div>
          <Link
            to="/"
            className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-[10px] bg-card px-3 py-2 text-[12px] font-semibold text-foreground border border-border hover:bg-muted"
          >
            Ir a planificación
            <ArrowRight size={14} strokeWidth={1.75} />
          </Link>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-4">
        <Panel title="Días por tipo de personal">
          <div className="flex h-[200px] items-center gap-3">
            <div className="h-full min-w-0 flex-1">
              <ResponsiveContainer>
                <PieChart>
                  <Pie
                    data={tipo}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={48}
                    outerRadius={70}
                    paddingAngle={tipo.length > 1 ? 2 : 0}
                  >
                    {tipo.map((_, i) => (
                      <Cell key={i} fill={TIPO_COLORS[i % TIPO_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value: number) => [`${value} días (${pctLabel(value, tipoTotal)})`, "Días"]} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <ul className="w-[118px] shrink-0 space-y-2">
              {tipo.map((row, i) => (
                <li key={row.name} className="text-[11px]">
                  <span className="mb-0.5 flex items-center gap-1.5 font-medium">
                    <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: TIPO_COLORS[i % TIPO_COLORS.length] }} />
                    <span className="truncate">{row.name}</span>
                  </span>
                  <span className="pl-3.5 tabular-nums text-muted-foreground">
                    {row.value} · {pctLabel(row.value, tipoTotal)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </Panel>

        <Panel title="Nivel de cobertura">
          <CoberturaGauge pct={data.cobertura_prom} />
        </Panel>

        <Panel title="Días por gerencia">
          <div style={{ height: Math.max(180, Math.min(220, ger.slice(0, 6).length * 32)) }}>
            <ResponsiveContainer>
              <BarChart data={ger.slice(0, 6)} layout="vertical" margin={{ top: 0, left: 0, right: 36, bottom: 0 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="short" width={108} tick={{ fontSize: 10, fill: "var(--foreground)" }} interval={0} />
                <Tooltip
                  formatter={(value: number, _n, item: { payload?: { pct?: number; name?: string } }) => [
                    `${value} días (${item.payload?.pct ?? 0}%)`,
                    item.payload?.name || "Días",
                  ]}
                />
                <Bar dataKey="value" fill="var(--primary)" radius={[0, 4, 4, 0]} barSize={14}>
                  <LabelList dataKey="label" position="right" style={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="% plantilla de vacaciones / semana">
          <div className="h-[200px]">
            <ResponsiveContainer>
              <LineChart data={trend} margin={{ top: 12, right: 8, left: -12, bottom: 0 }}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} interval={4} />
                <YAxis tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} unit="%" width={36} />
                <Tooltip
                  formatter={(value: number, name: string, item: { payload?: { personas?: number } }) => {
                    if (name === "pct") return [`${value}% (${item.payload?.personas ?? 0} pers.)`, "% plantilla"];
                    return [value, name];
                  }}
                  labelFormatter={(label) => `Semana ${String(label).replace("S", "")}`}
                />
                <Line type="monotone" dataKey="pct" stroke="var(--error)" strokeWidth={2.25} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <Panel title="Personas de vacaciones por día">
        <div className="overflow-x-auto">
          <div className="inline-block">
            <div className="mb-1 flex items-center gap-1">
              <div className="w-5 shrink-0" />
              {heatWeeks.map((wk) => (
                <div
                  key={wk}
                  className={`w-8 text-center text-[10px] font-semibold ${
                    wk === data.current_week ? "text-primary" : "text-muted-foreground"
                  }`}
                  title={`Semana ${wk}`}
                >
                  S{wk}
                </div>
              ))}
            </div>
            {DIAS.map((lab, r) => (
              <div key={lab} className="mb-1 flex items-center gap-1">
                <div className="flex w-5 shrink-0 items-center justify-center text-[11px] font-medium text-muted-foreground">
                  {lab}
                </div>
                {(data.heatmap[r] || []).slice(heatStart, heatStart + heatCols).map((v, c) => {
                  const wk = heatStart + c + 1;
                  return (
                    <div
                      key={`${wk}-${lab}`}
                      title={`S${wk} · ${lab}: ${v} personas (${pctLabel(v, data.total_people)})`}
                      className="flex h-6 w-8 items-center justify-center rounded-md text-[10px] font-semibold tabular-nums text-foreground/90"
                      style={{ background: heatFill(v, maxH) }}
                    >
                      {v > 0 ? v : ""}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Panel title="Ranking por área (días)">
          <div style={{ height: Math.max(220, Math.min(320, areas.length * 34)) }}>
            {areas.length === 0 ? (
              <p className="text-sm text-muted-foreground">Sin días programados en el filtro.</p>
            ) : (
              <ResponsiveContainer>
                <BarChart data={areas} layout="vertical" margin={{ top: 0, left: 0, right: 36, bottom: 0 }}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="short" width={120} tick={{ fontSize: 10, fill: "var(--foreground)" }} interval={0} />
                  <Tooltip
                    formatter={(value: number, _n, item: { payload?: { pct?: number; name?: string } }) => [
                      `${value} días (${item.payload?.pct ?? 0}%)`,
                      item.payload?.name || "Días",
                    ]}
                  />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={14}>
                    {areas.map((_, i) => (
                      <Cell key={i} fill={AREA_COLORS[i % AREA_COLORS.length]} />
                    ))}
                    <LabelList dataKey="label" position="right" style={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Panel>

        <Panel title="Semanas con mayor riesgo" bodyClassName="p-0 overflow-x-auto">
          <table className="w-full min-w-[360px] text-sm">
            <thead className="bg-muted text-left">
              <tr>
                {["#", "Semana", "Periodo", "Máx. día", "%"].map((h) => (
                  <th key={h} className="px-3 py-2 text-[11px] font-semibold text-muted-foreground">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {topRisk.map((r, i) => {
                const pct = Math.round(r.max_ausencia_pct * 100);
                return (
                  <tr key={r.semana} className="border-t border-border">
                    <td className="px-3 py-2 tabular-nums text-muted-foreground">{i + 1}</td>
                    <td className="px-3 py-2 font-medium">S{r.semana}</td>
                    <td className="px-3 py-2 text-[12px]">{r.periodo}</td>
                    <td className="px-3 py-2">{r.max_ausentes_dia}</td>
                    <td
                      className={cn(
                        "px-3 py-2 font-semibold tabular-nums",
                        pct >= 25 ? "text-error" : pct >= 15 ? "text-warning" : "text-foreground"
                      )}
                    >
                      {pct}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Panel>

        <Panel title="Recomendaciones">
          {recomendaciones.length === 0 ? (
            <p className="text-sm text-muted-foreground">El plan se ve equilibrado con el filtro actual.</p>
          ) : (
            <ul className="space-y-3">
              {recomendaciones.map((r) => (
                <li key={r.title} className="flex gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--primary-soft)] text-primary">
                    <r.icon size={15} strokeWidth={1.75} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[13px] font-semibold">{r.title}</p>
                    <p className="mt-0.5 text-[12px] text-muted-foreground">{r.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-border bg-[#0f1c2e] px-4 py-4 text-white sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-[13px] font-semibold tracking-wide">Impacto del plan</p>
          <p className="mt-1 text-[12px] text-white/70">
            {data.programados}/{data.total_people} con vacaciones · {data.dias_totales} días · cobertura {coberturaPct}%
            {critica ? ` · pico próximo: ${critica.max_ausentes_dia} pers.` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 rounded-[10px] bg-white px-3.5 py-2 text-[12px] font-semibold text-[#0f1c2e] hover:bg-white/90"
          >
            Ajustar plan
            <ArrowRight size={14} strokeWidth={1.75} />
          </Link>
          <Link
            to="/exportar"
            className="inline-flex items-center gap-1.5 rounded-[10px] border border-white/25 px-3.5 py-2 text-[12px] font-semibold text-white hover:bg-white/10"
          >
            Exportar Excel
          </Link>
        </div>
      </div>
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Pie,
  PieChart,
  Cell,
} from "recharts";
import { api, qs } from "../api";
import { useApp } from "../state";
import { Alert, Kpi, PageHeader } from "../components/ui";
import { CalendarDays, Percent, UserCheck, Users, UserX } from "lucide-react";

type Dash = {
  total_people: number;
  programados: number;
  pendientes: number;
  dias_totales: number;
  personas_hoy: number;
  cobertura_prom: number;
  agg_gerencia: Record<string, number>;
  agg_tipo: Record<string, number>;
  heatmap: number[][];
  weekly_unique_absent: number[];
  week_risk: { semana: number; periodo: string; max_ausentes_dia: number; max_ausencia_pct: number }[];
  proximas_criticas: { periodo: string; max_ausentes_dia: number; max_ausencia_pct: number }[];
  current_week: number | null;
  aptos?: number;
};

const TIPO_COLORS = ["var(--primary)", "var(--muted-foreground)", "var(--border)", "var(--success)"];
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
  const totalPeople = Math.max(1, data.aptos ?? data.total_people);

  const ger = Object.entries(data.agg_gerencia)
    .map(([name, value]) => ({
      name,
      short: name.length > 28 ? `${name.slice(0, 26)}…` : name,
      value,
      pct: Math.round((value / totalDias) * 100),
      label: `${Math.round((value / totalDias) * 100)}%`,
    }))
    .sort((a, b) => b.value - a.value);

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

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        help={`Plantilla completa · programados y cobertura solo de aptos · ${filters.year}.`}
      />

      {data.proximas_criticas[0]?.max_ausentes_dia > 0 ? (
        <Alert tone="warning" title="Próximas semanas con más gente de vacaciones">
          {data.proximas_criticas.map((c) => `${c.periodo}: hasta ${c.max_ausentes_dia} personas el mismo día`).join(". ")}
        </Alert>
      ) : null}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Kpi label="Trabajadores" value={data.total_people} hint="Personas en este filtro" icon={<Users size={18} strokeWidth={1.75} />} />
        <Kpi label="Programados" value={data.programados} hint={`Aptos con vacaciones en ${filters.year}`} icon={<UserCheck size={18} strokeWidth={1.75} />} />
        <Kpi label="Sin programar" value={data.pendientes} hint="Aptos aún sin días" icon={<UserX size={18} strokeWidth={1.75} />} />
        <Kpi label="Días" value={data.dias_totales} hint="Suma de aptos" icon={<CalendarDays size={18} strokeWidth={1.75} />} />
        <Kpi
          label="Cobertura %"
          value={`${Math.round(data.cobertura_prom * 100)}%`}
          hint="Promedio de aptos presentes"
          icon={<Percent size={18} strokeWidth={1.75} />}
          className="col-span-2 md:col-span-1"
        />
      </div>

      <section className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)]">
        <h3 className="mb-3 text-[13px] font-semibold">Personas de vacaciones por día</h3>
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
                      title={`S${wk} · ${lab}: ${v} personas (${pctLabel(v, data.aptos ?? data.total_people)})`}
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
      </section>

      <section className="h-72 rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)]">
        <h3 className="mb-3 text-[13px] font-semibold">Personas con vacaciones por semana</h3>
        <ResponsiveContainer>
          <LineChart data={trend} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} interval={3} />
            <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} allowDecimals={false} />
            <Tooltip
              formatter={(value: number, name: string, item: { payload?: { pct?: number } }) => {
                if (name === "personas") return [`${value} (${item.payload?.pct ?? 0}%)`, "Personas"];
                return [value, name];
              }}
              labelFormatter={(label) => `Semana ${String(label).replace("S", "")}`}
            />
            <Line type="monotone" dataKey="personas" stroke="var(--primary)" strokeWidth={2.5} dot={false}>
              <LabelList
                dataKey="pct"
                position="top"
                content={(props: { x?: string | number; y?: string | number; value?: string | number; index?: number }) => {
                  const { x, y, value, index } = props;
                  if (x == null || y == null || value == null || Number(value) <= 0) return null;
                  if ((index ?? 0) % 5 !== 0) return null;
                  return (
                    <text x={Number(x)} y={Number(y) - 6} textAnchor="middle" fontSize={9} fill="var(--muted-foreground)">
                      {value}%
                    </text>
                  );
                }}
              />
            </Line>
          </LineChart>
        </ResponsiveContainer>
      </section>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <section className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)]">
          <h3 className="mb-3 text-[13px] font-semibold">Días por gerencia</h3>
          <div style={{ height: Math.max(240, Math.min(420, ger.length * 36)) }}>
            <ResponsiveContainer>
              <BarChart data={ger} layout="vertical" margin={{ top: 4, left: 4, right: 40, bottom: 4 }}>
                <CartesianGrid stroke="var(--border)" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                <YAxis
                  type="category"
                  dataKey="short"
                  tick={{ fontSize: 11, fill: "var(--foreground)" }}
                  width={150}
                  interval={0}
                />
                <Tooltip
                  formatter={(value: number, _n, item: { payload?: { pct?: number; name?: string } }) => [
                    `${value} días (${item.payload?.pct ?? 0}%)`,
                    item.payload?.name || "Días",
                  ]}
                />
                <Bar dataKey="value" fill="var(--primary)" radius={[0, 4, 4, 0]} barSize={18}>
                  <LabelList dataKey="label" position="right" style={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)]">
          <h3 className="mb-3 text-[13px] font-semibold">Tipo de personal</h3>
          <div className="flex h-[280px] flex-col items-stretch gap-3 sm:flex-row sm:items-center">
            <div className="h-[200px] min-w-0 flex-1 sm:h-full">
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={tipo} dataKey="value" nameKey="name" innerRadius={48} outerRadius={72} paddingAngle={tipo.length > 1 ? 2 : 0}>
                    {tipo.map((_, i) => (
                      <Cell key={i} fill={TIPO_COLORS[i % TIPO_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value: number) => [`${value} días (${pctLabel(value, tipoTotal)})`, "Días"]} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <ul className="shrink-0 space-y-2 sm:w-44">
              {tipo.map((row, i) => (
                <li key={row.name} className="flex items-center justify-between gap-2 text-[12px]">
                  <span className="flex min-w-0 items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-sm"
                      style={{ background: TIPO_COLORS[i % TIPO_COLORS.length] }}
                    />
                    <span className="truncate font-medium">{row.name}</span>
                  </span>
                  <span className="shrink-0 tabular-nums text-muted-foreground">
                    {row.value} · {pctLabel(row.value, tipoTotal)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </div>

      <section className="overflow-x-auto rounded-[4px] border border-border bg-card shadow-[var(--shadow-card)]">
        <table className="w-full min-w-[480px] text-sm">
          <thead className="bg-muted text-left">
            <tr>
              {["Semana", "Periodo", "Máximo en un solo día", "% de la plantilla"].map((h) => (
                <th key={h} className="px-3 py-2 text-[11px] font-semibold text-muted-foreground">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.week_risk.slice(0, 10).map((r) => (
              <tr key={r.semana} className="border-t border-border">
                <td className="px-3 py-2">S{r.semana}</td>
                <td className="px-3 py-2">{r.periodo}</td>
                <td className="px-3 py-2">{r.max_ausentes_dia} personas</td>
                <td className="px-3 py-2 font-medium">{Math.round(r.max_ausencia_pct * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

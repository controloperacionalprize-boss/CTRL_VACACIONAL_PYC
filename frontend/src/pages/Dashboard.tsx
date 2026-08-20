import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
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
};

const TIPO_COLORS = ["var(--primary)", "var(--muted-foreground)", "var(--border)", "var(--success)"];

function heatFill(v: number, maxH: number) {
  if (v === 0) return "var(--muted)";
  const t = v / maxH;
  if (t <= 0.25) return "#C8E6C9";
  if (t <= 0.45) return "#FFF9C4";
  if (t <= 0.7) return "#FFCC80";
  return "#EF9A9A";
}

export function DashboardPage() {
  const { filters } = useApp();
  const [data, setData] = useState<Dash | null>(null);
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
    api<Dash>(`/api/dashboard${qs(params)}`).then(setData);
  }, [params]);

  if (!data) return <p className="text-sm text-muted-foreground">Cargando el dashboard…</p>;

  const ger = Object.entries(data.agg_gerencia).map(([name, value]) => ({ name, value }));
  const tipo = Object.entries(data.agg_tipo).map(([name, value]) => ({ name, value }));
  const trend = data.weekly_unique_absent.map((v, i) => ({ semana: i + 1, personas: v }));
  const maxH = Math.max(1, ...data.heatmap.flat());
  const heatCols = Math.min(12, data.heatmap[0]?.length || 0);
  const heatStart = data.current_week ? Math.max(0, Math.min((data.heatmap[0]?.length || 1) - heatCols, data.current_week - 5)) : 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        help={`Personas de vacaciones y semanas con más ausencias en ${filters.year}.`}
      />

      {data.proximas_criticas[0]?.max_ausentes_dia > 0 ? (
        <Alert tone="warning" title="Próximas semanas con más gente de vacaciones">
          {data.proximas_criticas.map((c) => `${c.periodo}: hasta ${c.max_ausentes_dia} personas el mismo día`).join(". ")}
        </Alert>
      ) : null}

      <div className="grid grid-cols-5 gap-3">
        <Kpi label="Trabajadores" value={data.total_people} hint="Personas en este filtro" icon={<Users size={18} strokeWidth={1.75} />} />
        <Kpi label="Programados" value={data.programados} hint={`Ya tienen vacaciones en ${filters.year}`} icon={<UserCheck size={18} strokeWidth={1.75} />} />
        <Kpi label="Sin programar" value={data.pendientes} hint="Aún sin días" icon={<UserX size={18} strokeWidth={1.75} />} />
        <Kpi label="Días" value={data.dias_totales} hint="Suma de vacaciones" icon={<CalendarDays size={18} strokeWidth={1.75} />} />
        <Kpi label="Cobertura %" value={`${Math.round(data.cobertura_prom * 100)}%`} hint="Promedio de gente presente" icon={<Percent size={18} strokeWidth={1.75} />} />
      </div>

      <section className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)]">
        <h3 className="mb-3 text-[13px] font-semibold">Cuántas personas faltan cada día (lunes a domingo, 12 semanas)</h3>
        <div className="overflow-auto">
          <div className="inline-block">
            {["L", "M", "X", "J", "V", "S", "D"].map((lab, r) => (
              <div key={r} className="mb-0.5 flex items-center gap-0.5">
                <div className="w-4 text-center text-[10px] text-muted-foreground">{lab}</div>
                {(data.heatmap[r] || []).slice(heatStart, heatStart + heatCols).map((v, c) => (
                  <div
                    key={c}
                    title={`Semana ${heatStart + c + 1}, ${lab}: ${v} persona(s)`}
                    className="h-3.5 w-[18px] rounded-sm"
                    style={{ background: heatFill(v, maxH) }}
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="h-72 rounded-xl border border-border bg-card p-4">
        <h3 className="mb-3 text-[13px] font-semibold">Personas con vacaciones por semana</h3>
        <ResponsiveContainer>
          <LineChart data={trend}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="semana" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} interval={3} />
            <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} allowDecimals={false} />
            <Tooltip />
            <Line type="monotone" dataKey="personas" stroke="var(--primary)" strokeWidth={2.5} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </section>

      <div className="grid grid-cols-2 gap-4">
        <section className="h-80 rounded-xl border border-border bg-card p-4">
          <h3 className="mb-3 text-[13px] font-semibold">Días por gerencia</h3>
          <ResponsiveContainer>
            <BarChart data={ger} layout="vertical" margin={{ left: 80 }}>
              <CartesianGrid stroke="var(--border)" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: "var(--foreground)" }} width={80} />
              <Tooltip />
              <Bar dataKey="value" fill="var(--primary)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </section>
        <section className="h-80 rounded-xl border border-border bg-card p-4">
          <h3 className="mb-3 text-[13px] font-semibold">Tipo de personal</h3>
          <ResponsiveContainer>
            <PieChart>
              <Pie data={tipo} dataKey="value" nameKey="name" innerRadius={60} outerRadius={90}>
                {tipo.map((_, i) => (
                  <Cell key={i} fill={TIPO_COLORS[i % TIPO_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </section>
      </div>

      <section className="overflow-hidden rounded-[4px] border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="bg-muted text-left">
            <tr>
              {["Semana", "Periodo", "Más personas el mismo día", "% del equipo"].map((h) => (
                <th key={h} className="px-3 py-2 text-[11px] font-semibold text-muted-foreground">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.week_risk.slice(0, 10).map((r) => (
              <tr key={r.semana} className="border-t border-border">
                <td className="px-3 py-2">{r.semana}</td>
                <td className="px-3 py-2">{r.periodo}</td>
                <td className="px-3 py-2">{r.max_ausentes_dia}</td>
                <td className="px-3 py-2">{Math.round(r.max_ausencia_pct * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

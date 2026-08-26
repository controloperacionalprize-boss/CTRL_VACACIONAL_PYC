import { useEffect, useMemo, useState, type ReactNode } from "react";
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
  CalendarDays,
  CircleHelp,
  Clock3,
  DoorOpen,
  Percent,
  Timer,
  Users,
} from "lucide-react";
import { api, qs } from "../api";
import { useApp } from "../state";
import { Kpi, cn, Select, Field } from "../components/ui";
import { formatFechaIso } from "../lib/dates";

type Dist = { key: string; label: string; value: number; pct: number };
type AreaRow = { name: string; short: string; evaluados: number; incumplen: number; pct: number; label: string };
type PersonRow = { nombre: string; area: string; incidentes: number; minutos: number; horas_txt: string };
type TipoRow = { name: string; n: number; cumple: number; incumple: number; cumple_pct: number; incumple_pct: number };

type Asist = {
  configured: boolean;
  times_ok: boolean;
  periodo: { desde: string; hasta: string };
  horario: {
    entrada: string;
    salida: string;
    margen_entrada: string;
    jornada_minutos: number;
    trujillo?: { entrada: string; margen_entrada: string; salida: string };
  };
  total_people: number;
  evaluados: number;
  incumplimiento_pct: number;
  personas_incumplen: number;
  detalle_incumplimiento?: {
    jornadas_con_2_marcas: number;
    jornadas_fuera: number;
  };
  horas_no_laboradas_txt: string;
  dias_equivalentes: number;
  llegadas_tarde: { casos: number; promedio_min: number };
  salidas_temprano: { casos: number; promedio_min: number };
  no_marcan: {
    casos: number;
    personas?: number;
    por_dia?: { fecha: string; dia: string; casos: number }[];
  };
  cumplimiento_jornada_pct: number;
  distribucion: Dist[];
  horas_por_categoria: { key: string; label: string; minutos: number; txt: string }[];
  tendencia_semana: { dia: number; label: string; pct: number; casos: number; n: number }[];
  ranking_area: AreaRow[];
  ranking_personas: PersonRow[];
  por_tipo: TipoRow[];
};

const DIST_COLORS: Record<string, string> = {
  tardanza: "#d97706",
  salida_temprano: "#047857",
  no_marcan: "#1d5fb8",
  jornada: "#dc2626",
};
const AREA_COLORS = ["#1a56db", "#1d5fb8", "#047857", "#d97706", "#dc2626", "#5b6b7c"];
const MESES = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];

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
        <h3 className="border-b border-border px-4 py-3.5 text-[13px] font-semibold uppercase tracking-wide text-muted-foreground">
          {title}
        </h3>
      ) : null}
      <div className={cn("p-5", bodyClassName)}>{children}</div>
    </section>
  );
}

function JornadaGauge({ pct }: { pct: number }) {
  const value = Math.max(0, Math.min(100, roundPct(pct)));
  const data = [
    { name: "ok", value },
    { name: "rest", value: 100 - value },
  ];
  const tone = value >= 85 ? "var(--success)" : value >= 70 ? "var(--warning)" : "var(--error)";
  return (
    <div className="relative mx-auto h-[260px] w-full max-w-[320px]">
      <ResponsiveContainer>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            startAngle={180}
            endAngle={0}
            innerRadius={72}
            outerRadius={98}
            paddingAngle={0}
            stroke="none"
          >
            <Cell fill={tone} />
            <Cell fill="var(--muted)" />
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-x-0 bottom-8 text-center">
        <div className="font-data text-[36px] font-semibold leading-none" style={{ color: tone }}>
          {value}%
        </div>
      </div>
    </div>
  );
}

function roundPct(pct: number) {
  return Math.round(pct);
}

function diaCorto(iso: string, dia: string) {
  const parts = iso.split("-");
  return parts.length === 3 ? `${parts[2]}/${parts[1]}` : dia;
}

export function AsistenciaPage() {
  const { filters } = useApp();
  const now = new Date();
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState<Asist | null>(null);
  const [error, setError] = useState("");

  const params = useMemo(
    () => ({
      year: filters.year,
      month,
      empresa: filters.empresas.includes("TODAS") ? undefined : filters.empresas,
      gerencia: filters.gerencias.includes("TODAS") ? undefined : filters.gerencias,
      area: filters.areas.includes("TODAS") ? undefined : filters.areas,
    }),
    [filters, month]
  );

  useEffect(() => {
    setData(null);
    setError("");
    api<Asist>(`/api/asistencia${qs(params)}`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "No se pudo cargar asistencia."));
  }, [params]);

  if (error) return <p className="text-sm text-error">{error}</p>;
  if (!data) return <p className="text-sm text-muted-foreground">Cargando asistencia…</p>;

  const horasMax = Math.max(1, ...data.horas_por_categoria.map((r) => r.minutos));
  const noMarcanDia = (data.no_marcan.por_dia || []).map((row) => ({
    ...row,
    label: diaCorto(row.fecha, row.dia),
  }));

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <h2 className="text-[22px] font-semibold tracking-tight text-foreground">Asistencia</h2>
        <div className="flex flex-wrap items-end gap-2">
          <Field label="PERIODO">
            <Select value={month} onChange={(e) => setMonth(Number(e.target.value))} className="w-[140px]">
              {MESES.map((name, i) => (
                <option key={name} value={i + 1}>
                  {name}
                </option>
              ))}
            </Select>
          </Field>
          <span className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 text-[12px] font-semibold text-muted-foreground">
            <CalendarDays size={14} strokeWidth={1.75} />
            {formatFechaIso(data.periodo.desde)} – {formatFechaIso(data.periodo.hasta)}
          </span>
          <span className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 text-[12px] font-semibold text-muted-foreground">
            <Users size={14} strokeWidth={1.75} />
            {data.evaluados} vigentes
          </span>
        </div>
      </div>

      {!data.configured ? (
        <div className="rounded-xl border border-warning bg-warning-muted px-4 py-3 text-sm">Sin fuente de marcación.</div>
      ) : null}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <Kpi
          label="Incumplimiento"
          value={`${data.incumplimiento_pct}%`}
          hint={
            data.detalle_incumplimiento
              ? `${data.detalle_incumplimiento.jornadas_fuera} / ${data.detalle_incumplimiento.jornadas_con_2_marcas} jornadas`
              : undefined
          }
          icon={<AlertTriangle size={18} strokeWidth={1.75} />}
          accent={data.incumplimiento_pct >= 25 ? "error" : data.incumplimiento_pct > 0 ? "warning" : "success"}
        />
        <Kpi
          label="Horas no laboradas"
          value={data.horas_no_laboradas_txt}
          hint={`${data.dias_equivalentes} días eq.`}
          icon={<Timer size={18} strokeWidth={1.75} />}
          accent="warning"
        />
        <Kpi
          label="Llegadas tarde"
          value={data.llegadas_tarde.casos}
          hint={`Prom. ${data.llegadas_tarde.promedio_min} min`}
          icon={<Clock3 size={18} strokeWidth={1.75} />}
          accent="warning"
        />
        <Kpi
          label="Salidas temprano"
          value={data.salidas_temprano.casos}
          hint={`Prom. ${data.salidas_temprano.promedio_min} min`}
          icon={<DoorOpen size={18} strokeWidth={1.75} />}
          accent="info"
        />
        <Kpi
          label="No marcan"
          value={data.no_marcan.casos}
          hint={`${data.no_marcan.personas ?? 0} personas`}
          icon={<CircleHelp size={18} strokeWidth={1.75} />}
          accent="info"
        />
        <Kpi
          label="Cumplimiento"
          value={`${Math.round(data.cumplimiento_jornada_pct)}%`}
          hint={`Paiján ${data.horario.margen_entrada} · Trujillo ${data.horario.trujillo?.margen_entrada ?? "08:20"}`}
          icon={<Percent size={18} strokeWidth={1.75} />}
          accent={data.cumplimiento_jornada_pct >= 85 ? "success" : "warning"}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Distribución de incumplimientos">
          {data.distribucion.length === 0 ? (
            <p className="text-sm text-muted-foreground">Sin incumplimientos.</p>
          ) : (
            <div className="flex h-[280px] items-center gap-4">
              <div className="h-full min-w-0 flex-1">
                <ResponsiveContainer>
                  <PieChart>
                    <Pie data={data.distribucion} dataKey="value" nameKey="label" innerRadius={62} outerRadius={92} paddingAngle={2}>
                      {data.distribucion.map((row) => (
                        <Cell key={row.key} fill={DIST_COLORS[row.key] || "#5b6b7c"} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value: number) => [`${value} casos`, ""]} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <ul className="w-[180px] shrink-0 space-y-2">
                {data.distribucion.map((row) => (
                  <li key={row.key} className="text-[13px]">
                    <span className="mb-0.5 flex items-center gap-2 font-medium">
                      <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: DIST_COLORS[row.key] || "#5b6b7c" }} />
                      <span className="truncate">{row.label}</span>
                    </span>
                    <span className="pl-5 tabular-nums text-muted-foreground">
                      {row.value} · {row.pct}%
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Panel>

        <Panel title="Cumplimiento de jornada">
          <JornadaGauge pct={data.cumplimiento_jornada_pct} />
        </Panel>

        <Panel title="Horas no laboradas">
          {data.horas_por_categoria.length === 0 ? (
            <p className="text-sm text-muted-foreground">Sin recortes de horario.</p>
          ) : (
            <div className="h-[280px]">
              <ResponsiveContainer>
                <BarChart data={data.horas_por_categoria} layout="vertical" margin={{ top: 8, left: 0, right: 56, bottom: 8 }}>
                  <XAxis type="number" hide domain={[0, horasMax]} />
                  <YAxis type="category" dataKey="label" width={140} tick={{ fontSize: 12, fill: "var(--foreground)" }} interval={0} />
                  <Tooltip formatter={(_v: number, _n, item: { payload?: { txt?: string } }) => [item.payload?.txt || "", "Horas"]} />
                  <Bar dataKey="minutos" radius={[0, 4, 4, 0]} barSize={22}>
                    {data.horas_por_categoria.map((row) => (
                      <Cell key={row.key} fill={DIST_COLORS[row.key] || "#5b6b7c"} />
                    ))}
                    <LabelList dataKey="txt" position="right" style={{ fontSize: 12, fill: "var(--muted-foreground)" }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>

        <Panel title="Tendencia semanal">
          <div className="h-[280px]">
            <ResponsiveContainer>
              <LineChart data={data.tendencia_semana} margin={{ top: 16, right: 12, left: 0, bottom: 8 }}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} />
                <YAxis tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} unit="%" width={42} />
                <Tooltip
                  formatter={(value: number, _n, item: { payload?: { casos?: number } }) => [
                    `${value}% (${item.payload?.casos ?? 0})`,
                    "Incumplimiento",
                  ]}
                />
                <Line type="monotone" dataKey="pct" stroke="var(--error)" strokeWidth={2.25} dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="No marcan por día">
          {noMarcanDia.length === 0 ? (
            <p className="text-sm text-muted-foreground">Sin días sin marca.</p>
          ) : (
            <div className="h-[280px]">
              <ResponsiveContainer>
                <BarChart data={noMarcanDia} margin={{ top: 16, right: 8, left: 0, bottom: 8 }}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                  <YAxis tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} width={36} allowDecimals={false} />
                  <Tooltip
                    formatter={(value: number) => [value, "Persona-días"]}
                    labelFormatter={(_, payload) => {
                      const row = payload?.[0]?.payload as { fecha?: string; dia?: string } | undefined;
                      return row?.fecha ? `${row.dia} ${formatFechaIso(row.fecha)}` : "";
                    }}
                  />
                  <Bar dataKey="casos" fill="#1d5fb8" radius={[4, 4, 0, 0]} barSize={18} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>

        <Panel title="Ranking por área">
          {data.ranking_area.length === 0 ? (
            <p className="text-sm text-muted-foreground">Sin datos de área.</p>
          ) : (
            <div className="h-[280px]">
              <ResponsiveContainer>
                <BarChart data={data.ranking_area} layout="vertical" margin={{ top: 8, left: 0, right: 48, bottom: 8 }}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="short" width={130} tick={{ fontSize: 12, fill: "var(--foreground)" }} interval={0} />
                  <Tooltip
                    formatter={(value: number, _n, item: { payload?: { name?: string; incumplen?: number } }) => [
                      `${value}% (${item.payload?.incumplen ?? 0})`,
                      item.payload?.name || "Área",
                    ]}
                  />
                  <Bar dataKey="pct" radius={[0, 4, 4, 0]} barSize={18}>
                    {data.ranking_area.map((_, i) => (
                      <Cell key={i} fill={AREA_COLORS[i % AREA_COLORS.length]} />
                    ))}
                    <LabelList dataKey="label" position="right" style={{ fontSize: 12, fill: "var(--muted-foreground)" }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Ranking por colaborador" bodyClassName="p-0 overflow-x-auto">
          <table className="w-full min-w-[360px] text-sm">
            <thead className="bg-muted text-left">
              <tr>
                {["#", "Nombre", "Área", "Casos", "Horas"].map((h) => (
                  <th key={h} className="px-4 py-2.5 text-[12px] font-semibold text-muted-foreground">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.ranking_personas.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-sm text-muted-foreground">
                    Nadie fuera de margen.
                  </td>
                </tr>
              ) : (
                data.ranking_personas.map((r, i) => (
                  <tr key={`${r.nombre}-${i}`} className="border-t border-border">
                    <td className="px-4 py-2.5 tabular-nums text-muted-foreground">{i + 1}</td>
                    <td className="max-w-[180px] truncate px-4 py-2.5 font-medium" title={r.nombre}>
                      {r.nombre}
                    </td>
                    <td className="max-w-[140px] truncate px-4 py-2.5 text-[13px]" title={r.area}>
                      {r.area}
                    </td>
                    <td className="px-4 py-2.5 tabular-nums">{r.incidentes}</td>
                    <td className="px-4 py-2.5 font-semibold tabular-nums">{r.horas_txt}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Panel>

        <Panel title="Por tipo de cargo">
          {data.por_tipo.length === 0 ? (
            <p className="text-sm text-muted-foreground">Sin jornadas evaluables.</p>
          ) : (
            <ul className="space-y-4">
              {data.por_tipo.map((row) => (
                <li key={row.name}>
                  <div className="mb-1.5 flex items-center justify-between text-[13px]">
                    <span className="font-medium">{row.name}</span>
                    <span className="tabular-nums text-muted-foreground">{row.cumple_pct}%</span>
                  </div>
                  <div className="flex h-2.5 overflow-hidden rounded-full bg-error-muted">
                    <div className="bg-success" style={{ width: `${row.cumple_pct}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-card px-4 py-3.5 text-[13px] text-foreground shadow-[var(--shadow-card)]">
        <span className="font-semibold tabular-nums">{data.horas_no_laboradas_txt}</span>
        <span className="text-muted-foreground">{data.dias_equivalentes} días equivalentes</span>
      </div>
    </div>
  );
}

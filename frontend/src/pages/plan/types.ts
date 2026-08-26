export type Worker = {
  dni: string;
  nombre: string;
  empresa: string;
  division: string;
  gerencia: string;
  area: string;
  cargo_actual: string;
  fecha_ingreso: string | null;
  tipo_personal: string;
  weeks: number[];
  total_dias: number;
  cambios: number;
  foto_url?: string | null;
  /** false = aún no cumple el año; solo puede pedir adelanto hasta tope_dias. */
  record_cumplido?: boolean;
  /** Tope real programable: 30 si ya cumplió el récord, o lo acumulado (adelanto) si no. */
  tope_dias?: number;
};

export type VacPeriod = {
  inicio: string;
  fin: string;
  dias: number;
  estado: string;
  editable: boolean;
};

export type DocumentoMeta = { escenario: number; titulo: string };

export type DocReady = DocumentoMeta & {
  dni: string;
  year: number;
  start_date: string;
  days: number;
  fin?: string;
  old_start?: string;
};

export type Plan = {
  year: number;
  today?: string;
  current_year: number;
  current_week: number;
  total_semanas: number;
  workers: Worker[];
  kpis: { trabajadores: number; programados: number; pendientes: number; dias: number };
};

export type WeekDay = { fecha: string; weekday: number; selected: boolean; past?: boolean };

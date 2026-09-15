export type Worker = {
  dni: string;
  nombre: string;
  empresa: string;
  division: string;
  gerencia: string;
  area: string;
  jefatura?: string;
  cargo_actual: string;
  fecha_ingreso: string | null;
  tipo_personal: string;
  weeks: number[]; // en pantalla siempre 53; el API manda solo las semanas con días
  total_dias: number;
  cambios: number;
  foto_url?: string | null;
  /** false = aún no cumple el año; solo puede pedir adelanto hasta tope_dias. */
  record_cumplido?: boolean;
  /** Tope real programable: 30 si ya cumplió el récord, o lo acumulado (adelanto) si no. */
  tope_dias?: number;
  flujo_estado?: string;
  flujo_observacion?: string;
  apto?: boolean;
  can_edit?: boolean;
  cumple_record?: string | null;
  record_vacacional?: string | null;
  fecha_vencimiento?: string | null;
};

export type VacPeriod = {
  inicio: string;
  fin: string;
  dias: number;
  estado: string;
  editable: boolean;
};

/** Documento que le toca al plan (solo Personas y Cultura). `key` lo identifica en /api/plan/documento. */
export type DocumentoMeta = { escenario: number; titulo: string; key: string };

/** Respuesta de guardar: el documento listo o, si el plan aún no está completo, el motivo. */
export type DocumentoResp = { documento?: DocumentoMeta; documento_falta?: string };

export type DocReady = DocumentoMeta & {
  dni: string;
  year: number;
};

export type Plan = {
  year: number;
  today?: string;
  /** Primer día que este usuario puede programar (jefatura: la semana cierra el viernes anterior). */
  primer_inicio?: string;
  current_year: number;
  current_week: number;
  total_semanas: number;
  workers: Worker[];
  kpis: { trabajadores: number; programados: number; pendientes: number; dias: number };
};

export type WeekDay = { fecha: string; weekday: number; selected: boolean; past?: boolean };

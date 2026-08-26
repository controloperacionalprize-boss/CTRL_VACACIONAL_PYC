

CREATE TABLE IF NOT EXISTS employees (
    dni TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    empresa TEXT NOT NULL DEFAULT '',
    division TEXT NOT NULL DEFAULT '',
    gerencia TEXT NOT NULL DEFAULT '',
    area TEXT NOT NULL DEFAULT '',
    jefatura TEXT NOT NULL DEFAULT '',
    cargo_actual TEXT NOT NULL DEFAULT '',
    fecha_ingreso DATE,
    tipo_personal TEXT NOT NULL DEFAULT 'ADMINISTRATIVO',
    vigencia TEXT NOT NULL DEFAULT '',
    fecha_cese DATE,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    actualizado TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_employees_gerencia ON employees (gerencia);
CREATE INDEX IF NOT EXISTS idx_employees_empresa ON employees (empresa);
CREATE INDEX IF NOT EXISTS idx_employees_division ON employees (division);

CREATE TABLE IF NOT EXISTS users (
    correo TEXT PRIMARY KEY,
    usuario TEXT NOT NULL DEFAULT '',
    nombre_usuario TEXT NOT NULL DEFAULT '',
    nombre_persona TEXT NOT NULL DEFAULT '',
    gerencia TEXT NOT NULL DEFAULT '',
    rol TEXT NOT NULL DEFAULT 'USER',
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    actualizado TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS daily_plan (
    jefatura TEXT NOT NULL,
    anio INTEGER NOT NULL,
    dni TEXT NOT NULL,
    fecha DATE NOT NULL,
    estado TEXT NOT NULL DEFAULT 'PROGRAMADO',
    usuario TEXT,
    actualizado TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (jefatura, anio, dni, fecha)
);

CREATE INDEX IF NOT EXISTS idx_daily_plan_dni ON daily_plan (dni, anio);
CREATE INDEX IF NOT EXISTS idx_daily_plan_dni_fecha ON daily_plan (dni, fecha);

CREATE TABLE IF NOT EXISTS weekly_plan (
    jefatura TEXT NOT NULL,
    anio INTEGER NOT NULL,
    dni TEXT NOT NULL,
    semana INTEGER NOT NULL,
    dias INTEGER NOT NULL DEFAULT 0,
    usuario TEXT,
    actualizado TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (jefatura, anio, dni, semana)
);

CREATE TABLE IF NOT EXISTS change_log (
    id SERIAL PRIMARY KEY,
    jefatura TEXT NOT NULL,
    anio INTEGER NOT NULL,
    dni TEXT NOT NULL,
    nombre TEXT,
    tipo_persona TEXT,
    fecha_hora TEXT NOT NULL,
    semana_anterior INTEGER,
    dias_anterior INTEGER NOT NULL DEFAULT 0,
    semana_nueva INTEGER,
    dias_nuevos INTEGER NOT NULL DEFAULT 0,
    usuario TEXT,
    nombre_persona TEXT,
    correo TEXT
);

CREATE INDEX IF NOT EXISTS idx_change_log_scope ON change_log (jefatura, anio, dni);
CREATE INDEX IF NOT EXISTS idx_change_log_anio_dni ON change_log (anio, dni);

-- Lo que envían los divisionales (programación de vacaciones de su personal).
CREATE TABLE IF NOT EXISTS cronograma (
    dni TEXT NOT NULL,
    nombre TEXT NOT NULL DEFAULT '',
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE NOT NULL,
    n_dias INTEGER,
    record_vacacional TEXT NOT NULL DEFAULT '',
    observacion TEXT NOT NULL DEFAULT '',
    obs_pagos TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (dni, fecha_inicio, fecha_fin)
);

-- Snapshot de RECORD_VACACIONALES (GTH). El cálculo vivo usa MASTER_EMPLEADO.fecha_ingreso.
CREATE TABLE IF NOT EXISTS vacation_records (
    id SERIAL PRIMARY KEY,
    dni TEXT NOT NULL,
    empresa TEXT NOT NULL DEFAULT '',
    nombre TEXT NOT NULL DEFAULT '',
    fecha_ingreso DATE,
    division TEXT NOT NULL DEFAULT '',
    sub_area TEXT NOT NULL DEFAULT '',
    desde_periodo INTEGER,
    hasta_periodo INTEGER,
    record_vacacional TEXT NOT NULL DEFAULT '',
    cumple_record DATE,
    dias_pendientes TEXT,
    dias_gozados TEXT,
    programado TEXT NOT NULL DEFAULT '',
    obs1 TEXT NOT NULL DEFAULT '',
    fecha_vencimiento DATE,
    fecha_limite DATE
);

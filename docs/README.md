# Documentación — Planificador de Vacaciones

Herramienta digital de **Personas y Cultura · Prize / Aquanqa** para armar el calendario de vacaciones del personal y dejarlo visible, ordenado y descargable desde un solo lugar.

**Objetivo:**  
Que cada gerencia programe con claridad los días libres de su equipo, detecte a tiempo si alguien se pasa del tope o deja el área descubierta, y cuente con un plan listo para compartir o exportar.

**Flujo de gestión:** Ingreso corporativo → Marcado del plan en la grilla → Chequeo de reglas y cobertura → Consulta de récord → Descarga en Excel.

**Próximamente:** Cierre de pruebas con usuarios reales y ajuste fino de lo ya construido.

---

Este documento explica **cómo funciona** la aplicación.

---

## Índice

1. [Alcance del sistema](#1-alcance-del-sistema)
2. [Inicio de sesión](#2-inicio-de-sesión)
3. [Fotos por trabajador](#3-fotos-por-trabajador)
4. [Planificación](#4-planificación)
5. [Dashboard, récord vacacional y exportar](#5-dashboard-récord-vacacional-y-exportar)
6. [Administración y datos](#6-administración-y-datos)

---

## 1. Alcance del sistema

### Para qué sirve

Ayuda a **planificar las vacaciones del año** del personal de Prize / Aquanqa.

Desde aquí se puede:

- Ver el personal filtrado por año, empresa, gerencia y área
- Marcar días o semanas de vacaciones en una grilla
- Revisar si el plan cumple las reglas (tope de días y fraccionamiento)
- Ver un tablero de cobertura (quién falta por área/semana)
- Consultar el récord vacacional de una persona y su asistencia
- Descargar el plan en Excel
- (Solo administradores) gestionar usuarios y ver el historial de cambios

### Qué no hace

- **No** es un sistema de planillas ni de liquidación de vacaciones
- **No** pide contraseña propia de la app: el acceso es con la cuenta Microsoft de la empresa
- **No** deja entrar a cualquiera con correo Microsoft: el correo debe estar registrado y activo en la lista de usuarios del sistema
- **No** guarda las fotos dentro de esta aplicación: las toma de un repositorio de imágenes aparte

### Quién puede usarlo

| Rol | Qué ve / qué puede hacer |
|-----|---------------------------|
| **Usuario normal** | Solo la gerencia que tiene asignada. Puede planificar y consultar dentro de ese alcance. |
| **Administrador** | Todas las gerencias, filtros libres, pantalla de Admin (usuarios, historial, cobertura de fotos). |

### Pantallas principales

| Menú | Qué encuentras |
|------|----------------|
| **Planificación** | La grilla principal: filas de trabajadores y columnas de semanas. Aquí se edita el plan. |
| **Dashboard** | Resumen: cuántos días van programados, mapa de calor, semanas con más riesgo de quedarse sin gente. |
| **Récord vacacional** | Vista de una persona: períodos, días usados/pendientes, marcación de asistencia. |
| **Exportar** | Revisa si el plan tiene errores y descarga el Excel. |
| **Admin** | Solo si eres administrador: usuarios del sistema y bitácora de cambios. |

Arriba o al costado siempre hay filtros de **año**, **empresa**, **gerencia** (solo admin) y **área**.

### Piezas técnicas (resumen simple)

- El **sistema** es una aplicación web (React)
- El **servidor** responde con datos y guarda el plan (FastAPI)
- La **base de datos** principal está en Neon (PostgreSQL)
- La **asistencia** puede venir de otra base (marcación) y, si hace falta, de un Excel en SharePoint
- Las **fotos** vienen de un repositorio público de imágenes en GitHub

---

## 2. Inicio de sesión

### Idea en corto

No hay usuario/contraseña de esta app. Entras con tu **cuenta Microsoft de la empresa**, con un **código** que la pantalla te muestra. Además, tu correo debe estar **validado e ingresado** en el sistema.

### Qué ve el usuario

1. Abre la aplicación.
2. Si no hay sesión, aparece la pantalla de bienvenida **Vacaciones** (Personas y Cultura · Prize / Aquanqa).
3. Pulsa el botón para iniciar con Microsoft.
4. La app muestra un **código** (letras/números) y un enlace a Microsoft.
5. Copias el código, abres el enlace de Microsoft, inicias sesión con tu correo corporativo y pegas el código.
6. La app, en segundo plano, pregunta cada pocos segundos: “¿ya autorizó?”.
7. Cuando Microsoft confirma, entras automáticamente a la aplicación.

No tienes que escribir la contraseña en esta app: eso lo maneja Microsoft.

### Condiciones para que ingreses al sistema

| Condición | Qué pasa si no se cumple |
|-----------|---------------------------|
| Completaste el código en Microsoft | La pantalla sigue esperando o termina con error |
| Tu correo existe en la lista de usuarios del sistema | No hay sesión aunque Microsoft te reconozca |
| El usuario está **activo** | Igual: no entra |
| Eres administrador | Ves el menú Admin y todas las gerencias; si no, solo tu gerencia |

En otras palabras: **Microsoft dice quién eres; esta app decide si tienes permiso** según la lista interna de usuarios.

### Qué guarda la sesión

Cuando el acceso es correcto, la app guarda un **token de sesión** en el navegador (unas 4 horas). Con ese token pide datos al servidor. Al cerrar sesión se borra.

No hace falta “recordar” una contraseña de Vacaciones: al caducar el token, vuelves a entrar con Microsoft.

### Escenarios frecuentes

**Caso normal**  
Correo corporativo registrado y activo → código en Microsoft → entras y ves Planificación con tu gerencia (o todas, si eres admin).

**“Microsoft me dejó pasar, pero la app no”**  
El correo no está en usuarios, o está inactivo. Hay que pedirle a un administrador que te registre o reactive.

**Error al generar el código**  
Problema de conexión con Microsoft o de configuración del servidor. Reintentar; si se repite, revisar la configuración de autenticación.

**Se te cerró la sesión a media jornada**  
El token venció (aprox. 4 horas) o borraste datos del navegador. Vuelve a iniciar con el código.

### Dónde está en el código (opcional)

| Parte | Archivo / lugar |
|-------|------------------|
| Pantalla del código | `frontend/src/pages/Login.tsx` |
| Pedir código y confirmar | `backend/app/routers/auth.py` y `backend/app/microsoft.py` |
| Buscar usuario por correo y crear sesión | `backend/app/auth.py` |
| Lista de quién puede entrar | tabla `users` en la base de datos |

---

## 3. Fotos por trabajador

### Idea en corto

Cuando ves un trabajador en la grilla o en el menú, la app intenta mostrar su **foto**. Esas fotos **no viven dentro de esta aplicación**: están en un repositorio de imágenes aparte (GitHub). Esta app solo **busca el archivo correcto** y arma el enlace.

Si no encuentra foto, muestra las **iniciales** del nombre.

### De dónde salen las fotos

1. Hay un repositorio público de imágenes (por defecto el de personal `PICTURES`).
2. Cada archivo suele llamarse como el **usuario del correo**, por ejemplo: `eabanto.jpg` para `eabanto@…`.
3. Esta app descarga la **lista de archivos** de ese repositorio (y la guarda en memoria una hora para no preguntar todo el tiempo).
4. Para cada trabajador, decide **qué nombre de archivo** le corresponde y construye la URL.

### Cómo decide “esta foto es de esta persona”

Hay dos caminos. El primero es el confiable; el segundo es solo un respaldo.

#### Camino 1 — Lista de personal (roster)

Existe un archivo interno con gente conocida: nombre, correo y usuario (la parte antes del `@`).

1. Se toma el **nombre** del trabajador tal como está en la base.
2. Se compara con los nombres del roster (sin importar mayúsculas, tildes ni el orden exacto de las palabras).
3. Si coincide, se toma el **usuario** (ej. `eabanto`).
4. Se busca en el repositorio un archivo `eabanto.jpg` (u otra extensión: png, webp, etc.).
5. Si hay archivo → se muestra esa foto.
6. Si la persona **está en el roster pero no hay archivo** → **no se inventa otro nombre**. Mejor sin foto que poner la de otra persona con apellido parecido.

Esa regla es importante: evita mezclar fotos entre homónimos o apellidos comunes.

#### Camino 2 — Solo si no está en el roster

Si la persona **no aparece** en esa lista:

1. La app prueba nombres de archivo “probables”, por ejemplo inicial + apellido (`lperez`, `jgarcia`, etc.).
2. No usa nombres que ya están “reservados” por gente del roster (otra vez: para no pisar fotos ajenas).
3. Si hay un archivo casi igual (muy parecido y misma letra inicial), también puede aceptarlo.
4. Si nada encaja → sin foto, solo iniciales.

#### Usuario que acaba de iniciar sesión

Para la foto del usuario logueado el orden es aún más directo: primero el usuario / la parte del correo, y si no, el mismo método por nombre.

### Qué ve la persona en pantalla

| Situación | Qué se muestra |
|-----------|----------------|
| Hay enlace de foto y la imagen carga | La foto |
| Hay enlace pero el archivo falló al cargar | Iniciales (la pantalla se recupera sola) |
| No se encontró coincidencia | Iniciales desde el principio |

### Escenarios

**Caso normal**  
“Luis Yoshi Vera” está en el roster como usuario `lvera`, existe `lvera.jpg` → se ve su foto.

**Está en el roster, pero falta el archivo**  
Aparece en la lista interna, pero en el repo de fotos no está `lvera.jpg` → **sin foto**. No se prueba otro nombre a ciegas. Solución: subir el archivo con el nombre de usuario correcto.

**No está en el roster, pero el archivo sigue la costumbre**  
Persona nueva no listada; en el repo existe algo como `jperez.jpg` y el nombre encaja → puede mostrarse por el camino de respaldo.

**Dos personas con apellido parecido**  
Si ambas están bien en el roster con usuarios distintos (`mflores` y `jflores`), cada una va a su archivo. Si hubiera duda solo por apellido, el sistema **prefiere no mostrar foto** antes que cruzarlas.

**Las fotos “desaparecieron” un rato**  
Si el repositorio no responde o las fotos están desactivadas por configuración, nadie tendrá foto hasta que vuelva el servicio o se reactive.


### Dónde está en el código (opcional)

| Parte | Archivo / lugar |
|-------|------------------|
| Lógica de búsqueda | `backend/app/photos.py` |
| Lista nombre ↔ usuario | `backend/app/data/personal_roster.json` |
| Avatar en pantalla | `frontend/src/components/EmpAvatar.tsx` |
| Reporte de cobertura | pantalla Admin / endpoint de fotos |
| Activar o apuntar al repo | variables `PICTURES_*` en la configuración |

---

## 4. Planificación

### Idea en corto

La pantalla **Planificación** es el corazón del sistema: una grilla con trabajadores (filas) y semanas del año (columnas). Ahí se marcan los días de vacaciones. El servidor **guarda** esos días y **rechaza** cambios que rompan las reglas.

### Qué puedes hacer en la grilla

- Ver cuántos días tiene cada persona por semana (0 a 7)
- Abrir el detalle de una semana y marcar **días concretos**
- Programar un **bloque seguido** de varios días desde una fecha
- Ver o **mover** un período ya armado
- Filtrar por año, empresa, gerencia (admin) y área

Los cambios se envían al servidor; si algo no cumple las reglas, verás un mensaje de error y el plan no se guarda así.

### Reglas que importan

#### Tope de días (derecho / adelanto)

- El derecho anual de referencia es **30 días**.
- Si la persona **aún no cumple el año** de récord, el tope puede ser menor: se acumula **2,5 días por mes** trabajado, hasta llegar a 30.
- No se puede programar **más días de los que el tope vigente permite**.

#### Fraccionamiento (Art. 8)

Cuando las vacaciones se parten en varios tramos:

| Forma válida | En palabras simples |
|--------------|---------------------|
| Un solo tramo | Todo junto: no hay problema de fraccionamiento |
| Un bloque de **15 o más** días corridos | Cumple aunque haya otros tramos más chicos |
| Dos bloques de al menos **7** y **8** días | También cumple; el resto puede ser desde 1 día |

Si solo hay tramos cortos (por ejemplo tres bloques de 5) **sin** cumplir lo de arriba, el sistema **no deja guardar** o lo marca como error al validar.

#### No editar el pasado

Semanas o fechas que ya pasaron (según la fecha de Lima-Perú) quedan **bloqueadas**. No se reescribe el historial desde la grilla.

#### Año y solapes

- Las fechas deben pertenecer al **año** que estás planificando.
- No se pueden solapar períodos de la misma persona de forma inconsistente (el servidor lo controla).

#### Días corridos vs hábiles

Por defecto el conteo suele ser en **días calendario**. Hay lógica para personal que solo cuenta días hábiles; eso depende del tipo de trabajador en los datos maestros.

### Validación del plan completo

Además de validar al guardar, existe una revisión global del plan (también usada al exportar):

| Tipo de problema | Qué significa para el usuario |
|------------------|-------------------------------|
| **Saldo** | Esa persona tiene más días programados que su tope vigente |
| **Art. 8** | El fraccionamiento no cumple la regla de 15 corridos o 7+8 |
| **Desajuste** | En la semana el número mostrado no cuadra con los días marcados uno a uno |
| **Fuera de rango** | Una semana aparece con más de 7 días (inválido) |

También puede haber **avisos** de cobertura (si en una semana se va mucha gente a la vez): no siempre bloquean, pero sirven para decidir con cuidado.

### Escenarios

**Caso normal**  
Marcas 15 días seguidos en julio y el resto en tramos cortos → saldo OK y Art. 8 OK → se guarda.

**Quieres tres semanas sueltas de 5 días**  
Sin un bloque de 15 ni el par 7+8 → el sistema rechaza o lo marca en validación. Hay que rearmar.

**Intentas poner 32 días en el año**  
Supera el tope → error de saldo.

**Intentas cambiar una semana de enero cuando ya estamos en agosto**  
Semana bloqueada por pasado → no edita.

**El número de la semana dice “3” pero solo hay 1 día marcado**  
Desajuste → hay que alinear el detalle diario con lo que muestra la semana.

### Resumen en una línea

**Planificas por semana/día, el sistema guarda solo lo que cabe en el tope y en el Art. 8, y no deja reescribir el pasado.**

### Dónde está en el código (opcional)

| Parte | Archivo / lugar |
|-------|------------------|
| Pantalla | `frontend/src/pages/Plan.tsx` |
| Endpoints de plan | `backend/app/routers/plan.py` |
| Reglas (tope, Art. 8, semanas) | `backend/app/domain/calendar.py` |
| Validación global | `backend/app/domain/plan.py` |
| Días guardados | tablas `daily_plan` y `weekly_plan` |

---

## 5. Dashboard, récord vacacional y exportar

### Dashboard

Resumen del plan del año filtrado:

- Totales de días programados / pendientes
- Vista por gerencia, área o tipo de personal
- Mapa de calor (semana × día): dónde se concentra la gente de vacaciones
- Semanas con más **riesgo** de quedar cortos de personal

Sirve para decidir si conviene mover períodos antes de confirmar el plan.

### Récord vacacional

Vista centrada en **una persona**:

- Derecho, días programados y pendientes
- Períodos de vacaciones en el calendario
- **Asistencia / faltas** cuando hay datos de marcación

La asistencia se arma así (cuando está configurada):

1. Primero se lee la **base de marcación** (reloj biométrico).
2. Si hace falta completar días más recientes, se puede usar un **Excel en SharePoint**.
3. El Excel solo aporta días **posteriores** a lo que ya hay en la base (no pisa lo ya cargado).
4. Algunos cargos (jefatura / gerencia) están **exentos** de marcación: no se pintan faltas; los días laborables cubiertos se muestran como asistencia.
5. Se consideran feriados de Perú al interpretar el calendario.

### Exportar

1. La pantalla puede **validar** el plan (mismos tipos de problema que en planificación).
2. Si está bien (o aceptas los avisos según el flujo), descarga un **Excel** con el plan y hojas de apoyo (historial / récord según lo que genere el export).

Útil para compartir con Personas y Cultura o archivar fuera del sistema.

### Dónde está en el código (opcional)

| Parte | Archivo / lugar |
|-------|------------------|
| Dashboard | `frontend/src/pages/Dashboard.tsx`, `backend/app/domain/dashboard.py` |
| Récord | `frontend/src/pages/Calendar.tsx`, `backend/app/domain/employee_calendar.py` |
| Asistencia | `backend/app/attendance.py` (y módulos de BD / Excel) |
| Export | `frontend/src/pages/Export.tsx`, `backend/app/domain/export.py` |

---

## 6. Administración y datos

### Admin (solo administradores)

Desde **Admin** se puede:

- **Listar / crear / actualizar usuarios** (correo, gerencia, rol, activo)
- Ver el **historial de cambios** del plan (quién cambió qué y cuándo)

Sin fila activa en usuarios, nadie entra aunque tenga Microsoft.

### De dónde salen los datos maestros

La carga habitual viene de Excel y se aplica a la base Neon:

| Origen típico | Contenido |
|---------------|-----------|
| `trabajadores.xlsx` | Empleados, cronograma, récord vacacional |
| `usuarios.xlsx` | Quién puede entrar a la app (correo, gerencia, rol) |

El script `backend/scripts/generar_sql_neon.py` prepara o aplica esa carga. Las tablas vacías se crean con `backend/sql/schema.sql`.

### Tablas principales (nombres simples)

| Tabla | Para qué |
|-------|----------|
| `users` | Quién puede iniciar sesión |
| `employees` | Trabajadores a planificar |
| `daily_plan` / `weekly_plan` | Días y semanas marcadas |
| `change_log` | Historial de cambios |
| `cronograma` / `vacation_records` | Datos de apoyo del récord |

### Idea general en una frase

Un usuario autorizado entra con Microsoft, ve al personal de su gerencia (o de todas, si es administrador), marca días de vacaciones respetando el tope legal y las reglas de fraccionamiento, revisa cobertura y asistencia, y puede exportar el plan a Excel.

import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { api, qs } from "../api";
import { useApp } from "../state";
import { Alert, Button, EmptyState, Field, Input, PageHeader, Select } from "../components/ui";

type AppUser = {
  correo: string;
  usuario: string;
  nombre_usuario: string;
  nombre_persona: string;
  gerencia: string;
  rol: string;
  activo: boolean;
};

type ChangeEvent = {
  id: number;
  n: number;
  fecha_hora: string;
  semana: number | null;
  dias_anterior: number;
  dias_nuevos: number;
  afectado: string;
  afectado_dni: string;
  afectado_iniciales: string;
  autor: string;
  correo: string;
  iniciales: string;
  foto_url: string | null;
};

type Thread = {
  dni: string;
  nombre: string;
  jefatura: string;
  cambios: number;
  events: ChangeEvent[];
};

const emptyForm = {
  correo: "",
  nombre_persona: "",
  gerencia: "",
  rol: "USER",
};

function formatWhen(value: string) {
  const raw = value.includes("T") ? value : value.replace(" ", "T");
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("es-PE", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function Avatar({
  name,
  initials,
  fotoUrl,
  size = "md",
}: {
  name: string;
  initials: string;
  fotoUrl?: string | null;
  size?: "sm" | "md";
}) {
  const dim = size === "sm" ? "h-6 w-6 text-[9px]" : "h-8 w-8 text-[11px]";
  return (
    <span
      title={name}
      className={`inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary/15 font-semibold text-primary ${dim}`}
    >
      {fotoUrl ? <img src={fotoUrl} alt="" className="h-full w-full object-cover" /> : initials || "?"}
    </span>
  );
}

const COLS = 4;

function snakeRows(events: ChangeEvent[]) {
  const rows: { rtl: boolean; labelsAbove: boolean; slots: Array<ChangeEvent | null> }[] = [];
  for (let i = 0; i < events.length; i += COLS) {
    const slice = events.slice(i, i + COLS);
    const rtl = rows.length % 2 === 1;
    const slots: Array<ChangeEvent | null> = Array(COLS).fill(null);
    slice.forEach((ev, idx) => {
      slots[rtl ? COLS - 1 - idx : idx] = ev;
    });
    rows.push({ rtl, labelsAbove: !rtl, slots });
  }
  return rows;
}

function StepLabel({ ev }: { ev: ChangeEvent }) {
  return (
    <div className="min-w-0 px-1 text-center">
      <p className="truncate text-[12px] font-semibold leading-tight">
        {ev.semana ? `Semana ${ev.semana}` : "Cambio"}
      </p>
      <p className="mt-0.5 font-data text-[12px] leading-tight text-foreground">
        {ev.dias_anterior} → {ev.dias_nuevos} días
      </p>
      <div className="mt-1 flex min-w-0 items-center justify-center gap-1">
        <Avatar name={ev.autor} initials={ev.iniciales} fotoUrl={ev.foto_url} size="sm" />
        <p className="min-w-0 truncate text-[10px] font-medium text-muted-foreground" title={ev.autor}>
          {ev.autor}
        </p>
      </div>
      <p className="mt-0.5 font-data text-[9px] leading-tight text-muted-foreground">{formatWhen(ev.fecha_hora)}</p>
    </div>
  );
}

function Snake({ events }: { events: ChangeEvent[] }) {
  const rows = snakeRows(events);

  return (
    <>
      <ol className="md:hidden">
        {events.map((ev, i) => (
          <li key={ev.id} className="flex gap-3">
            <div className="flex w-9 shrink-0 flex-col items-center">
              {i > 0 ? <div className="h-2 w-0.5 bg-primary/50" /> : <div className="h-2" />}
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-[12px] font-semibold text-primary-foreground">
                {ev.n}
              </div>
              {i < events.length - 1 ? <div className="w-0.5 flex-1 bg-primary/50" /> : <div className="h-2" />}
            </div>
            <div className="min-w-0 flex-1 pb-5 pt-1">
              <StepLabel ev={ev} />
            </div>
          </li>
        ))}
      </ol>

      <div className="hidden md:block">
        {rows.map((row, ri) => {
          const first = row.slots.findIndex((s: ChangeEvent | null) => s != null);
          let last = -1;
          for (let i = row.slots.length - 1; i >= 0; i--) {
            if (row.slots[i] != null) {
              last = i;
              break;
            }
          }
          const left = ((first + 0.5) / COLS) * 100;
          const right = ((last + 0.5) / COLS) * 100;
          const turnRight = ri % 2 === 0;
          return (
            <div key={ri}>
              {row.labelsAbove ? (
                <div className="mb-2 grid grid-cols-4">
                  {row.slots.map((ev, i) => (
                    <div key={i}>{ev ? <StepLabel ev={ev} /> : null}</div>
                  ))}
                </div>
              ) : null}

              <div className="relative h-9">
                {first >= 0 && last >= first ? (
                  <div
                    className="absolute top-1/2 h-0 border-t-2 border-dashed border-primary/50"
                    style={{ left: `${left}%`, width: `${right - left}%` }}
                    aria-hidden
                  />
                ) : null}
                <div className="grid h-9 grid-cols-4">
                  {row.slots.map((ev, i) => (
                    <div key={i} className="flex items-center justify-center">
                      {ev ? (
                        <div className="relative z-10 flex h-9 w-9 items-center justify-center rounded-full bg-primary text-[12px] font-semibold text-primary-foreground ring-[5px] ring-card">
                          {ev.n}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>

              {!row.labelsAbove ? (
                <div className="mt-2 grid grid-cols-4">
                  {row.slots.map((ev, i) => (
                    <div key={i}>{ev ? <StepLabel ev={ev} /> : null}</div>
                  ))}
                </div>
              ) : null}

              {ri < rows.length - 1 ? (
                <div
                  className="flex h-8"
                  style={{ paddingLeft: turnRight ? `${right}%` : undefined, paddingRight: turnRight ? undefined : `${100 - left}%` }}
                >
                  <div
                    className="h-full w-0 border-l-2 border-dashed border-primary/50"
                    style={{ marginLeft: turnRight ? "-1px" : "auto", marginRight: turnRight ? undefined : "-1px" }}
                    aria-hidden
                  />
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </>
  );
}

export function AdminPage() {
  const { user, filters } = useApp();
  const [tab, setTab] = useState<"users" | "logs">("users");
  const [users, setUsers] = useState<AppUser[]>([]);
  const [gerencias, setGerencias] = useState<string[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [threads, setThreads] = useState<Thread[]>([]);
  const [q, setQ] = useState("");

  function loadUsers() {
    return api<{ items: AppUser[]; gerencias: string[] }>("/api/admin/users").then((r) => {
      setUsers(r.items);
      setGerencias(r.gerencias);
    });
  }

  useEffect(() => {
    loadUsers().catch((e) => setError(e instanceof Error ? e.message : "No se pudieron cargar los usuarios."));
  }, []);

  useEffect(() => {
    if (tab !== "logs") return;
    api<{ threads: Thread[] }>(`/api/admin/timeline${qs({ year: filters.year })}`)
      .then((r) => setThreads(r.threads))
      .catch((e) => setError(e instanceof Error ? e.message : "No se pudo cargar el historial."));
  }, [tab, filters.year]);

  const visible = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return threads;
    return threads.filter(
      (th) =>
            th.nombre.toLowerCase().includes(t) ||
        th.dni.includes(t) ||
        th.events.some(
          (e) =>
            e.autor.toLowerCase().includes(t) ||
            e.correo.toLowerCase().includes(t) ||
            (e.afectado || "").toLowerCase().includes(t) ||
            (e.afectado_dni || "").includes(t)
        )
    );
  }, [q, threads]);

  if (!user?.is_admin) return <Navigate to="/" replace />;

  async function addUser() {
    setError("");
    setOk("");
    try {
      await api("/api/admin/users", { method: "POST", body: JSON.stringify(form) });
      setForm(emptyForm);
      setOk("Usuario agregado. Ya puede iniciar sesión con Microsoft.");
      await loadUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo agregar el usuario.");
    }
  }

  async function patchUser(correo: string, body: Partial<AppUser>) {
    setError("");
    setOk("");
    try {
      await api(`/api/admin/users/${encodeURIComponent(correo)}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      await loadUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo actualizar.");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Administración"
        help=""
      />

      <div className="flex gap-2">
        <Button variant={tab === "users" ? "primary" : "outline"} onClick={() => setTab("users")}>
          Usuarios
        </Button>
        <Button variant={tab === "logs" ? "primary" : "outline"} onClick={() => setTab("logs")}>
          Historial de cambios
        </Button>
      </div>

      {error ? (
        <Alert tone="error" title="No se pudo completar">
          {error}
        </Alert>
      ) : null}
      {ok ? (
        <Alert tone="success" title="Listo">
          {ok}
        </Alert>
      ) : null}

      {tab === "users" ? (
        <>
          <div className="grid grid-cols-[1.4fr_1.2fr_1fr_auto_auto] items-end gap-3 rounded-xl border border-border bg-card p-4">
            <Field label="CORREO">
              <Input
                type="email"
                value={form.correo}
                onChange={(e) => setForm({ ...form, correo: e.target.value })}
                placeholder="nombre@empresa.com"
              />
            </Field>
            <Field label="NOMBRE">
              <Input
                value={form.nombre_persona}
                onChange={(e) => setForm({ ...form, nombre_persona: e.target.value })}
              />
            </Field>
            <Field label="GERENCIA">
              <Input
                list="gerencias-admin"
                value={form.gerencia}
                onChange={(e) => setForm({ ...form, gerencia: e.target.value })}
              />
              <datalist id="gerencias-admin">
                {gerencias.map((g) => (
                  <option key={g} value={g} />
                ))}
              </datalist>
            </Field>
            <Field label="ROL" className="w-36">
              <Select value={form.rol} onChange={(e) => setForm({ ...form, rol: e.target.value })}>
                <option value="USER">USER</option>
                <option value="ADMIN">ADMIN</option>
              </Select>
            </Field>
            <Button onClick={addUser}>Agregar</Button>
          </div>

          <div className="overflow-auto rounded-[4px] border border-border bg-card">
            <table className="w-full text-sm">
              <thead className="bg-muted text-left">
                <tr>
                  {["Nombre", "Correo", "Gerencia", "Rol", "Estado"].map((h) => (
                    <th key={h} className="px-3 py-2 text-[11px] font-semibold text-muted-foreground">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.correo} className="border-t border-border">
                    <td className="px-3 py-2 font-medium">{u.nombre_persona || u.nombre_usuario}</td>
                    <td className="px-3 py-2">{u.correo}</td>
                    <td className="px-3 py-2">{u.gerencia}</td>
                    <td className="px-3 py-2">
                      <Select
                        value={u.rol}
                        onChange={(e) => patchUser(u.correo, { rol: e.target.value })}
                        disabled={u.correo === user.correo}
                      >
                        <option value="USER">USER</option>
                        <option value="ADMIN">ADMIN</option>
                      </Select>
                    </td>
                    <td className="px-3 py-2">
                      <Button
                        variant={u.activo ? "outline" : "primary"}
                        className="h-8 px-3 text-xs"
                        disabled={u.correo === user.correo}
                        onClick={() => patchUser(u.correo, { activo: !u.activo })}
                      >
                        {u.activo ? "Activo" : "Inactivo"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <>
          <p className="text-[13px] text-muted-foreground">
            El encabezado es el usuario modificado. Cada círculo es un cambio: semana, días, quién lo hizo y cuándo.
          </p>
          <Input
            type="search"
            className="max-w-sm"
            placeholder="Buscar trabajador o quién hizo el cambio…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          {visible.length === 0 ? (
            <EmptyState
              title="Sin cambios este año"
              body="Cuando alguien edite el plan, aquí verás el historial por persona."
            />
          ) : (
            <div className="space-y-4">
              {visible.map((th) => (
                <section key={th.dni} className="rounded-xl border border-border bg-card p-4">
                  <div className="mb-5 flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2.5">
                      <Avatar name={th.nombre} initials={th.events[0]?.afectado_iniciales || ""} />
                      <div className="min-w-0">
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Usuario modificado</p>
                        <h3 className="truncate text-[15px] font-semibold">{th.nombre}</h3>
                        <p className="text-[11px] text-muted-foreground">
                          DNI {th.dni}
                          {th.jefatura ? ` · ${th.jefatura}` : ""}
                        </p>
                      </div>
                    </div>
                    <p className="shrink-0 text-[11px] text-muted-foreground">
                      {th.cambios === 1 ? "1 modificación" : `${th.cambios} modificaciones`}
                    </p>
                  </div>
                  <Snake events={th.events} />
                </section>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

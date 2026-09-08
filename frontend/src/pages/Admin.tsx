import { useEffect, useMemo, useState } from "react";
import { ChevronDown, Pencil } from "lucide-react";
import { Navigate } from "react-router-dom";
import { api, qs } from "../api";
import { useApp } from "../state";
import { SnakeTimeline, type SnakePaso } from "../components/SnakeTimeline";
import { Alert, Button, EmptyState, Field, Input, PageHeader, Select } from "../components/ui";
import { EmpleadosRoster } from "./admin/EmpleadosRoster";

type AppUser = {
  correo: string;
  usuario: string;
  nombre_usuario: string;
  nombre_persona: string;
  gerencia: string;
  area: string;
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
  foto_url?: string | null;
  events: ChangeEvent[];
};

const emptyForm = {
  correo: "",
  nombre_persona: "",
  gerencia: "",
  area: "",
  rol: "GERENTE",
};

const ROLES = [
  { value: "GERENTE", label: "Gerente (división)" },
  { value: "JEFE", label: "Jefe (área)" },
  { value: "ADMIN", label: "Administrador" },
  { value: "USER", label: "Gerente (legado)" },
];

type UserForm = typeof emptyForm;

function rolEsGerente(rol: string) {
  return rol === "GERENTE" || rol === "USER";
}

function rolEsJefe(rol: string) {
  return rol === "JEFE";
}

function rolLabel(rol: string) {
  return ROLES.find((r) => r.value === rol)?.label || rol;
}

function formFromUser(u: AppUser): UserForm {
  return {
    correo: u.correo,
    nombre_persona: u.nombre_persona || u.nombre_usuario,
    gerencia: u.gerencia || "",
    area: u.area || "",
    rol: u.rol === "USER" ? "GERENTE" : u.rol,
  };
}

function applyRol(form: UserForm, rol: string): UserForm {
  return {
    ...form,
    rol,
    gerencia: rolEsGerente(rol) ? form.gerencia : "",
    area: rolEsJefe(rol) ? form.area : "",
  };
}

function ScopeFields({
  form,
  onChange,
  gerencias,
  areas,
}: {
  form: UserForm;
  onChange: (next: UserForm) => void;
  gerencias: string[];
  areas: string[];
}) {
  const divisiones = form.gerencia && !gerencias.includes(form.gerencia) ? [form.gerencia, ...gerencias] : gerencias;
  const areaOpts = form.area && !areas.includes(form.area) ? [form.area, ...areas] : areas;
  return (
    <>
      {rolEsGerente(form.rol) ? (
        <Field label="DIVISIÓN">
          <Select value={form.gerencia} onChange={(e) => onChange({ ...form, gerencia: e.target.value })}>
            <option value="">Selecciona…</option>
            {divisiones.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </Select>
        </Field>
      ) : null}
      {rolEsJefe(form.rol) ? (
        <Field label="ÁREA">
          <Select value={form.area} onChange={(e) => onChange({ ...form, area: e.target.value })}>
            <option value="">Selecciona…</option>
            {areaOpts.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </Select>
        </Field>
      ) : null}
    </>
  );
}

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

function eventsToPasos(events: ChangeEvent[]): SnakePaso[] {
  return events.map((ev) => ({
    id: String(ev.id),
    numero: ev.n,
    titulo: ev.semana ? `Semana ${ev.semana}` : "Cambio",
    detalle: `${ev.dias_anterior} → ${ev.dias_nuevos} días`,
    usuario: ev.autor,
    iniciales: ev.iniciales,
    fotoUrl: ev.foto_url,
    fecha: formatWhen(ev.fecha_hora),
  }));
}

/** Tarjeta desglosable: cabecera siempre visible; snake solo al expandir. */
function ThreadCard({
  th,
  open,
  onToggle,
}: {
  th: Thread;
  open: boolean;
  onToggle: () => void;
}) {
  const pasos = useMemo(() => eventsToPasos(th.events), [th.events]);

  return (
    <section className="rounded-xl border border-border bg-card shadow-[var(--shadow-card)]">
      <button
        type="button"
        className="flex w-full items-center gap-2.5 px-3.5 py-3 text-left"
        aria-expanded={open}
        onClick={onToggle}
      >
        <Avatar name={th.nombre} initials={th.events[0]?.afectado_iniciales || ""} fotoUrl={th.foto_url} />
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-[14px] font-semibold">{th.nombre}</h3>
          <p className="text-[11px] text-muted-foreground">
            DNI {th.dni}
            {th.jefatura ? ` · ${th.jefatura}` : ""}
          </p>
        </div>
        <span className="shrink-0 rounded-md bg-muted px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-muted-foreground">
          {th.cambios === 1 ? "1 cambio" : `${th.cambios} cambios`}
        </span>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden
        />
      </button>
      {open ? (
        <div className="border-t border-border px-3 pb-3.5 pt-3 sm:px-4">
          <SnakeTimeline pasos={pasos} />
        </div>
      ) : null}
    </section>
  );
}

export function AdminPage() {
  const { user, filters } = useApp();
  const [tab, setTab] = useState<"users" | "logs" | "empleados">("users");
  const [users, setUsers] = useState<AppUser[]>([]);
  const [gerencias, setGerencias] = useState<string[]>([]);
  const [areas, setAreas] = useState<string[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [editing, setEditing] = useState<AppUser | null>(null);
  const [editForm, setEditForm] = useState(emptyForm);
  const [editSaving, setEditSaving] = useState(false);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [threads, setThreads] = useState<Thread[]>([]);
  const [q, setQ] = useState("");
  const [openDnis, setOpenDnis] = useState<Set<string>>(() => new Set());

  function loadUsers() {
    return api<{ items: AppUser[]; gerencias: string[]; areas?: string[] }>("/api/admin/users").then((r) => {
      setUsers(r.items);
      setGerencias(r.gerencias);
      setAreas(r.areas || []);
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

  useEffect(() => {
    if (visible.length === 1) {
      setOpenDnis(new Set([visible[0].dni]));
    }
  }, [visible]);

  function toggleThread(dni: string) {
    setOpenDnis((prev) => {
      const next = new Set(prev);
      if (next.has(dni)) next.delete(dni);
      else next.add(dni);
      return next;
    });
  }

  if (!user?.is_admin) return <Navigate to="/" replace />;

  async function addUser() {
    setError("");
    setOk("");
    if (rolEsJefe(form.rol) && !form.area.trim()) {
      setError("El jefe debe tener un área.");
      return;
    }
    if (rolEsGerente(form.rol) && !form.gerencia.trim()) {
      setError("El gerente debe tener una división.");
      return;
    }
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

  async function saveEdit() {
    if (!editing) return;
    setError("");
    setOk("");
    if (rolEsJefe(editForm.rol) && !editForm.area.trim()) {
      setError("El jefe debe tener un área.");
      return;
    }
    if (rolEsGerente(editForm.rol) && !editForm.gerencia.trim()) {
      setError("El gerente debe tener una división.");
      return;
    }
    setEditSaving(true);
    try {
      await api(`/api/admin/users/${encodeURIComponent(editing.correo)}`, {
        method: "PATCH",
        body: JSON.stringify({
          nombre_persona: editForm.nombre_persona,
          rol: editForm.rol,
          gerencia: rolEsGerente(editForm.rol) ? editForm.gerencia : "",
          area: rolEsJefe(editForm.rol) ? editForm.area : "",
        }),
      });
      setEditing(null);
      setOk("Usuario actualizado.");
      await loadUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo actualizar.");
    } finally {
      setEditSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Administración"
        help=""
      />

      <div className="flex gap-2 overflow-x-auto">
        <Button variant={tab === "users" ? "primary" : "outline"} onClick={() => setTab("users")} className="shrink-0">
          Usuarios
        </Button>
        <Button variant={tab === "empleados" ? "primary" : "outline"} onClick={() => setTab("empleados")} className="shrink-0">
          Empleados
        </Button>
        <Button variant={tab === "logs" ? "primary" : "outline"} onClick={() => setTab("logs")} className="shrink-0">
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
          <div className="grid grid-cols-1 items-end gap-3 rounded-xl border border-border bg-card p-4 sm:grid-cols-2 lg:grid-cols-[1.3fr_1.1fr_1fr_auto_auto]">
            <Field label="CORREO" className="sm:col-span-2 lg:col-span-1">
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
            <Field label="ROL" className="w-full lg:w-44">
              <Select value={form.rol} onChange={(e) => setForm(applyRol(form, e.target.value))}>
                {ROLES.filter((r) => r.value !== "USER").map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </Select>
            </Field>
            <ScopeFields form={form} onChange={setForm} gerencias={gerencias} areas={areas} />
            <Button onClick={addUser} className="w-full lg:w-auto">
              Agregar
            </Button>
          </div>

          <div className="space-y-3 md:hidden">
            {users.map((u) => (
              <article key={u.correo} className="rounded-xl border border-border bg-card p-3.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-[14px] font-semibold">{u.nombre_persona || u.nombre_usuario}</p>
                    <p className="mt-0.5 truncate text-[12px] text-muted-foreground">{u.correo}</p>
                    <p className="mt-1 text-[12px] text-foreground">{rolLabel(u.rol)}</p>
                    <p className="mt-0.5 text-[12px] text-muted-foreground">
                      {rolEsJefe(u.rol)
                        ? u.area || "Sin área"
                        : rolEsGerente(u.rol)
                          ? u.gerencia || "Sin división"
                          : "Toda la organización"}
                    </p>
                  </div>
                  <Button
                    variant={u.activo ? "outline" : "primary"}
                    className="h-8 shrink-0 px-3 text-xs"
                    disabled={u.correo === user.correo}
                    onClick={() => patchUser(u.correo, { activo: !u.activo })}
                  >
                    {u.activo ? "Activo" : "Inactivo"}
                  </Button>
                </div>
                <Button
                  variant="outline"
                  className="mt-3 h-8 w-full text-xs"
                  onClick={() => {
                    setEditing(u);
                    setEditForm(formFromUser(u));
                    setError("");
                    setOk("");
                  }}
                >
                  <Pencil size={14} strokeWidth={1.75} />
                  Editar
                </Button>
              </article>
            ))}
          </div>

          <div className="hidden overflow-auto rounded-[4px] border border-border bg-card md:block">
            <table className="w-full text-sm">
              <thead className="bg-muted text-left">
                <tr>
                  {["Nombre", "Correo", "Alcance", "Rol", "Estado", ""].map((h) => (
                    <th key={h || "acciones"} className="px-3 py-2 text-[11px] font-semibold text-muted-foreground">
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
                    <td className="px-3 py-2 text-muted-foreground">
                      {rolEsJefe(u.rol)
                        ? u.area || "—"
                        : rolEsGerente(u.rol)
                          ? u.gerencia || "—"
                          : "—"}
                    </td>
                    <td className="px-3 py-2">{rolLabel(u.rol)}</td>
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
                    <td className="px-3 py-2 text-right">
                      <Button
                        variant="outline"
                        className="h-8 px-3 text-xs"
                        onClick={() => {
                          setEditing(u);
                          setEditForm(formFromUser(u));
                          setError("");
                          setOk("");
                        }}
                      >
                        <Pencil size={14} strokeWidth={1.75} />
                        Editar
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {editing ? (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay)] p-4">
              <div className="w-full max-w-[480px] rounded-xl border border-border bg-card shadow-[0_8px_24px_#1E2C3A14]">
                <div className="space-y-1.5 px-5 pt-5">
                  <h3 className="text-[15px] font-semibold">Editar usuario</h3>
                  <p className="text-[13px] text-muted-foreground">{editing.correo}</p>
                </div>
                <div className="space-y-3 px-5 py-3">
                  <Field label="NOMBRE">
                    <Input
                      value={editForm.nombre_persona}
                      onChange={(e) => setEditForm({ ...editForm, nombre_persona: e.target.value })}
                    />
                  </Field>
                  <Field label="ROL">
                    <Select
                      value={editForm.rol}
                      disabled={editing.correo === user.correo}
                      onChange={(e) => setEditForm(applyRol(editForm, e.target.value))}
                    >
                      {ROLES.filter((r) => r.value !== "USER").map((r) => (
                        <option key={r.value} value={r.value}>
                          {r.label}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <ScopeFields form={editForm} onChange={setEditForm} gerencias={gerencias} areas={areas} />
                </div>
                <div className="flex justify-end gap-2 px-5 pb-5">
                  <Button
                    variant="outline"
                    disabled={editSaving}
                    onClick={() => {
                      setEditing(null);
                      setError("");
                    }}
                  >
                    Cancelar
                  </Button>
                  <Button disabled={editSaving} onClick={() => void saveEdit()}>
                    {editSaving ? "Guardando…" : "Guardar"}
                  </Button>
                </div>
              </div>
            </div>
          ) : null}
        </>
      ) : tab === "empleados" ? (
        <EmpleadosRoster />
      ) : (
        <>
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
            <div className="space-y-2">
              {visible.map((th) => (
                <ThreadCard
                  key={th.dni}
                  th={th}
                  open={openDnis.has(th.dni)}
                  onToggle={() => toggleThread(th.dni)}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

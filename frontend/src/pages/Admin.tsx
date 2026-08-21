import { useEffect, useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Navigate } from "react-router-dom";
import { api, qs } from "../api";
import { useApp } from "../state";
import { SnakeTimeline, type SnakePaso } from "../components/SnakeTimeline";
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
  foto_url?: string | null;
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
  const [tab, setTab] = useState<"users" | "logs">("users");
  const [users, setUsers] = useState<AppUser[]>([]);
  const [gerencias, setGerencias] = useState<string[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [threads, setThreads] = useState<Thread[]>([]);
  const [q, setQ] = useState("");
  const [openDnis, setOpenDnis] = useState<Set<string>>(() => new Set());

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

      <div className="flex gap-2 overflow-x-auto">
        <Button variant={tab === "users" ? "primary" : "outline"} onClick={() => setTab("users")} className="shrink-0">
          Usuarios
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
          <div className="grid grid-cols-1 items-end gap-3 rounded-xl border border-border bg-card p-4 sm:grid-cols-2 lg:grid-cols-[1.4fr_1.2fr_1fr_auto_auto]">
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
        <Field label="ROL" className="w-full lg:w-36">
          <Select value={form.rol} onChange={(e) => setForm({ ...form, rol: e.target.value })}>
            <option value="USER">USER</option>
            <option value="ADMIN">ADMIN</option>
          </Select>
        </Field>
        <Button onClick={addUser} className="w-full lg:w-auto">Agregar</Button>
      </div>

      <div className="space-y-3 md:hidden">
        {users.map((u) => (
          <article key={u.correo} className="rounded-xl border border-border bg-card p-3.5">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-[14px] font-semibold">{u.nombre_persona || u.nombre_usuario}</p>
                <p className="mt-0.5 truncate text-[12px] text-muted-foreground">{u.correo}</p>
                <p className="mt-1 text-[12px] text-foreground">{u.gerencia || "—"}</p>
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
            <Field label="ROL" className="mt-3">
              <Select
                value={u.rol}
                onChange={(e) => patchUser(u.correo, { rol: e.target.value })}
                disabled={u.correo === user.correo}
              >
                <option value="USER">USER</option>
                <option value="ADMIN">ADMIN</option>
              </Select>
            </Field>
          </article>
        ))}
      </div>

      <div className="hidden overflow-auto rounded-[4px] border border-border bg-card md:block">
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

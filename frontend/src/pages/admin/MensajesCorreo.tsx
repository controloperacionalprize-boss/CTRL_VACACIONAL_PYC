import { useEffect, useState } from "react";
import { api } from "../../api";
import { Alert, Button, Field, Input } from "../../components/ui";

type Clave = "doc_asunto" | "doc_cuerpo" | "jefe_asunto" | "jefe_cuerpo";
type Mensajes = Record<Clave, string>;

type Config = {
  mensajes: Mensajes;
  defaults: Mensajes;
  variables: Record<Clave, string[]>;
  correo_activo: boolean;
  copia: string[];
};

const BLOQUES: { titulo: string; ayuda: string; asunto: Clave; cuerpo: Clave }[] = [
  {
    titulo: "Documentos al trabajador",
    ayuda: "Se envía con el PDF adjunto desde Documentos → Enviar por correo.",
    asunto: "doc_asunto",
    cuerpo: "doc_cuerpo",
  },
  {
    titulo: "Aviso a jefaturas",
    ayuda: "Se envía desde Alertas → Avisar a jefaturas. {detalle} es la lista armada por el sistema.",
    asunto: "jefe_asunto",
    cuerpo: "jefe_cuerpo",
  },
];

const textareaClass =
  "mt-1 min-h-[180px] w-full rounded-[10px] border border-border bg-card px-3 py-2 font-data text-[12px] leading-relaxed outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-soft)]";

export function MensajesCorreo() {
  const [config, setConfig] = useState<Config | null>(null);
  const [form, setForm] = useState<Mensajes | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");

  useEffect(() => {
    api<Config>("/api/admin/mensajes")
      .then((c) => {
        setConfig(c);
        setForm(c.mensajes);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "No se pudieron cargar los mensajes."));
  }, []);

  async function guardar() {
    if (!form) return;
    setBusy(true);
    setError("");
    setOk("");
    try {
      const res = await api<{ mensajes: Mensajes }>("/api/admin/mensajes", {
        method: "PUT",
        body: JSON.stringify(form),
      });
      setForm(res.mensajes);
      setOk("Mensajes guardados.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron guardar los mensajes.");
    } finally {
      setBusy(false);
    }
  }

  if (error && !config) {
    return (
      <Alert tone="error" title="No se pudo abrir">
        {error}
      </Alert>
    );
  }
  if (!config || !form) return <p className="text-sm text-muted-foreground">Cargando mensajes…</p>;

  return (
    <div className="space-y-4">
      {config.correo_activo ? (
        <Alert tone="success" title="Correo activo">
          {config.copia.length ? `Cada envío va con copia a ${config.copia.join(", ")}.` : "Sin copia fija configurada (MAIL_CC)."}
        </Alert>
      ) : (
        <Alert tone="warning" title="Correo aún no configurado">
          Puedes dejar los textos listos. Para enviar, TI debe definir en el servidor MAIL_ENABLED, SMTP_HOST, SMTP_USER,
          SMTP_PASSWORD, SMTP_FROM y, si se quiere copia, MAIL_CC.
        </Alert>
      )}
      {error ? (
        <Alert tone="error" title="No se pudo guardar">
          {error}
        </Alert>
      ) : null}
      {ok ? (
        <Alert tone="success" title="Listo">
          {ok}
        </Alert>
      ) : null}

      {BLOQUES.map((b) => (
        <section key={b.titulo} className="space-y-3 rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)] sm:p-5">
          <div>
            <p className="text-[15px] font-semibold">{b.titulo}</p>
            <p className="mt-0.5 text-[12px] text-muted-foreground">{b.ayuda}</p>
            <p className="mt-1 text-[12px] text-muted-foreground">
              Variables: {config.variables[b.cuerpo].map((v) => `{${v}}`).join(" ")}
            </p>
          </div>
          <Field label="ASUNTO">
            <Input value={form[b.asunto]} maxLength={300} onChange={(e) => setForm({ ...form, [b.asunto]: e.target.value })} />
          </Field>
          <Field label="MENSAJE">
            <textarea
              className={textareaClass}
              value={form[b.cuerpo]}
              maxLength={4000}
              onChange={(e) => setForm({ ...form, [b.cuerpo]: e.target.value })}
            />
          </Field>
          <Button
            variant="ghost"
            className="h-8 px-0 text-[12px]"
            onClick={() => setForm({ ...form, [b.asunto]: config.defaults[b.asunto], [b.cuerpo]: config.defaults[b.cuerpo] })}
          >
            Restaurar texto original
          </Button>
        </section>
      ))}

      <div className="flex justify-end">
        <Button disabled={busy} onClick={() => void guardar()}>
          {busy ? "Guardando…" : "Guardar mensajes"}
        </Button>
      </div>
    </div>
  );
}

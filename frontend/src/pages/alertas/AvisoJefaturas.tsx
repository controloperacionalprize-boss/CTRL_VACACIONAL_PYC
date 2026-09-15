import { useState } from "react";
import { Mail } from "lucide-react";
import { api, qs } from "../../api";
import { useApp } from "../../state";
import { Alert, Button } from "../../components/ui";

type Jefatura = {
  correo: string;
  nombre: string;
  area: string;
  pendientes: number;
  observados: number;
  salidas: number;
  correo_valido: boolean;
};

type Vista = {
  correo_activo: boolean;
  ultimo_envio: string;
  jefaturas: Jefatura[];
  sin_novedades: number;
};

/** Reemplaza el correo manual de inicio de mes: récord pendiente y salidas del mes siguiente por jefatura. */
export function AvisoJefaturas() {
  const { filters } = useApp();
  const [vista, setVista] = useState<Vista | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");

  async function preparar() {
    setBusy("vista");
    setError("");
    setOk("");
    try {
      setVista(await api<Vista>(`/api/notificaciones/jefaturas${qs({ year: filters.year })}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo preparar el aviso.");
    } finally {
      setBusy("");
    }
  }

  async function enviar() {
    if (!vista) return;
    setBusy("enviar");
    setError("");
    try {
      const res = await api<{ enviados: number; errores: string[] }>("/api/notificaciones/jefaturas", {
        method: "POST",
        body: JSON.stringify({ year: filters.year, correos: vista.jefaturas.map((j) => j.correo) }),
      });
      const extra = res.errores.length ? ` No se pudo: ${res.errores.slice(0, 3).join(" ")}` : "";
      setOk(`Aviso enviado a ${res.enviados} jefatura(s).${extra}`);
      setVista(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo enviar el aviso.");
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)] sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-[15px] font-semibold">Avisar a jefaturas por correo</p>
          <p className="mt-1 text-[13px] text-muted-foreground">
            A cada jefatura le llega quién de su equipo no tiene el goce completo, qué planes están observados y quién
            sale de vacaciones el mes siguiente.
          </p>
          {vista?.ultimo_envio ? (
            <p className="mt-1 text-[12px] text-muted-foreground">Último envío: {vista.ultimo_envio}</p>
          ) : null}
        </div>
        <Button variant="outline" className="shrink-0" disabled={Boolean(busy)} onClick={() => void preparar()}>
          <Mail size={16} strokeWidth={1.75} />
          {busy === "vista" ? "Preparando…" : "Ver a quién se envía"}
        </Button>
      </div>

      {error ? (
        <Alert tone="error" title="No se completó" className="mt-3">
          {error}
        </Alert>
      ) : null}
      {ok ? (
        <Alert tone="success" title="Listo" className="mt-3">
          {ok}
        </Alert>
      ) : null}

      {vista ? (
        <div className="mt-4 space-y-3">
          {!vista.correo_activo ? (
            <Alert tone="warning" title="Envío por correo no configurado">
              Falta configurar SMTP en el servidor. Puedes revisar la lista, pero todavía no se puede enviar.
            </Alert>
          ) : null}
          {vista.jefaturas.length === 0 ? (
            <p className="text-[13px] text-muted-foreground">Ninguna jefatura tiene novedades para avisar.</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full min-w-[560px] text-[13px]">
                <thead className="bg-muted/60 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                  <tr>
                    {["Jefatura", "Área", "Falta programar", "Observados", "Salen el mes siguiente"].map((h) => (
                      <th key={h} className="px-3 py-2 font-semibold">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {vista.jefaturas.map((j) => (
                    <tr key={j.correo} className="border-t border-border">
                      <td className="px-3 py-2">
                        <p className="font-medium">{j.nombre}</p>
                        <p className={j.correo_valido ? "text-[11px] text-muted-foreground" : "text-[11px] text-warning"}>
                          {j.correo}
                        </p>
                      </td>
                      <td className="px-3 py-2">{j.area}</td>
                      <td className="px-3 py-2 tabular-nums">{j.pendientes}</td>
                      <td className="px-3 py-2 tabular-nums">{j.observados}</td>
                      <td className="px-3 py-2 tabular-nums">{j.salidas}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-[12px] text-muted-foreground">
              {vista.sin_novedades} jefatura(s) sin novedades no reciben correo. El texto se edita en Admin → Mensajes de correo.
            </p>
            <Button
              disabled={Boolean(busy) || !vista.correo_activo || vista.jefaturas.length === 0}
              onClick={() => void enviar()}
            >
              {busy === "enviar" ? "Enviando…" : `Enviar a ${vista.jefaturas.length} jefatura(s)`}
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

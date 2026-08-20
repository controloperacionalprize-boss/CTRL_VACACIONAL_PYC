import { useEffect, useState } from "react";
import { api } from "../api";
import type { User } from "../state";
import { Alert, Button } from "../components/ui";

type Props = { onLogin: (token: string, user: User) => void };

type Flow = {
  flow_id: string;
  user_code: string;
  verification_uri: string;
  interval: number;
};

function MicrosoftLogo() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <rect width="7.5" height="7.5" fill="#F25022" />
      <rect x="8.5" width="7.5" height="7.5" fill="#7FBA00" />
      <rect y="8.5" width="7.5" height="7.5" fill="#00A4EF" />
      <rect x="8.5" y="8.5" width="7.5" height="7.5" fill="#FFB900" />
    </svg>
  );
}

export function Login({ onLogin }: Props) {
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [flow, setFlow] = useState<Flow | null>(null);

  useEffect(() => {
    if (!flow) return;
    let stop = false;
    const wait = Math.max(3, flow.interval || 5) * 1000;
    const id = window.setInterval(async () => {
      if (stop) return;
      try {
        const data = await api<{ status: string; access_token?: string; user?: User }>(
          "/api/auth/microsoft/poll",
          { method: "POST", body: JSON.stringify({ flow_id: flow.flow_id }) }
        );
        if (data.status === "ok" && data.access_token && data.user) {
          stop = true;
          onLogin(data.access_token, data.user);
        }
      } catch (err) {
        stop = true;
        setFlow(null);
        setLoading(false);
        setError(err instanceof Error ? err.message : "No se pudo confirmar el acceso con Microsoft.");
      }
    }, wait);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, [flow, onLogin]);

  async function startMicrosoft() {
    setError("");
    setLoading(true);
    try {
      const data = await api<Flow>("/api/auth/microsoft/start", { method: "POST" });
      setFlow(data);
      window.open(data.verification_uri, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo conectar con Microsoft. Inténtalo de nuevo.");
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-background px-4">
      <div className="flex w-full max-w-[440px] flex-col gap-4 rounded-xl border border-border bg-card px-11 py-10">
        <p className="text-xs font-medium text-muted-foreground">GTH · Prize / Aquanqa</p>
        <div>
          <h1 className="text-[28px] font-semibold tracking-tight text-foreground">Vacaciones</h1>
          {!flow ? (
            <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">
              Inicia sesión con tu cuenta corporativa de Microsoft.
            </p>
          ) : (
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Abre{" "}
              <a className="text-info underline" href={flow.verification_uri} target="_blank" rel="noreferrer">
                microsoft.com/devicelogin
              </a>{" "}
              e ingresa este código:
            </p>
          )}
        </div>

        {!flow ? (
          <button
            type="button"
            onClick={startMicrosoft}
            disabled={loading}
            className="flex h-10 w-full items-center justify-center gap-3 rounded-[8px] border border-border bg-card text-sm font-medium text-foreground hover:bg-muted disabled:opacity-50"
          >
            <MicrosoftLogo />
            Iniciar sesión con Microsoft
          </button>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-center rounded-[8px] border border-border bg-muted py-4">
              <span className="font-data text-[22px] font-semibold tracking-[0.25em] text-foreground">{flow.user_code}</span>
            </div>
            <p className="text-xs text-muted-foreground">Esperando confirmación en Microsoft…</p>
            <Button
              variant="ghost"
              className="w-fit px-0"
              onClick={() => {
                setFlow(null);
                setLoading(false);
              }}
            >
              Cancelar
            </Button>
          </div>
        )}

        {error ? (
          <Alert tone="error" title="No se pudo iniciar sesión">
            {error}
          </Alert>
        ) : null}
      </div>
    </div>
  );
}

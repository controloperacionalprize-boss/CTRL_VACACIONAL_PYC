import { useEffect, useMemo, useRef, useState } from "react";
import { Bell, BellOff, Check, RotateCcw } from "lucide-react";
import { Link } from "react-router-dom";
import { useApp } from "../state";
import { Button, cn } from "./ui";
import {
  browserPermission,
  inboxItems,
  markAttended,
  markPending,
  markSeen,
  maybePushBrowserAlerts,
  pendingBadgeCount,
  prioridadClass,
  prioridadLabel,
  relativeFrom,
  requestBrowserPermission,
  type AlertItem,
  type InboxEntry,
  type InboxStatus,
} from "../lib/alerts";

const TABS: { id: InboxStatus; label: string }[] = [
  { id: "nueva", label: "Nuevas" },
  { id: "pendiente", label: "Pendientes" },
  { id: "atendida", label: "Atendidas" },
];

function grouped(items: AlertItem[], inbox: Record<string, InboxEntry>, tab: InboxStatus) {
  return items.filter((i) => (inbox[i.id]?.status || "nueva") === tab);
}

function ctaLabel(item: AlertItem) {
  return item.accion || "Ver listado";
}

export function NotificationsBell() {
  const { user, filters, alerts, inbox, setInbox } = useApp();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<InboxStatus>("nueva");
  const [perm, setPerm] = useState(() => browserPermission());
  const boxRef = useRef<HTMLDivElement>(null);
  const correo = user?.correo || "";
  const year = filters.year;
  const items = inboxItems(alerts?.items || []);
  const badge = pendingBadgeCount(items, inbox);

  useEffect(() => {
    if (!correo || !items.length) return;
    maybePushBrowserAlerts(correo, items);
  }, [correo, items]);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  function openPanel() {
    setOpen(true);
    if (!correo) return;
    const nuevas = items.filter((i) => (inbox[i.id]?.status || "nueva") === "nueva").map((i) => i.id);
    if (nuevas.length) {
      setInbox(markSeen(correo, year, nuevas));
      setTab("pendiente");
    }
  }

  const visible = useMemo(() => grouped(items, inbox, tab), [items, inbox, tab]);
  const counts = useMemo(
    () => ({
      nueva: grouped(items, inbox, "nueva").length,
      pendiente: grouped(items, inbox, "pendiente").length,
      atendida: grouped(items, inbox, "atendida").length,
    }),
    [items, inbox]
  );

  async function enableBrowser() {
    const next = await requestBrowserPermission();
    setPerm(next);
    if (next === "granted") maybePushBrowserAlerts(correo, items);
  }

  return (
    <div className="relative" ref={boxRef}>
      <button
        type="button"
        onClick={() => (open ? setOpen(false) : openPanel())}
        className={cn(
          "relative inline-flex h-9 w-9 items-center justify-center rounded-[10px] text-muted-foreground hover:bg-muted hover:text-foreground",
          open ? "bg-muted text-foreground" : ""
        )}
        aria-label={badge ? `Alertas, ${badge} pendientes` : "Alertas"}
      >
        <Bell size={18} strokeWidth={1.75} />
        {badge > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-error px-1 text-[10px] font-semibold text-error-foreground">
            {badge > 9 ? "9+" : badge}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="absolute right-0 z-50 mt-2 w-[min(100vw-2rem,24rem)] overflow-hidden rounded-xl border border-border bg-card shadow-[0_8px_28px_#0f1c2e18]">
          <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
            <div>
              <p className="text-[14px] font-semibold">Alertas</p>
              <p className="text-[11px] text-muted-foreground">Qué requiere tu acción hoy</p>
            </div>
            <Link
              to="/alertas"
              onClick={() => setOpen(false)}
              className="text-[12px] font-semibold text-primary no-underline hover:underline"
            >
              Ver todas
            </Link>
          </div>
          <div className="flex border-b border-border">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={cn(
                  "flex-1 px-2 py-2 text-[12px] font-semibold",
                  tab === t.id ? "border-b-2 border-primary text-primary" : "text-muted-foreground"
                )}
              >
                {t.label}
                {counts[t.id] ? <span className="ml-1 tabular-nums">({counts[t.id]})</span> : null}
              </button>
            ))}
          </div>
          <div className="max-h-[min(24rem,60vh)] overflow-auto">
            {visible.length === 0 ? (
              <p className="px-4 py-8 text-center text-[13px] text-muted-foreground">
                {tab === "nueva"
                  ? "No hay alertas nuevas en tu alcance."
                  : tab === "pendiente"
                    ? "Nada pendiente de atender."
                    : "Aún no marcas alertas como atendidas."}
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {visible.map((item) => (
                  <li key={item.id} className="px-4 py-3">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-[13px] font-semibold leading-snug">{item.titulo}</p>
                      <span className={cn("shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium", prioridadClass(item.prioridad))}>
                        {prioridadLabel(item.prioridad)}
                      </span>
                    </div>
                    <p className="mt-1 text-[12px] leading-snug text-muted-foreground">{item.descripcion}</p>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      {item.count} {item.count === 1 ? "persona" : "personas"}
                      {inbox[item.id]?.firstSeenAt ? ` · ${relativeFrom(inbox[item.id].firstSeenAt)}` : ""}
                    </p>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <Link
                        to={item.href}
                        onClick={() => setOpen(false)}
                        className="inline-flex h-8 items-center rounded-[10px] bg-primary px-3 text-[12px] font-semibold text-primary-foreground no-underline"
                      >
                        {ctaLabel(item)}
                      </Link>
                      {tab === "atendida" ? (
                        <button
                          type="button"
                          className="inline-flex h-8 items-center gap-1 rounded-[10px] px-2 text-[12px] font-medium text-muted-foreground hover:text-foreground"
                          onClick={() => setInbox(markPending(correo, year, item.id))}
                        >
                          <RotateCcw size={13} strokeWidth={1.75} />
                          Reabrir
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="inline-flex h-8 items-center gap-1 rounded-[10px] px-2 text-[12px] font-medium text-muted-foreground hover:text-foreground"
                          onClick={() => setInbox(markAttended(correo, year, item.id))}
                        >
                          <Check size={13} strokeWidth={1.75} />
                          Atendida
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="border-t border-border bg-muted/40 px-4 py-2.5">
            {perm === "unsupported" ? (
              <p className="text-[11px] text-muted-foreground">Este navegador no admite avisos de escritorio.</p>
            ) : perm === "denied" ? (
              <p className="flex items-start gap-1.5 text-[11px] text-muted-foreground">
                <BellOff size={12} strokeWidth={1.75} className="mt-0.5 shrink-0" />
                El navegador bloqueó los avisos. Puedes habilitarlos en la configuración del sitio.
              </p>
            ) : perm === "granted" ? (
              <p className="text-[11px] text-muted-foreground">Avisos del navegador activos para alertas importantes y críticas.</p>
            ) : (
              <Button variant="ghost" className="h-8 px-0 text-[12px]" onClick={() => void enableBrowser()}>
                <Bell size={14} strokeWidth={1.75} />
                Activar avisos del navegador
              </Button>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

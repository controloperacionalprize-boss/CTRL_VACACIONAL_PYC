import type { ButtonHTMLAttributes, ReactNode, SelectHTMLAttributes, InputHTMLAttributes } from "react";

export function cn(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

type BtnVariant = "primary" | "outline" | "ghost" | "destructive";

export function Button({
  variant = "primary",
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant }) {
  const styles: Record<BtnVariant, string> = {
    primary: "bg-primary text-primary-foreground hover:opacity-90",
    outline: "bg-card text-foreground border border-border hover:bg-muted",
    ghost: "bg-transparent text-muted-foreground hover:text-foreground",
    destructive: "bg-error text-error-foreground hover:opacity-90",
  };
  return (
    <button
      type="button"
      className={cn(
        "inline-flex h-10 items-center justify-center gap-2 rounded-[10px] px-4 text-sm font-semibold disabled:opacity-50",
        styles[variant],
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

const fieldControl =
  "mt-1 h-9 w-full rounded-[10px] border border-border bg-card px-3 text-[13px] text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-soft)]";

export function Field({
  label,
  className,
  children,
}: {
  label?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <label className={cn("block min-w-0", className)}>
      {label ? (
        <span className="text-[11px] font-semibold tracking-wide text-muted-foreground">{label}</span>
      ) : null}
      {children}
    </label>
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(fieldControl, className)} {...props} />;
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(fieldControl, className)} {...props} />;
}

export function Kpi({
  label,
  value,
  hint,
  icon,
  className,
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("rounded-xl border border-border bg-card p-3.5 shadow-[var(--shadow-card)] md:p-4", className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold tracking-wide text-muted-foreground">{label}</div>
          <div className="font-data mt-1.5 text-[24px] font-semibold leading-none text-foreground md:text-[28px]">{value}</div>
          {hint ? <div className="mt-1.5 hidden text-[11px] text-muted-foreground sm:block">{hint}</div> : null}
        </div>
        {icon ? (
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-[var(--primary-soft)] text-primary md:h-9 md:w-9">
            {icon}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function PageHeader({ title, help }: { title: string; help?: string }) {
  return (
    <div>
      <h2 className="text-[22px] font-semibold tracking-tight text-foreground">{title}</h2>
      {help ? <p className="mt-1.5 text-[13px] text-muted-foreground">{help}</p> : null}
    </div>
  );
}

export function Alert({
  tone,
  title,
  children,
  className,
}: {
  tone: "error" | "success" | "warning";
  title: string;
  children?: ReactNode;
  className?: string;
}) {
  const box = {
    error: "bg-error-muted border-error text-foreground",
    success: "bg-success-muted border-success text-foreground",
    warning: "bg-warning-muted border-warning text-foreground",
  }[tone];
  const icon = { error: "circle-alert", success: "circle-check", warning: "triangle-alert" }[tone];
  const color = {
    error: "text-error",
    success: "text-success",
    warning: "text-warning",
  }[tone];
  return (
    <div className={cn("flex gap-3 rounded-[10px] border px-3.5 py-3.5", box, className)}>
      <AlertIcon name={icon} className={cn("mt-0.5 h-[18px] w-[18px] shrink-0", color)} />
      <div className="min-w-0">
        <p className="text-[13px] font-semibold">{title}</p>
        {children ? <div className="mt-1 text-xs text-muted-foreground">{children}</div> : null}
      </div>
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card px-8 py-10 text-center shadow-[var(--shadow-card)]">
      <svg className="mb-2 h-7 w-7 text-muted-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
      </svg>
      <p className="text-base font-semibold">{title}</p>
      <p className="mt-1 max-w-sm text-[13px] text-muted-foreground">{body}</p>
    </div>
  );
}

function AlertIcon({ name, className }: { name: string; className?: string }) {
  const paths: Record<string, ReactNode> = {
    "circle-alert": (
      <>
        <circle cx="12" cy="12" r="10" />
        <line x1="12" x2="12" y1="8" y2="12" />
        <line x1="12" x2="12.01" y1="16" y2="16" />
      </>
    ),
    "circle-check": (
      <>
        <circle cx="12" cy="12" r="10" />
        <path d="m9 12 2 2 4-4" />
      </>
    ),
    "triangle-alert": (
      <>
        <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" />
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
      </>
    ),
  };
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
}

export function Icon({
  name,
  className,
}: {
  name:
    | "calendar-range"
    | "layout-dashboard"
    | "calendar"
    | "file-spreadsheet"
    | "log-out"
    | "calendar-plus"
    | "download"
    | "loader";
  className?: string;
}) {
  const d: Record<string, ReactNode> = {
    "calendar-range": (
      <>
        <rect width="18" height="18" x="3" y="4" rx="2" />
        <path d="M16 2v4M8 2v4M3 10h18M17 14h-6M13 18H7M7 14h.01M17 18h.01" />
      </>
    ),
    "layout-dashboard": (
      <>
        <rect width="7" height="9" x="3" y="3" rx="1" />
        <rect width="7" height="5" x="14" y="3" rx="1" />
        <rect width="7" height="9" x="14" y="12" rx="1" />
        <rect width="7" height="5" x="3" y="16" rx="1" />
      </>
    ),
    calendar: (
      <>
        <path d="M8 2v4M16 2v4M3 10h18" />
        <rect width="18" height="18" x="3" y="4" rx="2" />
      </>
    ),
    "file-spreadsheet": (
      <>
        <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
        <path d="M14 2v4a2 2 0 0 0 2 2h4M8 13h2M14 13h2M8 17h2M14 17h2" />
      </>
    ),
    "log-out": (
      <>
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
        <polyline points="16 17 21 12 16 7" />
        <line x1="21" x2="9" y1="12" y2="12" />
      </>
    ),
    "calendar-plus": (
      <>
        <path d="M8 2v4M16 2v4M3 10h18" />
        <rect width="18" height="18" x="3" y="4" rx="2" />
        <path d="M10 16h4M12 14v4" />
      </>
    ),
    download: (
      <>
        <path d="M12 15V3" />
        <path d="m7 10 5 5 5-5" />
        <path d="M5 21h14" />
      </>
    ),
    loader: (
      <>
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
      </>
    ),
  };
  return (
    <svg className={cn("h-4 w-4", className)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      {d[name]}
    </svg>
  );
}

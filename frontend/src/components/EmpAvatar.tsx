import { useState } from "react";
import { cn } from "./ui";

function initials(nombre: string) {
  const parts = nombre.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase();
}

export function EmpAvatar({
  nombre,
  fotoUrl,
  className = "h-8 w-8 text-[10px]",
}: {
  nombre: string;
  fotoUrl?: string | null;
  className?: string;
}) {
  const [broken, setBroken] = useState(false);
  const show = Boolean(fotoUrl) && !broken;
  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-[var(--primary-soft)] font-semibold text-primary",
        className
      )}
    >
      {show ? (
        <img src={fotoUrl!} alt="" className="h-full w-full object-cover" onError={() => setBroken(true)} />
      ) : (
        initials(nombre)
      )}
    </div>
  );
}

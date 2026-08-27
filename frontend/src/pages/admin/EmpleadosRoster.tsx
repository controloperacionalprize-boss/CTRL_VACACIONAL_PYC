import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronLeft, ChevronRight, ChevronsUpDown, Filter, MoreVertical, Search } from "lucide-react";
import { api, qs } from "../../api";
import { formatFechaIso } from "../../lib/dates";
import { useApp } from "../../state";
import { Button, cn, EmptyState, Field, Select } from "../../components/ui";

type RosterEmp = {
  dni: string;
  nombre: string;
  empresa: string;
  gerencia: string;
  area: string;
  cargo_actual: string;
  fecha_ingreso: string | null;
  foto_url?: string | null;
};

const PAGE_SIZES = [10, 25, 50];
const AVATAR_TONES = [
  "bg-[#ede9fe] text-[#6d28d9]",
  "bg-[#ffedd5] text-[#c2410c]",
  "bg-[#dcfce7] text-[#15803d]",
  "bg-[#dbeafe] text-[#1d4ed8]",
  "bg-[#fce7f3] text-[#be185d]",
  "bg-[#e0e7ff] text-[#4338ca]",
];

function initials(nombre: string) {
  const parts = nombre.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase();
}

function avatarTone(key: string) {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h + key.charCodeAt(i) * (i + 1)) % AVATAR_TONES.length;
  return AVATAR_TONES[h];
}

function RosterAvatar({ nombre, dni, fotoUrl }: { nombre: string; dni: string; fotoUrl?: string | null }) {
  const [broken, setBroken] = useState(false);
  const show = Boolean(fotoUrl) && !broken;
  return (
    <span
      className={cn(
        "inline-flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-full text-[10px] font-semibold",
        show ? "bg-muted" : avatarTone(dni || nombre)
      )}
    >
      {show ? (
        <img
          src={fotoUrl!}
          alt=""
          loading="lazy"
          decoding="async"
          className="h-full w-full object-cover"
          onError={() => setBroken(true)}
        />
      ) : (
        initials(nombre)
      )}
    </span>
  );
}

function pageItems(current: number, total: number): Array<number | "…"> {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  if (current <= 3) return [1, 2, 3, 4, 5, "…", total];
  if (current >= total - 2) return [1, "…", total - 4, total - 3, total - 2, total - 1, total];
  return [1, "…", current - 1, current, current + 1, "…", total];
}

function SortHead({
  label,
  active,
  dir,
  onClick,
}: {
  label: string;
  active: boolean;
  dir: "asc" | "desc";
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 text-left text-[11px] font-semibold uppercase tracking-wide text-muted-foreground hover:text-foreground"
    >
      {label}
      <ChevronsUpDown
        size={13}
        strokeWidth={1.75}
        className={active ? "text-primary" : "opacity-40"}
        aria-hidden
      />
      <span className="sr-only">{active ? (dir === "asc" ? "ascendente" : "descendente") : "ordenar"}</span>
    </button>
  );
}

export function EmpleadosRoster() {
  const { user, filters, setFilters, options } = useApp();
  const [items, setItems] = useState<RosterEmp[]>([]);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [sort, setSort] = useState<"nombre" | "fecha_ingreso">("nombre");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [menuDni, setMenuDni] = useState<string | null>(null);
  const [copied, setCopied] = useState("");
  const filterRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLTableCellElement>(null);

  const activeFilters = [
    !filters.empresas.includes("TODAS"),
    Boolean(user?.is_admin && !filters.gerencias.includes("TODAS")),
    !filters.areas.includes("TODAS"),
  ].filter(Boolean).length;

  const rangeLabel =
    total === 0
      ? "0 colaboradores"
      : `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} de ${total} colaboradores`;

  useEffect(() => {
    const t = window.setTimeout(() => {
      const next = q.trim();
      setQuery((prev) => {
        if (prev !== next) setPage(1);
        return next;
      });
    }, 300);
    return () => window.clearTimeout(t);
  }, [q]);

  useEffect(() => {
    setPage(1);
  }, [filters.empresas, filters.gerencias, filters.areas, pageSize]);

  useEffect(() => {
    const params = {
      empresa: filters.empresas.includes("TODAS") ? undefined : filters.empresas,
      gerencia: filters.gerencias.includes("TODAS") ? undefined : filters.gerencias,
      area: filters.areas.includes("TODAS") ? undefined : filters.areas,
      q: query || undefined,
      page,
      page_size: pageSize,
      photos: true,
      sort,
      order,
    };
    let cancelled = false;
    setLoading(true);
    setError("");
    api<{ items: RosterEmp[]; total: number; pages: number }>(`/api/employees${qs(params)}`)
      .then((r) => {
        if (cancelled) return;
        setItems(r.items || []);
        setTotal(r.total || 0);
        setPages(Math.max(1, r.pages || 1));
      })
      .catch((e) => {
        if (cancelled) return;
        setItems([]);
        setTotal(0);
        setError(e instanceof Error ? e.message : "No se pudieron cargar los empleados.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filters.empresas, filters.gerencias, filters.areas, query, page, pageSize, sort, order]);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      const t = e.target as Node;
      if (!filterRef.current?.contains(t)) setFiltersOpen(false);
      if (!menuRef.current?.contains(t)) setMenuDni(null);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const numbers = useMemo(() => pageItems(page, pages), [page, pages]);

  function toggleSort(col: "nombre" | "fecha_ingreso") {
    if (sort === col) setOrder((o) => (o === "asc" ? "desc" : "asc"));
    else {
      setSort(col);
      setOrder("asc");
    }
    setPage(1);
  }

  async function copyDni(dni: string) {
    try {
      await navigator.clipboard.writeText(dni);
      setCopied(dni);
      window.setTimeout(() => setCopied(""), 1500);
    } catch {
      setCopied("");
    }
    setMenuDni(null);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative min-w-0 flex-1">
          <Search
            size={16}
            strokeWidth={1.75}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar por nombre, DNI, área, cargo o gerencia..."
            className="h-10 w-full rounded-[10px] border border-border bg-card pl-9 pr-3 text-[13px] text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-soft)]"
          />
        </div>
        <div className="flex items-center justify-between gap-3 lg:justify-end">
          <div ref={filterRef} className="relative">
            <Button variant="outline" className="h-10 bg-card" onClick={() => setFiltersOpen((v) => !v)}>
              <Filter size={16} strokeWidth={1.75} className="text-primary" />
              Filtros
              {activeFilters > 0 ? (
                <span className="ml-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground">
                  {activeFilters}
                </span>
              ) : null}
            </Button>
            {filtersOpen ? (
              <div className="absolute right-0 z-30 mt-1 w-[min(100vw-2rem,280px)] space-y-2 rounded-xl border border-border bg-card p-3 shadow-[var(--shadow-card)]">
                <Field label="EMPRESA">
                  <Select
                    value={filters.empresas.includes("TODAS") ? "TODAS" : filters.empresas[0]}
                    onChange={(e) =>
                      setFilters({
                        ...filters,
                        empresas: e.target.value === "TODAS" ? ["TODAS"] : [e.target.value],
                      })
                    }
                  >
                    <option value="TODAS">Todas</option>
                    {options.empresas.map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </Select>
                </Field>
                {user?.is_admin ? (
                  <Field label="GERENCIA">
                    <Select
                      value={filters.gerencias.includes("TODAS") ? "TODAS" : filters.gerencias[0]}
                      onChange={(e) =>
                        setFilters({
                          ...filters,
                          gerencias: e.target.value === "TODAS" ? ["TODAS"] : [e.target.value],
                        })
                      }
                    >
                      <option value="TODAS">Todas</option>
                      {options.gerencias.map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </Select>
                  </Field>
                ) : null}
                <Field label="ÁREA">
                  <Select
                    value={filters.areas.includes("TODAS") ? "TODAS" : filters.areas[0]}
                    onChange={(e) =>
                      setFilters({
                        ...filters,
                        areas: e.target.value === "TODAS" ? ["TODAS"] : [e.target.value],
                      })
                    }
                  >
                    <option value="TODAS">Todas</option>
                    {options.areas.map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
            ) : null}
          </div>
          <p className="whitespace-nowrap text-[12px] text-muted-foreground">{loading ? "Cargando…" : rangeLabel}</p>
        </div>
      </div>

      {error ? <p className="text-[13px] text-error">{error}</p> : null}

      {loading && items.length === 0 ? (
        <p className="text-sm text-muted-foreground">Cargando colaboradores…</p>
      ) : items.length === 0 ? (
        <EmptyState
          title="Sin colaboradores en este filtro"
          body="Cambia los filtros o prueba otra búsqueda."
        />
      ) : (
        <>
          <div className="overflow-auto rounded-[12px] border border-border bg-card shadow-[var(--shadow-card)]">
            <table className="w-full min-w-[860px] text-left text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-4 py-3">
                    <SortHead label="Nombre" active={sort === "nombre"} dir={order} onClick={() => toggleSort("nombre")} />
                  </th>
                  <th className="px-3 py-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    DNI
                  </th>
                  <th className="px-3 py-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    Gerencia
                  </th>
                  <th className="px-3 py-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    Área
                  </th>
                  <th className="px-3 py-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    Cargo
                  </th>
                  <th className="px-3 py-3">
                    <SortHead
                      label="Fecha de ingreso"
                      active={sort === "fecha_ingreso"}
                      dir={order}
                      onClick={() => toggleSort("fecha_ingreso")}
                    />
                  </th>
                  <th className="w-10 px-2 py-3" />
                </tr>
              </thead>
              <tbody>
                {items.map((e) => (
                  <tr key={e.dni} className="border-b border-border last:border-b-0 hover:bg-muted/40">
                    <td className="px-4 py-2.5">
                      <span className="inline-flex min-w-0 items-center gap-2.5">
                        <RosterAvatar nombre={e.nombre} dni={e.dni} fotoUrl={e.foto_url} />
                        <span className="truncate font-semibold uppercase tracking-wide">{e.nombre}</span>
                      </span>
                    </td>
                    <td className="px-3 py-2.5 font-data text-[12px] text-muted-foreground">{e.dni}</td>
                    <td className="px-3 py-2.5 uppercase">{e.gerencia || "—"}</td>
                    <td className="px-3 py-2.5 uppercase">{e.area || "—"}</td>
                    <td className="px-3 py-2.5 uppercase">{e.cargo_actual || "—"}</td>
                    <td className="px-3 py-2.5 tabular-nums">{formatFechaIso(e.fecha_ingreso)}</td>
                    <td className="relative px-2 py-2.5" ref={menuDni === e.dni ? menuRef : undefined}>
                      <button
                        type="button"
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                        aria-label={`Acciones de ${e.nombre}`}
                        onClick={() => setMenuDni((cur) => (cur === e.dni ? null : e.dni))}
                      >
                        <MoreVertical size={16} strokeWidth={1.75} />
                      </button>
                      {menuDni === e.dni ? (
                        <div className="absolute right-3 z-20 mt-1 w-40 rounded-lg border border-border bg-card py-1 shadow-[var(--shadow-card)]">
                          <button
                            type="button"
                            className="block w-full px-3 py-2 text-left text-[13px] hover:bg-muted"
                            onClick={() => void copyDni(e.dni)}
                          >
                            {copied === e.dni ? "DNI copiado" : "Copiar DNI"}
                          </button>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <label className="flex items-center gap-2 text-[12px] text-muted-foreground">
              Resultados por página
              <span className="relative">
                <select
                  value={pageSize}
                  onChange={(e) => setPageSize(Number(e.target.value))}
                  className="h-9 appearance-none rounded-[10px] border border-border bg-card py-0 pl-3 pr-8 text-[13px] text-foreground outline-none"
                >
                  {PAGE_SIZES.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
                <ChevronDown
                  size={14}
                  className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground"
                />
              </span>
            </label>

            <div className="flex flex-wrap items-center justify-center gap-1">
              <button
                type="button"
                disabled={loading || page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="inline-flex h-9 items-center gap-1 rounded-md px-2 text-[13px] text-muted-foreground hover:text-foreground disabled:opacity-40"
              >
                <ChevronLeft size={16} />
                Anterior
              </button>
              {numbers.map((n, i) =>
                n === "…" ? (
                  <span key={`e${i}`} className="px-1 text-[13px] text-muted-foreground">
                    …
                  </span>
                ) : (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setPage(n)}
                    className={cn(
                      "inline-flex h-8 min-w-8 items-center justify-center rounded-md px-2 text-[13px] font-medium",
                      n === page ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-muted"
                    )}
                  >
                    {n}
                  </button>
                )
              )}
              <button
                type="button"
                disabled={loading || page >= pages}
                onClick={() => setPage((p) => p + 1)}
                className="inline-flex h-9 items-center gap-1 rounded-md px-2 text-[13px] text-muted-foreground hover:text-foreground disabled:opacity-40"
              >
                Siguiente
                <ChevronRight size={16} />
              </button>
            </div>

            <p className="text-center text-[12px] text-muted-foreground lg:text-right">{rangeLabel}</p>
          </div>
        </>
      )}
    </div>
  );
}

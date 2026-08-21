import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

/** Port simplificado de TrackingTimelineFolios SnakeTimeline (+ snakeCapsules / timelineUtils). */

export type SnakePaso = {
  id: string;
  numero: number;
  titulo: string;
  detalle?: string;
  usuario?: string;
  iniciales?: string;
  fotoUrl?: string | null;
  fecha?: string;
};

const PASOS_POR_FILA = 4;
const NODE_RADIUS = 18;
const DASH_ARRAY = "8 6";
const LINE_COLOR_DEFAULT = "#1a56db";

type Point = { x: number; y: number };

type PathSeg = {
  d: string;
  color: string;
  marker: string;
};

function calcPasosPorFila(width: number) {
  const viewport = typeof window !== "undefined" ? window.innerWidth : 1280;
  if (viewport < 640) return 2;
  if (width < 520) return 2;
  if (width < 780) return 3;
  return PASOS_POR_FILA;
}

function dividirEnFilas(pasos: SnakePaso[], pasosPorFila: number) {
  const filas: {
    indice: number;
    slots: Array<SnakePaso | null>;
  }[] = [];

  for (let i = 0; i < pasos.length; i += pasosPorFila) {
    const indiceFila = filas.length;
    const chunk = pasos.slice(i, i + pasosPorFila);
    const rtl = indiceFila % 2 === 1;
    const slots: Array<SnakePaso | null> = Array.from({ length: pasosPorFila }, () => null);

    if (!rtl) {
      chunk.forEach((paso, idx) => {
        slots[idx] = paso;
      });
    } else {
      const rev = [...chunk].reverse();
      const start = pasosPorFila - rev.length;
      rev.forEach((paso, idx) => {
        slots[start + idx] = paso;
      });
    }

    filas.push({ indice: indiceFila, slots });
  }

  return filas;
}

function buildCurvePath(a: Point, b: Point, side: "right" | "left", compact: boolean) {
  const ax = side === "right" ? a.x + NODE_RADIUS * 0.35 : a.x - NODE_RADIUS * 0.35;
  const bx = side === "right" ? b.x + NODE_RADIUS + 5 : b.x - NODE_RADIUS - 5;
  const ay = a.y;
  const by = b.y;
  const dy = Math.abs(by - ay);
  const chord = Math.hypot(bx - ax, by - ay);
  const radius = Math.max(chord / 2 + 0.5, dy / 2, compact ? 22 : 28);
  const sweep = side === "right" ? 1 : 0;
  return `M ${ax} ${ay} A ${radius} ${radius} 0 0 ${sweep} ${bx} ${by}`;
}

function acortarFinal(a: Point, b: Point, dist: number): Point {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  return { x: b.x - (dx / len) * dist, y: b.y - (dy / len) * dist };
}

function PasoLabel({
  paso,
  compact,
}: {
  paso: SnakePaso;
  compact: boolean;
}) {
  return (
    <div className={`relative text-center ${compact ? "px-0.5" : "px-1"}`}>
      <div className="relative z-10 flex flex-col items-center gap-0.5 leading-tight">
        <p
          className={`font-semibold leading-tight text-foreground ${compact ? "line-clamp-2 text-[10px]" : "truncate text-[11px]"}`}
          title={paso.titulo}
        >
          {paso.titulo}
        </p>
        {paso.detalle ? (
          <p className={`font-data leading-tight text-foreground ${compact ? "text-[10px]" : "text-[11px]"}`}>
            {paso.detalle}
          </p>
        ) : null}
        {paso.usuario ? (
          <div className="flex max-w-full items-center justify-center gap-0.5" title={paso.usuario}>
            <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary/15 text-[7px] font-semibold text-primary">
              {paso.fotoUrl ? (
                <img src={paso.fotoUrl} alt="" className="h-full w-full object-cover" />
              ) : (
                paso.iniciales || "?"
              )}
            </span>
            <p className={`min-w-0 font-medium leading-tight text-muted-foreground ${compact ? "line-clamp-1 text-[9px]" : "truncate text-[10px]"}`}>
              {paso.usuario}
            </p>
          </div>
        ) : null}
        {paso.fecha ? (
          <p className={`tabular-nums leading-tight text-muted-foreground ${compact ? "text-[8px]" : "text-[9px]"}`}>
            {paso.fecha}
          </p>
        ) : null}
      </div>
    </div>
  );
}

export function SnakeTimeline({
  pasos,
  lineColor = LINE_COLOR_DEFAULT,
}: {
  pasos: SnakePaso[];
  lineColor?: string;
}) {
  const svgUid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const containerRef = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [pasosPorFila, setPasosPorFila] = useState(() =>
    typeof window !== "undefined" && window.innerWidth < 640 ? 2 : PASOS_POR_FILA
  );
  const [svgSize, setSvgSize] = useState({ w: 0, h: 0 });
  const [segments, setSegments] = useState<PathSeg[]>([]);
  const [pathsReady, setPathsReady] = useState(false);
  const measureRetries = useRef(0);

  const filas = useMemo(() => dividirEnFilas(pasos, pasosPorFila), [pasos, pasosPorFila]);
  const compact = pasosPorFila <= 2;
  const multi = filas.length > 1;
  const curvaIzq = filas.length > 2;
  const gridCols = `repeat(${pasosPorFila}, minmax(0, 1fr))`;
  const markerId = `flecha-${svgUid}`;

  const updatePaths = useCallback(() => {
    const container = containerRef.current;
    if (!container || pasos.length === 0) {
      setSegments([]);
      setPathsReady(true);
      measureRetries.current = 0;
      return;
    }

    const cRect = container.getBoundingClientRect();
    setSvgSize({ w: container.offsetWidth, h: container.offsetHeight });

    const centers = new Map<string, Point>();
    for (const paso of pasos) {
      const el = nodeRefs.current[paso.id];
      if (!el) continue;
      const rect = el.getBoundingClientRect();
      centers.set(paso.id, {
        x: rect.left + rect.width / 2 - cRect.left,
        y: rect.top + rect.height / 2 - cRect.top,
      });
    }

    if (centers.size < pasos.length && measureRetries.current < 10) {
      measureRetries.current += 1;
      setPathsReady(false);
      requestAnimationFrame(() => updatePaths());
      return;
    }
    measureRetries.current = 0;

    const cols = pasosPorFila;
    const next: PathSeg[] = [];
    for (let i = 0; i < pasos.length - 1; i++) {
      const from = pasos[i];
      const to = pasos[i + 1];
      const a = centers.get(from.id);
      const b = centers.get(to.id);
      if (!a || !b) continue;

      const rowFrom = Math.floor(i / cols);
      const sameRow = rowFrom === Math.floor((i + 1) / cols);
      const side: "right" | "left" = rowFrom % 2 === 0 ? "right" : "left";

      if (sameRow) {
        const fin = acortarFinal(a, b, NODE_RADIUS + 5);
        next.push({
          d: `M ${a.x} ${a.y} L ${fin.x} ${fin.y}`,
          color: lineColor,
          marker: markerId,
        });
      } else {
        next.push({
          d: buildCurvePath(a, b, side, compact),
          color: lineColor,
          marker: markerId,
        });
      }
    }

    setSegments(next);
    setPathsReady(true);
  }, [pasos, pasosPorFila, compact, lineColor, markerId]);

  const pasosKey = useMemo(() => pasos.map((p) => p.id).join(","), [pasos]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    let lastW = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const relayout = () => {
      measureRetries.current = 0;
      setPathsReady(false);
      requestAnimationFrame(() => requestAnimationFrame(updatePaths));
    };

    const sync = (width: number) => {
      const next = calcPasosPorFila(width);
      setPasosPorFila((prev) => (prev === next ? prev : next));
      clearTimeout(timer);
      timer = setTimeout(relayout, 40);
    };

    lastW = el.getBoundingClientRect().width;
    setPasosPorFila(calcPasosPorFila(lastW));

    const ro = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect?.width ?? 0;
      if (Math.abs(width - lastW) < 0.5) return;
      lastW = width;
      sync(width);
    });
    ro.observe(el);
    relayout();

    return () => {
      clearTimeout(timer);
      ro.disconnect();
    };
  }, [updatePaths, pasosKey]);

  if (pasos.length === 0) {
    return <p className="py-6 text-center text-sm text-muted-foreground">Sin cambios</p>;
  }

  return (
    <div
      ref={containerRef}
      className={`relative w-full [contain:layout] ${multi ? (compact ? "pr-6" : "pr-12") : ""} ${curvaIzq ? (compact ? "pl-6" : "pl-12") : ""}`}
    >
      <svg
        className={`pointer-events-none absolute inset-0 z-0 h-full w-full overflow-visible transition-opacity ${pathsReady ? "opacity-100" : "opacity-0"}`}
        height={svgSize.h || undefined}
        aria-hidden
      >
        <defs>
          <marker
            id={markerId}
            markerWidth="7"
            markerHeight="7"
            refX="5.5"
            refY="3.5"
            orient="auto"
            markerUnits="userSpaceOnUse"
          >
            <path d="M 0 0 L 7 3.5 L 0 7 z" fill={lineColor} />
          </marker>
        </defs>
        {segments.map((seg, idx) => (
          <path
            key={idx}
            d={seg.d}
            stroke={seg.color}
            strokeWidth="2.5"
            strokeOpacity="0.9"
            strokeLinecap="round"
            fill="none"
            strokeDasharray={DASH_ARRAY}
            markerEnd={`url(#${seg.marker})`}
          />
        ))}
      </svg>

      <div className={`relative z-10 flex flex-col ${multi ? (compact ? "gap-y-8" : "gap-y-10") : "gap-y-0"}`}>
        {filas.map((fila) => (
          <div key={`${fila.indice}-${pasosPorFila}`} className="relative w-full">
            <div
              className={`mb-2 grid items-end ${compact ? "min-h-[3.75rem] gap-x-2" : "min-h-[4rem] gap-x-3"}`}
              style={{ gridTemplateColumns: gridCols }}
            >
              {fila.slots.map((slot, slotIdx) => (
                <div key={`top-${fila.indice}-${slotIdx}`} className="min-w-0 self-end">
                  {slot ? <PasoLabel paso={slot} compact={compact} /> : null}
                </div>
              ))}
            </div>

            <div
              className={`grid items-center ${compact ? "gap-x-2" : "gap-x-3"}`}
              style={{ gridTemplateColumns: gridCols }}
            >
              {fila.slots.map((slot, slotIdx) => (
                <div key={`node-${fila.indice}-${slotIdx}`} className="flex h-8 justify-center">
                  {slot ? (
                    <div
                      ref={(el) => {
                        nodeRefs.current[slot.id] = el;
                      }}
                      className="relative z-10 flex h-8 w-8 items-center justify-center rounded-full bg-primary text-[11px] font-bold text-primary-foreground ring-[4px] ring-card"
                    >
                      {slot.numero}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

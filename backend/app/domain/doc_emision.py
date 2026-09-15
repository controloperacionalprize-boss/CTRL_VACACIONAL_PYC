"""Qué documentos le toca emitir a Personas y Cultura a cada plan recepcionado.

Reglas:
- Fraccionado: la solicitud y el convenio de fraccionamiento se emiten UNA sola vez, con los
  30 días. Después, por cada tramo, solo el memorando de vacaciones.
- El memorando de un tramo se emite el mes anterior a la salida (en noviembre lo de diciembre).
  Si el primer tramo ya cae en esa ventana, va en el mismo PDF que el convenio.
- Si un tramo cambia después de emitido el convenio, se emite la modificación del convenio.
- Goce de 30 días seguidos: solo memorando.

El flujo (RECEPCIONADO) no cambia al emitir; aquí solo se registra lo que ya salió.
"""
from __future__ import annotations

import calendar as _cal
import json
from datetime import date, datetime

from .calendar import DERECHO_ANUAL, parse_iso_date

TIPO_MEMORANDO = "memorando"
TIPO_FRACCIONAMIENTO = "fraccionamiento"
TIPO_MODIFICACION = "modificacion"
TIPO_ADELANTO = "adelanto"

TIPOS = (TIPO_MEMORANDO, TIPO_FRACCIONAMIENTO, TIPO_MODIFICACION, TIPO_ADELANTO)
TIPOS_CONVENIO = frozenset({TIPO_FRACCIONAMIENTO, TIPO_MODIFICACION})

ESCENARIO_DE_TIPO = {
    TIPO_MEMORANDO: 1,
    TIPO_FRACCIONAMIENTO: 2,
    TIPO_MODIFICACION: 3,
    TIPO_ADELANTO: 4,
}

TITULO_DE_TIPO = {
    TIPO_MEMORANDO: "Memorando de vacaciones",
    TIPO_FRACCIONAMIENTO: "Solicitud y convenio de fraccionamiento",
    TIPO_MODIFICACION: "Modificación del convenio de fraccionamiento",
    TIPO_ADELANTO: "Adelanto de goce de vacaciones",
}

POR_EMITIR = "por_emitir"
PROXIMO = "proximo"
EMITIDO = "emitido"

ESTADO_LABEL = {
    POR_EMITIR: "Por emitir",
    PROXIMO: "Próximo",
    EMITIDO: "Emitido",
}

MAX_ZIP = 40


def fin_de_ventana(today: date) -> date:
    """Último día del mes siguiente: los tramos que empiezan hasta aquí ya piden memorando."""
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return date(year, month, _cal.monthrange(year, month)[1])


def emitir_desde(inicio: date) -> date:
    """Primer día del mes anterior a la salida."""
    if inicio.month == 1:
        return date(inicio.year - 1, 12, 1)
    return date(inicio.year, inicio.month - 1, 1)


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return parse_iso_date(value)


def tramo_json(p: dict) -> dict:
    inicio, fin = _as_date(p.get("inicio")), _as_date(p.get("fin"))
    return {
        "inicio": inicio.isoformat() if inicio else "",
        "fin": fin.isoformat() if fin else "",
        "dias": int(p.get("dias") or 0),
    }


def tramos_desde_json(raw) -> list[dict]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "[]")
        except ValueError:
            raw = []
    out = []
    for p in raw or []:
        inicio, fin = _as_date(p.get("inicio")), _as_date(p.get("fin"))
        if inicio and fin:
            out.append({"inicio": inicio, "fin": fin, "dias": int(p.get("dias") or 0)})
    out.sort(key=lambda x: x["inicio"])
    return out


def _clave(p: dict) -> tuple[date, date]:
    return (_as_date(p["inicio"]), _as_date(p["fin"]))


def item_key(tipo: str, tramo_inicio: date | None) -> str:
    return f"{tipo}:{tramo_inicio.isoformat() if tramo_inicio else ''}"


def plan_completo(periodos: list[dict], derecho: int = DERECHO_ANUAL) -> bool:
    return sum(int(p.get("dias") or 0) for p in periodos) == int(derecho)


def _item(
    tipo: str,
    *,
    estado: str,
    periodos: list[dict],
    tramo: dict | None = None,
    anteriores: list[dict] | None = None,
    fecha_convenio: date | None = None,
) -> dict:
    return {
        "key": item_key(tipo, tramo["inicio"] if tramo else None),
        "tipo": tipo,
        "escenario": ESCENARIO_DE_TIPO[tipo],
        "titulo": TITULO_DE_TIPO[tipo],
        "estado": estado,
        "tramo": tramo,
        "periodos": periodos,
        "periodos_anteriores": anteriores or [],
        "fecha_convenio": fecha_convenio,
        "emitir_desde": emitir_desde(tramo["inicio"]) if tramo else None,
    }


def documentos_pendientes(
    *,
    periodos: list[dict],
    emitidos: list[dict],
    today: date,
    es_adelanto: bool = False,
) -> list[dict]:
    """Documentos que faltan emitir para un plan, en el orden en que Personas y Cultura los saca.

    `periodos`: tramos vigentes del plan ({inicio, fin, dias}).
    `emitidos`: filas de plan_documento ({tipo, tramo_inicio, tramo_fin, periodos, emitido_at}).
    """
    if not periodos:
        return []
    periodos = sorted(periodos, key=lambda p: p["inicio"])
    ventana = fin_de_ventana(today)
    vigentes = [p for p in periodos if p["fin"] >= today]

    def estado_tramo(p: dict) -> str:
        return POR_EMITIR if p["inicio"] <= ventana else PROXIMO

    if es_adelanto:
        hechos = {
            (_as_date(r.get("tramo_inicio")), _as_date(r.get("tramo_fin")))
            for r in emitidos
            if r.get("tipo") == TIPO_ADELANTO
        }
        return [
            _item(TIPO_ADELANTO, estado=estado_tramo(p), periodos=periodos, tramo=p)
            for p in vigentes
            if _clave(p) not in hechos
        ]

    memos = {
        (_as_date(r.get("tramo_inicio")), _as_date(r.get("tramo_fin")))
        for r in emitidos
        if r.get("tipo") == TIPO_MEMORANDO
    }
    sin_memo = [p for p in vigentes if _clave(p) not in memos]

    if len(periodos) == 1:
        return [
            _item(TIPO_MEMORANDO, estado=estado_tramo(p), periodos=periodos, tramo=p)
            for p in sin_memo
        ]

    convenios = sorted(
        (r for r in emitidos if r.get("tipo") in TIPOS_CONVENIO),
        key=lambda r: (_as_date(r.get("emitido_at")) or date.min, r.get("id") or 0),
    )
    base = convenios[-1] if convenios else None
    base_tramos = tramos_desde_json(base.get("periodos")) if base else []
    base_claves = {_clave(p) for p in base_tramos}
    actuales = {_clave(p) for p in periodos}

    items: list[dict] = []
    if base is None:
        tipo_paquete = TIPO_FRACCIONAMIENTO
        # Sin convenio firmado no sale ningún memorando suelto: el primero va dentro del paquete.
        cubiertos: set = set()
    elif base_claves != actuales:
        tipo_paquete = TIPO_MODIFICACION
        # Los tramos que no cambiaron siguen amparados por el convenio anterior.
        cubiertos = base_claves
    else:
        tipo_paquete = None
        cubiertos = actuales

    if tipo_paquete:
        candidatos = [p for p in sin_memo if _clave(p) not in cubiertos and estado_tramo(p) == POR_EMITIR]
        bundled = candidatos[0] if candidatos else None
        items.append(
            _item(
                tipo_paquete,
                estado=POR_EMITIR,
                periodos=periodos,
                tramo=bundled,
                anteriores=base_tramos if tipo_paquete == TIPO_MODIFICACION else None,
                fecha_convenio=_as_date(base.get("emitido_at")) if base else None,
            )
        )
        sin_memo = [p for p in sin_memo if p is not bundled]

    for p in sin_memo:
        if _clave(p) not in cubiertos:
            continue
        items.append(_item(TIPO_MEMORANDO, estado=estado_tramo(p), periodos=periodos, tramo=p))
    return items


def calendario_documentos(items: list[dict], periodos: list[dict], today: date) -> list[dict]:
    """Cómo se reparten los documentos del plan: lo que toca ahora y los memorandos que vienen.

    documentos_pendientes solo lista memorandos sueltos cuando el convenio ya salió; para mostrar
    el calendario completo antes de emitir, se agregan los memorandos de los demás tramos.
    """
    out = [
        {
            "titulo": i["titulo"],
            "tipo": i["tipo"],
            "tramo": tramo_json(i["tramo"]) if i.get("tramo") else None,
            "estado": i["estado"],
            "emitir_desde": i["emitir_desde"].isoformat() if i.get("emitir_desde") else None,
        }
        for i in items
    ]
    if not any(i["tipo"] in TIPOS_CONVENIO for i in items):
        return out
    ya = {(i["tramo"]["inicio"], i["tramo"]["fin"]) for i in items if i.get("tramo")}
    ventana = fin_de_ventana(today)
    for p in sorted(periodos, key=lambda x: x["inicio"]):
        if p["fin"] < today or (p["inicio"], p["fin"]) in ya:
            continue
        out.append({
            "titulo": TITULO_DE_TIPO[TIPO_MEMORANDO],
            "tipo": TIPO_MEMORANDO,
            "tramo": tramo_json(p),
            "estado": POR_EMITIR if p["inicio"] <= ventana else PROXIMO,
            "emitir_desde": emitir_desde(p["inicio"]).isoformat(),
        })
    return out


def filas_a_registrar(item: dict) -> list[dict]:
    """Filas de plan_documento que deja una emisión (el paquete y, si va dentro, su memorando)."""
    tramo = item.get("tramo")
    periodos = [tramo_json(p) for p in item.get("periodos") or []]
    anteriores = [tramo_json(p) for p in item.get("periodos_anteriores") or []]
    principal = {
        "tipo": item["tipo"],
        "tramo_inicio": tramo["inicio"] if tramo else None,
        "tramo_fin": tramo["fin"] if tramo else None,
        "dias": int(tramo["dias"]) if tramo else sum(p["dias"] for p in periodos),
        "periodos": periodos,
        "periodos_anteriores": anteriores,
        "fecha_convenio": item.get("fecha_convenio"),
    }
    filas = [principal]
    if item["tipo"] in TIPOS_CONVENIO and tramo:
        filas.append({
            "tipo": TIPO_MEMORANDO,
            "tramo_inicio": tramo["inicio"],
            "tramo_fin": tramo["fin"],
            "dias": int(tramo["dias"]),
            "periodos": periodos,
            "periodos_anteriores": [],
            "fecha_convenio": None,
        })
    return filas


def item_desde_fila(fila: dict) -> dict:
    """Arma un item re-imprimible a partir de lo que quedó registrado."""
    tipo = fila["tipo"]
    tramo = None
    inicio, fin = _as_date(fila.get("tramo_inicio")), _as_date(fila.get("tramo_fin"))
    if inicio and fin:
        tramo = {"inicio": inicio, "fin": fin, "dias": int(fila.get("dias") or 0)}
    return {
        **_item(
            tipo,
            estado=EMITIDO,
            periodos=tramos_desde_json(fila.get("periodos")),
            tramo=tramo,
            anteriores=tramos_desde_json(fila.get("periodos_anteriores")),
            fecha_convenio=_as_date(fila.get("fecha_convenio")),
        ),
        "id": fila.get("id"),
    }


def legacy_filas(escenario: int, plan_hash: str) -> list[dict]:
    """Convierte una descarga del esquema anterior (una fila por persona) al registro por documento."""
    fechas = sorted({d for d in (parse_iso_date(x) for x in (plan_hash or "").split("|")) if d})
    if not fechas:
        return []
    tramos: list[dict] = []
    for d in fechas:
        if tramos and (d - tramos[-1]["fin"]).days == 1:
            tramos[-1]["fin"] = d
            tramos[-1]["dias"] += 1
        else:
            tramos.append({"inicio": d, "fin": d, "dias": 1})
    tipo = {1: TIPO_MEMORANDO, 2: TIPO_FRACCIONAMIENTO, 3: TIPO_MODIFICACION, 4: TIPO_ADELANTO}.get(
        int(escenario or 0), TIPO_FRACCIONAMIENTO
    )
    # El PDF anterior siempre llevaba el memorando del primer tramo.
    item = _item(tipo, estado=EMITIDO, periodos=tramos, tramo=tramos[0])
    return filas_a_registrar(item)

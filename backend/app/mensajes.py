"""Textos de correo editables por Personas y Cultura y a quién se le envía cada cosa."""
from __future__ import annotations

import re

from .funcionarios_org import load_funcionarios_org
from .mailer import email_valido
from .photos import load_roster, name_token_set

DEFAULTS: dict[str, str] = {
    "doc_asunto": "{documento} – {nombre}",
    "doc_cuerpo": (
        "Estimado(a) {nombre}:\n\n"
        "Te enviamos adjunto el documento «{documento}» correspondiente a tus vacaciones "
        "({periodo}).\n\n"
        "Por favor, imprímelo, fírmalo y entrégalo al área de Personas y Cultura "
        "antes de tu fecha de salida.\n\n"
        "Atentamente,\nSub Gerencia de Personas y Cultura"
    ),
    "jefe_asunto": "Vacaciones de tu equipo – {mes}",
    "jefe_cuerpo": (
        "Hola {jefe}:\n\n"
        "Te compartimos el estado de vacaciones del área {area}.\n\n"
        "{detalle}\n\n"
        "Recuerda que el plan se puede programar o cambiar hasta el viernes de la semana "
        "anterior a cada salida.\n\n"
        "Atentamente,\nSub Gerencia de Personas y Cultura"
    ),
}

VARIABLES: dict[str, tuple[str, ...]] = {
    "doc_asunto": ("nombre", "documento", "periodo", "dias", "dni"),
    "doc_cuerpo": ("nombre", "documento", "periodo", "dias", "dni"),
    "jefe_asunto": ("jefe", "area", "mes"),
    "jefe_cuerpo": ("jefe", "area", "mes", "detalle"),
}

MAX_LEN = 4000
_VAR_RE = re.compile(r"\{([a-z_]+)\}")


def rellenar(plantilla: str, valores: dict[str, object]) -> str:
    """Reemplaza {variable} conocidas; lo demás queda tal cual (sin str.format, sin sorpresas)."""

    def sub(m: re.Match) -> str:
        key = m.group(1)
        return str(valores[key]) if key in valores else m.group(0)

    return _VAR_RE.sub(sub, plantilla or "")


def load_mensajes(cur) -> dict[str, str]:
    cur.execute("SELECT clave, valor FROM app_config WHERE clave = ANY(%s)", (list(DEFAULTS),))
    guardados = {r["clave"]: r["valor"] for r in cur.fetchall()}
    return {k: (guardados.get(k) or v) for k, v in DEFAULTS.items()}


def save_mensajes(cur, data: dict[str, str], user: dict) -> dict[str, str]:
    for clave, valor in data.items():
        if clave not in DEFAULTS:
            continue
        texto = (valor or "").strip()[:MAX_LEN]
        cur.execute(
            """INSERT INTO app_config (clave, valor, actualizado, actualizado_por)
               VALUES (%s, %s, NOW(), %s)
               ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor,
                   actualizado = NOW(), actualizado_por = EXCLUDED.actualizado_por""",
            (clave, texto, user.get("correo") or ""),
        )
    return load_mensajes(cur)


def correos_trabajador(cur, emp: dict) -> tuple[str, str]:
    """(correo de destino, de dónde salió). Corporativo primero; personal si no hay otro.

    Fuentes, en orden: tabla employees (Cubis) → maestro QBiz → roster de correos corporativos.
    """
    dni = str(emp.get("dni") or "")
    cur.execute("SELECT correo, correo_personal FROM employees WHERE dni = %s", (dni,))
    row = cur.fetchone() or {}
    corporativo = (row.get("correo") or "").strip()
    personal = (row.get("correo_personal") or "").strip()
    if not email_valido(corporativo) or not email_valido(personal):
        for m in load_funcionarios_org():
            if str(m.get("dni") or "") == dni:
                corporativo = corporativo if email_valido(corporativo) else (m.get("correo") or "").strip()
                personal = personal if email_valido(personal) else (m.get("correo_personal") or "").strip()
                break
    if email_valido(corporativo):
        return corporativo, "corporativo"
    tokens = name_token_set(emp.get("nombre") or "")
    if tokens:
        for r in load_roster():
            if name_token_set(r.get("nombre") or "") == tokens and email_valido(r.get("email")):
                return str(r["email"]).strip(), "roster de personal"
    if email_valido(personal):
        return personal, "personal"
    return "", ""

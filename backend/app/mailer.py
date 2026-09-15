"""Envío de correo por SMTP (p. ej. Office 365). Solo se usa si MAIL_ENABLED=true."""
from __future__ import annotations

import re
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage

from .config import get_settings

_EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")


def email_valido(value: str | None) -> bool:
    return bool(value) and bool(_EMAIL_RE.match(str(value).strip()))


def mail_configured() -> bool:
    s = get_settings()
    return bool(s.mail_enabled and s.smtp_host.strip() and (s.smtp_from or s.smtp_user).strip())


def cc_fijo() -> list[str]:
    return [x.strip() for x in (get_settings().mail_cc or "").split(",") if email_valido(x)]


@dataclass
class Adjunto:
    nombre: str
    contenido: bytes
    mime: str = "application/pdf"


@dataclass
class Correo:
    para: list[str]
    asunto: str
    cuerpo: str
    cc: list[str] = field(default_factory=list)
    adjuntos: list[Adjunto] = field(default_factory=list)


def _mensaje(correo: Correo, remitente: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = remitente
    msg["To"] = ", ".join(correo.para)
    if correo.cc:
        msg["Cc"] = ", ".join(correo.cc)
    # Sin saltos de línea en el asunto: evita inyección de cabeceras.
    msg["Subject"] = " ".join(correo.asunto.split())
    msg.set_content(correo.cuerpo)
    for adj in correo.adjuntos:
        main, _, sub = adj.mime.partition("/")
        msg.add_attachment(adj.contenido, maintype=main, subtype=sub or "octet-stream", filename=adj.nombre)
    return msg


class MailError(RuntimeError):
    pass


class Mailer:
    """Una conexión SMTP para varios envíos seguidos (lote de documentos)."""

    def __init__(self) -> None:
        if not mail_configured():
            raise MailError(
                "El correo no está configurado. Define MAIL_ENABLED, SMTP_HOST, SMTP_USER, "
                "SMTP_PASSWORD y SMTP_FROM en el servidor."
            )
        self._s = get_settings()
        self._smtp: smtplib.SMTP | None = None

    def __enter__(self) -> "Mailer":
        s = self._s
        try:
            smtp = smtplib.SMTP(s.smtp_host, int(s.smtp_port), timeout=20)
            if s.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
        except (OSError, smtplib.SMTPException) as exc:
            raise MailError(f"No se pudo conectar al servidor de correo: {exc}") from exc
        self._smtp = smtp
        return self

    def __exit__(self, *_exc) -> None:
        if self._smtp is not None:
            try:
                self._smtp.quit()
            except (OSError, smtplib.SMTPException):
                pass
            self._smtp = None

    def enviar(self, correo: Correo) -> None:
        para = [x for x in correo.para if email_valido(x)]
        if not para:
            raise MailError("No hay un correo válido de destino.")
        correo.para = para
        correo.cc = [x for x in correo.cc if email_valido(x) and x not in para]
        remitente = (self._s.smtp_from or self._s.smtp_user).strip()
        if self._smtp is None:
            raise MailError("Mailer se usa dentro de un bloque `with`.")
        try:
            self._smtp.send_message(_mensaje(correo, remitente))
        except (OSError, smtplib.SMTPException) as exc:
            raise MailError(f"El servidor de correo rechazó el envío: {exc}") from exc

from app.mailer import Adjunto, Correo, _mensaje, email_valido
from app.mensajes import DEFAULTS, rellenar


def test_rellenar_solo_variables_conocidas():
    texto = rellenar("Hola {nombre}, {desconocida} y {0} quedan igual.", {"nombre": "Ana"})
    assert texto == "Hola Ana, {desconocida} y {0} quedan igual."


def test_rellenar_no_evalua_formato_de_python():
    assert rellenar("{nombre.__class__}", {"nombre": "Ana"}) == "{nombre.__class__}"


def test_plantillas_por_defecto_tienen_sus_variables():
    assert "{nombre}" in DEFAULTS["doc_cuerpo"]
    assert "{detalle}" in DEFAULTS["jefe_cuerpo"]


def test_email_valido():
    assert email_valido("ana.perez@aquanqa.com")
    assert not email_valido("ana perez@aquanqa.com")
    assert not email_valido("a@b.com, c@d.com")
    assert not email_valido("")


def test_asunto_sin_saltos_de_linea():
    msg = _mensaje(
        Correo(
            para=["ana@aquanqa.com"],
            asunto="Memorando\r\nBcc: otro@x.com",
            cuerpo="Hola",
            adjuntos=[Adjunto("doc.pdf", b"%PDF-1.4")],
        ),
        "gth@aquanqa.com",
    )
    assert "\n" not in msg["Subject"]
    assert msg["Bcc"] is None
    assert any(part.get_filename() == "doc.pdf" for part in msg.iter_attachments())


def test_fotos_se_memorizan_por_nombre(monkeypatch):
    from app import photos

    llamadas = []
    monkeypatch.setattr(photos, "picture_index", lambda: {"aperez": "aperez.jpg"})
    monkeypatch.setattr(
        photos, "_resolve_foto_url", lambda nombre, index, base: llamadas.append(nombre) or "url"
    )
    photos._RESOLVED.clear()
    assert photos.resolve_foto_url("ANA PEREZ") == "url"
    assert photos.resolve_foto_url("ANA PEREZ") == "url"
    assert llamadas == ["ANA PEREZ"]
    photos._RESOLVED.clear()

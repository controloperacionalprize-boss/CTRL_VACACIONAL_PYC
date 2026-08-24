from app.photos import load_roster, resolve_foto_url, usuario_for_nombre, usuario_from_email


def test_usuario_from_email():
    assert usuario_from_email("eabanto@aquanqa.pe") == "eabanto"
    assert usuario_from_email("") is None


def test_roster_loaded():
    rows = load_roster()
    assert len(rows) >= 200
    assert any(r.get("usuario") == "ccoz" for r in rows)


def test_usuario_for_nombre_via_roster():
    # Roster: "Coz, Carlos Yordano" / ccoz@…
    assert usuario_for_nombre("COZ CARLOS YORDANO") == "ccoz"
    assert usuario_for_nombre("Vera, Luis Yoshi") == "lvera"
    assert usuario_for_nombre("VERA LUIS YOSHI") == "lvera"


def test_no_slug_steal_when_roster_usuario_missing_file():
    """En roster pero sin .jpg: no usar slug ajeno (ej. jflores de otro Flores)."""
    assert resolve_foto_url("Flores, Javier Edmundo") is not None
    assert resolve_foto_url("Flores, Joel Junior") is None
    assert resolve_foto_url("Flores, Paolo Jassat") is None


def test_no_slug_steal_reserved_stem():
    """Sin foto propia: no tomar sdiaz.jpg si sdiaz es usuario de otra persona."""
    assert resolve_foto_url("Díaz, Sandra Giseth") is None
    assert resolve_foto_url("Díaz, Segundo Luis Martín") is not None

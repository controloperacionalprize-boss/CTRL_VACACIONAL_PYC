from app.photos import load_roster, usuario_for_nombre, usuario_from_email


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

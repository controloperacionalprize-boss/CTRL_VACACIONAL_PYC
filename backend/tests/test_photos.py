from app.photos import slug_candidates


def test_slug_carlos_coz():
    c = slug_candidates("Carlos Coz")
    assert "ccoz" in c


def test_slug_pe_order_coz():
    c = slug_candidates("COZ CARLOS")
    assert "ccoz" in c


def test_slug_gabriel_rubio():
    c = slug_candidates("Gabriel Rubio")
    assert "grubio" in c


def test_slug_pe_rubio_gabriel():
    c = slug_candidates("RUBIO GABRIEL")
    assert "grubio" in c


def test_slug_pe_four_parts():
    c = slug_candidates("VERA PEREZ LUIS YOSHI")
    assert "lvera" in c


def test_slug_strips_accents():
    c = slug_candidates("Nuñez Pedro")
    assert "pnunez" in c or "npunez" in c or any("nunez" in x for x in c)

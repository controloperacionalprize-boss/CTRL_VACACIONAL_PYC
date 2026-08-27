from math import ceil


def test_paginacion_vacia_una_pagina():
    total = 0
    page_size = 25
    pages = max(1, ceil(total / page_size)) if total else 1
    assert pages == 1


def test_paginacion_redondea_hacia_arriba():
    assert ceil(26 / 25) == 2
    assert ceil(25 / 25) == 1
    assert ceil(100 / 25) == 4


def test_offset_de_pagina():
    page, page_size = 3, 25
    assert (page - 1) * page_size == 50

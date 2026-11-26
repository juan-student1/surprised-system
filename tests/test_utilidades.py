"""Dominio puro: normalización de números, país, puntaje de riesgo y enmascarado."""
import pytest
from fastapi import HTTPException

from centinela.utilidades import (
    calcular_score, enmascarar, formato, hash_reportero, nivel_de, normalizar, pais_de, prefijo_riesgo,
)


@pytest.mark.parametrize("entrada, esperado", [
    ("3001234567", "+573001234567"),          # celular colombiano sin indicativo
    ("300 123 4567", "+573001234567"),
    ("(300) 123-4567", "+573001234567"),
    ("6015551234", "+576015551234"),          # fijo colombiano (60x)
    ("+57 300 123 4567", "+573001234567"),
    ("0057 300 123 4567", "+573001234567"),   # 00 = internacional
    ("+1 809 555 1234", "+18095551234"),
    ("85432", "85432"),                       # código corto: se deja igual
    ("#611", "611"),
])
def test_normalizar(entrada, esperado):
    assert normalizar(entrada) == esperado


@pytest.mark.parametrize("entrada", ["", "12", "abc", "+1234567890123456", None])
def test_normalizar_invalido(entrada):
    with pytest.raises(HTTPException) as e:
        normalizar(entrada)
    assert e.value.status_code == 422


@pytest.mark.parametrize("numero, pais", [
    ("+573001234567", "Colombia"),
    ("+18095551234", "EE. UU. / Caribe"),
    ("+2250701234567", "Costa de Marfil"),    # gana el prefijo más largo (+225, no +2)
    ("+999123456", "Desconocido"),
    ("85432", "Código corto"),
])
def test_pais_de(numero, pais):
    assert pais_de(numero) == pais


@pytest.mark.parametrize("unicos, esperado", [(0, 0), (1, 30), (2, 50), (3, 65), (5, 83)])
def test_score_curva_por_reporteros(unicos, esperado):
    # La curva 100·(1 − e^(−0,35·n)) que se explica en el pitch
    assert calcular_score(unicos, 0, "+573001234567", False) == esperado


def test_score_verificado_es_cero():
    assert calcular_score(50, 0, "+18095551234", True) == 0


def test_score_prefijo_wangiri_suma_25():
    assert prefijo_riesgo("+18095551234")
    assert calcular_score(1, 0, "+18095551234", False) == 30 + 25


def test_score_extranjero_suma_10():
    assert calcular_score(1, 0, "+34600123456", False) == 40


def test_score_decae_con_el_tiempo():
    reciente = calcular_score(3, 0, "+573001234567", False)
    assert calcular_score(3, 45, "+573001234567", False) < reciente
    assert calcular_score(3, 120, "+573001234567", False) < calcular_score(3, 45, "+573001234567", False)


def test_score_tope_100():
    assert calcular_score(100, 0, "+2250701234567", False) == 100


@pytest.mark.parametrize("score, nivel", [(0, "bajo"), (24, "bajo"), (25, "medio"), (59, "medio"), (60, "alto"), (100, "alto")])
def test_nivel_de(score, nivel):
    assert nivel_de(score) == nivel


def test_enmascarar_y_formato():
    assert enmascarar("+573001234567") == "+57 300 ••• 4567"
    assert enmascarar("+18095551234") == "+1 809 ••• 1234"
    assert enmascarar("123") == "Número oculto"
    assert formato("+573001234567") == "+57 300 123 4567"


def test_hash_reportero_estable_y_sin_ip_en_claro():
    h = hash_reportero("190.1.2.3")
    assert h == hash_reportero("190.1.2.3") and len(h) == 16
    assert "190.1.2.3" not in h
    assert h != hash_reportero("190.1.2.4")

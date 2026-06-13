"""Tests del pronóstico de volatilidad (EWMA) y su medición de skill."""
import numpy as np
import pandas as pd
from src import volforecast as vf


def _df(rets):
    close = 100 * np.exp(np.cumsum(rets))
    ts = pd.date_range("2023-01-01", periods=len(rets), freq="1h", tz="UTC")
    return pd.DataFrame({"ts": ts, "open": close, "high": close, "low": close,
                         "close": close, "volume": 1.0})


def test_ewma_es_causal():
    """La predicción en t no usa el retorno de t (prefijo estable)."""
    rng = np.random.default_rng(1)
    rets = rng.normal(0, 0.01, 500)
    full = vf.ewma_vol(pd.Series(rets))
    cut = vf.ewma_vol(pd.Series(rets[:300]))
    assert np.allclose(full.iloc[:300].dropna(), cut.dropna())


def test_con_regimenes_de_vol_hay_skill():
    """Serie con vol que cambia de régimen (calma↔tormenta): la EWMA debe predecirla."""
    rng = np.random.default_rng(2)
    sigmas = np.where((np.arange(6000) // 500) % 2 == 0, 0.004, 0.02)   # bloques alternos
    r = vf.vol_skill(_df(rng.normal(0, sigmas)))
    assert r["skill"] > 0.10                      # mejora clara sobre la base constante
    assert r["corr"] > 0.30                       # el pronóstico sigue al realizado


def test_sin_regimenes_no_inventa_skill():
    """Con vol constante (iid) no hay nada que predecir: skill ≈ 0, no negativo grande."""
    rng = np.random.default_rng(3)
    r = vf.vol_skill(_df(rng.normal(0, 0.01, 6000)))
    assert abs(r["skill"]) < 0.05

"""Tests de la reliability curve del forecast."""
import numpy as np
import pandas as pd
from src import calibration as cal


def _rw(n=4000, seed=2):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.005, n)))
    ts = pd.date_range("2023-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"ts": ts, "open": close, "high": close * 1.001,
                         "low": close * 0.999, "close": close, "volume": 1})


def test_reliability_contrato():
    r = cal.reliability(_rw())
    assert set(r) == {"table", "brier", "brier_base", "skill", "n"}
    assert 0 <= r["brier"] <= 1 and r["n"] > 3000
    assert list(r["table"].columns) == ["bin", "prob. predicha (media)",
                                        "frec. observada", "n velas"]


def test_camino_aleatorio_sin_skill():
    """En un random walk las probabilidades del baseline no deben tener skill."""
    r = cal.reliability(_rw(6000, seed=11))
    assert r["skill"] < 0.05                          # ~0 o negativo: sin información
    # y la frecuencia observada no sigue a la predicha: se queda cerca de la base
    obs = r["table"]["frec. observada"]
    assert (obs.sub(obs.mean()).abs() < 0.2).all()


def test_verdict_honesto():
    r = {"n": 5000, "skill": -0.01, "brier": 0.26, "brier_base": 0.25, "table": None}
    assert "SIN valor predictivo" in cal.verdict(r)
    assert "insuficiente" in cal.verdict({**r, "n": 100})


def test_platt_recupera_un_mapa_conocido():
    """Si la verdad ES sigmoid(2x−0.5), Platt debe encontrar a≈2, b≈−0.5."""
    rng = np.random.default_rng(7)
    x = rng.normal(0, 1.5, 20000)
    p_true = 1 / (1 + np.exp(-(2.0 * x - 0.5)))
    y = (rng.random(20000) < p_true).astype(float)
    a, b = cal.platt_fit(x, y)
    assert abs(a - 2.0) < 0.15 and abs(b + 0.5) < 0.1


def test_platt_con_senal_conserva_la_discriminacion():
    """Con señal real, la versión calibrada mantiene skill > 0 (no lo destruye)."""
    rng = np.random.default_rng(3)
    x = rng.normal(0, 1, 12000)
    y = (rng.random(12000) < 1 / (1 + np.exp(-1.5 * x))).astype(float)
    a, b = cal.platt_fit(x[:6000], y[:6000])
    p = 1 / (1 + np.exp(-(a * x[6000:] + b)))
    yt = y[6000:]
    brier = ((p - yt) ** 2).mean()
    base = ((yt.mean() - yt) ** 2).mean()
    assert 1 - brier / base > 0.2                         # skill claro fuera de muestra


def test_walkforward_calibration_repara_la_mentira():
    """En un random walk: el raw tiene skill negativo; el calibrado lo sube a ≈0
    diciendo '~50%' casi siempre (dispersión mínima) — la respuesta honesta."""
    r = cal.walkforward_calibration(_rw(8000, seed=5))
    assert r["skill_cal"] > r["skill_raw"]                # calibrar nunca empeora aquí
    assert r["skill_cal"] > -0.02                         # ya no miente (≈ base)
    assert r["cal_prob_std"] < 0.05                       # colapsa a 'no sé' (~base rate)

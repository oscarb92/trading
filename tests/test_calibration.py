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

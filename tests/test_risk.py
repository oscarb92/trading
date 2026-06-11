"""Tests de las utilidades de gestión de riesgo (Fase 5)."""
import pandas as pd
from src import risk
from src.portfolio import Portfolio, Position


def test_kelly_y_fraccional():
    # W=0.5, R=2 → f* = 0.5 − 0.5/2 = 0.25
    assert abs(risk.kelly_fraction(0.5, 2.0) - 0.25) < 1e-9
    # media-Kelly = 0.125 (por debajo del cap 0.2)
    assert abs(risk.fractional_kelly(0.5, 2.0, fraction=0.5) - 0.125) < 1e-9
    # sin edge (W=0.3, R=1 → f*<0) → 0, no apostar
    assert risk.kelly_fraction(0.3, 1.0) == 0.0
    # el cap recorta a Kelly muy agresivo (W=0.8,R=3 → f*≈0.733; ½K≈0.367 > cap 0.2)
    assert risk.fractional_kelly(0.8, 3.0, fraction=0.5, cap=0.2) == 0.2


def test_size_from_risk_y_apalancamiento():
    r = risk.size_from_risk(equity=10000, risk_pct=1.0, entry=100.0, stop=95.0)
    assert abs(r["risk_amount"] - 100) < 1e-9     # 1% de 10000
    assert abs(r["qty"] - 20) < 1e-9              # 100 / |100-95|
    assert abs(r["notional"] - 2000) < 1e-9
    assert abs(r["leverage"] - 0.2) < 1e-9
    # stop = entrada → no calculable
    assert risk.size_from_risk(10000, 1.0, 100.0, 100.0)["qty"] == 0.0


def test_stress_test_gap_y_stop():
    pf = Portfolio(cash=1000.0,
                   positions={"BTC/USDT": Position("BTC/USDT", "long", 1.0, 100.0, stop=90.0)})
    prices = {"BTC/USDT": 100.0}
    s = risk.stress_test_gap(pf, prices, gap_pct=-0.20)
    assert abs(s["equity_before"] - 1000) < 1e-9
    assert abs(s["equity_after"] - 980) < 1e-9    # (80-100)*1 = -20
    assert abs(s["change_pct"] + 0.02) < 1e-9
    assert s["positions"][0]["stop_hit"] is True  # 80 <= stop 90


def test_exposure_bruta_y_neta():
    pf = Portfolio(cash=900.0, positions={
        "BTC/USDT": Position("BTC/USDT", "long", 1.0, 100.0),
        "ETH/USDT": Position("ETH/USDT", "short", 2.0, 50.0)})
    prices = {"BTC/USDT": 100.0, "ETH/USDT": 50.0}
    e = risk.exposure(pf, prices)
    assert abs(e["gross"] - 200) < 1e-9           # 100 + 100
    assert abs(e["net"] - 0) < 1e-9               # +100 − 100 (mercado-neutral)
    assert len(e["positions"]) == 2


def test_correlation_matrix(monkeypatch):
    import numpy as np
    from src import store
    n = 200
    base = np.cumsum(np.random.default_rng(0).normal(0, 1, n))
    def fake_load(sym, tf):
        ts = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
        close = 100 + base + (0 if sym == "A" else 0.01 * np.arange(n))  # casi idénticos
        return pd.DataFrame({"ts": ts, "close": close})
    monkeypatch.setattr(store, "load_ohlcv", fake_load)
    m = risk.correlation_matrix(["A", "B"], "1h")
    assert list(m.columns) == ["A", "B"]
    assert abs(m.loc["A", "A"] - 1.0) < 1e-9
    assert m.loc["A", "B"] > 0.9                  # series casi idénticas

"""Tests de la estrategia cross-sectional dólar-neutral."""
import numpy as np
import pandas as pd
import cross_sectional as xs


def _panel(n=400):
    ts = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    up = 100 * np.exp(np.cumsum(np.full(n, 0.003)))      # tendencia alcista
    dn = 100 * np.exp(np.cumsum(np.full(n, -0.003)))     # tendencia bajista
    f1 = 100 * np.exp(np.cumsum(np.full(n, 0.0002)))
    f2 = 100 * np.exp(np.cumsum(np.full(n, -0.0002)))
    return pd.DataFrame({"UP": up, "DN": dn, "F1": f1, "F2": f2}, index=ts)


def test_momentum_va_largo_del_que_sube():
    """Long top / short bottom por momentum → ganar con UP largo y DN corto."""
    P = _panel()
    R = P.pct_change().fillna(0.0)
    net = xs.portfolio_returns(P, R, "mom", lookback=60, gap=5, k=1, reb=21)
    assert (1 + net).prod() - 1 > 0.0                    # retorno acumulado positivo


def test_dolar_neutral_se_cancela_el_mercado():
    """Si TODOS los activos se mueven idéntico, la cartera dólar-neutral da ~0 (solo coste)."""
    ts = pd.date_range("2020-01-01", periods=400, freq="D", tz="UTC")
    base = 100 * np.exp(np.cumsum(np.full(400, 0.002)))
    P = pd.DataFrame({c: base for c in ["A", "B", "C", "D"]}, index=ts)
    R = P.pct_change().fillna(0.0)
    net = xs.portfolio_returns(P, R, "mom", lookback=60, gap=5, k=1, reb=21)
    assert abs((1 + net).prod() - 1) < 0.05              # el largo y el corto se cancelan


def test_score_es_causal():
    """La puntuación en t no usa precios futuros (solo shifts positivos)."""
    P = _panel(120)
    s = xs._score(P, "mom", lookback=60, gap=5)
    # con lookback+gap=65, las primeras 65 filas no tienen score (NaN)
    assert s.iloc[:65].isna().all().all()
    assert not s.iloc[66:].isna().all().all()

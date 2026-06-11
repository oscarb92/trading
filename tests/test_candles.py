"""Tests de la señal de patrones de velas japonesas."""
import numpy as np
import pandas as pd
from src import backtest as bt


def _df(o, h, l, c):
    n = len(o)
    ts = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"ts": ts, "open": o, "high": h, "low": l,
                         "close": c, "volume": np.ones(n)})


def test_envolvente_alcista_en_bajista_dispara_largo():
    """Tendencia bajista + vela roja + vela verde que la envuelve → +1 durante `hold`."""
    n = 40
    closes = list(np.linspace(120, 101, n - 2))          # bajista sostenida (close < EMA)
    opens = [x + 0.5 for x in closes]
    # vela roja: o=101, c=100 · vela envolvente verde: o=99.5, c=101.5
    o = opens + [101.0, 99.5]
    c = closes + [100.0, 101.5]
    h = [max(a, b) + 0.2 for a, b in zip(o, c)]
    l = [min(a, b) - 0.2 for a, b in zip(o, c)]
    s = bt.candlestick_signal(_df(o, h, l, c), hold=5)
    assert s.iloc[-1] == 1                               # patrón detectado en la última vela
    assert set(s.unique()).issubset({-1, 0, 1})


def test_hold_limita_la_duracion():
    """Tras el patrón, la posición dura como mucho `hold` velas y vuelve a plano."""
    n = 60
    closes = list(np.linspace(120, 101, n - 12))
    opens = [x + 0.5 for x in closes]
    o = opens + [101.0, 99.5] + [101.5] * 10             # tras el patrón, velas planas
    c = closes + [100.0, 101.5] + [101.5] * 10
    h = [max(a, b) + 0.05 for a, b in zip(o, c)]
    l = [min(a, b) - 0.05 for a, b in zip(o, c)]
    s = bt.candlestick_signal(_df(o, h, l, c), hold=3)
    fired = s[s != 0]
    assert 0 < len(fired) <= 4                           # patrón + hold acotado (sin re-disparo)
    assert s.iloc[-1] == 0                               # vuelve a plano


def test_senal_es_causal_prefijo():
    """El prefijo de la señal no cambia al añadir velas futuras (sin look-ahead)."""
    rng = np.random.default_rng(8)
    n = 300
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * 1.004
    l = np.minimum(o, c) * 0.996
    df = _df(o, h, l, c)
    full = bt.candlestick_signal(df, hold=5)
    cut = bt.candlestick_signal(df.iloc[:200].reset_index(drop=True), hold=5)
    assert (full.iloc[:200].values == cut.values).all()

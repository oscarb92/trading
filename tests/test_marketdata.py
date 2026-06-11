"""Tests del adaptador multi-mercado (yfinance) y de la anualización por activo."""
import numpy as np
import pandas as pd
from src import marketdata as md, backtest as bt


def test_fetch_yahoo_normaliza_ohlcv(monkeypatch):
    """Normaliza la salida de yfinance (columnas MultiIndex) al esquema OHLCV estándar."""
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    cols = pd.MultiIndex.from_product([["Open", "High", "Low", "Close", "Volume"], ["AAPL"]])
    fake = pd.DataFrame(np.arange(25).reshape(5, 5).astype(float), index=idx, columns=cols)
    fake.index.name = "Date"
    monkeypatch.setattr(md, "_HAS_YF", True)
    monkeypatch.setattr(md.yf, "download", lambda *a, **k: fake)

    r = md.fetch_yahoo("AAPL", "1d", start="2020-01-01")
    assert r.source == "yahoo"
    assert list(r.df.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert len(r.df) == 5
    assert str(r.df["ts"].dtype).startswith("datetime64[ns, UTC")


def test_clase_y_anualizacion():
    assert md.periods_per_year("BTC-USD") == 365      # cripto cotiza 7 días/semana
    assert md.periods_per_year("SPY") == 252          # bolsa ~252 hábiles
    assert md.asset_class("GC=F") == "commodity"
    assert md.label("AAPL") == "Apple"


def test_ppy_escala_el_sharpe():
    """Con la misma serie, el Sharpe anualizado escala con sqrt(ppy)."""
    n = 300
    pos = pd.Series(1.0, index=range(n))              # siempre largo
    raw = pd.Series(np.random.default_rng(0).normal(0.0005, 0.01, n))
    m252 = bt.metrics_from_position(pos, raw, "1d", ppy=252)["metrics"]
    m365 = bt.metrics_from_position(pos, raw, "1d", ppy=365)["metrics"]
    assert m365.sharpe > m252.sharpe > 0
    assert abs(m365.sharpe / m252.sharpe - (365 / 252) ** 0.5) < 0.05

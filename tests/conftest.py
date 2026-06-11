"""Fixtures: aíslan estado (portfolio/journal) en tmp y permiten simular datos reales."""
import pytest
import pandas as pd
import numpy as np
from pathlib import Path


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    import src.portfolio as P
    import src.journal as J
    monkeypatch.setattr(P, "STATE_PATH", tmp_path / "portfolio.json")
    monkeypatch.setattr(J, "JOURNAL_PATH", tmp_path / "trades.csv")
    yield


def _df(last_close=30000.0, n=300):
    rng = np.random.default_rng(0)
    close = last_close * np.exp(np.cumsum(rng.normal(0, 0.005, n)))
    close = close * (last_close / close[-1])           # fijar último close
    high = close * 1.002; low = close * 0.998
    open_ = np.concatenate([[close[0]], close[:-1]])
    ts = pd.to_datetime(range(n), unit="h", utc=True)
    return pd.DataFrame({"ts": ts, "open": open_, "high": high, "low": low,
                         "close": close, "volume": np.ones(n)})


@pytest.fixture
def real_data(monkeypatch):
    """Hace que fetch_ohlcv devuelva datos etiquetados como 'binance' (no sintéticos)."""
    from src.data import FetchResult
    def fake(symbol="BTC/USDT", timeframe="1h", limit=300, exchange="binance"):
        return FetchResult(_df(), "binance", symbol, timeframe)
    monkeypatch.setattr("src.data.fetch_ohlcv", fake)
    return fake


@pytest.fixture
def synth_data(monkeypatch):
    """fetch_ohlcv devuelve datos etiquetados como 'synthetic' (simula red caída)."""
    from src.data import FetchResult
    def fake(symbol="BTC/USDT", timeframe="1h", limit=300, exchange="binance"):
        return FetchResult(_df(), "synthetic", symbol, timeframe)
    monkeypatch.setattr("src.data.fetch_ohlcv", fake)
    return fake

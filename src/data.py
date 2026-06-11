"""Capa de datos de mercado. Precios REALES vía CCXT (Binance por defecto).

Si no hay red o ccxt no está disponible, cae a un generador sintético
(solo para desarrollo offline) marcado claramente como tal.
"""
from __future__ import annotations
import time
from dataclasses import dataclass
import numpy as np
import pandas as pd

try:
    import ccxt  # type: ignore
    _HAS_CCXT = True
except Exception:  # pragma: no cover
    _HAS_CCXT = False


@dataclass
class FetchResult:
    df: pd.DataFrame          # columns: ts, open, high, low, close, volume
    source: str               # "binance" | "synthetic"
    symbol: str
    timeframe: str


_EX_CACHE: dict = {}


def _exchange(name: str = "binance"):
    if not _HAS_CCXT:
        raise RuntimeError("ccxt no instalado")
    # Reusa la instancia (evita reconstruir el cliente en cada llamada)
    if name not in _EX_CACHE:
        _EX_CACHE[name] = getattr(ccxt, name)({"enableRateLimit": True})
    return _EX_CACHE[name]


def fetch_ohlcv(symbol: str = "BTC/USDT", timeframe: str = "1h",
                limit: int = 500, exchange: str = "binance",
                since: int | None = None) -> FetchResult:
    """Descarga OHLCV real. Si falla, genera datos sintéticos de respaldo.

    `since` (epoch ms) permite paginar el histórico: pide `limit` velas a partir
    de ese instante. Sin `since`, devuelve las `limit` velas más recientes.
    """
    if _HAS_CCXT:
        try:
            ex = _exchange(exchange)
            raw = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit, since=since)
            df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
            df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
            return FetchResult(df, "binance", symbol, timeframe)
        except Exception as e:  # red bloqueada, símbolo inválido, etc.
            print(f"[data] fetch real falló ({e}); usando datos sintéticos.")
    return _synthetic(symbol, timeframe, limit)


def current_price(symbol: str = "BTC/USDT", exchange: str = "binance") -> float:
    if _HAS_CCXT:
        try:
            ex = _exchange(exchange)
            return float(ex.fetch_ticker(symbol)["last"])
        except Exception as e:
            print(f"[data] ticker real falló ({e}); usando último sintético.")
    return float(_synthetic(symbol, "1h", 50).df["close"].iloc[-1])


def _synthetic(symbol: str, timeframe: str, limit: int) -> FetchResult:
    """Camino aleatorio reproducible por símbolo (solo desarrollo offline)."""
    seed = abs(hash(symbol)) % (2**32)
    rng = np.random.default_rng(seed)
    base = 30000.0 if "BTC" in symbol else 2000.0
    rets = rng.normal(0, 0.01, limit)
    close = base * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, 0.004, limit)))
    low = close * (1 - np.abs(rng.normal(0, 0.004, limit)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = np.abs(rng.normal(100, 30, limit))
    end = int(time.time() * 1000)
    step = 3600_000
    ts = pd.to_datetime([end - step * (limit - i) for i in range(limit)], unit="ms", utc=True)
    df = pd.DataFrame({"ts": ts, "open": open_, "high": high, "low": low,
                       "close": close, "volume": vol})
    return FetchResult(df, "synthetic", symbol, timeframe)

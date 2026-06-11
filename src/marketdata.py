"""Datos de mercado NO-cripto vía yfinance: oro, petróleo, plata, índices, acciones, ETF.

Devuelve el MISMO esquema OHLCV que `src/data.py` (ts, open, high, low, close, volume) con
fuente "yahoo", de modo que `store`, `backtest` y `validation` funcionan sin cambios. Los
precios de acciones/ETF vienen ajustados por splits y dividendos (auto_adjust=True).

Mercados no 24/7: fines de semana y festivos NO son huecos de datos, son días sin cotización.
Por eso la anualización en diario usa 252 (bolsa) en vez de 365 (cripto) — ver `periods_per_year`.
"""
from __future__ import annotations
import pandas as pd

try:
    import yfinance as yf
    _HAS_YF = True
except Exception:  # pragma: no cover
    _HAS_YF = False

from .data import FetchResult  # (df, source, symbol, timeframe)

# Etiquetas legibles y clasificación por clase de activo (para anualización y reporte)
UNIVERSE = {
    "GC=F": ("Oro (futuro)", "commodity"),
    "SI=F": ("Plata (futuro)", "commodity"),
    "CL=F": ("Petróleo WTI (futuro)", "commodity"),
    "GLD":  ("Oro (ETF)", "etf"),
    "SLV":  ("Plata (ETF)", "etf"),
    "USO":  ("Petróleo (ETF)", "etf"),
    "SPY":  ("S&P 500 (ETF)", "etf"),
    "QQQ":  ("Nasdaq 100 (ETF)", "etf"),
    "IWM":  ("Russell 2000 (ETF)", "etf"),
    "DIA":  ("Dow 30 (ETF)", "etf"),
    "AAPL": ("Apple", "stock"),
    "MSFT": ("Microsoft", "stock"),
    "NVDA": ("NVIDIA", "stock"),
    "TSLA": ("Tesla", "stock"),
    "BTC-USD": ("Bitcoin", "crypto"),
    "ETH-USD": ("Ethereum", "crypto"),
}

_BARS_PER_YEAR = {"1d": {"crypto": 365, "default": 252},
                  "1wk": {"crypto": 52, "default": 52}}


def asset_class(symbol: str) -> str:
    return UNIVERSE.get(symbol, ("", "stock"))[1]


def label(symbol: str) -> str:
    return UNIVERSE.get(symbol, (symbol, ""))[0]


def periods_per_year(symbol: str, timeframe: str = "1d") -> float:
    """Periodos por año para anualizar (cripto cotiza 365 días; la bolsa ~252 hábiles)."""
    tf = _BARS_PER_YEAR.get(timeframe, _BARS_PER_YEAR["1d"])
    return tf["crypto"] if asset_class(symbol) == "crypto" else tf["default"]


def fetch_yahoo(symbol: str, timeframe: str = "1d",
                start: str = "2018-01-01", end: str | None = None) -> FetchResult:
    """Descarga OHLCV de Yahoo. Acciones/ETF ajustados (splits+dividendos)."""
    if not _HAS_YF:
        raise RuntimeError("yfinance no instalado (pip install yfinance)")
    interval = {"1d": "1d", "1h": "1h", "1wk": "1wk"}.get(timeframe, "1d")
    raw = yf.download(symbol, start=start, end=end, interval=interval,
                      auto_adjust=True, progress=False)
    empty = pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    if raw is None or len(raw) == 0:
        return FetchResult(empty, "yahoo", symbol, timeframe)
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):            # yfinance multi-nivel para 1 ticker
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    df = df.rename(columns={df.columns[0]: "ts", "Open": "open", "High": "high",
                            "Low": "low", "Close": "close", "Volume": "volume"})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    cols = [c for c in ["ts", "open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[cols].dropna(subset=["close"]).reset_index(drop=True)
    # Saneo: precios <= 0 (p.ej. WTI cotizó a -37.63 el 2020-04-20) rompen pct_change al
    # cruzar el cero. Se descartan esas barras: un retorno sobre precio negativo no tiene
    # sentido y, sin filtrar, el clip a ±50% lo enmascararía en silencio.
    bad = int((df["close"] <= 0).sum())
    if bad:
        print(f"[marketdata] {symbol}: descartadas {bad} barra(s) con precio <= 0.")
        df = df[df["close"] > 0].reset_index(drop=True)
    return FetchResult(df, "yahoo", symbol, timeframe)

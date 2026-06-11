"""Almacenamiento histórico en Parquet (Fase 2a).

Guarda OHLCV por símbolo/timeframe en data/, con append incremental sin
duplicados, detección de huecos y descarga paginada vía CCXT. El backtesting
lee de aquí, no de la red.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import time
import pandas as pd

from . import data as data_mod

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# minutos por timeframe (para detectar huecos)
TF_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
TF_MS = {tf: m * 60_000 for tf, m in TF_MINUTES.items()}


def _path(symbol: str, timeframe: str) -> Path:
    # Nombre de fichero seguro: cripto usa "BTC/USDT", Yahoo usa "GC=F", "^GSPC", etc.
    safe = (symbol.replace("/", "-").replace("=", "_").replace("^", "")
            .replace(":", "-").replace(" ", ""))
    return DATA_DIR / f"{safe}_{timeframe}.parquet"


def save_ohlcv(df: pd.DataFrame, symbol: str, timeframe: str) -> Path:
    """Guarda/añade velas, eliminando duplicados por timestamp y ordenando."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    p = _path(symbol, timeframe)
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    if p.exists():
        old = pd.read_parquet(p)
        df = pd.concat([old, df], ignore_index=True)
    df = (df.drop_duplicates(subset="ts", keep="last")
            .sort_values("ts").reset_index(drop=True))
    # Guardia: detectar saltos de precio absurdos (>50%) entre velas, típicos de
    # mezclar histórico sintético con real. Avisa para que el usuario use clear().
    if len(df) > 1:
        jumps = df["close"].pct_change().abs()
        if (jumps > 0.5).any():
            print(f"[store] AVISO: discontinuidad de precio >50% en {symbol} {timeframe}. "
                  "Posible mezcla de datos sintéticos y reales. Usa store.clear() o "
                  "'python backtest.py --fresh --download N' para rehacer el histórico.")
    df.to_parquet(p, index=False)
    return p


def clear(symbol: str, timeframe: str) -> bool:
    """Borra el histórico local de un símbolo/timeframe (para empezar limpio)."""
    p = _path(symbol, timeframe)
    if p.exists():
        p.unlink()
        return True
    return False


def load_ohlcv(symbol: str, timeframe: str) -> pd.DataFrame:
    p = _path(symbol, timeframe)
    if not p.exists():
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    df = pd.read_parquet(p)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.sort_values("ts").reset_index(drop=True)


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Reagrega OHLCV a un timeframe mayor (p.ej. 1h→4h) sin volver a descargar.
    open=primera, high=máx, low=mín, close=última, volume=suma. Útil para probar
    el baseline en marcos más lentos (menos ruido, menos sobre-trading)."""
    if df.empty:
        return df.copy()
    g = (df.set_index(pd.to_datetime(df["ts"], utc=True))
           .resample(timeframe, label="left", closed="left"))
    out = pd.DataFrame({
        "open": g["open"].first(),
        "high": g["high"].max(),
        "low": g["low"].min(),
        "close": g["close"].last(),
        "volume": g["volume"].sum(),
    }).dropna(subset=["close"]).reset_index().rename(columns={"index": "ts"})
    out = out.rename(columns={out.columns[0]: "ts"})
    return out


def detect_gaps(df: pd.DataFrame, timeframe: str) -> list[tuple]:
    """Devuelve [(inicio, fin, n_velas_faltantes)] de huecos en la serie."""
    if len(df) < 2:
        return []
    step = pd.Timedelta(minutes=TF_MINUTES.get(timeframe, 60))
    ts = df["ts"].sort_values().reset_index(drop=True)
    deltas = ts.diff()
    gaps = []
    for i in range(1, len(ts)):
        if deltas[i] > step:
            missing = int(deltas[i] / step) - 1
            gaps.append((ts[i - 1], ts[i], missing))
    return gaps


@dataclass
class HistorySummary:
    symbol: str
    timeframe: str
    candles: int
    start: object
    end: object
    gaps: int
    missing_candles: int


def summary(symbol: str, timeframe: str) -> HistorySummary:
    df = load_ohlcv(symbol, timeframe)
    if df.empty:
        return HistorySummary(symbol, timeframe, 0, None, None, 0, 0)
    g = detect_gaps(df, timeframe)
    return HistorySummary(symbol, timeframe, len(df), df["ts"].iloc[0], df["ts"].iloc[-1],
                          len(g), sum(x[2] for x in g))


def update_history(symbol: str = "BTC/USDT", timeframe: str = "1h",
                   total: int = 17520, exchange: str = "binance",
                   since: int | None = None) -> HistorySummary:
    """Backfill histórico REAL paginando hacia delante en el tiempo.

    A diferencia de pedir siempre las últimas N velas (que nunca avanza), aquí se
    arranca en `now - total*tf` (o en `since` si se da) y se avanza el cursor con
    cada bloque de 1000 hasta alcanzar el presente. `save_ohlcv` deduplica, así que
    re-ejecutar es idempotente y solo baja lo que falta.

    Garantía de integridad: si la red devuelve datos sintéticos (sin conexión a
    Binance), NO se persisten — el store histórico nunca se contamina. Bajar datos
    reales debe hacerse en una máquina con acceso a Binance.
    """
    tf_ms = TF_MS.get(timeframe, 3_600_000)
    now_ms = int(time.time() * 1000)
    if since is None:
        since = now_ms - total * tf_ms
    last_seen = None
    while since < now_ms:
        res = data_mod.fetch_ohlcv(symbol, timeframe=timeframe, limit=1000,
                                   exchange=exchange, since=since)
        if res.source != "binance":
            print(f"[store] fetch no-real (source={res.source}); se aborta el backfill "
                  "sin guardar datos sintéticos. Ejecuta esto en una máquina con red real.")
            break
        if res.df.empty:
            break
        save_ohlcv(res.df, symbol, timeframe)
        last_ms = int(res.df["ts"].iloc[-1].timestamp() * 1000)
        if last_ms == last_seen:        # sin progreso: corta para no ciclar
            break
        last_seen = last_ms
        since = last_ms + tf_ms
        if len(res.df) < 1000:          # alcanzamos el borde (velas más recientes)
            break
    return summary(symbol, timeframe)

"""Predicción base: indicadores -> dirección, probabilidad y confianza.

Modelo BASELINE honesto (no caja negra). Combina momentum, tendencia y RSI
en un score, lo mapea a probabilidad con una sigmoide y estima confianza por
la fuerza/acuerdo de las señales. Sustituible más adelante por un ML validado.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class Forecast:
    symbol: str
    direction: str        # "alza" | "baja" | "lateral"
    probability: float    # prob. de que la dirección acierte (0-1)
    confidence: float     # 0-1
    horizon: str
    detail: dict


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).rolling(n).mean()
    down = (-delta.clip(upper=0)).rolling(n).mean()
    rs = up / down.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def _sigmoid(x: float) -> float:
    return 1 / (1 + np.exp(-x))


def predict(df: pd.DataFrame, symbol: str, horizon: str = "4h") -> Forecast:
    close = df["close"].astype(float)
    if len(close) < 50:
        return Forecast(symbol, "lateral", 0.5, 0.0, horizon, {"reason": "datos insuficientes"})

    ema_fast = _ema(close, 12)
    ema_slow = _ema(close, 26)
    rsi = _rsi(close, 14)
    ret = close.pct_change()
    # Vol EWMA (RiskMetrics): la única magnitud con skill predictivo medido (+ ver
    # volforecast.py). Alimenta stops/sizing y la penalización de confianza.
    from .volforecast import ewma_vol
    vol = float(ewma_vol(ret).iloc[-1])
    mom = (close.iloc[-1] / close.iloc[-10] - 1)          # momentum 10 velas
    trend = (ema_fast.iloc[-1] - ema_slow.iloc[-1]) / close.iloc[-1]
    rsi_now = rsi.iloc[-1]
    rsi_signal = (rsi_now - 50) / 50                       # -1..1

    # Score combinado (pesos simples, normalizados)
    score = (np.tanh(mom * 20) * 0.4
             + np.tanh(trend * 50) * 0.4
             + rsi_signal * 0.2)

    prob_up = _sigmoid(score * 3)                          # 0-1
    if prob_up > 0.55:
        direction, probability = "alza", prob_up
    elif prob_up < 0.45:
        direction, probability = "baja", 1 - prob_up
    else:
        direction, probability = "lateral", 0.5

    # Confianza: acuerdo de señales + penalización por alta volatilidad
    agree = np.mean([np.sign(mom) == np.sign(score),
                     np.sign(trend) == np.sign(score),
                     np.sign(rsi_signal) == np.sign(score)])
    vol_pen = float(np.clip(1 - (vol or 0) * 30, 0, 1))
    confidence = float(np.clip(abs(score) * agree * vol_pen, 0, 1))

    return Forecast(
        symbol, direction, float(probability), confidence, horizon,
        {"momentum_10": float(mom), "trend": float(trend),
         "rsi": float(rsi_now), "volatility": float(vol or 0),
         "score": float(score), "prob_up": float(prob_up)},
    )

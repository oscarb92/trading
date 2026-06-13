"""Predicción de VOLATILIDAD (EWMA / RiskMetrics) — lo que SÍ se puede predecir.

La dirección del precio resultó impredecible (skill ≈ 0, ver calibration.py). La
volatilidad es otra historia: se agrupa en el tiempo (días movidos siguen a días
movidos), y eso la hace genuinamente pronosticable. Este módulo lo MIDE con la
misma vara honesta que usamos para la dirección: predicción causal, evaluación en
la segunda mitad del histórico, y skill contra una base ingenua.

Para qué sirve (sin necesidad de saber la dirección): dimensionar stops y posiciones
(`size_position` ya reduce tamaño cuando la vol sube), presupuestar riesgo y stress
tests. Información técnica, no asesoría financiera.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def ewma_vol(ret: pd.Series, lam: float = 0.94) -> pd.Series:
    """Volatilidad EWMA (RiskMetrics): sigma²_t = λ·sigma²_{t-1} + (1−λ)·r²_{t-1}.

    CAUSAL: la predicción para la vela t usa solo retornos hasta t−1 (shift).
    """
    r2 = ret.fillna(0.0) ** 2
    sig2 = r2.ewm(alpha=1 - lam, adjust=False).mean().shift(1)
    return np.sqrt(sig2)


def vol_skill(df: pd.DataFrame, lam: float = 0.94) -> dict:
    """¿Cuánto mejor predice la EWMA la magnitud del próximo movimiento que una base
    ingenua (la vol media constante del train)?

    Mismo esquema que la calibración: la 1ª mitad fija la base; se evalúa TODO en la
    2ª mitad. skill = 1 − MSE(modelo)/MSE(base) sobre |retorno| (≈ Brier de la vol).
    También reporta la correlación pronóstico↔realizado, más intuitiva.
    """
    ret = df["close"].astype(float).pct_change()
    pred = ewma_vol(ret, lam)
    realized = ret.abs()
    mask = pred.notna() & realized.notna()
    pred, realized = pred[mask].reset_index(drop=True), realized[mask].reset_index(drop=True)
    n = len(pred)
    if n < 1000:
        return {"n": n, "error": "muestra insuficiente"}
    half = n // 2
    base = float(realized.iloc[:half].mean())          # base: 'la vol de mañana = la media'
    p_test, r_test = pred.iloc[half:].values, realized.iloc[half:].values
    # E|r| de una normal = sigma·sqrt(2/pi): ajustar la escala del pronóstico
    p_abs = p_test * np.sqrt(2 / np.pi)
    mse_model = float(((p_abs - r_test) ** 2).mean())
    mse_base = float(((base - r_test) ** 2).mean())
    corr = float(np.corrcoef(p_test, r_test)[0, 1])
    return {"n": n, "n_test": int(n - half), "lam": lam,
            "skill": round(1 - mse_model / mse_base, 4),
            "corr": round(corr, 4), "base_abs_ret": round(base, 5)}

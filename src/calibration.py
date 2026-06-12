"""Calibración del forecast: reliability curve (cierre del pendiente de Fase 3).

Una probabilidad está CALIBRADA si, cuando el modelo dice "60% de subir", el precio
sube ~60% de las veces. Aquí se compara la probabilidad causal del baseline
(`backtest.prob_up`, misma lógica que `forecast.predict`) contra la frecuencia
observada en la vela siguiente, por tramos (bins).

También se reporta el Brier score contra la base climatológica (predecir siempre la
frecuencia media): si el skill ≤ 0, las probabilidades no aportan información y NO
deben usarse para sizing (Kelly) ni para filtrar señales por "confianza".
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from . import backtest as bt


def reliability(df: pd.DataFrame, n_bins: int = 10, min_bin: int = 30) -> dict:
    """Curva de fiabilidad de prob_up sobre un histórico OHLCV.

    Devuelve {"table": DataFrame(bin, prob_predicha, frec_observada, n),
              "brier": float, "brier_base": float, "skill": float, "n": int}.
    skill = 1 − brier/brier_base; ≤ 0 → sin valor predictivo sobre la base.
    """
    p = bt.prob_up(df)
    ret_next = df["close"].astype(float).pct_change().shift(-1)
    mask = p.notna() & ret_next.notna()
    p = p[mask].astype(float)
    y = (ret_next[mask] > 0).astype(float)

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        m = idx == b
        if int(m.sum()) < min_bin:                  # bins casi vacíos: sin evidencia
            continue
        rows.append({"bin": f"{edges[b]:.2f}–{edges[b + 1]:.2f}",
                     "prob. predicha (media)": round(float(p[m].mean()), 3),
                     "frec. observada": round(float(y[m].mean()), 3),
                     "n velas": int(m.sum())})
    brier = float(((p - y) ** 2).mean()) if len(p) else float("nan")
    base_rate = float(y.mean()) if len(y) else 0.5
    brier_base = float(((base_rate - y) ** 2).mean()) if len(y) else float("nan")
    skill = 1.0 - brier / brier_base if brier_base > 0 else 0.0
    return {"table": pd.DataFrame(rows), "brier": round(brier, 4),
            "brier_base": round(brier_base, 4), "skill": round(skill, 4), "n": int(len(p))}


def verdict(r: dict) -> str:
    """Lectura honesta de la calibración para mostrar al usuario."""
    if r["n"] < 500:
        return "Muestra insuficiente para juzgar la calibración."
    if r["skill"] <= 0:
        return (f"SIN valor predictivo: Brier {r['brier']} ≥ base {r['brier_base']} "
                f"(skill {r['skill']:+.2%}). Las probabilidades del forecast NO están "
                "calibradas: no usarlas para sizing ni como 'confianza' real.")
    return (f"Skill {r['skill']:+.2%} sobre la base (Brier {r['brier']} vs {r['brier_base']}). "
            "Modesto: verificar estabilidad por subperiodos antes de fiarse.")

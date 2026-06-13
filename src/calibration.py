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


# ---------------------------------------------------------------------------
# RE-calibración (Platt scaling): reaprende el mapa score -> probabilidad con
# datos, en vez de la sigmoide de constantes a mano. Importante: calibrar
# arregla la MENTIRA del número, no crea poder predictivo. Si el score no
# discrimina, el calibrador honesto colapsa todo a la tasa base (~50%) = "no sé".
# ---------------------------------------------------------------------------

def platt_fit(x: np.ndarray, y: np.ndarray, iters: int = 60) -> tuple[float, float]:
    """Regresión logística 1D por Newton-Raphson: P(y=1) = sigmoid(a·x + b).

    Sin sklearn: dos parámetros, hessiana 2x2 cerrada. `x` es el logit crudo del
    modelo (o el score), `y` los resultados observados {0,1}.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    a, b = 1.0, 0.0
    for _ in range(iters):
        z = np.clip(a * x + b, -35, 35)
        p = 1.0 / (1.0 + np.exp(-z))
        g_a = float(np.sum((p - y) * x))            # gradiente
        g_b = float(np.sum(p - y))
        w = p * (1 - p)
        h_aa = float(np.sum(w * x * x)) + 1e-9      # hessiana
        h_ab = float(np.sum(w * x))
        h_bb = float(np.sum(w)) + 1e-9
        det = h_aa * h_bb - h_ab * h_ab
        if abs(det) < 1e-12:
            break
        da = (g_a * h_bb - g_b * h_ab) / det
        db = (g_b * h_aa - g_a * h_ab) / det
        a, b = a - da, b - db
        if abs(da) < 1e-10 and abs(db) < 1e-10:
            break
    return float(a), float(b)


def _logit(p: pd.Series) -> pd.Series:
    p = p.clip(1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def walkforward_calibration(df: pd.DataFrame, n_bins: int = 10) -> dict:
    """Calibra en la 1ª mitad (train) y evalúa en la 2ª (test): raw vs calibrado.

    Sin look-ahead: los parámetros (a, b) solo ven el pasado. Devuelve Brier/skill
    de ambas versiones en TEST, los parámetros aprendidos y la dispersión de las
    probabilidades calibradas (si ~0, el calibrador dice "no sé" siempre — que es
    la respuesta honesta de un score sin señal).
    """
    p_raw = bt.prob_up(df)
    ret_next = df["close"].astype(float).pct_change().shift(-1)
    mask = p_raw.notna() & ret_next.notna()
    p_raw = p_raw[mask].astype(float).reset_index(drop=True)
    y = (ret_next[mask] > 0).astype(float).reset_index(drop=True)
    n = len(p_raw)
    if n < 1000:
        return {"n": n, "error": "muestra insuficiente"}
    half = n // 2
    x = _logit(p_raw)

    a, b = platt_fit(x.iloc[:half].values, y.iloc[:half].values)
    z = np.clip(a * x.iloc[half:].values + b, -35, 35)
    p_cal = 1.0 / (1.0 + np.exp(-z))
    p_test_raw = p_raw.iloc[half:].values
    y_test = y.iloc[half:].values

    base = float(y_test.mean())
    brier_base = float(((base - y_test) ** 2).mean())
    brier_raw = float(((p_test_raw - y_test) ** 2).mean())
    brier_cal = float(((p_cal - y_test) ** 2).mean())
    return {"n": n, "n_test": int(n - half), "a": round(a, 4), "b": round(b, 4),
            "base_rate": round(base, 4), "brier_base": round(brier_base, 4),
            "brier_raw": round(brier_raw, 4), "brier_cal": round(brier_cal, 4),
            "skill_raw": round(1 - brier_raw / brier_base, 4),
            "skill_cal": round(1 - brier_cal / brier_base, 4),
            "cal_prob_media": round(float(p_cal.mean()), 4),
            "cal_prob_std": round(float(p_cal.std()), 4)}

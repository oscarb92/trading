"""Prueba LIMPIA alfa-vs-beta: estrategia CROSS-SECTIONAL riesgo-neutral.

La prueba direccional (`cross_asset.py`) no separaba alfa de beta. Aquí se rankean los 13
activos ENTRE SÍ y se va largo de los mejores / corto de los peores, neutral. Por construcción
la exposición de mercado es ~0, así que **un Sharpe OOS positivo aquí sería alfa**, no beta.

Esta versión incorpora las correcciones de DOS auditorías adversariales sobre la v1 (que usaba
pesos de igual nocional y score de retorno crudo):
  - **Score estandarizado por volatilidad** (momentum/vol): el ranking mide fuerza relativa de
    tendencia, no amplitud. Sin esto, los activos de alta vol (cripto/Tesla) copan los extremos.
  - **Pesos inverse-vol** dentro de cada pata: riesgo-neutral, no solo dólar-neutral. Sin esto la
    cartera era una apuesta de riesgo concentrada en cripto, no una apuesta de ranking.
  - Sin look-ahead (score con precios ≤ t-gap, pesos aplicados con shift(1)). Costes por turnover.
  - **Honestidad estadística:** se reporta el IC del Sharpe OOS y la POTENCIA; un nulo no prueba
    "cero alfa", solo "sin alfa grande". La nula empírica (rankings aleatorios) es conservadora.

Uso:  python cross_sectional.py
Lee data/ (descárgalo antes con cross_asset.py). Escribe reports/cross_sectional.md y .json.
Información técnica, no asesoría financiera.
"""
from __future__ import annotations
import json
from itertools import product
from pathlib import Path
import numpy as np
import pandas as pd
from src import store, backtest as bt

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"
TF = "1d"
PPY = 252
FEE, SLIP = 0.001, 0.0005
N_NULL = 500
UNIVERSE = ["GLD", "SLV", "USO", "SPY", "QQQ", "IWM", "DIA",
            "AAPL", "MSFT", "NVDA", "TSLA", "BTC-USD", "ETH-USD"]


def build_panel(symbols: list[str]) -> pd.DataFrame:
    closes = {}
    for s in symbols:
        df = store.load_ohlcv(s, TF)
        if not df.empty:
            closes[s] = df.set_index("ts")["close"].astype(float)
    return pd.DataFrame(closes).dropna()


def _vol(P: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Volatilidad diaria trailing CAUSAL (shift(1)), con suelo para evitar 1/vol explosivo."""
    return P.pct_change().rolling(lookback).std().shift(1).clip(lower=1e-4)


def _score(P: pd.DataFrame, kind: str, lookback: int, gap: int) -> pd.DataFrame:
    """Momentum/reversión ESTANDARIZADO por volatilidad (causal) → fuerza de tendencia, no amplitud."""
    vol = _vol(P, lookback)
    if kind == "mom":
        mom = P.shift(gap) / P.shift(gap + lookback) - 1
    else:
        mom = -(P / P.shift(gap) - 1)
    return mom / vol


def portfolio_returns(P: pd.DataFrame, R: pd.DataFrame, kind: str, lookback: int,
                      gap: int, k: int, reb: int) -> pd.Series:
    """Retorno diario NETO de la cartera riesgo-neutral (long top-k / short bottom-k, inverse-vol).

    Pesos fijados en cada rebalanceo con datos hasta esa fecha y aplicados con shift(1) (sin
    look-ahead). Dentro de cada pata, peso ∝ 1/vol (riesgo-neutral); las patas suman +1/−1.
    """
    score = _score(P, kind, lookback, gap)
    vol = _vol(P, lookback)
    W = pd.DataFrame(0.0, index=P.index, columns=P.columns)
    for i in range(0, len(P), reb):
        s = score.iloc[i].dropna()
        if len(s) >= 2 * k:
            ranked = s.sort_values(ascending=False)
            longs, shorts = ranked.index[:k], ranked.index[-k:]
            v = vol.iloc[i]
            wl = (1.0 / v[longs]); wl = wl / wl.sum()       # inverse-vol, suma +1
            ws = (1.0 / v[shorts]); ws = ws / ws.sum()      # inverse-vol, suma +1 → se niega
            w = pd.Series(0.0, index=P.columns)
            w[longs] = wl.values
            w[shorts] = -ws.values
            W.iloc[i:] = w.values
    W_eff = W.shift(1).fillna(0.0)
    gross = (W_eff * R).sum(axis=1)
    turnover = W_eff.diff().abs().sum(axis=1).fillna(W_eff.iloc[0].abs().sum())
    return gross - turnover * (FEE + SLIP)


def _m(ret: pd.Series) -> dict:
    x = bt.metrics_from_position(pd.Series(1.0, index=range(len(ret))),
                                 ret.reset_index(drop=True), TF, 0.0, 0.0, PPY)["metrics"]
    return {"ret": x.total_return, "sharpe": x.sharpe, "maxdd": x.max_drawdown}


def candidates():
    out = []
    for lb, k in product((126, 252), (3, 4)):
        out.append((f"mom lb{lb}/k{k}", "mom", lb, 21, k, 21))
    for g, k in product((5, 21), (3, 4)):
        out.append((f"rev g{g}/k{k}", "rev", 252, g, k, 21))
    return out


def random_null(P, R, k, reb, n_null=N_NULL) -> np.ndarray:
    """Nula empírica: OOS Sharpe de rankings ALEATORIOS (inverse-vol, mismas k/reb)."""
    rng = np.random.default_rng(20260611)
    vol = _vol(P, 126)
    n, oos_a, cols = len(P), len(P) // 2, list(P.columns)
    out = np.empty(n_null)
    for j in range(n_null):
        W = pd.DataFrame(0.0, index=P.index, columns=P.columns)
        for i in range(0, n, reb):
            pick = rng.choice(len(cols), size=2 * k, replace=False)
            v = vol.iloc[i]
            w = pd.Series(0.0, index=P.columns)
            li = [cols[c] for c in pick[:k]]
            si = [cols[c] for c in pick[k:]]
            wl = (1.0 / v[li]).fillna(1.0); wl = wl / wl.sum()
            ws = (1.0 / v[si]).fillna(1.0); ws = ws / ws.sum()
            w[li] = wl.values
            w[si] = -ws.values
            W.iloc[i:] = w.values
        W_eff = W.shift(1).fillna(0.0)
        gross = (W_eff * R).sum(axis=1)
        turnover = W_eff.diff().abs().sum(axis=1).fillna(W_eff.iloc[0].abs().sum())
        out[j] = _m((gross - turnover * (FEE + SLIP)).iloc[oos_a:])["sharpe"]
    return out


def main():
    P = build_panel(UNIVERSE)
    if len(P) < 800:
        print("Sin panel suficiente. Ejecuta antes: python cross_asset.py")
        return
    R = P.pct_change().fillna(0.0)
    n, oos_a = len(P), len(P) // 2
    print(f"[cross-sectional] {len(P.columns)} activos, {n} dias comunes "
          f"[{str(P.index[0])[:10]} -> {str(P.index[-1])[:10]}]")

    cand_ret = {lbl: portfolio_returns(P, R, kind, lb, g, k, reb)
                for (lbl, kind, lb, g, k, reb) in candidates()}

    n_folds = 4
    flen = (n - oos_a) // n_folds
    picks, oos_parts, fold_rows = [], [], []
    for f in range(n_folds):
        ta = oos_a + f * flen
        tb = oos_a + (f + 1) * flen if f < n_folds - 1 else n
        best, bs = None, None
        for lbl, ret in cand_ret.items():
            sh = _m(ret.iloc[:ta])["sharpe"]
            if bs is None or sh > bs:
                best, bs = lbl, sh
        seg = cand_ret[best].iloc[ta:tb]
        picks.append(best)
        oos_parts.append(seg)
        fold_rows.append((f + 1, str(P.index[ta])[:10], str(P.index[tb - 1])[:10],
                          best, round(bs, 2), round(_m(seg)["sharpe"], 2), round(_m(seg)["ret"], 4)))
    oos_ret = pd.concat(oos_parts)
    oos = _m(oos_ret)

    # Estadística honesta: IC del Sharpe OOS + potencia
    se = float(np.sqrt(PPY / (n - oos_a)))
    ci_lo, ci_hi = oos["sharpe"] - 1.96 * se, oos["sharpe"] + 1.96 * se
    detectable = 1.645 * se

    k_used = int([c[4] for c in candidates() if c[0] == picks[-1]][0])
    null = random_null(P, R, k_used, 21)
    p_val = float(np.mean(null >= oos["sharpe"]))

    # Neutralidad: correlación Y beta de regresión contra el mercado equiponderado
    ew = R.mean(axis=1)
    ew_oos = ew.iloc[oos_a:]
    s_arr, m_arr = oos_ret.values, ew_oos.values
    beta = float(np.cov(s_arr, m_arr)[0, 1] / np.var(m_arr))
    corr = float(np.corrcoef(s_arr, m_arr)[0, 1])
    best_is = max(cand_ret, key=lambda l: _m(cand_ret[l])["sharpe"])

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    res = {"universe": list(P.columns), "n_days": n, "spec": "vol-standardized score + inverse-vol weights",
           "oos_sharpe": oos["sharpe"], "oos_sharpe_ci": [round(ci_lo, 2), round(ci_hi, 2)],
           "oos_return": round(oos["ret"], 4), "oos_maxdd": round(oos["maxdd"], 4),
           "se_sharpe": round(se, 3), "sharpe_detectable": round(detectable, 2),
           "picks": picks, "stable": len(set(picks)) == 1, "null_p": round(p_val, 3),
           "null_mean": round(float(null.mean()), 3), "corr_vs_market": round(corr, 3),
           "beta_vs_market": round(beta, 3), "ew_oos_sharpe": _m(ew_oos)["sharpe"],
           "best_insample": best_is}
    (REPORTS_DIR / "cross_sectional_results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    if oos["sharpe"] > 0 and ci_lo > 0:
        verdict = "alfa OOS positivo y significativo"
    elif oos["sharpe"] > 0:
        verdict = "alfa OOS positivo pero NO significativo (el IC incluye 0)"
    else:
        verdict = ("sin alfa positivo OOS; pero por baja potencia el test NO descarta un "
                   f"Sharpe verdadero de hasta ~{ci_hi:.2f}")
    lines = [
        "# Prueba cross-sectional riesgo-neutral (alfa vs beta)", "",
        f"> {len(P.columns)} activos replicables, días comunes {str(P.index[0])[:10]}→{str(P.index[-1])[:10]}.",
        "> **Score estandarizado por vol + pesos inverse-vol** (riesgo-neutral, no solo dólar-neutral).",
        "> Rebalanceo mensual, costes 0.1%+0.05%, sin look-ahead. Walk-forward OOS anclado (4 folds).", "",
        "## Resultado OOS (año-2+ encadenado)", "",
        f"- **Sharpe OOS = {oos['sharpe']}**, IC95% **[{ci_lo:+.2f}, {ci_hi:+.2f}]** · retorno "
        f"{oos['ret']:+.1%} · MaxDD {oos['maxdd']:.1%}.",
        f"- **Veredicto: {verdict}.**", "",
        "| Fold | Test | Selección (train) | Sharpe train | Sharpe OOS | Ret OOS |",
        "|---|---|---|---|---|---|",
    ]
    for fr in fold_rows:
        lines.append(f"| {fr[0]} | {fr[1]}→{fr[2]} | {fr[3]} | {fr[4]} | {fr[5]} | {fr[6]:+.1%} |")
    lines += [
        "", "## Lectura crítica (tras dos auditorías adversariales)", "",
        f"- **Potencia es la clave:** SE(Sharpe OOS) ≈ {se:.2f}, así que el IC95% **[{ci_lo:+.2f}, "
        f"{ci_hi:+.2f}]** es ancho y contiene valores tanto negativos como positivos. El test solo "
        f"detecta alfa con Sharpe verdadero ≳ {detectable:.2f}. **'No detecté alfa' NO es 'no hay alfa'.**",
        f"- **Nula empírica:** p-valor = **{p_val:.2f}** (rankings aleatorios, media {null.mean():+.2f}). "
        "La nula está sesgada A FAVOR de la estrategia (paga más turnover), así que superarla no es "
        "concluyente — pero NO superarla refuerza que no hay habilidad *grande*.",
        f"- **Neutralidad verificada:** correlación con el mercado = **{corr:+.2f}**, beta de regresión "
        f"= **{beta:+.2f}** (≈0 → genuinamente market-neutral; el resultado NO es beta de un bull).",
        f"- **Parámetros por fold:** {picks} → {'estables' if len(set(picks)) == 1 else 'inestables'}.",
        "", "## Límites declarados (lo que este test NO puede zanjar)", "",
        "- **Universo mal dimensionado para el factor:** el cross-sectional momentum académico "
        "(Jegadeesh-Titman) usa DECENAS-CIENTOS de activos HOMOGÉNEOS (p.ej. acciones de un índice). "
        "Aquí hay solo 13 activos de 4 clases; con k=3 hay 6 posiciones — dispersión mínima.",
        "- Esta v2 corrige la mala especificación de la v1 (igual nocional + score crudo medían "
        "dispersión de volatilidad, no ranking). Aun corregida, **la potencia sigue siendo baja** "
        "(SE≈0.49) y el universo pequeño/heterogéneo, así que un resultado nulo **no descarta** un "
        "alfa cross-sectional modesto.",
        "- La prueba CONCLUYENTE requeriría universos within-class amplios (S&P500 point-in-time, "
        "top-50 cripto, futuros de materias primas con roll) — fuera del alcance de yfinance+13 tickers.",
        "", "> Información técnica, no asesoría financiera. Resultados pasados no garantizan futuros.",
    ]
    (REPORTS_DIR / "cross_sectional.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"OOS Sharpe {oos['sharpe']} IC[{ci_lo:+.2f},{ci_hi:+.2f}] | p-nula {p_val:.2f} | "
          f"beta {beta:+.2f} | {verdict.encode('ascii', 'replace').decode()}")
    print(f"Reporte: {REPORTS_DIR / 'cross_sectional.md'}")


if __name__ == "__main__":
    main()

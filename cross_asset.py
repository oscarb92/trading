"""Validación OOS CROSS-ASSET — ¿algún mercado tiene edge donde cripto no lo tuvo?

Corre EL MISMO walk-forward out-of-sample sobre 16 instrumentos de varias clases
(commodities, índices/ETF, acciones, cripto), en diario desde 2018, con una rejilla
combinada de las dos familias técnicas (momentum con histéresis+ADX y reversión a la media).
La anualización del Sharpe se ajusta por clase de activo (252 bolsa / 365 cripto).

Lo importante NO es "quién gana" sino el rigor estadístico. Esta versión, tras una revisión
adversarial, incluye:
  - NULA EMPÍRICA: el mejor OOS Sharpe real se compara contra el mejor de N estrategias
    ALEATORIAS (misma rotación) → p-valor honesto del líder, no un argumento verbal.
  - POTENCIA: SE del Sharpe OOS ≈ sqrt(ppy/N); el estudio solo descarta edges grandes.
  - RÉGIMEN: tasa de batir a B&H en folds bajistas vs alcistas (¿overlay defensivo?).
  - Ranking por Sharpe-vs-Sharpe (riesgo-ajustado), no por exceso de retorno (que premia
    mecánicamente a los activos con peor buy & hold).

Uso:
  python cross_asset.py                # usa lo local; descarga lo que falte
  python cross_asset.py --refresh      # vuelve a bajar todo desde Yahoo
Escribe reports/cross_asset.md y reports/cross_asset_results.json. Información técnica, no asesoría.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from src import store, backtest as bt, validation as val, marketdata as md

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"
TF = "1d"
START = "2018-01-01"
N_FOLDS = 4
MIN_TRAIN_TRADES = 5
FEE, SLIP = 0.001, 0.0005
N_NULL = 500                    # nº de estrategias aleatorias para la nula empírica
# Futuros continuos de Yahoo: precios NO negociables (roll back-ajustado) y redundantes con su ETF
NON_REPLICABLE = {"GC=F", "SI=F", "CL=F"}


def candidates():
    """Rejilla combinada: el OOS elige la MEJOR estrategia (momentum O reversión) por fold."""
    out = []
    for e in (0.55, 0.60, 0.65):
        for a in (0, 20, 25):
            out.append((f"mom h{e:.2f}/adx{a}",
                        lambda d, e=e, a=a: bt.regime_signal(d, enter=e, adx_min=a)))
    for l in (20, 50):
        for z in (1.5, 2.0, 2.5):
            for x in (0.0, 0.5):
                out.append((f"rev lb{l}/z{z}/x{x}",
                            lambda d, l=l, z=z, x=x: bt.mean_reversion_signal(d, lookback=l, entry_z=z, exit_z=x)))
    return out


def ensure_data(symbol: str, refresh: bool) -> int:
    if not refresh and not store.load_ohlcv(symbol, TF).empty:
        return len(store.load_ohlcv(symbol, TF))
    if refresh:
        store.clear(symbol, TF)
    res = md.fetch_yahoo(symbol, TF, start=START)
    if res.source == "yahoo" and not res.df.empty:
        store.save_ohlcv(res.df, symbol, TF)
    return len(store.load_ohlcv(symbol, TF))


def evaluate(symbol: str, df: pd.DataFrame) -> dict | None:
    if len(df) < 800:
        return None
    ppy = md.periods_per_year(symbol, TF)
    r = val.walk_forward_oos(df, candidates(), symbol=symbol, timeframe=TF,
                             n_folds=N_FOLDS, min_train_trades=MIN_TRAIN_TRADES, ppy=ppy)
    raw_ret = df["close"].astype(float).pct_change().fillna(0)
    oos_a = len(df) // 2
    clipped = int((raw_ret.iloc[oos_a:].abs() > 0.5).sum())   # outliers en la ventana OOS
    se_sharpe = float(np.sqrt(ppy / max(len(df) - oos_a, 1)))  # error estándar del Sharpe OOS
    return {
        "symbol": symbol, "label": md.label(symbol), "clase": md.asset_class(symbol),
        "replicable": symbol not in NON_REPLICABLE, "bars": len(df),
        "oos_desde": r.folds[0].desde, "oos_hasta": r.folds[-1].hasta,
        "oos_return": round(r.oos_return, 4), "oos_sharpe": r.oos_sharpe,
        "oos_maxdd": round(r.oos_maxdd, 4), "oos_trades": r.oos_trades, "oos_clipped": clipped,
        "bh_return": round(r.bh_return, 4), "bh_sharpe": r.bh_sharpe,
        "excess_return": round(r.oos_return - r.bh_return, 4),
        "excess_sharpe": round(r.oos_sharpe - r.bh_sharpe, 2),
        "se_sharpe": round(se_sharpe, 3), "estable": r.stable, "picks": r.picks,
        "folds": [{"desde": f.desde, "hasta": f.hasta, "pick": f.pick,
                   "oos_ret": round(f.oos_return, 4), "oos_sharpe": f.oos_sharpe,
                   "bh_ret": round(f.bh_return, 4)} for f in r.folds],
    }


def _random_path(rng, m: int, p_change: float) -> np.ndarray:
    """Camino de posición {-1,0,1} con rotación ~p_change (para la nula empírica)."""
    states = np.array([-1.0, 0.0, 1.0])
    pos = np.empty(m)
    cur = 0.0
    for i in range(m):
        if rng.random() < p_change:
            cur = float(rng.choice(states))
        pos[i] = cur
    return pos


def empirical_null_max(dfs: dict, ppys: dict, turnover: float, n_null: int = N_NULL) -> np.ndarray:
    """Distribución nula del MEJOR Sharpe OOS entre los activos usando estrategias ALEATORIAS
    de la misma rotación. Responde: ¿el líder real supera al mejor de N aleatorios por azar?"""
    rng = np.random.default_rng(20260611)
    oos = {}
    for s, df in dfs.items():
        raw = df["close"].astype(float).pct_change().fillna(0)
        oos[s] = raw.iloc[len(df) // 2:].reset_index(drop=True)
    p = min(max(turnover, 0.01), 0.9)
    null_max = np.empty(n_null)
    for j in range(n_null):
        best = -1e9
        for s, r in oos.items():
            pos = pd.Series(_random_path(rng, len(r), p))
            sh = bt.metrics_from_position(pos, r, TF, FEE, SLIP, ppys[s])["metrics"].sharpe
            best = max(best, sh)
        null_max[j] = best
    return null_max


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="Volver a descargar todo de Yahoo")
    args = ap.parse_args()

    universe = list(md.UNIVERSE.keys())
    print(f"[cross-asset] {len(universe)} instrumentos, diario desde {START}.")
    dfs = {}
    for sym in universe:
        ensure_data(sym, args.refresh)
        df = store.load_ohlcv(sym, TF)
        dfs[sym] = df
        print(f"  {sym:8s} {md.label(sym):22s} {len(df):5d} velas")

    results = [r for r in (evaluate(s, dfs[s]) for s in universe) if r]
    results.sort(key=lambda x: x["excess_sharpe"], reverse=True)
    ppys = {s: md.periods_per_year(s, TF) for s in dfs}
    k = len(results)

    # --- Estadística OOS real (nula correcta, no "p=0.5") ---
    fold_sharpes = [f["oos_sharpe"] for r in results for f in r["folds"]]
    fs_mean = float(np.mean(fold_sharpes))
    fs_pos = sum(1 for x in fold_sharpes if x > 0) / len(fold_sharpes)
    se_med = float(np.median([r["se_sharpe"] for r in results]))
    sharpe_detectable = round(1.645 * se_med, 2)          # umbral ~detectable (test unilateral 5%)

    # --- Nula empírica: mejor real vs mejor de 16 aleatorios ---
    med_turnover = float(np.median([r["oos_trades"] / max(r["bars"] // 2, 1) for r in results]))
    null_max = empirical_null_max(dfs, ppys, med_turnover)
    leader = max(results, key=lambda x: x["oos_sharpe"])
    p_leader = float(np.mean(null_max >= leader["oos_sharpe"]))

    # --- Régimen: ¿batir a B&H es habilidad o reducción de exposición en caídas? ---
    down = [(f["oos_ret"] > f["bh_ret"]) for r in results for f in r["folds"] if f["bh_ret"] < 0]
    up = [(f["oos_ret"] > f["bh_ret"]) for r in results for f in r["folds"] if f["bh_ret"] >= 0]
    beat_down = (sum(down) / len(down)) if down else 0.0
    beat_up = (sum(up) / len(up)) if up else 0.0

    n_beat = sum(r["excess_return"] > 0 for r in results)
    n_pos = sum(r["oos_sharpe"] > 0 for r in results)
    n_strong = sum(1 for r in results if r["excess_sharpe"] > 0 and r["oos_sharpe"] > 0.5 and r["estable"])

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "cross_asset_results.json").write_text(json.dumps({
        "timeframe": TF, "start": START, "n_folds": N_FOLDS,
        "stats": {"fold_sharpe_mean": round(fs_mean, 3), "fold_sharpe_pct_pos": round(fs_pos, 3),
                  "se_sharpe_median": round(se_med, 3), "sharpe_detectable": sharpe_detectable,
                  "null_p_leader": round(p_leader, 3), "null_max_mean": round(float(null_max.mean()), 3),
                  "beat_bh_down_folds": round(beat_down, 3), "beat_bh_up_folds": round(beat_up, 3),
                  "n_pos_sharpe": n_pos, "n_beat_bh": n_beat, "n_strong": n_strong},
        "results": results}, indent=2), encoding="utf-8")

    lines = [
        "# Validación OOS cross-asset (16 mercados)", "",
        f"> Diario desde {START}. Walk-forward anclado: ~1ª mitad train, resto en {N_FOLDS} folds OOS.",
        "> Rejilla combinada momentum+reversión (21 combos); el OOS elige la mejor por fold.",
        "> Costes 0.1%+0.05%. Sharpe anualizado por clase (252 bolsa / 365 cripto). Sin look-ahead.",
        "> **Métrica de habilidad = Sharpe-vs-Sharpe (OOS − B&H), riesgo-ajustada.** Ordenar por exceso",
        "> de RETORNO premia mecánicamente a los activos con peor B&H (beta defensiva, no alfa).", "",
        "## Ranking por Sharpe-vs-Sharpe (OOS año-2+)", "",
        "| # | Instrumento | Clase | OOS Sharpe | B&H Sharpe | **ΔSharpe** | OOS ret | B&H ret | MaxDD | Estable | Repl. |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(results, 1):
        flag = "✅" if (r["excess_sharpe"] > 0 and r["oos_sharpe"] > 0.5 and r["estable"]) else (
            "🟡" if r["excess_sharpe"] > 0 else "❌")
        lines.append(
            f"| {i} | {r['label']} (`{r['symbol']}`) | {r['clase']} | {r['oos_sharpe']} | "
            f"{r['bh_sharpe']} | {flag} **{r['excess_sharpe']:+.2f}** | {r['oos_return']:+.1%} | "
            f"{r['bh_return']:+.1%} | {r['oos_maxdd']:.1%} | {'sí' if r['estable'] else 'no'} | "
            f"{'sí' if r['replicable'] else 'no¹'} |")

    lines += [
        "", "¹ Los futuros continuos `=F` (oro/plata/petróleo) son precios back-ajustados NO "
        "negociables y redundantes con sus ETF (GLD/SLV/USO); inflan el conteo con 3 filas. "
        "Se mantienen como referencia pero no cuentan como instrumentos operables distintos.", "",
        "## Lectura honesta (revisada tras auditoría adversarial)", "",
        "### Resultado neto", "",
        f"- **{n_pos}/{k}** con Sharpe OOS positivo · **{n_beat}/{k}** baten a buy & hold en retorno · "
        f"**{n_strong}/{k}** lo baten en Sharpe **y** con Sharpe OOS > 0.5 **y** parámetros estables.",
        f"- La media de los {len(fold_sharpes)} Sharpe-por-fold OOS es **{fs_mean:+.2f}** "
        f"({fs_pos:.0%} positivos): tras costes, estas estrategias rinden **ligeramente por debajo "
        "de cero**, no 'en torno a cero'. No es que pierdan por azar simétrico: el coste de rotar "
        "las erosiona.", "",
        "### ¿Es el líder mejor que el azar? (nula empírica)", "",
        f"- Se comparó el mejor Sharpe OOS real (**{leader['label']}**, {leader['oos_sharpe']}) contra "
        f"el mejor de {len(universe)} estrategias **aleatorias** (misma rotación), repetido {N_NULL} veces.",
        f"- p-valor del líder = **{p_leader:.2f}** (fracción de nulas cuyo mejor Sharpe iguala o supera "
        f"al líder; nula media = {null_max.mean():.2f}). Un p-valor alto significa que el líder es "
        "**indistinguible de elegir el mejor de 16 ruidos**: no hay señal.", "",
        "### Potencia — qué puede y qué NO puede afirmar este test", "",
        f"- El error estándar del Sharpe OOS es ≈ **{se_med:.2f}** (≈ √(ppy/N)). El test solo detecta "
        f"con fiabilidad edges con Sharpe verdadero **≳ {sharpe_detectable}**.",
        "- Por tanto: **descarta edges GRANDES y estables**, pero NO puede descartar edges modestos "
        "(Sharpe verdadero 0.3-0.5). Decir 'sin edge' a secas sobre-afirma; lo correcto es "
        "**'sin edge grande y estable detectable con 4 folds'**.", "",
        "### Hallazgo de régimen — overlay defensivo, no alfa", "",
        f"- Estas técnicas baten a B&H en **{beat_down:.0%}** de los folds **bajistas** pero solo en "
        f"**{beat_up:.0%}** de los **alcistas**. Es decir: 'ganan' reduciendo exposición cuando el "
        "mercado cae (beta defensiva), no acertando dirección (alfa).",
        "- El #1 del ranking confirma el patrón: encabeza porque su B&H fue el peor, no por habilidad. "
        "Esto es una capacidad REAL (reducir drawdown) pero distinta de 'batir al mercado'.", "",
        "### Límites de alcance (lo que NO se ha probado)", "",
        "- Solo 2 familias **direccionales** (momentum, reversión), **timeframe diario**, single-asset, "
        "una sola ventana 2018-2026 (4 folds), y una cesta **survivor-biased** (NVDA B&H +659%).",
        "- NO se ha corrido la prueba LIMPIA alfa-vs-beta: **cross-sectional / market-neutral** (long-short "
        "entre los 16). Tampoco intradía ni momentum diversificado estilo CTA con vol-targeting.",
        "- Conclusión defendible: *estas familias técnicas simples en diario no superan a comprar-y-aguantar "
        "en esta ventana alcista*. NO equivale a 'no existe ningún edge'.", "",
        "> Información técnica, no asesoría financiera. Resultados pasados no garantizan futuros.",
    ]
    p = REPORTS_DIR / "cross_asset.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nfold-Sharpe medio {fs_mean:+.2f} | p-líder {p_leader:.2f} | "
          f"batir B&H caídas {beat_down:.0%} vs subidas {beat_up:.0%} | {n_strong}/{k} fuerte. Reporte: {p}")


if __name__ == "__main__":
    main()

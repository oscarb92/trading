"""Motor de validación walk-forward OUT-OF-SAMPLE (Fase 3+).

Reutilizable para CUALQUIER familia de estrategia: se le pasa una rejilla de
candidatos `(label, signal_fn)` y los evalúa con el mismo estándar honesto que
cazó el sobreajuste del momentum. Así, momentum, reversión a la media, breakout…
se juzgan con la MISMA vara.

Garantías anti-trampa:
  - Señal calculada sobre la serie COMPLETA (indicadores causales) y desplazada
    shift(1); el PnL se aísla por ventana → sin warm-up contaminado ni look-ahead.
  - Selección de parámetros SOLO con datos anteriores al fold (ventana anclada).
  - Cada fold de test se evalúa UNA vez. Benchmark buy & hold obligatorio.
  - Costes (fees+slippage) incluidos en todo.

Limitación: con pocos folds la muestra OOS es pequeña; un OOS positivo es señal
direccional, no prueba estadística. Información técnica, no asesoría financiera.
"""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from . import backtest as bt


@dataclass
class FoldResult:
    fold: int
    desde: str
    hasta: str
    pick: str
    train_sharpe: float
    oos_return: float
    oos_sharpe: float
    oos_trades: int
    bh_return: float


@dataclass
class OOSResult:
    symbol: str
    timeframe: str
    folds: list
    oos_return: float
    oos_sharpe: float
    oos_maxdd: float
    oos_trades: int
    bh_return: float
    bh_sharpe: float
    picks: list
    stable: bool
    insample_best: str
    insample_sharpe: float


def _win(pos, raw_ret, a, b, tf, fee, slip, ppy=None):
    return bt.metrics_from_position(pos.iloc[a:b], raw_ret.iloc[a:b], tf, fee, slip, ppy)["metrics"]


def walk_forward_oos(df: pd.DataFrame, candidates: list, symbol: str = "",
                     timeframe: str = "4h", fee: float = 0.001, slippage: float = 0.0005,
                     n_folds: int = 4, min_train_trades: int = 10,
                     ppy: float | None = None) -> OOSResult:
    """`candidates`: lista de (label, signal_fn) con signal_fn(df) -> Series {-1,0,1}.
    Año 1 = train inicial; año 2 = `n_folds` folds OOS con re-optimización anclada.
    `ppy` anualiza el Sharpe según el mercado (252 bolsa / 365 cripto en diario)."""
    raw_ret = df["close"].astype(float).pct_change().fillna(0)
    grid = {label: fn(df).shift(1).fillna(0) for label, fn in candidates}
    long_bh = pd.Series(1.0, index=df.index)
    n = len(df)
    oos_start = n // 2
    flen = (n - oos_start) // n_folds

    folds, picks, pos_parts, ret_parts = [], [], [], []
    for k in range(n_folds):
        ta = oos_start + k * flen
        tb = oos_start + (k + 1) * flen if k < n_folds - 1 else n

        # --- Selección SOLO con train = [0, ta) ---
        best, best_sh = None, None
        for label, pos in grid.items():
            tm = _win(pos, raw_ret, 0, ta, timeframe, fee, slippage, ppy)
            if tm.trades < min_train_trades:
                continue
            if best_sh is None or tm.sharpe > best_sh:
                best, best_sh = label, tm.sharpe
        if best is None:                                  # nadie supera el mínimo de trades
            for label, pos in grid.items():
                tm = _win(pos, raw_ret, 0, ta, timeframe, fee, slippage, ppy)
                if best_sh is None or tm.sharpe > best_sh:
                    best, best_sh = label, tm.sharpe

        # --- Evaluación UNA vez en test = [ta, tb) ---
        oosm = _win(grid[best], raw_ret, ta, tb, timeframe, fee, slippage, ppy)
        bh = _win(long_bh, raw_ret, ta, tb, timeframe, fee, slippage, ppy)
        picks.append(best)
        pos_parts.append(grid[best].iloc[ta:tb])
        ret_parts.append(raw_ret.iloc[ta:tb])
        folds.append(FoldResult(k + 1, str(df["ts"].iloc[ta])[:10], str(df["ts"].iloc[tb - 1])[:10],
                                best, best_sh, oosm.total_return, oosm.sharpe, oosm.trades,
                                bh.total_return))

    # --- OOS encadenado (curva real del año 2, con coste de transición entre folds) ---
    oos = bt.metrics_from_position(pd.concat(pos_parts).reset_index(drop=True),
                                   pd.concat(ret_parts).reset_index(drop=True),
                                   timeframe, fee, slippage, ppy)["metrics"]
    bh_full = _win(long_bh, raw_ret, oos_start, n, timeframe, fee, slippage, ppy)

    is_best, is_sh = None, None
    for label, pos in grid.items():
        m = _win(pos, raw_ret, 0, n, timeframe, fee, slippage, ppy)
        if is_sh is None or m.sharpe > is_sh:
            is_best, is_sh = label, m.sharpe

    return OOSResult(symbol, timeframe, folds, oos.total_return, oos.sharpe, oos.max_drawdown,
                     oos.trades, bh_full.total_return, bh_full.sharpe, picks,
                     len(set(picks)) == 1, is_best, is_sh)


def verdict(r: OOSResult) -> str:
    """Veredicto MECÁNICO (no sustituye la lectura crítica humana)."""
    bate_bh = r.oos_return > r.bh_return
    positivo = r.oos_return > 0 and r.oos_sharpe > 0
    if positivo and bate_bh:
        return "✅ OOS positivo Y supera buy & hold → señal de edge (confirmar con más datos/activos)."
    if bate_bh:
        return ("⚠ Pierde menos que buy & hold pero OOS ≤ 0 → defensivo en mercado bajista, "
                "no edge positivo demostrado.")
    return "❌ No supera buy & hold en OOS → el 'edge' in-sample no sobrevive (sobreajuste)."


def to_markdown(r: OOSResult) -> list[str]:
    lines = [f"## {r.symbol} — {r.timeframe}", "",
             "| Fold | Test (desde→hasta) | Selección | Sharpe train | OOS ret | "
             "OOS Sharpe | Trades | B&H ret |",
             "|---|---|---|---|---|---|---|---|"]
    for f in r.folds:
        lines.append(f"| {f.fold} | {f.desde}→{f.hasta} | {f.pick} | {f.train_sharpe} | "
                     f"{f.oos_return:+.2%} | {f.oos_sharpe} | {f.oos_trades} | {f.bh_return:+.2%} |")
    estab = "ESTABLES" if r.stable else "INESTABLES (cambian entre folds → más ruido que señal)"
    lines += ["",
              f"**OOS encadenado (año 2):** retorno **{r.oos_return:+.2%}** · Sharpe "
              f"**{r.oos_sharpe}** · MaxDD {r.oos_maxdd:.2%} · {r.oos_trades} trades.",
              f"**Buy & hold (año 2):** {r.bh_return:+.2%} (Sharpe {r.bh_sharpe}).",
              f"**Parámetros por fold:** {r.picks} → {estab}.",
              f"**Referencia in-sample** (mejor mirando los 2 años): {r.insample_best}, "
              f"Sharpe {r.insample_sharpe}.",
              f"**Veredicto {r.symbol}:** {verdict(r)}", ""]
    return lines

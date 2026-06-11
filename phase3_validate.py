"""Fase 3 — Validación walk-forward OOS de la familia MOMENTUM.

Pregunta: el filtro de régimen ADX que acercó ETH al break-even, ¿es edge real o
optimización in-sample? Se evalúa con el motor honesto `src.validation` (mismo
estándar para todas las familias): año 1 train, año 2 en folds OOS anclados,
selección por Sharpe de train, evaluación única en test, benchmark buy & hold.

Uso:  python phase3_validate.py
Lee data/ local. Escribe reports/phase3_validation.md.
"""
from __future__ import annotations
import argparse
from itertools import product
from pathlib import Path
from src import store, backtest as bt, validation as val

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"

TF = "4h"
ENTERS = [0.55, 0.60, 0.65, 0.70]
ADX_MINS = [0, 20, 25, 30, 35]          # 0 = histéresis pura (sin filtro)


def candidates():
    out = []
    for e, a in product(ENTERS, ADX_MINS):
        out.append((f"({e:.2f},{a})",
                    lambda d, e=e, a=a: bt.regime_signal(d, enter=e, adx_min=a)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", nargs="+", default=["BTC/USDT", "ETH/USDT"])
    args = ap.parse_args()

    out = ["# Fase 3 — Validación walk-forward OOS (momentum)", "",
           f"> {TF}, rejilla enter∈{ENTERS} × adx_min∈{ADX_MINS}. Motor `src.validation`:",
           "> año 1 train, año 2 en 4 folds OOS anclados, selección por Sharpe de train,",
           "> evaluación única en test. Costes 0.1%+0.05%. Sin look-ahead.", ""]
    for symbol in args.symbol:
        df = store.resample_ohlcv(store.load_ohlcv(symbol, "1h"), TF)
        if df.empty:
            out += [f"_(sin datos locales para {symbol})_", ""]
            continue
        r = val.walk_forward_oos(df, candidates(), symbol=symbol, timeframe=TF)
        out += val.to_markdown(r)
        print(f"[validate] {symbol}: OOS {r.oos_return:+.2%} (Sharpe {r.oos_sharpe}) | "
              f"B&H {r.bh_return:+.2%}")

    out += ["---", "",
            "> **Poder estadístico:** 4 folds OOS por activo es muy poca muestra; un OOS",
            "> positivo es señal direccional, no prueba. Información técnica, no asesoría financiera."]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    p = REPORTS_DIR / "phase3_validation.md"
    p.write_text("\n".join(out), encoding="utf-8")
    print(f"Reporte: {p}")


if __name__ == "__main__":
    main()

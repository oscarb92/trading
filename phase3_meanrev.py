"""Fase 3 — Familia REVERSIÓN A LA MEDIA, validada OOS desde el principio.

El momentum no tuvo edge out-of-sample. Aquí se prueba la familia opuesta
(contrarian: comprar lo sobrevendido, vender lo sobrecomprado) con EXACTAMENTE el
mismo motor honesto `src.validation` — para no caer otra vez en el espejismo
in-sample. Se barre lookback × entry_z × exit_z en 1h y 4h, BTC y ETH.

Uso:  python phase3_meanrev.py
Lee data/ local. Escribe reports/phase3_meanrev.md.
"""
from __future__ import annotations
import argparse
from itertools import product
from pathlib import Path
from src import store, backtest as bt, validation as val

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"

TIMEFRAMES = ["1h", "4h"]
LOOKBACKS = [20, 50]
ENTRY_Z = [1.5, 2.0, 2.5]
EXIT_Z = [0.0, 0.5]                      # 12 combos: rejilla modesta (menos multiple-testing)


def candidates():
    out = []
    for lb, ez, xz in product(LOOKBACKS, ENTRY_Z, EXIT_Z):
        out.append((f"lb{lb}/in{ez}/out{xz}",
                    lambda d, lb=lb, ez=ez, xz=xz:
                        bt.mean_reversion_signal(d, lookback=lb, entry_z=ez, exit_z=xz)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", nargs="+", default=["BTC/USDT", "ETH/USDT"])
    args = ap.parse_args()

    out = ["# Fase 3 — Reversión a la media, validación OOS", "",
           f"> Rejilla lookback∈{LOOKBACKS} × entry_z∈{ENTRY_Z} × exit_z∈{EXIT_Z} ({len(candidates())} combos).",
           "> Motor `src.validation` (mismo estándar que momentum): año 1 train, año 2 en 4 folds",
           "> OOS anclados, selección por Sharpe de train, evaluación única en test. Costes",
           "> 0.1%+0.05%. Sin look-ahead. Benchmark buy & hold.", ""]

    for tf in TIMEFRAMES:
        out += [f"# Timeframe {tf}", ""]
        for symbol in args.symbol:
            base = store.load_ohlcv(symbol, "1h")
            df = base if tf == "1h" else store.resample_ohlcv(base, tf)
            if df.empty:
                out += [f"_(sin datos locales para {symbol})_", ""]
                continue
            r = val.walk_forward_oos(df, candidates(), symbol=symbol, timeframe=tf)
            out += val.to_markdown(r)
            print(f"[meanrev] {tf} {symbol}: OOS {r.oos_return:+.2%} (Sharpe {r.oos_sharpe}) | "
                  f"B&H {r.bh_return:+.2%} | params {r.picks}")

    out += ["---", "",
            "> **Poder estadístico:** 4 folds OOS por activo/timeframe es muy poca muestra; un OOS",
            "> positivo es señal direccional, no prueba. Si los parámetros saltan entre folds, el",
            "> 'óptimo' es ruido. Información técnica, no asesoría financiera."]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    p = REPORTS_DIR / "phase3_meanrev.md"
    p.write_text("\n".join(out), encoding="utf-8")
    print(f"Reporte: {p}")


if __name__ == "__main__":
    main()

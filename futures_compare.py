"""¿Qué hace el APALANCAMIENTO a una estrategia sin edge? Medición con datos reales.

Toma la mejor configuración defensiva del research (histéresis enter=0.65 en 4h) y
buy & hold, y las corre como futuros perpetuos a 1x/2x/3x/5x con funding (0.01%/8h)
y liquidación intrabar, sobre BTC y ETH (2 años reales).

Uso:  python futures_compare.py        →  reports/futures.md
Información técnica, no asesoría financiera.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from src import store, backtest as bt, futures as fut

REPORTS_DIR = Path(__file__).resolve().parent / "reports"
LEVERAGES = [1, 2, 3, 5]
STRATS = [
    ("Histéresis 0.65 (la 'menos mala')", lambda d: bt.hysteresis_signal(d, enter=0.65)),
    ("Buy & hold (siempre largo)", lambda d: pd.Series(1, index=d.index)),
]


def main():
    lines = ["# Futuros paper — el efecto del apalancamiento, medido", "",
             "> Perpetuos simulados: funding 0.01%/8h, margen de mantenimiento 0.5%,",
             "> liquidación INTRABAR (la mecha cuenta, no solo el cierre), costes 0.1%+0.05%.",
             "> Datos reales 4h, 2 años (BTC/ETH). Modelo cruzado de cuenta completa:",
             "> liquidación = cuenta a cero, sin recuperación posible.", ""]
    for symbol in ["BTC/USDT", "ETH/USDT"]:
        df = store.resample_ohlcv(store.load_ohlcv(symbol, "1h"), "4h")
        if df.empty:
            continue
        lines += [f"## {symbol} (4h, {len(df)} velas)", "",
                  "| Estrategia | Apalanc. | Retorno | Sharpe | MaxDD | ¿Liquidado? |",
                  "|---|---|---|---|---|---|"]
        for name, fn in STRATS:
            for lev in LEVERAGES:
                r = fut.simulate_futures(df, "4h", fn, leverage=lev)
                m = r["metrics"]
                liq = ("💀 SÍ (vela " + str(r["liq_bar"]) + ")") if r["liquidated"] else "no"
                lines.append(f"| {name} | {lev}x | {m['total_return']:+.1%} | "
                             f"{m['sharpe']} | {m['max_drawdown']:.1%} | {liq} |")
                print(f"{symbol} {name} {lev}x: ret {m['total_return']:+.1%} "
                      f"liq={r['liquidated']}")
        lines.append("")
    lines += ["## Lectura", "",
              "- **Sin edge, el apalancamiento solo decide CUÁNDO pierdes, no SI pierdes.**",
              "  Multiplica el coste de rotación y el funding, y añade la ruina por mecha.",
              "- Buy & hold apalancado tampoco se salva: una corrección normal de cripto",
              "  (−20/−35%) liquida las cuentas a 3-5x aunque el precio luego se recupere.",
              "- El único 'uso' defendible del modo futuros en este sandbox es PEDAGÓGICO:",
              "  ver estos números antes de que te los enseñe un exchange con dinero real.", "",
              "> Información técnica, no asesoría financiera."]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    p = REPORTS_DIR / "futures.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    print(f"Reporte: {p}")


if __name__ == "__main__":
    main()

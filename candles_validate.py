"""Validación OOS de la familia PATRONES DE VELAS (price action).

Responde con evidencia a "¿tenéis en cuenta la evaluación de tipos de velas?":
la señal `backtest.candlestick_signal` (envolventes, martillo, estrella fugaz con
contexto de tendencia) se somete AL MISMO walk-forward out-of-sample que el resto
de familias, sobre cripto (4h) y mercados diarios (bolsa/oro), con costes.

Uso:  python candles_validate.py
Lee data/ local (cripto vía backtest.py --download; resto vía cross_asset.py).
Escribe reports/candlestick.md. Información técnica, no asesoría financiera.
"""
from __future__ import annotations
from itertools import product
from pathlib import Path
from src import store, backtest as bt, validation as val, marketdata as md

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"

MARKETS = [("BTC/USDT", "4h"), ("ETH/USDT", "4h"),
           ("SPY", "1d"), ("GLD", "1d"), ("NVDA", "1d"), ("BTC-USD", "1d")]
HOLDS = (3, 5, 10)
SPANS = (20, 50)


def candidates():
    return [(f"velas hold{hd}/ema{sp}",
             lambda d, hd=hd, sp=sp: bt.candlestick_signal(d, hold=hd, trend_span=sp))
            for hd, sp in product(HOLDS, SPANS)]


def load(symbol: str, tf: str):
    if "/" in symbol:                                   # cripto CCXT local 1h → resample
        base = store.load_ohlcv(symbol, "1h")
        return base if tf == "1h" else store.resample_ohlcv(base, tf)
    return store.load_ohlcv(symbol, tf)                 # yahoo diario


def main():
    rows, summaries = [], []
    for symbol, tf in MARKETS:
        df = load(symbol, tf)
        if len(df) < 800:
            print(f"[candles] {symbol} {tf}: sin datos suficientes, omitido.")
            continue
        ppy = md.periods_per_year(symbol, tf) if tf == "1d" else None
        r = val.walk_forward_oos(df, candidates(), symbol=symbol, timeframe=tf,
                                 min_train_trades=5, ppy=ppy)
        d_sharpe = r.oos_sharpe - r.bh_sharpe
        rows.append((symbol, tf, r.oos_sharpe, r.bh_sharpe, d_sharpe, r.oos_return,
                     r.bh_return, r.oos_trades, r.stable))
        summaries.append(d_sharpe)
        print(f"[candles] {symbol} {tf}: OOS Sharpe {r.oos_sharpe} vs B&H {r.bh_sharpe} "
              f"(d {d_sharpe:+.2f}), trades {r.oos_trades}")

    n_beat = sum(1 for d in summaries if d > 0)
    lines = [
        "# Patrones de velas japonesas — validación OOS", "",
        "> Señal: envolvente alcista/bajista + martillo + estrella fugaz, con contexto de",
        "> tendencia (EMA) y salida a plano tras `hold` velas. Rejilla hold∈{3,5,10} × ema∈{20,50}.",
        "> Mismo walk-forward OOS anclado que el resto de familias; costes 0.1%+0.05%; sin look-ahead.",
        "> Sharpe anualizado por clase (252 bolsa / 365 cripto en diario).", "",
        "| Mercado | TF | OOS Sharpe | B&H Sharpe | ΔSharpe | OOS ret | B&H ret | Trades | Params estables |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for (sym, tf, osh, bsh, d, oret, bret, tr, stab) in rows:
        flag = "🟡" if d > 0 else "❌"
        lines.append(f"| {sym} | {tf} | {osh} | {bsh} | {flag} {d:+.2f} | {oret:+.1%} | "
                     f"{bret:+.1%} | {tr} | {'sí' if stab else 'no'} |")
    lines += [
        "", "## Lectura honesta", "",
        f"- {n_beat}/{len(rows)} mercados con ΔSharpe positivo vs buy & hold.",
        "- Misma vara que las demás familias: potencia limitada (4 folds), multiplicidad (6 combos),",
        "  y el sesgo conocido de 'batir a B&H' en tramos bajistas por exposición reducida.",
        "- Los patrones de velas son señales de muy corto plazo: pocas ocurrencias → pocos trades →",
        "  varianza alta del Sharpe. Un resultado positivo aislado aquí NO es validación.",
        "", "> Información técnica, no asesoría financiera.",
    ]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    p = REPORTS_DIR / "candlestick.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{n_beat}/{len(rows)} con dSharpe>0. Reporte: {p}")


if __name__ == "__main__":
    main()

"""Barrido de Fase 3 — ¿el sobre-trading es el problema?

Compara el baseline (bandas 0.55/0.45, sin memoria) contra la señal con histéresis
(banda muerta) variando el umbral de entrada y el timeframe (1h vs 4h reagregado).
El objetivo NO es maximizar nada todavía, sino DIAGNOSTICAR: aislar cuánto del
desastre del baseline viene del coste por flipear de posición casi cada vela.

Uso:
  python phase3.py                       # BTC/USDT y ETH/USDT, 1h y 4h
  python phase3.py --symbol BTC/USDT

Lee el histórico local de data/ (no descarga). Escribe reports/phase3_sweep.md.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from src import store, backtest as bt

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"

ENTERS = [0.55, 0.60, 0.65, 0.70]      # umbral de convicción de la histéresis
TIMEFRAMES = ["1h", "4h"]


def _row(name: str, m) -> str:
    turnover = m.trades / max(m.bars, 1)
    return (f"| {name} | {m.total_return:.2%} | {m.annual_return:.2%} | {m.sharpe} | "
            f"{m.max_drawdown:.2%} | {m.win_rate}% | {m.profit_factor} | {m.trades} | "
            f"{turnover:.3f} | {m.cost_drag:.1%} |")


def evaluate(symbol: str) -> list[str]:
    base_1h = store.load_ohlcv(symbol, "1h")
    if base_1h.empty:
        return [f"_(sin datos locales para {symbol}; baja con `python backtest.py "
                f"--fresh --download 17520 --symbol {symbol}`)_", ""]

    lines = [f"## {symbol}", ""]
    for tf in TIMEFRAMES:
        df = base_1h if tf == "1h" else store.resample_ohlcv(base_1h, tf)
        lines += [f"### {tf} ({len(df)} velas)", "",
                  "| Estrategia | Retorno | Anual | Sharpe | MaxDD | Win | PF | Trades | Turnover | Coste |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        # Referencia: baseline actual
        ref = bt.run_backtest(df, tf, signal_fn=bt.baseline_signal)
        lines.append(_row("baseline (0.55/0.45)", ref["metrics"]))
        # Histéresis con distintos umbrales de entrada (salida fija al centro 0.50)
        for enter in ENTERS:
            r = bt.run_backtest(df, tf,
                                signal_fn=lambda d, e=enter: bt.hysteresis_signal(d, enter=e))
            lines.append(_row(f"histéresis enter={enter:.2f}", r["metrics"]))
        lines.append("")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", nargs="+", default=["BTC/USDT", "ETH/USDT"])
    args = ap.parse_args()

    out = ["# Fase 3 — Barrido baseline vs histéresis", "",
           "> Diagnóstico de sobre-trading: misma señal subyacente (momentum+tendencia+RSI),",
           "> distinta gestión de entradas/salidas. Costes 0.1% fee + 0.05% slippage, sin",
           "> look-ahead. Turnover = trades/vela (más bajo = menos sobre-trading).", ""]
    for symbol in args.symbol:
        out += evaluate(symbol)
        print(f"[phase3] {symbol} evaluado.")

    out += ["---", "",
            "> Lectura honesta: si la histéresis sube el retorno y baja el turnover pero el",
            "> resultado sigue siendo negativo, el sobre-trading era PARTE del problema pero la",
            "> señal subyacente tampoco tiene edge a este timeframe. Si en 4h mejora claramente,",
            "> el camino es operar más lento. Información técnica, no asesoría financiera."]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    p = REPORTS_DIR / "phase3_sweep.md"
    p.write_text("\n".join(out), encoding="utf-8")
    print(f"Reporte: {p}")


if __name__ == "__main__":
    main()

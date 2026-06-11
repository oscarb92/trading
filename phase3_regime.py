"""Fase 3 — ¿un filtro de régimen (ADX) estabiliza el momentum?

El walk-forward de la histéresis mostró que el baseline gana en tendencia y pierde
en lateral. Hipótesis: si solo operamos cuando hay tendencia (ADX alto), nos
quedamos con los segmentos buenos y saltamos los malos → más estabilidad
out-of-sample (no necesariamente más retorno en el periodo completo).

Experimento controlado: fija timeframe=4h y enter=0.65; varía SOLO el umbral de
ADX. Mide periodo completo Y walk-forward (4 segmentos), porque lo que se juzga
es la ESTABILIDAD, no el número global.

Uso:  python phase3_regime.py
Lee data/ local. Escribe reports/phase3_regime.md.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from src import store, backtest as bt

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"

TF = "4h"
ENTER = 0.65
ADX_MINS = [0, 20, 25, 30, 35]      # 0 = sin filtro (histéresis pura)
N_SPLITS = 4


def _sig(adx_min: float):
    return lambda d: bt.regime_signal(d, enter=ENTER, adx_min=adx_min)


def evaluate(symbol: str) -> list[str]:
    df = store.resample_ohlcv(store.load_ohlcv(symbol, "1h"), TF)
    if df.empty:
        return [f"_(sin datos locales para {symbol})_", ""]

    lines = [f"## {symbol} — {TF}, enter={ENTER}", "",
             "| ADX min | Retorno | Sharpe | Trades | seg1 | seg2 | seg3 | seg4 | seg>0 | peor seg |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for adx_min in ADX_MINS:
        full = bt.run_backtest(df, TF, signal_fn=_sig(adx_min))["metrics"]
        wf = bt.walk_forward(df, TF, n_splits=N_SPLITS, signal_fn=_sig(adx_min))
        segs = [s["metrics"].total_return for s in wf]
        n_pos = sum(1 for x in segs if x > 0)
        worst = min(segs) if segs else 0.0
        name = "sin filtro" if adx_min == 0 else f"{adx_min}"
        seg_cells = " | ".join(f"{x:+.1%}" for x in segs)
        lines.append(f"| {name} | {full.total_return:.2%} | {full.sharpe} | {full.trades} | "
                     f"{seg_cells} | {n_pos}/{len(segs)} | {worst:+.1%} |")
    lines.append("")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", nargs="+", default=["BTC/USDT", "ETH/USDT"])
    args = ap.parse_args()

    out = ["# Fase 3 — Filtro de régimen (ADX)", "",
           f"> Timeframe {TF}, histéresis enter={ENTER}, salida al centro 0.50. Solo se inicia/",
           "> invierte posición cuando ADX ≥ umbral (hay tendencia). Costes 0.1%+0.05%, sin",
           "> look-ahead. Se juzga la ESTABILIDAD del walk-forward, no el retorno global.", ""]
    for symbol in args.symbol:
        out += evaluate(symbol)
        print(f"[regime] {symbol} evaluado.")

    out += ["---", "",
            "> Lectura: el filtro AYUDA si sube `seg>0` y mejora `peor seg` respecto a 'sin",
            "> filtro' — es decir, si recorta las pérdidas en los segmentos laterales. Si solo",
            "> baja trades sin mejorar la dispersión entre segmentos, el ADX no aporta edge y",
            "> toca otra hipótesis. Información técnica, no asesoría financiera."]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    p = REPORTS_DIR / "phase3_regime.md"
    p.write_text("\n".join(out), encoding="utf-8")
    print(f"Reporte: {p}")


if __name__ == "__main__":
    main()

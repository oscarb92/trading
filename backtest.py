"""CLI de backtesting (Fase 2).

Uso:
  python backtest.py                                  # BTC/USDT 1h desde data/ local
  python backtest.py --symbol ETH/USDT --tf 1h
  python backtest.py --symbol BTC/USDT ETH/USDT       # varios símbolos de una pasada
  python backtest.py --fresh --download 17520         # rehace 2 años limpios (red real) y testea

Lee el histórico de data/ (Parquet). Si está vacío, lo descarga con store.update_history.
"""
from __future__ import annotations
import argparse
from src import store, backtest as bt


def run_one(symbol: str, tf: str, download: int, fresh: bool, splits: int) -> None:
    if fresh and store.clear(symbol, tf):
        print(f"Histórico local de {symbol} {tf} borrado (--fresh).")
    if download > 0:
        s = store.update_history(symbol, tf, total=download)
        print(f"Histórico {symbol}: {s.candles} velas "
              f"[{s.start} → {s.end}], huecos={s.gaps}, faltantes={s.missing_candles}")

    df = store.load_ohlcv(symbol, tf)
    if df.empty:
        print(f"No hay datos locales de {symbol} {tf}. Usa --download N (en una máquina con red real).")
        return
    if df.attrs.get("source") == "synthetic":
        print("AVISO: datos sintéticos (sin red). El backtest es solo demostrativo.")

    full = bt.run_backtest(df, tf)
    wf = bt.walk_forward(df, tf, n_splits=splits)
    path = bt.report(symbol, tf, full, wf)
    m = full["metrics"]
    print(f"\n{symbol} {tf} | {m.bars} velas")
    print(f"  Retorno {m.total_return:.2%} | Sharpe {m.sharpe} | MaxDD {m.max_drawdown:.2%} "
          f"| Win {m.win_rate}% | PF {m.profit_factor} | {m.trades} trades")
    print(f"  Reporte: {path}")
    if m.sharpe > 3:
        print("  ⚠ Sharpe > 3: sospechoso en datos reales (posible overfitting o bug). Revisar.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", nargs="+", default=["BTC/USDT"],
                    help="Uno o varios símbolos, p.ej. --symbol BTC/USDT ETH/USDT")
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--download", type=int, default=0,
                    help="Nº de velas a descargar antes de testear (0 = usar lo local)")
    ap.add_argument("--fresh", action="store_true",
                    help="Borra el histórico local antes de descargar (evita mezclar datos)")
    ap.add_argument("--splits", type=int, default=4)
    args = ap.parse_args()

    for symbol in args.symbol:
        run_one(symbol, args.tf, args.download, args.fresh, args.splits)


if __name__ == "__main__":
    main()

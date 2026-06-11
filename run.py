"""CLI: corre UNA pasada del ciclo. Útil para tareas programadas.

Uso:
    python run.py                 # una pasada con la config actual
    python run.py --deposit 1000  # agrega saldo simulado y sale
"""
from __future__ import annotations
import argparse
import json
from src.config import load_config
from src.portfolio import Portfolio
from src.engine import run_cycle


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deposit", type=float, default=None, help="Agregar saldo simulado")
    args = ap.parse_args()

    pf = Portfolio.load()
    if args.deposit is not None:
        pf.deposit(args.deposit)
        print(f"Saldo agregado: {args.deposit}. Cash actual: {pf.cash}")
        return

    cfg = load_config()
    result = run_cycle(cfg, pf)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

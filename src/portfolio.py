"""Estado del portfolio: efectivo, posiciones y PnL. Persistente en JSON.

Modelo de contabilidad: PnL/margen. El efectivo solo cambia por comisiones y
PnL realizado; el equity = efectivo + PnL no realizado. Esto evita el doble
conteo del notional al abrir posiciones (especialmente cortos).
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "state" / "portfolio.json"


@dataclass
class Position:
    symbol: str
    side: str            # "long" | "short"
    qty: float
    entry: float
    stop: float = 0.0
    take_profit: float = 0.0


@dataclass
class Portfolio:
    cash: float = 0.0
    base_currency: str = "USDT"
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0

    # ---- persistencia ----
    @classmethod
    def load(cls) -> "Portfolio":
        if STATE_PATH.exists():
            d = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            pos = {k: Position(**v) for k, v in d.get("positions", {}).items()}
            return cls(cash=d.get("cash", 0.0), base_currency=d.get("base_currency", "USDT"),
                       positions=pos, realized_pnl=d.get("realized_pnl", 0.0))
        return cls()

    def save(self) -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        d = {"cash": self.cash, "base_currency": self.base_currency,
             "realized_pnl": self.realized_pnl,
             "positions": {k: asdict(v) for k, v in self.positions.items()}}
        STATE_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")

    # ---- operaciones de saldo ----
    def deposit(self, amount: float) -> None:
        self.cash += float(amount)
        self.save()

    def unrealized(self, prices: dict[str, float]) -> float:
        u = 0.0
        for sym, p in self.positions.items():
            px = prices.get(sym, p.entry)
            u += (px - p.entry) * p.qty if p.side == "long" else (p.entry - px) * p.qty
        return u

    def equity(self, prices: dict[str, float]) -> float:
        # equity = efectivo + PnL no realizado de las posiciones abiertas
        return self.cash + self.unrealized(prices)

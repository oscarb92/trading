"""Brokers de ejecución.

PaperBroker: ejecuta contra PRECIOS REALES con saldo simulado que tú agregas.
Modelo PnL/margen: al abrir solo se descuenta la comisión; al cerrar se acredita
el PnL (ganancia/pérdida) menos comisión. Aplica slippage para realismo.

LiveBroker: esqueleto para ejecución real vía CCXT (Binance) / Alpaca.
NO operar en real hasta validar en paper. Requiere claves en .env.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from .portfolio import Portfolio, Position
from .futures import liquidation_price


@dataclass
class Fill:
    symbol: str
    side: str          # "buy" | "sell"
    qty: float
    price: float       # precio efectivo con slippage
    fee: float
    note: str = ""


class PaperBroker:
    def __init__(self, portfolio: Portfolio, fee_rate: float = 0.001, slippage: float = 0.0005):
        self.pf = portfolio
        self.fee_rate = fee_rate
        self.slippage = slippage

    def _exec_price(self, price: float, side: str) -> float:
        return price * (1 + self.slippage) if side == "buy" else price * (1 - self.slippage)

    def open(self, symbol: str, side: str, qty: float, price: float,
             stop: float = 0.0, tp: float = 0.0,
             leverage: float = 1.0, maint_pct: float = 0.5) -> Fill:
        ps = "long" if side == "buy" else "short"
        px = self._exec_price(price, side)
        fee = qty * px * self.fee_rate
        self.pf.cash -= fee
        liq = liquidation_price(px, ps, leverage, maint_pct) if leverage > 1 else 0.0
        now = datetime.now(timezone.utc).isoformat()
        self.pf.positions[symbol] = Position(symbol, ps, qty, px, stop, tp,
                                             leverage=leverage, liq_price=liq,
                                             last_funding=now)
        self.pf.save()
        return Fill(symbol, side, qty, px, fee,
                    f"open lev={leverage:g}x liq={liq:.2f}" if leverage > 1 else "open")

    def close(self, symbol: str, price: float) -> Fill | None:
        pos = self.pf.positions.get(symbol)
        if not pos:
            return None
        side = "sell" if pos.side == "long" else "buy"
        px = self._exec_price(price, side)
        fee = pos.qty * px * self.fee_rate
        gross = (px - pos.entry) * pos.qty if pos.side == "long" else (pos.entry - px) * pos.qty
        pnl = gross - fee
        self.pf.cash += pnl
        self.pf.realized_pnl += pnl
        del self.pf.positions[symbol]
        self.pf.save()
        return Fill(symbol, side, pos.qty, px, fee, f"close pnl={pnl:.2f}")


class LiveBroker:  # pragma: no cover - esqueleto, no usar sin validar
    """Esqueleto de ejecución real. Implementar con cuidado en Fase 6."""
    def __init__(self, exchange: str = "binance", api_key: str = "", secret: str = "", testnet: bool = True):
        self.exchange, self.api_key, self.secret, self.testnet = exchange, api_key, secret, testnet
        self._client = None

    def connect(self):
        import ccxt
        self._client = getattr(ccxt, self.exchange)({
            "apiKey": self.api_key, "secret": self.secret, "enableRateLimit": True})
        if self.testnet and hasattr(self._client, "set_sandbox_mode"):
            self._client.set_sandbox_mode(True)
        return self._client

    def open(self, *a, **k):
        raise NotImplementedError("Ejecución real deshabilitada hasta validar en paper (Fase 6).")

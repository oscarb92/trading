"""Tests del core de contabilidad y modos (pytest)."""
from src.config import load_config
from src.portfolio import Portfolio
from src.broker import PaperBroker
from src.engine import run_cycle


def _cfg(**over):
    c = load_config()
    c.update(over)
    return c


def test_equity_invariante_y_pnl():
    pf = Portfolio(cash=10000.0)
    b = PaperBroker(pf)
    b.open("BTC/USDT", "buy", 0.1, 30000.0, stop=29000, tp=33000)
    # equity = cash + unrealized; al abrir ~10000 (solo fee/slippage)
    assert abs(pf.equity({"BTC/USDT": 30000.0}) - 10000) < 60
    assert pf.equity({"BTC/USDT": 30000.0}) == pf.cash + pf.unrealized({"BTC/USDT": 30000.0})
    b.close("BTC/USDT", 33000.0)            # cierre a favor
    assert pf.realized_pnl > 0 and not pf.positions
    assert abs(pf.equity({}) - pf.cash) < 1e-9


def test_recomendacion_no_ejecuta(real_data):
    cfg = _cfg(mode="recomendacion", enabled=True)
    cfg["forecast"]["min_confidence"] = 0.0
    r = run_cycle(cfg, Portfolio(cash=5000.0))
    assert not any(p["executed"] for p in r["proposals"])


def test_killswitch_enabled_false(real_data):
    cfg = _cfg(mode="auto_testnet", enabled=False)
    assert run_cycle(cfg, Portfolio(cash=5000.0))["ok"] is False

"""Tests de las correcciones P0 (C1-C4)."""
from datetime import datetime, timezone
from src.config import load_config
from src.portfolio import Portfolio, Position
from src.engine import run_cycle
from src import journal as J


def _cfg(**over):
    c = load_config(); c.update(over)
    c["forecast"]["min_confidence"] = 0.0
    return c


def test_C1_sinteticos_no_ejecuta(synth_data):
    # Forzamos source='synthetic' (no depende de que haya o no red).
    cfg = _cfg(mode="auto_testnet", enabled=True)
    r = run_cycle(cfg, Portfolio(cash=10000.0))
    assert not any(p["executed"] for p in r["proposals"]), "no debe ejecutar con datos sinteticos"
    assert any("SINTETIC" in (p["note"] or "").upper() for p in r["proposals"])


def test_C1_datos_reales_si_ejecuta(real_data):
    cfg = _cfg(mode="auto_testnet", enabled=True)
    r = run_cycle(cfg, Portfolio(cash=10000.0))
    # con datos 'binance' al menos una propuesta de abrir se ejecuta
    assert any(p["executed"] for p in r["proposals"])


def test_C2_killswitch_perdida_diaria(real_data):
    pf = Portfolio(cash=10000.0); pf.save()
    # Registrar una perdida de hoy del 4% (> max_daily_loss 3%)
    J.log_trade({"symbol": "BTC/USDT", "evento": "close", "pnl": -400, "modo": "test"})
    cfg = _cfg(mode="auto_testnet", enabled=True)
    r = run_cycle(cfg, pf)
    assert r["ok"] is False and "Kill-switch" in r["reason"]
    assert cfg["enabled"] is False, "debe desactivar la automatizacion"


def test_C3_take_profit_cierra(real_data, monkeypatch):
    # Forzar prevision neutral para aislar el cierre por take-profit (sin "senal contraria")
    from src.forecast import Forecast
    monkeypatch.setattr("src.forecast.predict",
                        lambda df, sym, hz="4h": Forecast(sym, "lateral", 0.5, 0.0, hz, {}))
    pf = Portfolio(cash=10000.0)
    # Long con TP por debajo del precio actual (~30000) -> price >= tp dispara take-profit
    pf.positions["BTC/USDT"] = Position("BTC/USDT", "long", 0.1, 100.0, stop=0.0, take_profit=100.0)
    pf.save()
    cfg = _cfg(mode="auto_testnet", enabled=True)
    r = run_cycle(cfg, pf)
    cerrar = [p for p in r["proposals"] if p["action"] == "cerrar"]
    assert cerrar and "take-profit" in cerrar[0]["note"]
    assert cerrar[0]["executed"] and "BTC/USDT" not in pf.positions


def test_C4_journal_fecha_no_vacia():
    J.log_trade({"symbol": "ETH/USDT", "evento": "open", "lado": "buy"})
    import csv
    with open(J.JOURNAL_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows and rows[-1]["fecha"], "la fecha no debe quedar vacia"
    # parseable como ISO
    datetime.fromisoformat(rows[-1]["fecha"])


def test_C4_today_pnl_suma_hoy(real_data):
    J.log_trade({"symbol": "BTC/USDT", "evento": "close", "pnl": -123.0})
    assert abs(J.today_pnl() - (-123.0)) < 1e-9

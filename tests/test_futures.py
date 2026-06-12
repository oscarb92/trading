"""Tests de futuros paper: liquidación, funding, apalancamiento (sim + broker + engine)."""
import numpy as np
import pandas as pd
from src import futures as fut, risk
from src.broker import PaperBroker
from src.portfolio import Portfolio, Position


def _df(closes, lows=None, highs=None):
    n = len(closes)
    c = np.asarray(closes, dtype=float)
    o = np.r_[c[0], c[:-1]]
    h = np.asarray(highs, dtype=float) if highs is not None else np.maximum(o, c) * 1.001
    l = np.asarray(lows, dtype=float) if lows is not None else np.minimum(o, c) * 0.999
    ts = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"ts": ts, "open": o, "high": h, "low": l, "close": c, "volume": 1.0})


def test_precio_de_liquidacion():
    # Largo a 5x con maint 0.5%: cae ~19.9% → liq ≈ 80.1
    assert abs(fut.liquidation_price(100, "long", 5) - 80.1) < 0.01
    # Corto a 5x: sube ~19.9% → liq ≈ 119.9
    assert abs(fut.liquidation_price(100, "short", 5) - 119.9) < 0.01
    # A 1x el largo solo muere cerca de cero
    assert fut.liquidation_price(100, "long", 1) < 1.0


def test_apalancamiento_escala_el_pnl():
    """Sin liquidación ni funding, 3x ≈ 3× el retorno por vela de 1x."""
    closes = 100 * np.exp(np.cumsum(np.full(300, 0.001)))    # subida suave
    df = _df(closes)
    always_long = lambda d: pd.Series(1, index=d.index)
    r1 = fut.simulate_futures(df, "1h", always_long, leverage=1, funding_8h_pct=0.0)
    r3 = fut.simulate_futures(df, "1h", always_long, leverage=3, funding_8h_pct=0.0)
    assert not r1["liquidated"] and not r3["liquidated"]
    # En retornos log-compuestos no es exactamente 3x, pero sí claramente mayor
    assert r3["metrics"]["total_return"] > 2.5 * r1["metrics"]["total_return"]


def test_liquidacion_intrabar_aniquila_la_cuenta():
    """Una mecha de −25% con 5x liquida aunque el cierre recupere."""
    closes = [100.0] * 50
    lows = [99.9] * 50
    lows[30] = 75.0                                           # mecha del −25% intrabar
    df = _df(closes, lows=lows)
    always_long = lambda d: pd.Series(1, index=d.index)
    r = fut.simulate_futures(df, "1h", always_long, leverage=5, funding_8h_pct=0.0)
    assert r["liquidated"] and r["liq_bar"] == 30
    assert r["metrics"]["total_return"] <= -0.99              # cuenta a ~0, sin recuperación
    r1 = fut.simulate_futures(df, "1h", always_long, leverage=1, funding_8h_pct=0.0)
    assert not r1["liquidated"]                               # a 1x la mecha no mata


def test_funding_lo_paga_el_largo_y_lo_cobra_el_corto():
    closes = [100.0] * 200                                    # precio plano: solo funding
    df = _df(closes, lows=[100.0] * 200, highs=[100.0] * 200)
    long_fn = lambda d: pd.Series(1, index=d.index)
    short_fn = lambda d: pd.Series(-1, index=d.index)
    rl = fut.simulate_futures(df, "1h", long_fn, leverage=2, fee=0, slippage=0,
                              funding_8h_pct=0.05)
    rs = fut.simulate_futures(df, "1h", short_fn, leverage=2, fee=0, slippage=0,
                              funding_8h_pct=0.05)
    assert rl["metrics"]["total_return"] < 0                  # largo sangra funding
    assert rs["metrics"]["total_return"] > 0                  # corto lo cobra


def test_size_position_respeta_tope_de_apalancamiento():
    cfg = {"max_per_trade_pct": 50.0, "max_daily_loss_pct": 99, "max_open_positions": 5}
    # stop muy cercano → notional enorme; a 1x se capa en equity, a 3x en 3×equity
    r1 = risk.size_position(100.0, 1000.0, cfg, "alza", atr_pct=0.001, leverage=1.0)
    r3 = risk.size_position(100.0, 1000.0, cfg, "alza", atr_pct=0.001, leverage=3.0)
    assert abs(r1.notional - 1000.0) < 1e-6
    assert abs(r3.notional - 3000.0) < 1e-6


def test_broker_abre_con_liq_price_y_persiste(tmp_path, monkeypatch):
    import src.portfolio as P
    monkeypatch.setattr(P, "STATE_PATH", tmp_path / "pf.json")
    pf = Portfolio(cash=1000.0)
    b = PaperBroker(pf, fee_rate=0.0, slippage=0.0)
    b.open("BTC/USDT", "buy", 0.01, 50000.0, leverage=5)
    pos = pf.positions["BTC/USDT"]
    assert pos.leverage == 5 and 0 < pos.liq_price < 50000.0 and pos.last_funding
    loaded = Portfolio.load()                                 # roundtrip JSON con campos nuevos
    assert loaded.positions["BTC/USDT"].liq_price == pos.liq_price


def test_engine_liquida_forzosamente(real_data, tmp_path, monkeypatch):
    """Si el precio cruza liq_price, el engine cierra con nota LIQUIDACION."""
    from src.config import load_config
    from src.engine import run_cycle
    cfg = load_config()
    cfg.update(mode="auto_testnet", enabled=True)
    cfg["futures"] = {"enabled": True, "leverage": 5, "max_leverage": 5,
                      "funding_8h_pct": 0.0, "maintenance_margin_pct": 0.5}
    pf = Portfolio(cash=1000.0)
    # corto abierto en 28000 con liq en 29000; el precio del fixture es 30000 → liquida
    pf.positions["BTC/USDT"] = Position("BTC/USDT", "short", 0.01, 28000.0,
                                        stop=40000.0, leverage=5, liq_price=29000.0,
                                        last_funding="")
    r = run_cycle(cfg, pf)
    liq = [p for p in r["proposals"] if "LIQUIDACION" in p.get("note", "")]
    assert liq and liq[0]["executed"]
    assert "BTC/USDT" not in pf.positions                     # posición cerrada a la fuerza

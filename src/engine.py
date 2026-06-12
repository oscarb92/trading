"""AutoTrader: orquesta UNA pasada del ciclo datos -> forecast -> riesgo -> decisión.

Respeta el modo de automation_config.yaml:
  recomendacion -> devuelve propuestas (no ejecuta)
  auto_testnet  -> ejecuta en PaperBroker (precios reales, saldo simulado)
  auto_live     -> bloqueado en Fase 1 (requiere validación)

Correcciones P0 aplicadas (ver PLAN.md):
  C1 - nunca ejecuta sobre datos sintéticos (FetchResult.source != "binance").
  C2 - kill-switch de pérdida diaria conectado al journal.
  C3 - cierre por take-profit, no solo por stop o señal contraria.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from . import data as data_mod
from . import forecast as fc_mod
from . import risk as risk_mod
from .portfolio import Portfolio
from .broker import PaperBroker
from .journal import log_trade, today_pnl
from .config import save_config


def _accrue_funding(pf: Portfolio, pos, price: float, funding_8h_pct: float) -> float:
    """Cobra/paga el funding devengado desde el último cobro (futuros paper).

    Largo paga tasa positiva; corto la cobra. Notional = qty × precio actual.
    Devuelve el importe aplicado al cash (negativo = costó dinero).
    """
    if pos.leverage <= 1 or not pos.last_funding:
        return 0.0
    now = datetime.now(timezone.utc)
    try:
        last = datetime.fromisoformat(pos.last_funding)
    except ValueError:
        last = now
    hours = max((now - last).total_seconds() / 3600.0, 0.0)
    if hours <= 0:
        return 0.0
    rate = (funding_8h_pct / 100.0) * (hours / 8.0)
    amount = pos.qty * price * rate
    signed = -amount if pos.side == "long" else amount
    pf.cash += signed
    pos.last_funding = now.isoformat()
    return signed


@dataclass
class Proposal:
    symbol: str
    action: str            # "abrir" | "cerrar" | "mantener"
    side: str              # "buy" | "sell" | ""
    forecast: dict
    risk: dict
    price: float
    executed: bool = False
    note: str = ""


def run_cycle(cfg: dict, portfolio: Portfolio | None = None) -> dict:
    pf = portfolio or Portfolio.load()
    mode = cfg.get("mode", "recomendacion")
    if not cfg.get("enabled", False) and mode != "recomendacion":
        return {"ok": False, "reason": "Automatizacion deshabilitada (enabled=false)", "proposals": []}

    risk_cfg = cfg.get("risk", {})
    max_daily_loss = risk_cfg.get("max_daily_loss_pct", 3.0)
    min_conf = cfg.get("forecast", {}).get("min_confidence", 0.6)
    horizon = cfg.get("forecast", {}).get("horizon", "4h")
    fut_cfg = cfg.get("futures", {})
    fut_on = bool(fut_cfg.get("enabled", False))
    lev = float(min(fut_cfg.get("leverage", 1), fut_cfg.get("max_leverage", 5))) if fut_on else 1.0
    funding_8h = float(fut_cfg.get("funding_8h_pct", 0.01))
    maint_pct = float(fut_cfg.get("maintenance_margin_pct", 0.5))

    # --- C2: kill-switch de perdida diaria (antes de operar) ---
    equity_ref = pf.equity({})
    pnl_today = today_pnl()
    daily_loss_pct = (pnl_today / equity_ref * 100.0) if equity_ref > 0 else 0.0
    if daily_loss_pct <= -abs(max_daily_loss):
        if cfg.get("enabled"):
            cfg["enabled"] = False
            try:
                save_config(cfg)
            except Exception:
                pass
        return {"ok": False, "mode": mode, "proposals": [],
                "reason": f"Kill-switch: perdida diaria {daily_loss_pct:.2f}% "
                          f"alcanzo el limite {max_daily_loss}%. Automatizacion desactivada."}

    broker = PaperBroker(pf)
    proposals: list[Proposal] = []
    prices: dict[str, float] = {}

    for symbol in cfg.get("symbols", []):
        res = data_mod.fetch_ohlcv(symbol, timeframe="1h", limit=300)
        is_synthetic = res.source != "binance"          # C1
        price = float(res.df["close"].iloc[-1])
        prices[symbol] = price
        f = fc_mod.predict(res.df, symbol, horizon)

        can_exec = (mode == "auto_testnet" and cfg.get("enabled") and not is_synthetic)
        synth_note = " · DATOS SINTETICOS: no se ejecuta" if is_synthetic else ""

        # ---- Cerrar posicion existente? (liquidacion, senal contraria, stop o TP) ----
        pos = pf.positions.get(symbol)
        if pos:
            # Futuros: funding devengado + LIQUIDACION forzosa (manda sobre todo lo demas)
            _accrue_funding(pf, pos, price, funding_8h)
            liquidated = pos.liq_price > 0 and (
                (pos.side == "long" and price <= pos.liq_price) or
                (pos.side == "short" and price >= pos.liq_price))
            if liquidated:
                p = Proposal(symbol, "cerrar", "", asdict(f), {}, price,
                             note=f"LIQUIDACION {pos.leverage:g}x (liq={pos.liq_price:.2f})"
                                  + synth_note)
                if can_exec:
                    fill = broker.close(symbol, pos.liq_price)   # se ejecuta AL precio de liq
                    p.executed = True
                    log_trade({"symbol": symbol, "evento": "close", "lado": fill.side,
                               "qty": fill.qty, "precio": fill.price, "fee": fill.fee,
                               "pnl": fill.note.split("pnl=")[-1], "modo": mode,
                               "nota": "LIQUIDACION"})
                proposals.append(p)
                continue
            opposite = (pos.side == "long" and f.direction == "baja") or \
                       (pos.side == "short" and f.direction == "alza")
            hit_stop = (pos.side == "long" and price <= pos.stop) or \
                       (pos.side == "short" and price >= pos.stop)
            hit_tp = pos.take_profit > 0 and (
                     (pos.side == "long" and price >= pos.take_profit) or
                     (pos.side == "short" and price <= pos.take_profit))
            if opposite or hit_stop or hit_tp:
                reason = ("senal contraria" if opposite else
                          "take-profit" if hit_tp else "stop")
                p = Proposal(symbol, "cerrar", "", asdict(f), {}, price,
                             note=reason + synth_note)
                if can_exec:
                    fill = broker.close(symbol, price)
                    p.executed = True
                    log_trade({"symbol": symbol, "evento": "close", "lado": fill.side,
                               "qty": fill.qty, "precio": fill.price, "fee": fill.fee,
                               "pnl": fill.note.split("pnl=")[-1], "modo": mode, "nota": reason})
                proposals.append(p)
            else:
                proposals.append(Proposal(symbol, "mantener", "", asdict(f), {}, price))
            continue

        # ---- Abrir nueva posicion? ----
        if f.confidence < min_conf or f.direction == "lateral":
            proposals.append(Proposal(symbol, "mantener", "", asdict(f), {}, price,
                                      note=f"confianza {f.confidence:.2f} < {min_conf}"))
            continue

        equity = pf.equity(prices)
        atr_pct = f.detail.get("volatility", 0.02) or 0.02
        rd = risk_mod.size_position(price, equity, risk_cfg, f.direction,
                                    atr_pct=atr_pct, open_positions=len(pf.positions),
                                    daily_loss_pct=daily_loss_pct, leverage=lev)  # C2
        if not rd.approved:
            proposals.append(Proposal(symbol, "mantener", "", asdict(f), asdict(rd), price,
                                      note=rd.reason))
            continue

        side = "buy" if f.direction == "alza" else "sell"
        p = Proposal(symbol, "abrir", side, asdict(f), asdict(rd), price,
                     note=("DATOS SINTETICOS: no se ejecuta" if is_synthetic else ""))
        if can_exec:
            fill = broker.open(symbol, side, rd.qty, price, rd.stop_price, rd.take_profit,
                               leverage=lev, maint_pct=maint_pct)
            p.executed = True
            log_trade({"symbol": symbol, "evento": "open", "lado": side, "qty": fill.qty,
                       "precio": fill.price, "fee": fill.fee, "prob": round(f.probability, 3),
                       "confianza": round(f.confidence, 3), "modo": mode})
        proposals.append(p)

    pf.save()
    return {"ok": True, "mode": mode, "prices": prices,
            "proposals": [asdict(p) for p in proposals],
            "equity": pf.equity(prices)}

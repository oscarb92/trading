"""Gestión de riesgo: tamaño de posición, stops y validación de límites."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class RiskDecision:
    approved: bool
    qty: float            # unidades del activo
    notional: float       # valor en moneda de cotización
    stop_price: float
    take_profit: float
    reason: str


def size_position(price: float, equity: float, risk_cfg: dict,
                  direction: str, atr_pct: float = 0.02,
                  open_positions: int = 0, daily_loss_pct: float = 0.0) -> RiskDecision:
    max_per_trade = risk_cfg.get("max_per_trade_pct", 1.0) / 100.0
    max_daily_loss = risk_cfg.get("max_daily_loss_pct", 3.0)
    max_open = risk_cfg.get("max_open_positions", 3)

    # Kill-switch por pérdida diaria
    if daily_loss_pct <= -abs(max_daily_loss):
        return RiskDecision(False, 0, 0, 0, 0, "Límite de pérdida diaria alcanzado")
    if open_positions >= max_open:
        return RiskDecision(False, 0, 0, 0, 0, "Máximo de posiciones abiertas alcanzado")
    if direction == "lateral":
        return RiskDecision(False, 0, 0, 0, 0, "Sin señal direccional")

    # Riesgo monetario por operación; stop a ~1.5x ATR, objetivo 1:1.5
    risk_amount = equity * max_per_trade
    stop_dist = max(price * atr_pct * 1.5, price * 0.002)
    qty = risk_amount / stop_dist
    notional = qty * price
    # No exceder el equity disponible
    if notional > equity:
        qty = equity / price
        notional = qty * price

    if direction == "alza":
        stop_price = price - stop_dist
        take_profit = price + stop_dist * 1.5
    else:
        stop_price = price + stop_dist
        take_profit = price - stop_dist * 1.5

    return RiskDecision(True, qty, notional, stop_price, take_profit, "OK")


# ---------------------------------------------------------------------------
# Utilidades de gestión de riesgo (Fase 5) — herramientas informativas para el
# dashboard. NO ejecutan nada; calculan y reportan. Información técnica, no
# asesoría financiera.
# ---------------------------------------------------------------------------

def kelly_fraction(win_rate: float, win_loss_ratio: float) -> float:
    """Fracción de Kelly completa: f* = W − (1−W)/R.

    W = probabilidad de ganar [0,1]; R = ratio ganancia media / pérdida media.
    Devuelve 0 si no hay edge (f* ≤ 0): Kelly dice "no apuestes"."""
    if win_loss_ratio <= 0:
        return 0.0
    f = win_rate - (1 - win_rate) / win_loss_ratio
    return max(0.0, f)


def fractional_kelly(win_rate: float, win_loss_ratio: float,
                     fraction: float = 0.5, cap: float = 0.2) -> float:
    """Kelly fraccionario (≤ ½ Kelly por defecto), recortado a `cap` del equity.

    El Kelly completo es muy agresivo y sensible a errores de estimación de W/R;
    media-Kelly reduce la varianza a cambio de poco retorno. `cap` es un tope duro
    de prudencia (regla: nunca aumentar riesgo sobre los límites)."""
    fraction = max(0.0, min(fraction, 1.0))
    f = kelly_fraction(win_rate, win_loss_ratio) * fraction
    return min(f, max(0.0, cap))


def size_from_risk(equity: float, risk_pct: float, entry: float, stop: float) -> dict:
    """Sizing por riesgo fijo: arriesgar `risk_pct`% del equity con stop en `stop`.

    qty = (equity·risk%) / |entry−stop|. Reporta también el apalancamiento implícito
    (notional/equity) para que se vea si una operación 'de bajo riesgo' esconde
    una posición enorme por tener el stop muy cerca."""
    stop_dist = abs(entry - stop)
    risk_amount = equity * (risk_pct / 100.0)
    if stop_dist <= 0 or equity <= 0 or entry <= 0:
        return {"qty": 0.0, "notional": 0.0, "risk_amount": risk_amount,
                "leverage": 0.0, "reason": "Stop = entrada o equity/precio inválidos"}
    qty = risk_amount / stop_dist
    notional = qty * entry
    return {"qty": qty, "notional": notional, "risk_amount": risk_amount,
            "leverage": notional / equity, "reason": "OK"}


def stress_test_gap(portfolio, prices: dict, gap_pct: float = -0.20) -> dict:
    """Aplica un shock instantáneo de `gap_pct` a los precios y reporta el impacto.

    Caso pesimista (mark-to-gap): asume que el hueco salta los stops (en gaps reales,
    los stops resbalan). Marca qué stops se habrían cruzado para distinguir la pérdida
    'si el stop aguanta' de la del hueco completo."""
    eq_before = portfolio.equity(prices)
    rows, shocked = [], {}
    for sym, p in portfolio.positions.items():
        px = prices.get(sym, p.entry)
        sx = px * (1 + gap_pct)
        shocked[sym] = sx
        pnl_b = (px - p.entry) * p.qty if p.side == "long" else (p.entry - px) * p.qty
        pnl_a = (sx - p.entry) * p.qty if p.side == "long" else (p.entry - sx) * p.qty
        stop_hit = bool(p.stop > 0 and ((p.side == "long" and sx <= p.stop) or
                                        (p.side == "short" and sx >= p.stop)))
        rows.append({"symbol": sym, "side": p.side, "price": px, "shocked": sx,
                     "pnl_change": pnl_a - pnl_b, "stop_hit": stop_hit})
    merged = dict(prices)
    merged.update(shocked)
    eq_after = portfolio.equity(merged)
    change = eq_after - eq_before
    return {"gap_pct": gap_pct, "equity_before": eq_before, "equity_after": eq_after,
            "change": change, "change_pct": (change / eq_before) if eq_before else 0.0,
            "positions": rows}


def exposure(portfolio, prices: dict) -> dict:
    """Exposición por activo y agregada (bruta y neta) en % del equity."""
    eq = portfolio.equity(prices)
    rows, gross, net = [], 0.0, 0.0
    for sym, p in portfolio.positions.items():
        px = prices.get(sym, p.entry)
        notional = p.qty * px
        gross += notional
        net += notional if p.side == "long" else -notional
        rows.append({"symbol": sym, "side": p.side, "notional": notional,
                     "pct_equity": (notional / eq) if eq else 0.0})
    return {"equity": eq, "positions": rows, "gross": gross, "net": net,
            "gross_pct": (gross / eq) if eq else 0.0,
            "net_pct": (net / eq) if eq else 0.0}


def correlation_matrix(symbols: list, timeframe: str = "1h"):
    """Matriz de correlación de retornos entre activos (diversificación).

    Carga del histórico local (`store`); alinea por timestamp. Correlaciones altas
    entre posiciones = diversificación ilusoria (todo se mueve junto en un crash)."""
    import pandas as pd
    from . import store
    series = {}
    for s in symbols:
        df = store.load_ohlcv(s, timeframe)
        if not df.empty:
            series[s] = df.set_index("ts")["close"].astype(float).pct_change()
    if len(series) < 2:
        return pd.DataFrame()
    return pd.DataFrame(series).dropna().corr()

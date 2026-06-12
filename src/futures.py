"""Simulación de FUTUROS PERPETUOS en paper (apalancamiento, funding, liquidación).

Modelo honesto y documentado (no pretende replicar el motor de riesgo de Binance):
  - **Margen cruzado de cuenta completa**: el apalancamiento multiplica el PnL de la
    cuenta; una liquidación = la cuenta queda a ~0 (no liquidación parcial por posición).
  - **Liquidación intrabar**: se usa la excursión adversa de la vela (low para largos,
    high para cortos). Si el movimiento adverso × apalancamiento ≥ (1 − margen de
    mantenimiento), la cuenta se liquida ESA vela, aunque el cierre hubiera recuperado.
  - **Funding**: tasa cada 8h (los largos pagan tasa positiva; los cortos la cobran),
    prorrateada por vela y aplicada sobre el notional apalancado.

La conclusión de fondo del proyecto no cambia con futuros: sin edge, el apalancamiento
solo acelera la pérdida y añade el riesgo de ruina total. Este módulo existe para PODER
MEDIRLO con datos propios. Información técnica, no asesoría financiera.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from . import backtest as bt

# horas por vela (para prorratear el funding de 8h)
_BAR_HOURS = {"1m": 1 / 60, "5m": 5 / 60, "15m": 0.25, "30m": 0.5,
              "1h": 1.0, "4h": 4.0, "1d": 24.0}


def liquidation_price(entry: float, side: str, leverage: float,
                      maint_pct: float = 0.5) -> float:
    """Precio aproximado de liquidación (margen cruzado simplificado).

    Un largo a apalancamiento L se liquida si el precio cae ~(1 − maint)/L;
    un corto, si sube esa misma fracción. maint_pct en porcentaje (0.5 = 0.5%).
    A 1× el largo solo se liquida cerca de cero y el corto al duplicarse el precio.
    """
    if leverage <= 0 or entry <= 0:
        return 0.0
    frac = (1.0 - maint_pct / 100.0) / leverage
    return entry * (1.0 - frac) if side == "long" else entry * (1.0 + frac)


def funding_per_bar(funding_8h_pct: float, timeframe: str) -> float:
    """Fracción de funding por vela (tasa de 8h prorrateada)."""
    return (funding_8h_pct / 100.0) * (_BAR_HOURS.get(timeframe, 1.0) / 8.0)


def simulate_futures(df: pd.DataFrame, timeframe: str = "1h", signal_fn=None,
                     leverage: float = 1.0, fee: float = 0.001, slippage: float = 0.0005,
                     funding_8h_pct: float = 0.01, maint_pct: float = 0.5,
                     ppy: float | None = None) -> dict:
    """Backtest de una señal {-1,0,1} operada como perpetuo a `leverage`×.

    Devuelve {"metrics": dict, "equity": Series, "liquidated": bool, "liq_bar": int|None}.
    Si hay liquidación, el equity cae a ~0 en esa vela y ahí termina la historia
    (total_return = −100%): no hay 'recuperación' posible tras perder la cuenta.
    """
    df = df.reset_index(drop=True)
    sig = (signal_fn or bt.baseline_signal)(df)
    pos = sig.shift(1).fillna(0).astype(float)

    close = df["close"].astype(float)
    prev = close.shift(1)
    ret = close.pct_change().fillna(0).clip(-0.5, 0.5)
    fund = funding_per_bar(funding_8h_pct, timeframe)

    cost = pos.diff().abs().fillna(pos.abs()) * (fee + slippage) * leverage
    gross = leverage * pos * ret
    funding = leverage * pos * fund            # largo paga (resta), corto cobra (suma)
    net = (gross - cost - funding).fillna(0)

    # Liquidación intrabar: excursión adversa de la vela contra la posición
    adverse_long = (df["low"].astype(float) / prev - 1)        # caída máx. intrabar
    adverse_short = (df["high"].astype(float) / prev - 1)      # subida máx. intrabar
    wipe = 1.0 - maint_pct / 100.0
    liq_mask = (((pos > 0) & (adverse_long * leverage <= -wipe)) |
                ((pos < 0) & (adverse_short * leverage >= wipe))).fillna(False)

    liq_bar = int(liq_mask.idxmax()) if bool(liq_mask.any()) else None
    if liq_bar is not None:
        net = net.copy()
        net.iloc[liq_bar] = -1.0               # la cuenta se esfuma esa vela
        if liq_bar + 1 < len(net):
            net.iloc[liq_bar + 1:] = 0.0       # no hay nada que componer después

    equity = (1 + net).cumprod()
    n = len(df)
    ppy = ppy if ppy is not None else bt.PPY.get(timeframe, 8760)
    total_return = float(equity.iloc[-1] - 1) if n else 0.0
    # Sharpe sobre la parte VIVA (pre-liquidación); con cuenta muerta no tiene sentido
    live = net.iloc[:liq_bar] if liq_bar is not None else net
    std = live.std()
    sharpe = float(live.mean() / std * np.sqrt(ppy)) if std and std > 0 else 0.0
    roll_max = equity.cummax()
    max_dd = float(((equity - roll_max) / roll_max).min()) if n else 0.0
    trades = int((pos.diff().abs() > 0).sum())
    metrics = {"total_return": round(total_return, 4), "sharpe": round(sharpe, 2),
               "max_drawdown": round(max_dd, 4), "trades": trades, "bars": n,
               "leverage": leverage, "funding_8h_pct": funding_8h_pct,
               "cost_drag": round(float(cost.sum() + (funding.clip(lower=0)).sum()), 4),
               "liquidated": liq_bar is not None}
    return {"metrics": metrics, "equity": equity, "liquidated": liq_bar is not None,
            "liq_bar": liq_bar}

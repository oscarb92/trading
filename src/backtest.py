"""Motor de backtesting (Fase 2b).

Evalúa el baseline (mismo cálculo que forecast.predict, vectorizado) sobre datos
históricos locales. Sin look-ahead (la señal se aplica a la vela siguiente),
con comisiones y slippage. Incluye walk-forward y métricas honestas.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"

PPY = {"1m": 525600, "5m": 105120, "15m": 35040, "30m": 17520,
       "1h": 8760, "4h": 2190, "1d": 365}


def prob_up(df: pd.DataFrame) -> pd.Series:
    """Probabilidad de subida [0,1] por vela (momentum+tendencia+RSI).
    Misma lógica que forecast.predict, vectorizada. Núcleo compartido por todas
    las señales (baseline y variantes de Fase 3)."""
    close = df["close"].astype(float)
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    delta = close.diff()
    up = delta.clip(lower=0).rolling(14).mean()
    down = (-delta.clip(upper=0)).rolling(14).mean()
    rs = up / down.replace(0, np.nan)
    rsi = (100 - 100 / (1 + rs)).fillna(50)
    mom = close / close.shift(10) - 1
    trend = (ema_fast - ema_slow) / close
    rsi_sig = (rsi - 50) / 50
    score = np.tanh(mom * 20) * 0.4 + np.tanh(trend * 50) * 0.4 + rsi_sig * 0.2
    return 1 / (1 + np.exp(-score * 3))


def baseline_signal(df: pd.DataFrame) -> pd.Series:
    """Posición objetivo {-1,0,1} por vela. Réplica vectorizada de forecast.predict.
    Se DESPLAZA 1 vela al simular para no usar información futura."""
    p = prob_up(df)
    pos = pd.Series(0, index=df.index)
    pos[p > 0.55] = 1
    pos[p < 0.45] = -1
    return pos.fillna(0)


def hysteresis_signal(df: pd.DataFrame, enter: float = 0.60,
                      exit_: float = 0.50) -> pd.Series:
    """Señal con BANDA MUERTA / histéresis (Fase 3) para frenar el sobre-trading.

    El baseline flipea de posición casi cada vela porque sus bandas (0.55/0.45)
    están pegadas. Aquí se entra solo con convicción (`enter`/`1-enter`) y se
    MANTIENE la posición hasta que la probabilidad cruza el centro (`exit_`),
    momento en que se sale a plano o se invierte si hay convicción contraria.

    Es secuencial (depende de la posición previa), por eso no es un simple umbral
    vectorizado. enter=0.60, exit_=0.50 → entra 0.60/0.40, sale en 0.50.
    """
    p = prob_up(df).values
    lo = 1 - enter
    out = np.zeros(len(p), dtype=int)
    cur = 0
    for i in range(len(p)):
        pi = p[i]
        if np.isnan(pi):
            out[i] = cur
            continue
        if cur == 0:
            if pi > enter:
                cur = 1
            elif pi < lo:
                cur = -1
        elif cur == 1:
            if pi < exit_:                       # se rompe la convicción alcista
                cur = -1 if pi < lo else 0
        elif cur == -1:
            if pi > (1 - exit_):                 # se rompe la convicción bajista
                cur = 1 if pi > enter else 0
        out[i] = cur
    return pd.Series(out, index=df.index)


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index [0,100] (suavizado de Wilder).

    Mide la FUERZA de la tendencia con independencia de su dirección. ADX alto
    (>~25) = mercado en tendencia; bajo = lateral/rango. Es la pieza que usa el
    filtro de régimen para no operar momentum donde no hay tendencia que seguir."""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
                        index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
                         index=df.index)
    a = 1 / period                               # suavizado de Wilder ≈ ewm(alpha=1/period)
    atr = tr.ewm(alpha=a, adjust=False).mean().replace(0, np.nan)
    plus_di = 100 * plus_dm.ewm(alpha=a, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=a, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=a, adjust=False).mean().fillna(0)


def regime_signal(df: pd.DataFrame, enter: float = 0.60, exit_: float = 0.50,
                  adx_min: float = 25.0, adx_period: int = 14) -> pd.Series:
    """Histéresis + FILTRO DE RÉGIMEN (Fase 3).

    El walk-forward mostró que el momentum gana en tendencia y pierde en lateral.
    Aquí solo se INICIA (o invierte) una posición cuando ADX >= `adx_min` (hay
    tendencia); la salida a plano funciona igual que en la histéresis. Así se busca
    quedarse con los tramos buenos y saltarse el rango. adx_min=0 → sin filtro."""
    p = prob_up(df).values
    a = adx(df, adx_period).values
    lo = 1 - enter
    out = np.zeros(len(p), dtype=int)
    cur = 0
    for i in range(len(p)):
        pi, ai = p[i], a[i]
        if np.isnan(pi):
            out[i] = cur
            continue
        trending = ai >= adx_min
        if cur == 0:
            if trending and pi > enter:
                cur = 1
            elif trending and pi < lo:
                cur = -1
        elif cur == 1:
            if pi < exit_:                       # se rompe la convicción alcista
                cur = -1 if (pi < lo and trending) else 0
        elif cur == -1:
            if pi > (1 - exit_):                 # se rompe la convicción bajista
                cur = 1 if (pi > enter and trending) else 0
        out[i] = cur
    return pd.Series(out, index=df.index)


def mean_reversion_signal(df: pd.DataFrame, lookback: int = 20,
                          entry_z: float = 2.0, exit_z: float = 0.5) -> pd.Series:
    """Reversión a la media (familia OPUESTA al momentum).

    z = (close − media móvil) / desv. típica móvil. Si el precio está MUY por
    debajo de su media (z < −entry_z) se compra apostando a que vuelve; si está
    muy por encima (z > +entry_z) se vende. Se sale a plano cuando el precio
    revierte cerca de la media (|z| < exit_z). Histéresis natural: entrar lejos,
    salir cerca. NO invierte directamente long↔short (sale a plano y espera el
    siguiente extremo), lo que limita el sobre-trading.

    Aviso: en cripto, vender en corto lo que 'está caro' es peligroso en tendencia
    alcista. La validación OOS dirá si esta lógica tiene edge o no.
    """
    close = df["close"].astype(float)
    ma = close.rolling(lookback).mean()
    sd = close.rolling(lookback).std()
    z = ((close - ma) / sd.replace(0, np.nan)).values
    out = np.zeros(len(z), dtype=int)
    cur = 0
    for i in range(len(z)):
        zi = z[i]
        if np.isnan(zi):
            out[i] = cur
            continue
        if cur == 0:
            if zi < -entry_z:
                cur = 1                          # precio bajo → comprar (revertirá al alza)
            elif zi > entry_z:
                cur = -1                         # precio alto → vender
        elif cur == 1:
            if zi >= -exit_z:                    # revirtió hacia la media → cerrar
                cur = 0
        elif cur == -1:
            if zi <= exit_z:
                cur = 0
        out[i] = cur
    return pd.Series(out, index=df.index)


def candlestick_signal(df: pd.DataFrame, hold: int = 5, trend_span: int = 20) -> pd.Series:
    """Patrones de velas japonesas con contexto de tendencia (familia 'price action').

    Detecta de forma vectorizada y CAUSAL (vela actual + anterior, nada futuro):
      - Envolvente alcista en tendencia bajista / envolvente bajista en alcista.
      - Martillo (mecha inferior ≥ 2× cuerpo, casi sin mecha superior) bajo la EMA.
      - Estrella fugaz (espejo del martillo) sobre la EMA.
    Tras un patrón se mantiene la posición `hold` velas y se vuelve a plano (los
    patrones de velas son señales de giro de corto plazo, no de tendencia).

    El folclore de las velas rara vez se valida con costes; esta señal existe para
    poder JUZGARLA con el mismo walk-forward OOS que las demás familias.
    """
    o = df["open"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)
    body = c - o
    absb = body.abs()
    rng = h - l
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    ema = c.ewm(span=trend_span, adjust=False).mean()
    down = c < ema                                   # contexto: buscamos giros contra la EMA
    up = c > ema
    po, pc, pbody = o.shift(1), c.shift(1), body.shift(1)

    bull_engulf = (body > 0) & (pbody < 0) & (c >= po) & (o <= pc) & down
    bear_engulf = (body < 0) & (pbody > 0) & (c <= po) & (o >= pc) & up
    hammer = (rng > 0) & (lower >= 2 * absb) & (upper <= 0.25 * rng) & down
    star = (rng > 0) & (upper >= 2 * absb) & (lower <= 0.25 * rng) & up
    bull = (bull_engulf | hammer).fillna(False).values
    bear = (bear_engulf | star).fillna(False).values

    out = np.zeros(len(df), dtype=int)
    cur, left = 0, 0
    for i in range(len(df)):
        if bull[i] and not bear[i]:
            cur, left = 1, hold
        elif bear[i] and not bull[i]:
            cur, left = -1, hold
        if left > 0:
            out[i] = cur
            left -= 1
        else:
            cur = 0
    return pd.Series(out, index=df.index)


@dataclass
class BTMetrics:
    total_return: float
    annual_return: float
    sharpe: float
    sortino: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    trades: int
    bars: int
    cost_drag: float = 0.0      # suma de costes (fees+slippage) en fracción
    clipped_bars: int = 0       # velas con retorno recortado (outliers/huecos)


def _trades_pnl(pos: pd.Series, net: pd.Series) -> list[float]:
    """PnL compuesto por cada periodo de posición constante no nula."""
    pnls, cur, start = [], 0, None
    p = pos.values
    for i in range(len(p)):
        if p[i] != cur:
            if cur != 0 and start is not None:
                seg = net.iloc[start:i]
                pnls.append(float((1 + seg).prod() - 1))
            cur, start = p[i], i
    if cur != 0 and start is not None:
        pnls.append(float((1 + net.iloc[start:]).prod() - 1))
    return pnls


def metrics_from_position(pos: pd.Series, raw_ret: pd.Series, timeframe: str = "1h",
                          fee: float = 0.001, slippage: float = 0.0005,
                          ppy: float | None = None) -> dict:
    """Calcula métricas a partir de una posición y retornos crudos YA alineados.

    Núcleo compartido por `run_backtest` y por la validación walk-forward. Permite
    evaluar una VENTANA (slice) usando una señal calculada sobre la serie completa
    —los indicadores son causales—, evitando recomputar el warm-up del ADX/EMA en
    cada fold. `pos` ya debe venir desplazada (shift(1)) si se quiere evitar look-ahead.

    `ppy` (periodos por año) sobreescribe la anualización por defecto del timeframe.
    Clave para comparar entre mercados: en diario, bolsa ≈ 252 días hábiles, cripto = 365.
    """
    pos = pos.reset_index(drop=True).astype(float)
    raw_ret = raw_ret.reset_index(drop=True).astype(float)
    ret = raw_ret.clip(-0.5, 0.5)                        # blindaje outliers/huecos
    clipped = int((raw_ret.abs() > 0.5).sum())
    cost = pos.diff().abs().fillna(pos.abs()) * (fee + slippage)
    net = pos * ret - cost
    equity = (1 + net).cumprod()

    ppy = ppy if ppy is not None else PPY.get(timeframe, 8760)
    n = len(pos)
    total_return = float(equity.iloc[-1] - 1) if n else 0.0
    annual_return = float(equity.iloc[-1] ** (ppy / max(n, 1)) - 1) if n else 0.0
    std = net.std()
    sharpe = float(net.mean() / std * np.sqrt(ppy)) if std > 0 else 0.0
    downside = net[net < 0].std()
    sortino = float(net.mean() / downside * np.sqrt(ppy)) if downside and downside > 0 else 0.0
    roll_max = equity.cummax()
    max_dd = float(((equity - roll_max) / roll_max).min()) if n else 0.0

    pnls = _trades_pnl(pos, net)
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]
    win_rate = round(len(wins) / len(pnls) * 100, 1) if pnls else 0.0
    pf = float(sum(wins) / abs(sum(losses))) if losses else (float("inf") if wins else 0.0)

    m = BTMetrics(round(total_return, 4), round(annual_return, 4), round(sharpe, 2),
                  round(sortino, 2), round(max_dd, 4), win_rate,
                  round(pf, 2), len(pnls), n,
                  cost_drag=round(float(cost.sum()), 4), clipped_bars=clipped)
    return {"metrics": m, "equity": equity, "net": net, "position": pos}


def run_backtest(df: pd.DataFrame, timeframe: str = "1h",
                 fee: float = 0.001, slippage: float = 0.0005,
                 signal_fn=None, ppy: float | None = None) -> dict:
    df = df.reset_index(drop=True)
    sig = (signal_fn or baseline_signal)(df)
    pos = sig.shift(1).fillna(0)                         # actuar en la vela siguiente
    raw_ret = df["close"].astype(float).pct_change().fillna(0)
    return metrics_from_position(pos, raw_ret, timeframe, fee, slippage, ppy)


def walk_forward(df: pd.DataFrame, timeframe: str = "1h", n_splits: int = 4,
                 fee: float = 0.001, slippage: float = 0.0005,
                 signal_fn=None) -> list[dict]:
    """Divide la serie en segmentos temporales y evalúa cada uno (out-of-sample
    en el tiempo). El baseline no se ajusta, así mide estabilidad temporal."""
    df = df.reset_index(drop=True)
    size = len(df) // n_splits
    out = []
    for k in range(n_splits):
        seg = df.iloc[k * size:(k + 1) * size] if k < n_splits - 1 else df.iloc[k * size:]
        if len(seg) < 60:
            continue
        r = run_backtest(seg, timeframe, fee, slippage, signal_fn=signal_fn)
        out.append({"segmento": k + 1, "desde": str(seg["ts"].iloc[0]),
                    "hasta": str(seg["ts"].iloc[-1]), "metrics": r["metrics"]})
    return out


def report(symbol: str, timeframe: str, full: dict, wf: list[dict]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    m = full["metrics"]
    p = REPORTS_DIR / f"backtest_{symbol.replace('/', '-')}_{timeframe}.md"
    lines = [f"# Backtest baseline — {symbol} {timeframe}", "",
             "> Estrategia: baseline (momentum+tendencia+RSI). Costes: 0.1% fee + 0.05% slippage.",
             "> Sin look-ahead (señal aplicada a la vela siguiente).", "",
             "## Resultado global", "",
             "| Métrica | Valor |", "|---|---|",
             f"| Retorno total | {m.total_return:.2%} |",
             f"| Retorno anualizado | {m.annual_return:.2%} |",
             f"| Sharpe | {m.sharpe} |",
             f"| Sortino | {m.sortino} |",
             f"| Max drawdown | {m.max_drawdown:.2%} |",
             f"| Win rate | {m.win_rate}% |",
             f"| Profit factor | {m.profit_factor} |",
             f"| Nº trades | {m.trades} |",
             f"| Turnover (trades/vela) | {m.trades / max(m.bars,1):.2f} |",
             f"| Coste acumulado (fees+slippage) | {m.cost_drag:.2%} |",
             f"| Velas | {m.bars} |", "",
             "## Walk-forward (estabilidad temporal)", "",
             "| Segmento | Desde | Hasta | Retorno | Sharpe | MaxDD | Trades |",
             "|---|---|---|---|---|---|---|"]
    for s in wf:
        sm = s["metrics"]
        lines.append(f"| {s['segmento']} | {s['desde'][:10]} | {s['hasta'][:10]} | "
                     f"{sm.total_return:.2%} | {sm.sharpe} | {sm.max_drawdown:.2%} | {sm.trades} |")
    avisos = []
    if m.clipped_bars > 0:
        avisos.append(f"⚠ {m.clipped_bars} vela(s) con retorno > 50% recortadas: probable "
                      "histórico contaminado (¿mezcla de datos sintéticos y reales?). "
                      "Vuelve a bajar el histórico limpio: `python backtest.py --fresh --download N`.")
    if m.trades / max(m.bars, 1) > 0.3:
        avisos.append(f"⚠ Sobre-trading: {m.trades} trades en {m.bars} velas. El baseline "
                      "cambia de posición casi cada vela y el coste se come el capital. "
                      "Esto se corrige en Fase 3 (banda muerta/histéresis), no es fallo del motor.")
    if avisos:
        lines += ["", "## Avisos", ""] + [f"- {a}" for a in avisos]
    lines += ["", "> Información técnica, no asesoría financiera. Resultados pasados no "
              "garantizan resultados futuros. Un baseline con métricas malas también es "
              "información útil: dice que esta estrategia simple no tiene edge."]
    p.write_text("\n".join(lines), encoding="utf-8")
    return p

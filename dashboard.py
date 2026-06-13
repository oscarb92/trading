"""Dashboard — Trading App (sandbox de research y simulación)

Ejecutar:   streamlit run dashboard.py

Herramienta HONESTA: backtesting con costes, validación walk-forward out-of-sample,
journal, paper trading con precios reales y gestión de riesgo. NO promete rentabilidad
—la validación OOS mostró que las estrategias incluidas no tienen edge demostrado.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from src.config import load_config, save_config
from src.portfolio import Portfolio
from src.broker import PaperBroker, LiveBroker
from src.engine import run_cycle
from src import data as data_mod
from src import journal as journal_mod
from src import store, backtest as bt, validation as val
from src import risk as risk_mod
from src import marketdata as md
from src import futures as fut_mod

REPORTS_DIR = Path(__file__).resolve().parent / "reports"

st.set_page_config(page_title="Trading App — Sandbox", layout="wide", page_icon="📈")


# --- Cache de datos: evita re-pedir precios/velas a la red en cada re-ejecución
#     de Streamlit. TTL corto para mantenerlo "casi en vivo". Usa el botón
#     Reload del navegador o cambia de símbolo para forzar refresco. ---
@st.cache_data(ttl=15, show_spinner=False)
def cached_price(symbol: str) -> float:
    return data_mod.current_price(symbol)


cfg = load_config()
pf = Portfolio.load()


@st.cache_data(ttl=300, show_spinner=False)
def _available_markets() -> list[dict]:
    """Mercados con histórico local: cripto CCXT (1h/4h) + multi-mercado yfinance (1d)."""
    out = []
    for s in ["BTC/USDT", "ETH/USDT"]:
        if not store.load_ohlcv(s, "1h").empty:
            out.append({"sym": s, "label": f"{s} (cripto)", "tfs": ["1h", "4h"]})
    for s in md.UNIVERSE:
        if not store.load_ohlcv(s, "1d").empty:
            out.append({"sym": s, "label": f"{md.label(s)} ({s})", "tfs": ["1d"]})
    return out or [{"sym": "BTC/USDT", "label": "BTC/USDT (cripto)", "tfs": ["1h", "4h"]}]


def _load_tf(symbol: str, tf: str) -> pd.DataFrame:
    if "/" in symbol:                                   # cripto CCXT: base 1h local
        base = store.load_ohlcv(symbol, "1h")
        return base if tf == "1h" else store.resample_ohlcv(base, tf)
    return store.load_ohlcv(symbol, tf)                 # yfinance: diario


def _ppy_for(symbol: str, tf: str) -> float | None:
    """Anualización por clase de activo en diario; en intradía vale el default por timeframe."""
    return md.periods_per_year(symbol, tf) if tf == "1d" else None


# --- Ciclo automático EN-APP: corre solo mientras el dashboard está abierto. ---
# Sustituye a la tarea programada del SO: cero consumo con la app cerrada, y se
# pausa desde la propia UI (toggle) o con el kill-switch del sidebar.
LAST_CYCLE_PATH = Path(__file__).resolve().parent / "state" / "last_cycle.json"


def _last_cycle_ts() -> float:
    try:
        return float(json.loads(LAST_CYCLE_PATH.read_text(encoding="utf-8"))["ts"])
    except Exception:
        return 0.0


def _mark_cycle_ts(ts: float) -> None:
    LAST_CYCLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_CYCLE_PATH.write_text(json.dumps({"ts": ts}), encoding="utf-8")


@st.fragment(run_every="60s")
def _auto_cycle_tick():
    """Tic periódico (solo refresca este fragmento, no toda la app). Si el ciclo
    automático está activo y ya tocó por intervalo, corre UNA pasada del engine."""
    import time as _t
    c = load_config()
    if not c["schedule"].get("app_auto"):
        st.caption("⏸️ Ciclo automático en-app apagado. Actívalo arriba: correrá solo "
                   "mientras esta app esté abierta.")
        return
    every_s = max(int(c["schedule"].get("app_every_min", 60)), 1) * 60
    now = _t.time()
    elapsed = now - _last_cycle_ts()
    if elapsed >= every_s:
        _mark_cycle_ts(now)              # marcar ANTES de correr: evita dobles pasadas
        res = run_cycle(c, Portfolio.load())
        st.session_state["last_result"] = res
        st.session_state["last_auto_at"] = _t.strftime("%H:%M:%S")
        st.rerun(scope="app")            # refrescar propuestas/portfolio en toda la app
    else:
        remaining = int((every_s - elapsed) / 60) + 1
        prev = st.session_state.get("last_auto_at")
        st.caption(f"⏱️ Ciclo automático ACTIVO mientras la app esté abierta · próxima "
                   f"pasada en ~{remaining} min" + (f" · última: {prev}" if prev else "") +
                   ". Al cerrar la app no corre nada.")


# --- Gráficas estilo app de mercado (Plotly): zoom con la barra de herramientas
#     (lupa, +/-, autoescala, pan) y SIN captura de la rueda del ratón (scrollZoom off),
#     así la página hace scroll normal. Colores verde/rojo estándar de trading. ---
_UP, _DOWN, _BLUE = "#26a69a", "#ef5350", "#2962ff"
_PLOTLY_CFG = {"scrollZoom": False, "displaylogo": False, "locale": "es",
               "modeBarButtonsToRemove": ["lasso2d", "select2d"]}


def _candles_fig(d: pd.DataFrame, max_bars: int = 300) -> go.Figure:
    """Velas japonesas + volumen (subgráfico), con selector de rango temporal."""
    d = d.tail(max_bars)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.78, 0.22], vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(
        x=d["ts"], open=d["open"], high=d["high"], low=d["low"], close=d["close"],
        name="OHLC", increasing_line_color=_UP, decreasing_line_color=_DOWN,
        increasing_fillcolor=_UP, decreasing_fillcolor=_DOWN), row=1, col=1)
    vcolors = [_UP if c >= o else _DOWN for o, c in zip(d["open"], d["close"])]
    fig.add_trace(go.Bar(x=d["ts"], y=d["volume"], marker_color=vcolors,
                         opacity=0.5, name="Volumen"), row=2, col=1)
    fig.update_layout(
        template="plotly_white", height=520, margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False, dragmode="pan", xaxis_rangeslider_visible=False,
        xaxis=dict(rangeselector=dict(buttons=[
            dict(count=1, label="1d", step="day", stepmode="backward"),
            dict(count=7, label="1sem", step="day", stepmode="backward"),
            dict(count=1, label="1mes", step="month", stepmode="backward"),
            dict(count=6, label="6m", step="month", stepmode="backward"),
            dict(step="all", label="todo")])))
    fig.update_yaxes(title_text=None)
    return fig


def _equity_dd_fig(eq: pd.Series, dd: pd.Series) -> go.Figure:
    """Curva de equity + drawdown enlazados (zoom/pan conjunto con la barra superior)."""
    x = np.arange(len(eq))
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3],
                        vertical_spacing=0.06,
                        subplot_titles=("Curva de equity (capital relativo, base 1.0)",
                                        "Drawdown"))
    fig.add_trace(go.Scatter(x=x, y=eq, mode="lines", name="Equity",
                             line=dict(color=_BLUE, width=1.6)), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=dd, mode="lines", name="Drawdown",
                             line=dict(color=_DOWN, width=1), fill="tozeroy",
                             fillcolor="rgba(239,83,80,0.25)"), row=2, col=1)
    fig.update_layout(template="plotly_white", height=480, showlegend=False,
                      margin=dict(l=10, r=10, t=30, b=10), dragmode="pan")
    fig.update_xaxes(title_text="vela", row=2, col=1)
    return fig

# ------------------------------------------------------------------ Sidebar (menú + estado)
PAGES = ["🔬 Backtest & Validación", "🧭 Decisiones & Research", "🛡️ Riesgo",
         "💼 Portfolio", "🔄 Ciclo", "📊 Mercado", "📓 Diario", "🔌 Conexiones",
         "⚙️ Configuración"]

with st.sidebar:
    st.markdown("## 📈 Trading App")
    page = st.radio("Menú", PAGES, key="nav_page", label_visibility="collapsed")
    st.divider()
    st.markdown("#### 📟 Estado")
    st.markdown(f"**Modo:** `{cfg.get('mode', 'recomendacion')}`")
    ks = st.toggle("Automatización activa (kill-switch)", value=bool(cfg.get("enabled", False)),
                   key="sb_killswitch",
                   help="Interruptor de emergencia: apágalo y el ciclo deja de operar al instante.")
    if bool(ks) != bool(cfg.get("enabled", False)):     # guardar al vuelo (es el botón de pánico)
        fresh = load_config()
        fresh["enabled"] = bool(ks)
        save_config(fresh)
        cfg["enabled"] = bool(ks)
    auto_on = bool(cfg["schedule"].get("app_auto", False))
    every = int(cfg["schedule"].get("app_every_min", 60))
    st.caption(("⏱️ Ciclo en-app: **activo** cada "
                f"{every} min (con la app abierta)" if auto_on else "⏱️ Ciclo en-app: apagado")
               + " · " + ("🟢 operando en paper" if cfg.get("enabled") else "⏸️ sin operar"))
    st.divider()
    st.caption("Toda la configuración vive en **⚙️ Configuración** (menú).")

# ------------------------------------------------------------------ Header
st.title("📈 Trading App — Sandbox de research y simulación")
st.warning(
    "**Herramienta de análisis, no asesoría financiera.** La validación walk-forward "
    "out-of-sample mostró que las estrategias incluidas (momentum, reversión) **no tienen "
    "edge demostrado** neto de costes en BTC/ETH a 1h/4h. Úsala para backtestear, validar y "
    "simular con honestidad. La ejecución real está **congelada** por diseño.")
prices = {s: cached_price(s) for s in cfg.get("symbols", [])}
equity = pf.equity(prices)
unreal = pf.unrealized(prices)
m = journal_mod.metrics()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Efectivo", f"{pf.cash:,.2f} {pf.base_currency}")
c2.metric("Equity (valor total)", f"{equity:,.2f}")
c3.metric("PnL no realizado", f"{unreal:,.2f}")
c4.metric("PnL realizado", f"{pf.realized_pnl:,.2f}")
c5.metric("Win rate", f"{m['win_rate']}%  ({m['trades']} ops)")

# El tick del ciclo automático corre SIEMPRE (independiente de la sección activa):
# con menú lateral solo se renderiza una sección, y el ciclo no puede depender de
# que el usuario esté mirando la de Ciclo.
_auto_cycle_tick()

st.markdown(f"### {page}")

# ------------------------------------------------------------------ Backtest
if page == "🔬 Backtest & Validación":
    st.subheader("Backtest honesto + validación out-of-sample")
    st.caption("Costes 0.1% fee + 0.05% slippage · señal aplicada a la vela siguiente (sin "
               "look-ahead). El backtest es in-sample (optimista); la validación OOS es el juez real.")
    markets = _available_markets()
    c1b, c2b, c3b = st.columns(3)
    msel = c1b.selectbox("Mercado", markets, format_func=lambda m: m["label"], key="bt_sym")
    bsym = msel["sym"]
    btf = c2b.radio("Timeframe", msel["tfs"], horizontal=True, key=f"bt_tf_{bsym}")
    strat = c3b.selectbox("Estrategia", ["Baseline momentum", "Histéresis (banda muerta)",
                                         "Reversión a la media", "Velas japonesas (patrones)"],
                          key="bt_strat")
    ppy = _ppy_for(bsym, btf)

    # Parámetros y rejilla de validación según la familia elegida
    if strat == "Histéresis (banda muerta)":
        enter = st.slider("Umbral de entrada (convicción)", 0.50, 0.75, 0.60, 0.05)
        sig_fn = lambda d: bt.hysteresis_signal(d, enter=enter, exit_=0.50)
        grid = [(f"enter={e:.2f}", (lambda d, e=e: bt.hysteresis_signal(d, enter=e)))
                for e in (0.55, 0.60, 0.65, 0.70)]
    elif strat == "Reversión a la media":
        cz = st.columns(3)
        lb = cz[0].select_slider("Lookback", [10, 20, 50], 20)
        ez = cz[1].select_slider("Entrada z", [1.5, 2.0, 2.5], 2.0)
        xz = cz[2].select_slider("Salida z", [0.0, 0.5, 1.0], 0.5)
        sig_fn = lambda d: bt.mean_reversion_signal(d, lookback=lb, entry_z=ez, exit_z=xz)
        grid = [(f"lb{l}/in{e}/out{x}",
                 (lambda d, l=l, e=e, x=x: bt.mean_reversion_signal(d, lookback=l, entry_z=e, exit_z=x)))
                for l in (20, 50) for e in (1.5, 2.0, 2.5) for x in (0.0, 0.5)]
    elif strat == "Velas japonesas (patrones)":
        cz = st.columns(2)
        hd = cz[0].select_slider("Velas en posición (hold)", [3, 5, 10], 5)
        sp = cz[1].select_slider("EMA de contexto", [20, 50], 20)
        sig_fn = lambda d: bt.candlestick_signal(d, hold=hd, trend_span=sp)
        grid = [(f"hold{h}/ema{s}",
                 (lambda d, h=h, s=s: bt.candlestick_signal(d, hold=h, trend_span=s)))
                for h in (3, 5, 10) for s in (20, 50)]
        st.caption("Envolventes + martillo + estrella fugaz con contexto de tendencia. Validado OOS: "
                   "0/6 mercados con ΔSharpe>0 vs buy & hold (ver pestaña Decisiones & Research).")
    else:
        sig_fn = bt.baseline_signal
        grid = [("baseline", bt.baseline_signal)]

    lev_bt = st.select_slider(
        "Apalancamiento (simulación de futuros: funding 0.01%/8h + liquidación intrabar)",
        [1, 2, 3, 5], 1, key="bt_lev",
        help="1 = spot (como siempre). >1 simula un perpetuo: multiplica PnL y costes, "
             "y una mecha adversa puede LIQUIDAR la cuenta. La validación OOS siempre corre a 1×.")

    cga, cgb, cgc = st.columns([2, 2, 1])
    run_bt = cga.button("▶️ Ejecutar backtest", type="primary", width="stretch")
    run_oos = cgb.button("🔬 Validar out-of-sample", width="stretch")
    if cgc.button("🧹 Limpiar", width="stretch"):
        st.session_state.pop("bt_result", None)
        st.session_state.pop("oos_result", None)

    label = f"{msel['label']} · {btf} · {strat}"
    # Se guarda cada resultado en session_state y se renderiza SIEMPRE, así el
    # backtest y la validación conviven en pantalla (una pulsación no borra la otra).
    if run_bt:
        df = _load_tf(bsym, btf)
        if df.empty:
            st.session_state["bt_result"] = {"error": "Sin datos locales. Cripto: "
                "`python backtest.py --fresh --download 17520` · Multi-mercado: `python cross_asset.py`"}
        elif lev_bt > 1:                                   # simulación de futuros
            rf = fut_mod.simulate_futures(df, btf, sig_fn, leverage=lev_bt, ppy=ppy)
            eq = rf["equity"].reset_index(drop=True)
            st.session_state["bt_result"] = {"label": f"{label} · {lev_bt}× futuros",
                                             "fut": rf["metrics"], "liq_bar": rf["liq_bar"],
                                             "equity": eq, "drawdown": eq / eq.cummax() - 1}
        else:
            r = bt.run_backtest(df, btf, signal_fn=sig_fn, ppy=ppy)
            eq = r["equity"].reset_index(drop=True)
            st.session_state["bt_result"] = {"label": label, "m": r["metrics"],
                                             "equity": eq, "drawdown": eq / eq.cummax() - 1}
    if run_oos:
        df = _load_tf(bsym, btf)
        if df.empty:
            st.session_state["oos_result"] = {"error": "Sin datos locales para validar."}
        elif len(df) < 400:
            st.session_state["oos_result"] = {"error": "Pocos datos para una validación OOS fiable."}
        else:
            with st.spinner(f"Walk-forward anclado sobre {len(grid)} combo(s)…"):
                res = val.walk_forward_oos(df, grid, symbol=bsym, timeframe=btf,
                                           min_train_trades=5 if btf == "1d" else 10, ppy=ppy)
            st.session_state["oos_result"] = {"label": label, "res": res}

    # --- Render persistente de ambos resultados ---
    btr = st.session_state.get("bt_result")
    if btr:
        with st.expander(f"📈 Backtest — {btr.get('label', '')}", expanded=True):
            if btr.get("error"):
                st.error(btr["error"])
            elif btr.get("fut"):                            # resultado en modo futuros
                fm = btr["fut"]
                k = st.columns(4)
                k[0].metric("Retorno total", f"{fm['total_return']:.2%}")
                k[1].metric("Sharpe (pre-liq.)", fm["sharpe"])
                k[2].metric("Max drawdown", f"{fm['max_drawdown']:.2%}")
                k[3].metric("Apalancamiento", f"{fm['leverage']:g}×")
                if fm["liquidated"]:
                    st.error(f"💀 **CUENTA LIQUIDADA** en la vela {btr['liq_bar']}: una mecha "
                             "adversa superó el margen. A partir de ahí no hay recuperación: "
                             "la cuenta queda a cero.")
                st.plotly_chart(_equity_dd_fig(btr["equity"], btr["drawdown"]),
                                width="stretch", config=_PLOTLY_CFG)
                st.caption("Incluye funding 0.01%/8h y liquidación intrabar. Compara con 1× "
                           "para ver el efecto puro del apalancamiento.")
            else:
                m = btr["m"]
                k = st.columns(4)
                k[0].metric("Retorno total", f"{m.total_return:.2%}")
                k[1].metric("Sharpe", m.sharpe)
                k[2].metric("Max drawdown", f"{m.max_drawdown:.2%}")
                k[3].metric("Trades", m.trades)
                k2 = st.columns(4)
                k2[0].metric("Win rate", f"{m.win_rate}%")
                k2[1].metric("Profit factor", m.profit_factor)
                k2[2].metric("Coste acumulado", f"{m.cost_drag:.1%}")
                k2[3].metric("Velas", m.bars)
                st.plotly_chart(_equity_dd_fig(btr["equity"], btr["drawdown"]),
                                width="stretch", config=_PLOTLY_CFG)
                st.caption("Zoom: lupa o ＋/− de la barra superior · arrastra para desplazarte · "
                           "🏠 restaura. La rueda del ratón no mueve la gráfica.")

    oosr = st.session_state.get("oos_result")
    if oosr:
        with st.expander(f"🔬 Validación OOS — {oosr.get('label', '')}", expanded=True):
            if oosr.get("error"):
                st.error(oosr["error"])
            else:
                res = oosr["res"]
                v = val.verdict(res)
                (st.success if v.startswith("✅") else
                 st.warning if v.startswith("⚠") else st.error)(v)
                k = st.columns(3)
                k[0].metric("OOS retorno (año 2)", f"{res.oos_return:.2%}")
                k[1].metric("OOS Sharpe", res.oos_sharpe)
                k[2].metric("Buy & hold", f"{res.bh_return:.2%}")
                st.markdown("\n".join(val.to_markdown(res)))

# ------------------------------------------------------------------ Decisiones & Research
if page == "🧭 Decisiones & Research":
    st.subheader("📌 Qué dice la evidencia (decisiones soportadas por los tests)")
    st.caption("Resumen honesto de TODO el research validado out-of-sample. No es asesoría "
               "financiera: es lo que los datos del sandbox soportan y lo que no.")

    st.markdown("#### Las 4 conclusiones validadas")
    cc = st.columns(2)
    with cc[0]:
        st.error("**1 · Ninguna estrategia técnica tiene edge demostrado.** Momentum, reversión, "
                 "filtro ADX, ranking market-neutral y patrones de velas fueron validados "
                 "walk-forward OOS en hasta 16 mercados: el mejor resultado es indistinguible "
                 "del azar (nulas empíricas p=0.97 direccional, p=0.59 neutral, 0/6 velas).")
        st.warning("**2 · Lo único robusto: overlay DEFENSIVO.** Las señales técnicas batieron a "
                   "comprar-y-aguantar en el **74%** de los tramos bajistas pero solo en el **9%** "
                   "de los alcistas. Sirven para *reducir drawdown en caídas*, no para generar alfa.")
    with cc[1]:
        st.info("**3 · El coste es el enemigo silencioso.** La media de los Sharpe-por-fold OOS es "
                "**−0.12**: tras fees+slippage estas estrategias rinden ligeramente bajo cero. "
                "Operar menos (timeframes lentos, histéresis) mejoró TODAS las métricas.")
        st.success("**4 · Las decisiones de menor probabilidad de pérdida** (según el sandbox): "
                   "arriesgar ≤1% del equity por trade · kill-switch de pérdida diaria · "
                   "no concentrar posiciones correlacionadas (BTC/ETH ≈ 0.82) · y **si Kelly = 0 "
                   "(sin edge), la talla óptima de apuesta es NO apostar** — que es exactamente "
                   "lo que la evidencia indica aquí.")

    # --- Tabla por mercado desde el JSON del estudio cross-asset ---
    ca_path = REPORTS_DIR / "cross_asset_results.json"
    if ca_path.exists():
        st.markdown("#### Por mercado (estudio cross-asset, OOS 2022→2026)")
        st.caption("ΔSharpe = estrategia − buy & hold (riesgo-ajustado). El 'mejor' mercado para "
                   "estas técnicas sigue sin ser distinguible del azar; los B&H altos reflejan "
                   "una década alcista, no una predicción.")
        data = json.loads(ca_path.read_text(encoding="utf-8"))
        rows = [{"Mercado": r["label"], "Clase": r["clase"],
                 "Sharpe estrategia (OOS)": r["oos_sharpe"], "Sharpe B&H": r["bh_sharpe"],
                 "ΔSharpe": r["excess_sharpe"], "MaxDD estrategia": f"{r['oos_maxdd']:.0%}",
                 "Replicable": "sí" if r.get("replicable", True) else "no (futuro continuo)"}
                for r in data["results"]]
        st.dataframe(pd.DataFrame(rows).sort_values("ΔSharpe", ascending=False),
                     width="stretch", hide_index=True)
        s = data.get("stats", {})
        if s:
            st.caption(f"Estadística honesta: p-valor del líder vs azar = {s.get('null_p_leader')} · "
                       f"batir B&H en folds bajistas {s.get('beat_bh_down_folds', 0):.0%} vs alcistas "
                       f"{s.get('beat_bh_up_folds', 0):.0%} · el test solo descarta edges con Sharpe "
                       f"≳ {s.get('sharpe_detectable')} (potencia limitada).")
    else:
        st.caption("Genera el estudio multi-mercado con `python cross_asset.py`.")

    st.divider()
    st.subheader("🧪 Informes de research (validación OOS)")
    REPORT_INDEX = [
        ("futures.md", "Futuros paper: efecto del apalancamiento (1×-5×, funding y liquidación)"),
        ("cross_asset.md", "Cross-asset: 16 mercados, momentum+reversión direccional"),
        ("cross_sectional.md", "Market-neutral: prueba limpia alfa-vs-beta (riesgo-neutral)"),
        ("candlestick.md", "Patrones de velas japonesas: validación OOS"),
        ("phase3_validation.md", "Momentum cripto 4h: walk-forward OOS"),
        ("phase3_meanrev.md", "Reversión a la media cripto: walk-forward OOS"),
        ("phase3_regime.md", "Filtro de régimen ADX: barrido"),
        ("phase3_sweep.md", "Histéresis vs baseline: barrido"),
    ]
    avail = [(f, desc) for f, desc in REPORT_INDEX if (REPORTS_DIR / f).exists()]
    if avail:
        rsel = st.selectbox("Informe", avail, format_func=lambda x: x[1], key="rep_sel")
        st.markdown((REPORTS_DIR / rsel[0]).read_text(encoding="utf-8"))
    else:
        st.caption("Aún no hay informes en reports/.")

# ------------------------------------------------------------------ Riesgo
if page == "🛡️ Riesgo":
    st.subheader("Gestión de riesgo")
    st.caption("Calculadoras informativas sobre tu portfolio simulado. Información técnica, "
               "no asesoría financiera.")
    jm = journal_mod.metrics()                       # métricas frescas (no depender de `m`)

    # --- 1) Tamaño de posición ---
    st.markdown("#### 1) Tamaño de posición")
    cs = st.columns(2)
    with cs[0]:
        st.markdown("**Riesgo fijo** — arriesgar X% del equity con stop")
        eq_in = st.number_input("Equity", min_value=0.0,
                                value=float(round(equity, 2)) or 1000.0, step=100.0, key="rk_eq")
        rp = st.number_input("Riesgo por trade (%)", 0.0, 100.0, 1.0, 0.25, key="rk_rp")
        ent = st.number_input("Precio de entrada", min_value=0.0, value=100.0, key="rk_ent")
        stp = st.number_input("Stop", min_value=0.0, value=95.0, key="rk_stp")
        sr = risk_mod.size_from_risk(eq_in, rp, ent, stp)
        if sr["qty"] > 0:
            st.write(f"Cantidad: **{sr['qty']:.6f}** · Notional: **{sr['notional']:,.2f}** · "
                     f"Apalancamiento implícito: **{sr['leverage']:.2f}×**")
            if sr["leverage"] > 1:
                st.warning("Apalancamiento >1×: el stop está muy cerca → posición grande para "
                           "ese 'bajo riesgo'. Un gap puede saltarlo y perder más de lo previsto.")
        else:
            st.info(sr["reason"])
    with cs[1]:
        st.markdown("**Kelly fraccionario** (≤ ½ Kelly)")
        wr_def = (jm.get("win_rate", 0) or 0) / 100.0 or 0.5
        wr = st.slider("Win rate (W)", 0.0, 1.0, float(wr_def), 0.01, key="rk_wr")
        rr = st.number_input("Ratio ganancia/pérdida (R)", min_value=0.0, value=1.5,
                             step=0.1, key="rk_rr")
        frac = st.slider("Fracción de Kelly", 0.0, 1.0, 0.5, 0.05, key="rk_frac")
        kf = risk_mod.kelly_fraction(wr, rr)
        fk = risk_mod.fractional_kelly(wr, rr, fraction=frac)
        st.write(f"Kelly completo: **{kf:.1%}** del equity · "
                 f"Kelly×{frac:.2f} (cap 20%): **{fk:.1%}** ≈ {fk * eq_in:,.2f}")
        if kf == 0:
            st.error("Kelly = 0: sin edge (W y R no compensan). La recomendación es NO apostar.")

    with st.expander("📐 Precio de liquidación (futuros paper)"):
        lc1, lc2, lc3 = st.columns(3)
        l_entry = lc1.number_input("Precio de entrada", min_value=0.01, value=100.0, key="lq_e")
        l_side = lc2.radio("Lado", ["long", "short"], horizontal=True, key="lq_s")
        l_lev = lc3.select_slider("Apalancamiento", [1, 2, 3, 5, 10], 3, key="lq_l")
        lp = fut_mod.liquidation_price(l_entry, l_side, l_lev)
        move = abs(lp - l_entry) / l_entry
        st.write(f"Liquidación ≈ **{lp:,.2f}** — un movimiento adverso del **{move:.1%}** "
                 f"aniquila la cuenta a {l_lev}×. (Cripto se mueve 3-5% en un día normal.)")

    st.divider()
    # --- 2) Stress test ---
    st.markdown("#### 2) Stress test — hueco de mercado")
    gp = st.slider("Shock de precio sobre todas las posiciones (%)", -50, 0, -20, 5, key="rk_gap") / 100.0
    if st.button("💥 Simular shock sobre el portfolio", width="stretch"):
        if not pf.positions:
            st.info("Sin posiciones abiertas: nada que estresar.")
        else:
            s = risk_mod.stress_test_gap(pf, prices, gp)
            ks = st.columns(3)
            ks[0].metric("Equity antes", f"{s['equity_before']:,.2f}")
            ks[1].metric("Equity después", f"{s['equity_after']:,.2f}", f"{s['change_pct']:.1%}")
            ks[2].metric("Cambio", f"{s['change']:,.2f}")
            st.dataframe(pd.DataFrame([
                {"Símbolo": r["symbol"], "Lado": r["side"], "Precio": round(r["price"], 2),
                 "Tras shock": round(r["shocked"], 2), "ΔPnL": round(r["pnl_change"], 2),
                 "Stop cruzado": "sí" if r["stop_hit"] else "no"} for r in s["positions"]]),
                width="stretch", hide_index=True)
            st.caption("Caso pesimista: asume que el hueco salta los stops (en gaps reales resbalan).")

    st.divider()
    # --- 3) Exposición y correlación ---
    st.markdown("#### 3) Exposición y correlación")
    ex = risk_mod.exposure(pf, prices)
    if ex["positions"]:
        ke = st.columns(2)
        ke[0].metric("Exposición bruta", f"{ex['gross_pct']:.0%} del equity")
        ke[1].metric("Exposición neta", f"{ex['net_pct']:.0%} del equity")
        st.dataframe(pd.DataFrame([
            {"Símbolo": r["symbol"], "Lado": r["side"], "Notional": round(r["notional"], 2),
             "% equity": f"{r['pct_equity']:.0%}"} for r in ex["positions"]]),
            width="stretch", hide_index=True)
    else:
        st.caption("Sin posiciones abiertas.")
    cmat = risk_mod.correlation_matrix(cfg.get("symbols", ["BTC/USDT", "ETH/USDT"]), "1h")
    if not cmat.empty:
        st.markdown("**Correlación de retornos (histórico local 1h)**")
        st.dataframe(cmat.round(2), width="stretch")
        st.caption("Correlaciones altas entre posiciones = diversificación ilusoria "
                   "(todo cae junto en un crash).")

# ------------------------------------------------------------------ Portfolio
if page == "💼 Portfolio":
    st.subheader("Agregar saldo simulado")
    col_a, col_b = st.columns([1, 3])
    amount = col_a.number_input("Monto", min_value=0.0, value=1000.0, step=100.0)
    if col_a.button("➕ Agregar saldo"):
        pf.deposit(amount)
        st.success(f"Agregado {amount:,.2f}. Recarga para ver el saldo.")
    col_b.info("En modo test el saldo es virtual, pero las operaciones usan precios reales "
               "del mercado para medir probabilidades y detectar problemas.")

    st.subheader("Posiciones abiertas")
    if pf.positions:
        rows = []
        for s, p in pf.positions.items():
            px = prices.get(s, p.entry)
            pnl = (px - p.entry) * p.qty if p.side == "long" else (p.entry - px) * p.qty
            rows.append({"Símbolo": s, "Lado": p.side, "Cantidad": round(p.qty, 6),
                         "Entrada": round(p.entry, 2), "Precio actual": round(px, 2),
                         "Stop": round(p.stop, 2), "Objetivo": round(p.take_profit, 2),
                         "Apal.": f"{p.leverage:g}×" if p.leverage > 1 else "spot",
                         "⚠ Liq.": round(p.liq_price, 2) if p.liq_price > 0 else "—",
                         "PnL": round(pnl, 2)})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        close_sym = st.selectbox("Cerrar posición", list(pf.positions.keys()))
        if st.button("Cerrar seleccionada"):
            fill = PaperBroker(pf).close(close_sym, prices.get(close_sym))
            journal_mod.log_trade({"symbol": close_sym, "evento": "close", "lado": fill.side,
                                   "qty": fill.qty, "precio": fill.price, "fee": fill.fee,
                                   "pnl": fill.note.split("pnl=")[-1], "modo": "manual"})
            st.success(f"Cerrada: {fill.note}")
    else:
        st.caption("Sin posiciones abiertas.")

# ------------------------------------------------------------------ Wallets
if page == "🔌 Conexiones":
    st.subheader("Conectar monederos y brokers")
    st.caption("En Fase 1 la conexión es para **testnet/paper**. Las claves se usan solo en tu "
               "máquina. Nunca uses claves con permiso de retiro.")
    cw, ce = st.columns(2)
    with cw:
        st.markdown("### 🪙 Cripto (Binance)")
        bk = st.text_input("API Key (testnet)", type="password", key="bk")
        bs = st.text_input("API Secret (testnet)", type="password", key="bs")
        if st.button("Probar conexión Binance"):
            try:
                LiveBroker("binance", bk, bs, testnet=True).connect()
                st.success("Conexión OK (testnet).")
            except Exception as e:
                st.warning(f"No se pudo conectar: {e}")
    with ce:
        st.markdown("### 📈 Acciones / ETF (Alpaca)")
        ak = st.text_input("API Key (paper)", type="password", key="ak")
        as_ = st.text_input("API Secret (paper)", type="password", key="as")
        st.button("Probar conexión Alpaca (pendiente integración)", disabled=True)
        st.caption("Integración Alpaca prevista; en Fase 1 se simula igual con precios reales.")
    st.info("Para operar REAL hace falta cambiar a modo auto_live (Fase 6) con aprobación explícita.")

# ------------------------------------------------------------------ Cycle
if page == "🔄 Ciclo":
    st.subheader("Correr ciclo (datos → predicción → riesgo → decisión)")
    st.warning("**Demo de simulación.** El forecast baseline NO tiene edge validado OOS y sus "
               "probabilidades NO están calibradas (skill negativo, ver abajo). Las propuestas "
               "son material de sandbox para ejercitar el flujo paper, no recomendaciones.")
    with st.expander("📏 Calibración del forecast (reliability curve) — por qué no fiarse del %"):
        from src import calibration as cal_mod

        @st.cache_data(ttl=3600, show_spinner=False)
        def _calibration(sym: str, tf: str):
            d = _load_tf(sym, tf)
            return cal_mod.reliability(d) if len(d) > 1000 else None

        csym = st.selectbox("Histórico", ["BTC/USDT", "ETH/USDT"], key="cal_sym")
        ctf = st.radio("Timeframe", ["1h", "4h"], horizontal=True, key="cal_tf")
        rcal = _calibration(csym, ctf)
        if rcal is None:
            st.caption("Sin histórico local suficiente para calibrar.")
        else:
            (st.error if rcal["skill"] <= 0 else st.warning)(cal_mod.verdict(rcal))
            st.dataframe(rcal["table"], width="stretch", hide_index=True)
            st.caption("Calibrado = la columna 'frec. observada' sigue a 'prob. predicha'. "
                       "Aquí no lo hace: la frecuencia real se queda pegada a ~50% diga lo "
                       "que diga el modelo. Por eso Kelly con estas probabilidades sería ruina.")

            @st.cache_data(ttl=3600, show_spinner=False)
            def _wf_cal(sym: str, tf: str):
                d = _load_tf(sym, tf)
                return cal_mod.walkforward_calibration(d) if len(d) > 1000 else None

            rc = _wf_cal(csym, ctf)
            if rc and "error" not in rc:
                st.markdown("**¿Y si re-calibramos?** (Platt scaling: el mapa score→probabilidad "
                            "se re-aprende con la 1ª mitad del histórico y se evalúa en la 2ª)")
                cc = st.columns(3)
                cc[0].metric("Skill crudo", f"{rc['skill_raw']:+.2%}")
                cc[1].metric("Skill calibrado", f"{rc['skill_cal']:+.2%}")
                cc[2].metric("Prob. calibrada (todas)", f"{rc['cal_prob_media']:.0%} ± {rc['cal_prob_std']:.1%}")
                st.info("Calibrar **repara la mentira** (el skill vuelve a ≈0) pero **revela la "
                        "verdad**: el modelo calibrado dice '~50%' siempre — es decir, *no sé*. "
                        "La calibración no crea conocimiento, solo deja de inventarlo. Un ciclo "
                        "que usara la probabilidad calibrada no operaría nunca: esa ES la "
                        "recomendación estadísticamente honesta de este forecast.")

    cyc_auto = st.toggle("⏱️ Ciclo automático mientras la app esté abierta",
                         value=bool(cfg["schedule"].get("app_auto", False)), key="cyc_auto",
                         help="Corre solo con el dashboard abierto; al cerrarlo, cero consumo. "
                              "La frecuencia se ajusta en ⚙️ Configuración. Respeta el kill-switch.")
    if bool(cyc_auto) != bool(cfg["schedule"].get("app_auto", False)):
        fresh = load_config()                      # persistir SOLO esta clave
        fresh["schedule"]["app_auto"] = bool(cyc_auto)
        save_config(fresh)
        cfg["schedule"]["app_auto"] = bool(cyc_auto)

    if st.button("▶️ Ejecutar una pasada", type="primary"):
        result = run_cycle(cfg, pf)
        st.session_state["last_result"] = result

    result = st.session_state.get("last_result")
    if result:
        if not result["ok"]:
            st.warning(result["reason"])
        for prop in result["proposals"]:
            f = prop["forecast"]
            with st.container(border=True):
                cols = st.columns([2, 2, 2, 2, 2])
                cols[0].markdown(f"**{prop['symbol']}**")
                cols[1].markdown(f"Acción: `{prop['action']}` {prop.get('side','')}")
                cols[2].markdown(f"Dir: **{f['direction']}**  ({f['probability']:.0%})")
                cols[3].markdown(f"Confianza: {f['confidence']:.2f}")
                cols[4].markdown(f"Precio: {prop['price']:.2f}")
                if prop["note"]:
                    st.caption(prop["note"])
                # Aprobación manual en modo recomendación
                if prop["action"] == "abrir" and not prop["executed"] and cfg["mode"] == "recomendacion":
                    rd = prop["risk"]
                    st.caption(f"Propuesta: {prop['side']} {rd.get('qty',0):.6f} | "
                               f"stop {rd.get('stop_price',0):.2f} | objetivo {rd.get('take_profit',0):.2f}")
                    if st.button(f"✅ Aprobar y ejecutar {prop['symbol']}", key=f"ap_{prop['symbol']}"):
                        fill = PaperBroker(pf).open(prop["symbol"], prop["side"], rd["qty"],
                                                    prop["price"], rd["stop_price"], rd["take_profit"])
                        journal_mod.log_trade({"symbol": prop["symbol"], "evento": "open",
                                               "lado": prop["side"], "qty": fill.qty,
                                               "precio": fill.price, "fee": fill.fee,
                                               "prob": round(f["probability"], 3),
                                               "confianza": round(f["confidence"], 3), "modo": "aprobado"})
                        st.success(f"Ejecutado: {prop['side']} {prop['symbol']}")
                elif prop["executed"]:
                    st.success("Ejecutado automáticamente.")

# ------------------------------------------------------------------ Market
if page == "📊 Mercado":
    st.subheader("Mercado")
    mkts = _available_markets()
    mc1, mc2, mc3 = st.columns([2, 1, 1])
    mket = mc1.selectbox("Mercado", mkts, format_func=lambda m: m["label"], key="mkt_sym")
    mtf = mc2.radio("Timeframe", mket["tfs"], horizontal=True, key=f"mkt_tf_{mket['sym']}")
    nbars = mc3.select_slider("Velas", [150, 300, 600, 1000], 300, key="mkt_nbars")
    dfm = _load_tf(mket["sym"], mtf)
    if dfm.empty:
        st.info("Sin histórico local de este mercado. Descárgalo: cripto con "
                "`python backtest.py --fresh --download 17520` · resto con `python cross_asset.py`.")
    else:
        last, prev = float(dfm["close"].iloc[-1]), float(dfm["close"].iloc[-2])
        k1, k2, k3 = st.columns(3)
        k1.metric(mket["label"], f"{last:,.2f}", f"{last / prev - 1:+.2%}")
        if "/" in mket["sym"]:                              # cripto: precio vivo de Binance
            k2.metric("Precio en vivo (Binance)", f"{cached_price(mket['sym']):,.2f}")
        k3.metric("Última vela local", str(dfm["ts"].iloc[-1])[:16])
        st.plotly_chart(_candles_fig(dfm, nbars), width="stretch", config=_PLOTLY_CFG)
        st.caption("Velas japonesas + volumen · usa los botones 1d/1sem/1mes/6m/todo o la lupa "
                   "y ＋/− de la barra para enfocar tramos; la rueda del ratón no mueve la gráfica. "
                   "Histórico local — refréscalo con los comandos de descarga.")

# ------------------------------------------------------------------ Journal
if page == "📓 Diario":
    st.subheader("Diario de operaciones")
    jp = journal_mod.JOURNAL_PATH
    if jp.exists():
        st.dataframe(pd.read_csv(jp), width="stretch", hide_index=True)
        mm = journal_mod.metrics()
        st.write(f"**Trades:** {mm['trades']} · **Win rate:** {mm['win_rate']}% · "
                 f"**PnL total:** {mm['pnl_total']} · Ganadoras {mm['wins']} / Perdedoras {mm['losses']}")
    else:
        st.caption("Aún no hay operaciones registradas.")

# ------------------------------------------------------------------ Configuración
if page == "⚙️ Configuración":
    st.subheader("⚙️ Configuración")
    st.caption("Todos los ajustes en un solo sitio. Los cambios se aplican al pulsar **Guardar**. "
               "El kill-switch de emergencia vive en la barra lateral.")
    _FREQS = [("Cada 5 min", 5), ("Cada 15 min", 15), ("Cada 30 min", 30),
              ("Cada hora", 60), ("Cada 4 horas", 240), ("Cada 12 horas", 720)]
    cur_min = int(cfg["schedule"].get("app_every_min", 60))
    freq_idx = min(range(len(_FREQS)), key=lambda i: abs(_FREQS[i][1] - cur_min))

    with st.form("cfg_form"):
        st.markdown("#### Ciclo de simulación")
        c1f, c2f = st.columns(2)
        f_mode = c1f.selectbox(
            "Modo", ["recomendacion", "auto_testnet"],
            index=1 if cfg.get("mode") == "auto_testnet" else 0,
            help="recomendacion: propone y espera tu aprobación · auto_testnet: ejecuta en paper. "
                 "(auto_live está congelado por diseño: sin edge OOS demostrado.)")
        f_freq = c2f.selectbox("Frecuencia del ciclo automático", [f[0] for f in _FREQS],
                               index=freq_idx,
                               help="Cada cuánto corre el ciclo mientras la app está abierta. "
                                    "Sin cron ni formatos crípticos.")
        f_auto = st.toggle("Ciclo automático mientras la app esté abierta",
                           value=bool(cfg["schedule"].get("app_auto", False)),
                           help="Igual que el toggle de la pestaña Ciclo; al cerrar la app no corre nada.")
        f_syms = st.text_input("Símbolos del ciclo (separados por coma)",
                               ", ".join(cfg.get("symbols", [])),
                               help="Pares cripto que evalúa cada pasada, p.ej. BTC/USDT, ETH/USDT")

        st.markdown("#### Predicción")
        f_conf = st.slider("Confianza mínima para proponer/operar", 0.0, 1.0,
                           float(cfg["forecast"].get("min_confidence", 0.6)), 0.05,
                           help="OJO: la 'confianza' del baseline está descalibrada (skill negativo). "
                                "Valores altos ≈ el ciclo casi nunca opera; es un umbral de demo.")

        st.markdown("#### Límites de riesgo (paper)")
        r1, r2, r3 = st.columns(3)
        f_per_trade = r1.number_input("Riesgo por trade (%)", 0.1, 10.0,
                                      float(cfg["risk"].get("max_per_trade_pct", 1.0)), 0.1)
        f_daily = r2.number_input("Pérdida diaria máx. (%)", 0.5, 20.0,
                                  float(cfg["risk"].get("max_daily_loss_pct", 3.0)), 0.5,
                                  help="Al alcanzarla, el kill-switch se apaga solo.")
        f_maxpos = r3.number_input("Posiciones abiertas máx.", 1, 10,
                                   int(cfg["risk"].get("max_open_positions", 3)), 1)

        st.markdown("#### Futuros (paper) — apalancamiento simulado")
        fut_cfg = cfg.get("futures", {})
        fu1, fu2, fu3 = st.columns([1, 1, 1])
        f_fut_on = fu1.toggle("Modo futuros", value=bool(fut_cfg.get("enabled", False)),
                              help="El ciclo abre posiciones apalancadas con funding y "
                                   "precio de liquidación. SOLO simulación.")
        f_lev = fu2.select_slider("Apalancamiento", [1, 2, 3, 5],
                                  int(fut_cfg.get("leverage", 2)))
        f_funding = fu3.number_input("Funding %/8h", 0.0, 0.2,
                                     float(fut_cfg.get("funding_8h_pct", 0.01)), 0.01,
                                     help="Los largos pagan, los cortos cobran. Típico: 0.01%.")
        st.caption("⚠️ El research midió qué hace el apalancamiento sin edge: BTC −23% a 1× "
                   "pasa a −99% a 5×; ETH buy&hold a 5× acaba **liquidado** "
                   "(ver informe 'Futuros' en Decisiones & Research).")

        saved = st.form_submit_button("💾 Guardar configuración", type="primary",
                                      width="stretch")
    if saved:
        fresh = load_config()
        fresh["mode"] = f_mode
        fresh["symbols"] = [s.strip() for s in f_syms.split(",") if s.strip()]
        fresh["schedule"]["app_auto"] = bool(f_auto)
        fresh["schedule"]["app_every_min"] = dict(_FREQS)[f_freq]
        fresh["forecast"]["min_confidence"] = float(f_conf)
        fresh["risk"]["max_per_trade_pct"] = float(f_per_trade)
        fresh["risk"]["max_daily_loss_pct"] = float(f_daily)
        fresh["risk"]["max_open_positions"] = int(f_maxpos)
        fresh["futures"]["enabled"] = bool(f_fut_on)
        fresh["futures"]["leverage"] = int(f_lev)
        fresh["futures"]["funding_8h_pct"] = float(f_funding)
        save_config(fresh)
        st.success("Configuración guardada.")
        st.rerun()

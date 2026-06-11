"""Dashboard — Trading App (sandbox de research y simulación)

Ejecutar:   streamlit run dashboard.py

Herramienta HONESTA: backtesting con costes, validación walk-forward out-of-sample,
journal, paper trading con precios reales y gestión de riesgo. NO promete rentabilidad
—la validación OOS mostró que las estrategias incluidas no tienen edge demostrado.
"""
from __future__ import annotations
import json
from pathlib import Path
import altair as alt
import numpy as np
import pandas as pd
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

REPORTS_DIR = Path(__file__).resolve().parent / "reports"

st.set_page_config(page_title="Trading App — Sandbox", layout="wide", page_icon="📈")


# --- Cache de datos: evita re-pedir precios/velas a la red en cada re-ejecución
#     de Streamlit. TTL corto para mantenerlo "casi en vivo". Usa el botón
#     Reload del navegador o cambia de símbolo para forzar refresco. ---
@st.cache_data(ttl=15, show_spinner=False)
def cached_price(symbol: str) -> float:
    return data_mod.current_price(symbol)


@st.cache_data(ttl=30, show_spinner=False)
def cached_ohlcv(symbol: str, timeframe: str = "1h", limit: int = 200):
    res = data_mod.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    return res.df, res.source

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


def _zoom_chart(series: pd.Series, key: str, title: str, area: bool = False,
                extra: pd.Series | None = None, extra_title: str = "") -> None:
    """Gráfica Altair ESTÁTICA (no captura la rueda del ratón al hacer scroll) con
    controles de zoom: ➕ acerca, ➖ aleja, ⟲ resetea, y un slider para enfocar tramos.
    Si se pasa `extra`, se dibuja una segunda gráfica con el MISMO tramo (p.ej. drawdown)."""
    n = len(series)
    wkey = f"{key}_rng"
    if wkey not in st.session_state:
        st.session_state[wkey] = (0, n - 1)
    lo, hi = st.session_state[wkey]
    lo, hi = max(0, min(int(lo), n - 2)), max(1, min(int(hi), n - 1))
    st.session_state[wkey] = (lo, hi)        # re-clampar si cambió la longitud de la serie
    span = hi - lo
    cz = st.columns([1, 1, 1, 9])
    if cz[0].button("➕", key=f"{key}_zi", help="Acercar (recorta el tramo un 25% por lado)"):
        q = max(span // 4, 2)
        st.session_state[wkey] = (lo + q, max(lo + q + 2, hi - q))
    if cz[1].button("➖", key=f"{key}_zo", help="Alejar (amplía el tramo)"):
        q = max(span // 2, 4)
        st.session_state[wkey] = (max(0, lo - q), min(n - 1, hi + q))
    if cz[2].button("⟲", key=f"{key}_zr", help="Ver la serie completa"):
        st.session_state[wkey] = (0, n - 1)
    cz[3].slider("Tramo (velas)", 0, n - 1, key=wkey, label_visibility="collapsed")
    lo, hi = st.session_state[wkey]

    def _draw(s: pd.Series, t: str, as_area: bool):
        seg = s.iloc[lo:hi + 1]
        # Columna interna fija: un título con puntos/paréntesis rompe el shorthand de Altair
        dfc = pd.DataFrame({"vela": np.arange(lo, hi + 1), "valor": seg.values})
        base = alt.Chart(dfc)
        mark = base.mark_area(opacity=0.6) if as_area else base.mark_line()
        ch = mark.encode(x=alt.X("vela:Q", title="vela"),
                         y=alt.Y("valor:Q", title=t, scale=alt.Scale(zero=False)))
        st.altair_chart(ch, width="stretch")            # sin .interactive(): el scroll no la mueve

    st.markdown(f"**{title}**")
    _draw(series, title, area)
    if extra is not None:
        st.markdown(f"**{extra_title}**")
        _draw(extra, extra_title, True)

# ------------------------------------------------------------------ Sidebar
with st.sidebar:
    st.header("⚙️ Control")
    cfg["mode"] = st.selectbox(
        "Modo", ["recomendacion", "auto_testnet", "auto_live"],
        index=["recomendacion", "auto_testnet", "auto_live"].index(cfg.get("mode", "recomendacion")),
        help="recomendacion: propone y esperas aprobación · auto_testnet: opera en paper · auto_live: real (bloqueado en Fase 1)",
    )
    cfg["enabled"] = st.toggle("Automatización activa (kill-switch)", value=cfg.get("enabled", False))
    if cfg["mode"] == "auto_live":
        st.error("auto_live está **congelado** por diseño: ninguna estrategia superó la validación "
                 "OOS. La app es una herramienta, no un bot. No se ejecuta en real.")

    st.divider()
    st.subheader("Programación")
    cfg["schedule"]["cron"] = st.text_input("Cron", cfg["schedule"].get("cron", "0 * * * *"),
                                            help="Ej: '0 * * * *' cada hora · '*/15 * * * *' cada 15 min")
    cfg["schedule"]["managed_by"] = st.radio("Gestiona la frecuencia",
                                             ["usuario", "ia"],
                                             index=0 if cfg["schedule"].get("managed_by") == "usuario" else 1,
                                             horizontal=True)
    st.subheader("Predicción")
    cfg["forecast"]["min_confidence"] = st.slider("Confianza mínima", 0.0, 1.0,
                                                  float(cfg["forecast"].get("min_confidence", 0.6)), 0.05)
    syms = st.text_input("Símbolos (coma)", ", ".join(cfg.get("symbols", [])))
    cfg["symbols"] = [s.strip() for s in syms.split(",") if s.strip()]

    if st.button("💾 Guardar configuración", width="stretch"):
        save_config(cfg)
        st.success("Configuración guardada.")

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

tab_bt, tab_research, tab_risk, tab_pf, tab_cycle, tab_market, tab_journal, tab_wallets = st.tabs(
    ["🔬 Backtest & Validación", "🧭 Decisiones & Research", "🛡️ Riesgo", "💼 Portfolio",
     "🔄 Ciclo", "📊 Mercado", "📓 Diario", "🔌 Conexiones"])

# ------------------------------------------------------------------ Backtest
with tab_bt:
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
                _zoom_chart(btr["equity"], key="btchart",
                            title="Curva de equity (capital relativo, base 1.0)",
                            extra=btr["drawdown"], extra_title="Drawdown")

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
with tab_research:
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
with tab_risk:
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
with tab_pf:
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
with tab_wallets:
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
with tab_cycle:
    st.subheader("Correr ciclo (datos → predicción → riesgo → decisión)")
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
with tab_market:
    st.subheader("Mercado (precios reales)")
    sym = st.selectbox("Símbolo", cfg.get("symbols", ["BTC/USDT"]))
    df_raw, source = cached_ohlcv(sym, "1h", 200)
    if source == "synthetic":
        st.warning("Sin acceso a internet: mostrando datos SINTÉTICOS de desarrollo.")
    df = df_raw.set_index("ts")
    st.line_chart(df["close"])
    st.caption(f"Fuente: {source} · {len(df)} velas · último: {df['close'].iloc[-1]:.2f}")

# ------------------------------------------------------------------ Journal
with tab_journal:
    st.subheader("Diario de operaciones")
    jp = journal_mod.JOURNAL_PATH
    if jp.exists():
        st.dataframe(pd.read_csv(jp), width="stretch", hide_index=True)
        mm = journal_mod.metrics()
        st.write(f"**Trades:** {mm['trades']} · **Win rate:** {mm['win_rate']}% · "
                 f"**PnL total:** {mm['pnl_total']} · Ganadoras {mm['wins']} / Perdedoras {mm['losses']}")
    else:
        st.caption("Aún no hay operaciones registradas.")

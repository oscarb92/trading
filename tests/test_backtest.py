"""Tests del motor de backtesting (Fase 2)."""
import numpy as np, pandas as pd
from src import backtest as bt, store, validation as val


def _series(n=1500, seed=3):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    ts = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"ts": ts, "open": close, "high": close*1.001,
                         "low": close*0.999, "close": close, "volume": 1})


def test_backtest_sin_lookahead_y_metricas():
    df = _series()
    r = bt.run_backtest(df, "1h")
    m = r["metrics"]
    assert m.bars == len(df)
    assert abs(r["equity"].iloc[0] - 1) < 1e-9          # señal desplazada (no usa el futuro)
    assert -1.0 <= m.max_drawdown <= 0.0
    assert 0 <= m.win_rate <= 100


def test_walk_forward_segmentos():
    wf = bt.walk_forward(_series(2000), "1h", n_splits=4)
    assert len(wf) == 4
    assert all(s["metrics"].bars > 0 for s in wf)


def test_baseline_signal_en_rango():
    s = bt.baseline_signal(_series())
    assert set(s.unique()).issubset({-1, 0, 1})


def test_hysteresis_reduce_sobre_trading(monkeypatch):
    """La banda muerta debe operar MENOS que el baseline (mismo subyacente)."""
    df = _series(3000, seed=7)
    s = bt.hysteresis_signal(df, enter=0.60)
    assert set(s.unique()).issubset({-1, 0, 1})
    base = bt.run_backtest(df, "1h", signal_fn=bt.baseline_signal)["metrics"]
    hyst = bt.run_backtest(df, "1h",
                           signal_fn=lambda d: bt.hysteresis_signal(d, enter=0.60))["metrics"]
    assert hyst.trades <= base.trades


def test_adx_en_rango():
    a = bt.adx(_series(1000, seed=5))
    assert len(a) == 1000
    assert a.min() >= 0 and a.max() <= 100 + 1e-6        # ADX acotado [0,100]


def test_metrics_from_position_consistente():
    """El refactor no cambia nada: run_backtest == metrics_from_position sobre la misma pos."""
    df = _series(800, seed=4)
    full = bt.run_backtest(df, "1h", signal_fn=bt.baseline_signal)
    pos = bt.baseline_signal(df).shift(1).fillna(0)
    raw = df["close"].astype(float).pct_change().fillna(0)
    win = bt.metrics_from_position(pos, raw, "1h")
    assert win["metrics"] == full["metrics"]


def test_mean_reversion_contrarian():
    """Sobre una serie oscilante, la reversión debe operar en AMBOS sentidos."""
    n = 600
    t = np.arange(n)
    close = 100 + 10 * np.sin(t / 10.0)                  # oscila en torno a 100
    ts = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    df = pd.DataFrame({"ts": ts, "open": close, "high": close * 1.001,
                       "low": close * 0.999, "close": close, "volume": 1})
    s = bt.mean_reversion_signal(df, lookback=20, entry_z=1.0, exit_z=0.0)
    assert set(s.unique()).issubset({-1, 0, 1})
    assert 1 in s.values and -1 in s.values             # compra suelos y vende techos


def test_walk_forward_oos_contrato():
    """El motor de validación devuelve la estructura esperada y respeta n_folds."""
    df = _series(2000, seed=11)
    cands = [("A", bt.baseline_signal),
             ("B", lambda d: bt.hysteresis_signal(d, enter=0.60))]
    r = val.walk_forward_oos(df, cands, symbol="X", timeframe="1h",
                             n_folds=4, min_train_trades=1)
    assert len(r.folds) == 4 and len(r.picks) == 4
    assert r.insample_best in {"A", "B"}
    assert isinstance(r.oos_return, float) and isinstance(r.bh_return, float)


def test_regime_signal_filtra_entradas():
    """Con filtro de régimen no se puede estar MÁS tiempo en posición que sin él."""
    df = _series(3000, seed=9)
    sin = bt.regime_signal(df, enter=0.60, adx_min=0)    # adx_min=0 ≡ histéresis pura
    con = bt.regime_signal(df, enter=0.60, adx_min=30)
    assert set(con.unique()).issubset({-1, 0, 1})
    assert int((con != 0).sum()) <= int((sin != 0).sum())


def test_resample_1h_a_4h():
    df = _series(400)                                    # ts horario alineado a la rejilla 4h
    r = store.resample_ohlcv(df, "4h")
    assert len(r) == 100                                 # 400 / 4
    assert list(r.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert (r["high"] >= r["close"]).all()               # OHLC coherente
    assert (r["low"] <= r["close"]).all()
    assert store.detect_gaps(r, "4h") == []


def test_store_dedup_y_huecos(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    df = _series(300)
    df2 = pd.concat([df.iloc[:200], df.iloc[150:]])     # solape
    store.save_ohlcv(df2, "BTC/USDT", "1h")
    loaded = store.load_ohlcv("BTC/USDT", "1h")
    assert len(loaded) == 300                            # sin duplicados
    assert store.detect_gaps(loaded, "1h") == []


def test_update_history_pagina_forward(tmp_path, monkeypatch):
    """El backfill avanza el cursor `since`: cubre más velas que un solo bloque."""
    from src.data import FetchResult
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store.time, "time", lambda: 100_000 * 3600)   # 'ahora' fijo
    calls = {"n": 0}

    def fake(symbol="BTC/USDT", timeframe="1h", limit=1000, exchange="binance", since=None):
        calls["n"] += 1
        ts = pd.to_datetime([since + i * 3_600_000 for i in range(1000)], unit="ms", utc=True)
        df = pd.DataFrame({"ts": ts, "open": 1.0, "high": 1.0, "low": 1.0,
                           "close": 1.0, "volume": 1.0})
        return FetchResult(df, "binance", symbol, timeframe)

    monkeypatch.setattr("src.data.fetch_ohlcv", fake)
    s = store.update_history("BTC/USDT", "1h", total=2500)
    assert calls["n"] >= 3                               # paginó (no se quedó en 1 bloque)
    assert s.candles >= 2500                             # cubrió el rango pedido
    assert s.gaps == 0


def test_update_history_no_persiste_sintetico(tmp_path, monkeypatch):
    """Garantía de integridad: sin red real, NO se contamina el store con sintético."""
    from src.data import FetchResult
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store.time, "time", lambda: 100_000 * 3600)

    def fake(symbol="BTC/USDT", timeframe="1h", limit=1000, exchange="binance", since=None):
        ts = pd.to_datetime([since + i * 3_600_000 for i in range(10)], unit="ms", utc=True)
        df = pd.DataFrame({"ts": ts, "open": 1.0, "high": 1.0, "low": 1.0,
                           "close": 1.0, "volume": 1.0})
        return FetchResult(df, "synthetic", symbol, timeframe)   # red caída

    monkeypatch.setattr("src.data.fetch_ohlcv", fake)
    s = store.update_history("BTC/USDT", "1h", total=2500)
    assert s.candles == 0                                # nada persistido
    assert store.load_ohlcv("BTC/USDT", "1h").empty


def test_backtest_robusto_ante_contaminacion():
    # Serie con un salto enorme (mezcla sintético+real) no debe romper las métricas
    import numpy as np, pandas as pd
    from src import backtest as bt
    n = 600
    close = np.r_[np.full(300, 30000.0), np.full(300, 95000.0)]  # salto 30k->95k
    close = close * (1 + np.random.default_rng(0).normal(0, 0.002, n))
    ts = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    df = pd.DataFrame({"ts": ts, "open": close, "high": close*1.001,
                       "low": close*0.999, "close": close, "volume": 1})
    r = bt.run_backtest(df, "1h")
    m = r["metrics"]
    assert m.max_drawdown >= -1.0, "el equity no debe volverse negativo"
    assert m.clipped_bars >= 1, "debe recortar el salto de precio"
    assert (r["equity"] > 0).all()

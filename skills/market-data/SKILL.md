---
name: market-data
description: Descargar, normalizar y cachear datos de mercado (OHLCV, orderbook, trades) desde exchanges vía CCXT/Binance. Usar cuando el usuario pida "bajar datos", "histórico de un par", "precios en vivo", "actualizar dataset" o necesite datos para backtest o señales.
---

# Skill: market-data

Capa de obtención de datos de mercado. Fuente principal: **CCXT** (unificado), con **Binance** por defecto.

## Código real / estado
`src/data.py::fetch_ohlcv` ya descarga OHLCV (con fallback **sintético** si falla la
red — revisar `FetchResult.source` y NUNCA usar datos sintéticos para operar ni backtest).
La capa de caché Parquet/DuckDB todavía NO existe: es la tarea principal de Fase 1
(ver PLAN.md). Al implementarla, hacerlo en `src/store.py` e integrarla en `fetch_ohlcv`.

## Cuándo usar
- Descargar histórico OHLCV de uno o varios símbolos.
- Suscribirse a precios/orderbook en tiempo real (WebSocket).
- Refrescar el dataset local antes de un backtest.

## Procedimiento
1. Cargar el exchange con CCXT (`ccxt.binance()`; para datos en vivo usar `ccxt.pro`).
2. Validar el símbolo (`BTC/USDT`) y el timeframe (`1m`, `5m`, `1h`, `1d`).
3. Descargar con paginación (`fetch_ohlcv` por bloques de 1000 velas).
4. Normalizar a DataFrame: `timestamp, open, high, low, close, volume` (UTC).
5. Guardar en **Parquet** particionado por símbolo/timeframe en `data/`. Si ya existe, hacer append incremental sin duplicar.
6. Reportar: rango de fechas, nº de velas, huecos detectados.

## Ejemplo mínimo (Python)
```python
import ccxt, pandas as pd
ex = ccxt.binance()
ohlcv = ex.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=1000)
df = pd.DataFrame(ohlcv, columns=["ts","open","high","low","close","volume"])
df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
df.to_parquet("data/BTC-USDT_1h.parquet")
```

## Reglas
- Nunca usar claves API para datos públicos (no hacen falta).
- Respetar rate limits: `ex.enableRateLimit = True`.
- Registrar la descarga en `MEMORIA_PROYECTO.md` (bitácora).

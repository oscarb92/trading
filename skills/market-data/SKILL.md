---
name: market-data
description: Descargar, normalizar y cachear datos de mercado OHLCV — cripto vía CCXT/Binance y multi-mercado (oro, petróleo, plata, índices/ETF, acciones) vía yfinance. Usar cuando el usuario pida "bajar datos", "histórico de un par", "precios en vivo", "actualizar dataset" o necesite datos para backtest o señales.
---

# Skill: market-data

Capa de datos del sandbox. Dos fuentes, un mismo esquema OHLCV (`ts, open, high, low, close, volume`).

## Código real (usar, no reinventar)
- **Cripto (CCXT/Binance):** `src/data.py::fetch_ohlcv` (acepta `since` en ms para paginar)
  y `current_price`. Fallback **sintético** si falla la red — revisar `FetchResult.source`.
- **Multi-mercado (yfinance):** `src/marketdata.py::fetch_yahoo` (`source="yahoo"`,
  auto-ajustado por splits/dividendos, descarta `close<=0`). Universo en `marketdata.UNIVERSE`
  (16 instrumentos con etiqueta y clase); anualización por clase: `periods_per_year`
  (252 bolsa / 365 cripto).
- **Caché Parquet:** `src/store.py` — `save_ohlcv` (dedup + aviso de saltos >50%),
  `load_ohlcv`, `detect_gaps`, `summary`, `resample_ohlcv` (1h→4h),
  `update_history` (backfill paginado idempotente que NUNCA persiste datos sintéticos)
  y `clear` para rehacer un histórico.

## Comandos de descarga
- Cripto: `python backtest.py --fresh --download 17520 --symbol BTC/USDT ETH/USDT` (2 años 1h).
- Multi-mercado: `python cross_asset.py` (baja lo que falte) o `--refresh` (rehace todo).

## Reglas
- **Nunca** usar datos `source == "synthetic"` para operar, backtestear ni guardar en `data/`.
- Mercados no-24/7: los fines de semana NO son huecos; anualizar con `periods_per_year`.
- Los futuros continuos de Yahoo (`GC=F`, `CL=F`, `SI=F`) son precios NO negociables
  (roll back-ajustado); preferir sus ETF (GLD/SLV/USO) para análisis replicables.
- Sin claves API para datos públicos; respetar rate limits (ya activado en `src/data.py`).

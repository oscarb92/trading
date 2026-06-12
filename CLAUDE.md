# CLAUDE.md — trading-app

Contexto para Claude al trabajar en este proyecto. Leer también `MEMORIA_PROYECTO.md` (visión/decisiones) y `PLAN.md` (qué hacer y en qué orden).

## Qué es

**Herramienta honesta de research/backtesting/journal/riesgo** para cripto (Binance vía CCXT). NO es un bot que promete rentabilidad.
Fases 2-3 completas. **Pivote 2026-06-11 (opción A):** la validación walk-forward OOS demostró que ni momentum ni reversión sobre velas 1h/4h tienen edge neto de costes en BTC/ETH (sobreajuste cazado, ver `MEMORIA_PROYECTO.md` §11-§12). El objetivo dejó de ser "batir al mercado"; ahora es un sandbox que mide/simula/registra con rigor. Ejecución real **CONGELADA**. Fases 4 (dashboard backtest/validación OOS) y 5 (utilidades de riesgo: sizing/Kelly, stress test, exposición/correlación) **COMPLETADAS** y verificadas en navegador.

## Comandos

```bash
pip install -r requirements.txt        # deps: ccxt, pandas, numpy, pyyaml, streamlit
pytest -q                              # tests (47 en verde: core+correcciones+backtest+datos+señales+validación+riesgo+multimercado+cross-sectional+velas+calibración+futuros)
python futures_compare.py              # efecto del apalancamiento 1x-5x con funding/liquidación → reports/futures.md
python cross_asset.py                  # validación OOS sobre 16 mercados (yfinance) → reports/cross_asset.md
python cross_sectional.py              # prueba market-neutral (alfa vs beta) → reports/cross_sectional.md
python candles_validate.py             # patrones de velas japonesas, validación OOS → reports/candlestick.md
python run.py                          # una pasada del ciclo (CLI / tarea programada)
python run.py --deposit 1000           # agregar saldo simulado
streamlit run dashboard.py             # dashboard web
```

## Mapa del código

| Archivo | Rol |
|---------|-----|
| `src/config.py` | Carga/guarda `automation_config.yaml` con defaults (deep merge) |
| `src/data.py` | OHLCV/ticker vía CCXT-Binance (cripto); **fallback sintético si falla la red** (marcado en `FetchResult.source`) |
| `src/marketdata.py` | OHLCV NO-cripto vía **yfinance** (oro, petróleo, plata, índices/ETF, acciones); `source="yahoo"`, anualización por clase (252 bolsa / 365 cripto) |
| `src/validation.py` | Motor walk-forward **OOS reutilizable** (`walk_forward_oos`): selección por Sharpe de train, evaluación única en test, benchmark B&H. Usado por cripto y cross-asset |
| `cross_asset.py` | Validación OOS sobre 16 mercados (`reports/cross_asset.md`) con análisis de multiple-testing |
| `src/forecast.py` | Baseline momentum+tendencia+RSI → dirección, probabilidad, confianza |
| `src/risk.py` | `size_position`: sizing por riesgo fijo, stop ~1.5×ATR, TP 1:1.5, límites |
| `src/portfolio.py` | Estado persistente en `state/portfolio.json` (cash, posiciones, PnL) |
| `src/broker.py` | `PaperBroker` (precios reales, modelo PnL/margen, fees+slippage) y `LiveBroker` (esqueleto, NO implementar hasta Fase 6) |
| `src/journal.py` | Diario en `journal/trades.csv` + métricas acumuladas |
| `src/engine.py` | `run_cycle`: orquesta datos→forecast→riesgo→decisión según modo |
| `automation_config.yaml` | Config central: modo, símbolos, riesgo, cadencia |
| `skills/` | Skills del proyecto — DEBEN usar el código de `src/`, no reinventarlo |

## Modos de operación

- `recomendacion` (default): propone, nunca ejecuta.
- `auto_testnet`: ejecuta en PaperBroker sin pedir permiso (requiere `enabled: true`).
- `auto_live`: bloqueado hasta Fase 6 + aprobación humana explícita.

## Reglas no negociables

1. **Nunca** activar `auto_live` ni implementar `LiveBroker.open` sin aprobación humana explícita y Fases 2-5 validadas.
2. **Nunca** ejecutar operaciones sobre datos sintéticos (`source == "synthetic"`).
3. El salto `auto_testnet` → `auto_live` siempre lo decide el usuario, jamás la IA.
4. La IA puede reducir riesgo o pausar de forma autónoma; nunca aumentarlo sobre los límites de `risk`.
5. Claves API solo en `.env` (nunca en git), permisos mínimos, sin retiros.
6. Antes de dar por terminado un cambio: correr los tests y verificar que no haya bytes nulos en los archivos (`grep -rlP '\x00' src/ tests/`) — hubo incidentes previos.

## Correcciones P0 (RESUELTAS, ver tests)

- C1 ✅ engine no ejecuta con datos sintéticos (gate `source == "binance"`).
- C2 ✅ kill-switch de pérdida diaria conectado (`journal.today_pnl` → `size_position`; desactiva).
- C3 ✅ cierre por take-profit (`pos.take_profit`).
- C4 ✅ `journal.log_trade` escribe timestamp UTC; añadido `today_pnl`.
- C5 ✅ tests en pytest con `conftest.py` (sin fricción de PYTHONPATH).
- Almacenamiento histórico ✅ `src/store.py` (Parquet, dedup, huecos).

## Convenciones

- Código y comentarios en español; dataclasses para estructuras; type hints modernos (`X | None`).
- Mantener `src/` pequeño y legible; optimizar solo el camino crítico (datos→señal→orden).
- Tras cada hito o decisión: actualizar `MEMORIA_PROYECTO.md` (bitácora/decision log) y los checkboxes de `PLAN.md`.
- El forecast es un baseline honesto: no presentar sus probabilidades como validadas hasta pasar Fase 2.
- Esto es información técnica, no asesoría financiera; recordarlo en salidas orientadas al usuario.

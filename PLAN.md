# PLAN DETALLADO — App de Trading

> Plan operativo por fases con tareas concretas y criterios de salida.
> La visión y decisiones viven en `MEMORIA_PROYECTO.md`; este archivo es el "qué hacer y en qué orden".

**Estado:** P0 ✅ · Fase 1 (datos) ✅ · Fase 2 (backtesting honesto) ✅ · Fase 3 (sin edge OOS) ✅ · **PIVOTE a herramienta (opción A)** ✅ · Fase 4 (dashboard backtest/validación) ✅ · Fase 5 (utilidades de riesgo) ✅. Fase 6 (real) CONGELADA.
**Última actualización:** 2026-06-11

---

## Prioridad 0 — Correcciones de seguridad (ANTES de cualquier ciclo automático)

Detectadas en la auditoría del 2026-06-10:

| # | Corrección | Archivo | Criterio de hecho |
|---|-----------|---------|-------------------|
| C1 ✅ | Bloquear ejecución con datos sintéticos: si `FetchResult.source == "synthetic"`, el engine NO ejecuta (solo propone con advertencia) | `src/engine.py` | Test: con red caída, `auto_testnet` no abre posiciones |
| C2 ✅ | Conectar kill-switch de pérdida diaria: calcular `daily_loss_pct` desde el journal y pasarlo a `size_position`; si se alcanza, poner `enabled: false` | `src/engine.py`, `src/journal.py` | Test: con pérdida ≥ `max_daily_loss_pct`, no abre y desactiva |
| C3 ✅ | Ejecutar take-profit: el engine cierra posición cuando el precio toca `pos.tp` (hoy solo cierra por stop o señal contraria) | `src/engine.py` | Test: precio ≥ tp (long) → cierra |
| C4 ✅ | Bug journal: la columna `fecha` se guarda vacía (`setdefault` no actúa porque el dict ya trae `fecha: ""`) | `src/journal.py` | Filas nuevas con timestamp UTC |
| C5 ✅ | Tests ejecutables sin fricción: empaquetar o documentar `PYTHONPATH=.`; migrar a pytest | `tests/` | `pytest` corre en verde desde la raíz |

---

## Fase 1 — Capa de datos (la verdadera Fase 1, pendiente)

Lo construido hasta hoy adelantó Fases 3-5 (forecast/riesgo/paper). Falta la base de datos histórica, requisito para backtesting.

- [x] `src/store.py`: guardar OHLCV en **Parquet** particionado por símbolo/timeframe en `data/`.
- [x] Descarga histórica paginada (store.update_history) (bloques de 1000 velas vía CCXT) con append incremental sin duplicados.
- [x] Detección de huecos (store.detect_gaps) en el histórico y reporte (rango, nº velas, huecos).
- [x] Lectura desde caché local (store.load_ohlcv) local y solo baja lo que falta.
- [ ] (Opcional) WebSocket en vivo con `ccxt.pro` — puede posponerse a Fase 4.

**Criterio de salida:** ≥ 2 años de histórico 1h de BTC/USDT y ETH/USDT en Parquet, sin huecos, recargable con un comando. ✅ **CUMPLIDO 2026-06-11** — 17.520 velas/símbolo (2024-06-11 → 2026-06-11), 0 huecos. Bug de paginación corregido (`fetch_ohlcv(since=...)` + backfill forward) y store blindado contra contaminación sintética. Recarga: `python backtest.py --fresh --download 17520 --symbol BTC/USDT ETH/USDT`.

## Fase 2 — Backtesting

- [x] Motor de backtest (src/backtest.py + CLI backtest.py) (`backtesting.py` o `vectorbt`) sobre el Parquet local.
- [x] Baseline como estrategia vectorizada (backtest.baseline_signal) testeable (`señal(df) -> {-1,0,1}`).
- [x] Métricas: retorno total/anualizado, Sharpe, Sortino, max drawdown, win rate, profit factor, nº trades.
- [x] Validación **walk-forward** (train/test temporal, sin look-ahead) + comisiones 0.1% + slippage.
- [x] Reportes en `reports/` (backtest.report) y resultado anotado en `MEMORIA_PROYECTO.md`.

**Criterio de salida:** backtest reproducible del baseline con métricas honestas (aunque sean malas — eso es información). ✅ **CUMPLIDO 2026-06-11** — sobre datos REALES: BTC −99.03% (Sharpe −5.18), ETH −98.90% (Sharpe −3.26); walk-forward negativo en los 4 segmentos. El baseline simple no tiene edge neto de costes (fees+slippage acumulan ~479% en BTC). Reportes en `reports/`.

## Fase 3 — Señales / Forecast validado  (EN CURSO)

- [x] Evaluar el baseline contra el backtest (`phase3.py` → `reports/phase3_sweep.md`).
- [x] Banda muerta / histéresis (`backtest.hysteresis_signal`) + prueba en 4h (`store.resample_ohlcv`): recorta sobre-trading, mejora todas las métricas. **Hallazgo: el momentum no tiene edge ESTABLE (gana en tendencia, pierde en lateral; ver walk-forward en `MEMORIA_PROYECTO.md` §11).**
- [x] Filtro de régimen ADX (`backtest.adx`, `backtest.regime_signal`, `phase3_regime.py`): **asimétrico** — lleva ETH a ≈break-even (Sharpe +0.20, 3/4 segmentos), pero no rescata a BTC (1/4). Sin edge estable y simétrico.
- [x] Validación temporal real (`phase3_validate.py`, walk-forward anclado OOS, benchmark B&H): **el ADX NO se elige fuera de muestra (sobreajuste confirmado)**; BTC OOS −33%, ETH OOS +5.4% pero por baja exposición en mercado bajista, no alfa, y con params inestables. Ver `reports/phase3_validation.md` y `MEMORIA_PROYECTO.md` §11.
- [x] Cambiar de FAMILIA: reversión a la media (`backtest.mean_reversion_signal`) validada con el motor reutilizable `src/validation.py` → `reports/phase3_meanrev.md`. **Aún peor que momentum** (1h −44/−64%, 4h −12/−55% OOS). **Meta-conclusión: ni momentum ni reversión sobre velas 1h/4h tienen edge OOS en BTC/ETH.**
- [x] **Extensión MULTI-MERCADO** (`src/marketdata.py` yfinance + `cross_asset.py`): misma validación OOS sobre 16 mercados (oro/petróleo/plata/índices/ETF/acciones/cripto), diario 2018-26. **Auditado por panel adversarial** (workflow). Veredicto verificado: ninguna estrategia técnica direccional en diario tiene edge demostrable; líder indistinguible del azar (nula empírica **p=0.97**); funcionan como **overlay defensivo** (74% vs 9% batir B&H en caídas/subidas), no alfa. Solo descarta edges grandes (SE Sharpe≈0.49). Ver `reports/cross_asset.md` y §13.
- [ ] **Siguiente experimento de mayor valor (pendiente):** prueba LIMPIA alfa-vs-beta **cross-sectional / market-neutral** (long-short entre los 16) — lo único que separa "las técnicas no sirven" de "el formato direccional/long-bias es el problema". Después: intradía, momentum estilo CTA con vol-targeting (conectar `src/risk.py` al backtest).
- [ ] **DECISIÓN DEL USUARIO (bloquea Fase 4):** (A) reorientar el proyecto a herramienta honesta de research/journal/sandbox de riesgo (recomendado), o (B) cambiar de inputs (order book/microestructura, funding, on-chain, otros horizontes) con la misma validación OOS. NO seguir probando familias de TA sobre las mismas velas (sería p-hacking).
- [x] Calibrar `probability`/`confidence` (reliability curve): `src/calibration.py` + expander en la pestaña Ciclo. **Veredicto: SIN valor predictivo** (skill negativo en BTC/ETH 1h y 4h: −12.6% a −30.1%; la frecuencia observada se queda en ~50% diga lo que diga el modelo). Las probabilidades del forecast NO deben usarse para sizing ni como confianza; la pestaña Ciclo queda etiquetada como demo de simulación.
- [x] Solo sustituir el baseline si el candidato lo supera out-of-sample → ningún candidato lo supera; **no se sustituye.**

**Criterio de salida:** forecast con edge positivo neto de costes en walk-forward, o decisión documentada de seguir iterando. → **CUMPLIDO por la rama 2 con veredicto fuerte (2026-06-11): la familia momentum NO tiene edge out-of-sample en BTC ni ETH a 4h; la validación rigurosa cazó el sobreajuste que las métricas in-sample sugerían. NO pasar a Fase 4 con esta estrategia.** Maquinaria de Fase 2-3 (datos limpios, backtest, walk-forward OOS, benchmark) lista y reutilizable para el siguiente candidato.

---

## REORIENTACIÓN 2026-06-11 — de "batir al mercado" a HERRAMIENTA honesta

Decisión de Oscar (opción A). La validación OOS descartó edge en TA simple (Fase 3). Las fases
siguientes se redefinen: el producto es un **sandbox de research/simulación/riesgo**, no un bot
rentable. La ejecución real queda bloqueada y deja de ser el norte. Ver `MEMORIA_PROYECTO.md` §1 y §12.

## Fase 4 (NUEVA) — Herramienta de research usable

- [ ] **Dashboard de backtesting:** pestaña en `dashboard.py` para elegir símbolo/timeframe/estrategia
      (baseline / histéresis / reversión) y ver métricas con costes + curva de equity y drawdown.
- [ ] **Validación OOS en la UI:** botón que corre `src.validation.walk_forward_oos` y muestra la
      tabla por folds, el OOS encadenado, el benchmark buy & hold y el veredicto honesto.
- [ ] **Mensaje honesto omnipresente:** banner "ninguna estrategia tiene edge OOS demostrado;
      herramienta de análisis, no asesoría". Quitar/renombrar el lenguaje de "Fase 1" y "auto_live".
- [ ] Journal y equity curve del paper trading ya existentes, integrados como parte del sandbox.

**Criterio de salida:** un usuario puede, desde el dashboard, backtestear y VALIDAR OOS cualquiera
de las estrategias incluidas y leer un veredicto honesto, sin tocar la CLI.

## Fase 5 — Utilidades de gestión de riesgo (como herramienta, no para ir a real) ✅

- [x] Calculadora de sizing (fracción fija con apalancamiento implícito + Kelly fraccionado ≤ ½ Kelly con cap) en la UI — `src/risk.py` (`size_from_risk`, `kelly_fraction`, `fractional_kelly`), pestaña 🛡️ Riesgo del dashboard.
- [x] Stress test: shock configurable (gap −20% por defecto) sobre el portfolio, equity antes/después, ΔPnL por posición y aviso de stops cruzados — `risk.stress_test_gap`.
- [x] Exposición bruta/neta por activo + matriz de correlación de retornos (diversificación) — `risk.exposure`, `risk.correlation_matrix`.

**Criterio de salida:** ✅ las tres utilidades funcionan en el dashboard (verificadas en navegador: sizing 2.0/200/0.20×, Kelly 16.7%→8.3%, correlación BTC/ETH 0.82, stress test robusto con portfolio vacío). 28 tests en verde (+5 de riesgo).

## Fase 6 — Real (CONGELADA)

Bloqueada por diseño y por falta de edge. Solo se reconsideraría si un candidato superase la
validación OOS con holgura y de forma estable. No se implementa `LiveBroker.open` ni `auto_live`.

---

## Reglas de avance

1. No se pasa de fase sin cumplir el criterio de salida.
2. Toda decisión/hito se anota en `MEMORIA_PROYECTO.md` (decision log + bitácora).
3. Las correcciones P0 van antes que cualquier feature nueva.
4. **Dinero real: CONGELADO.** No hay estrategia con edge OOS; la app es una herramienta, no un bot.
5. Toda salida orientada al usuario recuerda: información técnica, no asesoría financiera.

# MEMORIA DEL PROYECTO — App de Trading (Simulación → Real)

> Archivo vivo de control y memoria. Actualízalo (o pídeme que lo actualice) cada vez
> que tomes una decisión, completes un hito o cambies de rumbo. Es la "fuente de verdad".

**Owner:** Oscar (oscarberrocal92@gmail.com)
**Inicio:** 2026-06-10
**Estado actual:** Fases 2-3 completas. **Reorientación 2026-06-11:** sin edge OOS en TA simple →
el proyecto pivota a **herramienta honesta de research/backtesting/journal/riesgo** (opción A, ver §12). Fase 4+ redefinida en `PLAN.md`.

---

## 1. Objetivo

> **Reorientación 2026-06-11 (decisión de Oscar, opción A).** La validación out-of-sample
> demostró que ni momentum ni reversión sobre velas 1h/4h tienen edge neto de costes (§11-§12).
> El objetivo deja de ser "batir al mercado" y pasa a ser una **herramienta honesta**:

1. **Sandbox de research:** backtesting con costes reales, validación walk-forward OOS y
   benchmark buy & hold para juzgar CUALQUIER estrategia con un estándar riguroso (sin autoengaño).
2. **Simulación / paper trading** con precios reales y journal de operaciones + métricas.
3. **Gestión de riesgo** (sizing, stops, límites, kill-switch) como utilidad de primera clase.
4. La ejecución real sigue siendo *posible* pero permanece **bloqueada** y NO es el objetivo:
   solo tendría sentido si algún día un candidato superase la validación OOS (hoy ninguno lo hace).

Principio rector: **honestidad por encima de promesas**. La app no afirma generar rentabilidad;
afirma medir, simular y registrar con rigor. Información técnica, no asesoría financiera.

Prioridad de diseño: **equilibrio** entre velocidad de desarrollo y eficiencia de ejecución.

---

## 2. Decisiones tomadas (Decision Log)

| Fecha | Decisión | Motivo |
|-------|----------|--------|
| 2026-06-10 | Mercado principal: **Cripto** (Binance), opción de añadir acciones US (Alpaca) | Cripto = datos abiertos, gratis, 24/7, testnet gratis y mayor profundidad histórica para calcular probabilidades |
| 2026-06-10 | Stack: **Python** (fase 1) → extraer motor de ejecución a **Rust** (fase real) | Python para iterar rápido en estrategia/backtest; Rust para latencia mínima en el camino crítico |
| 2026-06-10 | Capa de datos/ejecución: **CCXT** (unificada) + Binance directo | Un solo API para 100+ exchanges; cambiar de exchange sin reescribir |
| 2026-06-10 | Automatización con 3 modos (recomendación / auto_testnet / auto_live) + kill-switch | El usuario puede activar auto en test o vivo; máxima seguridad por defecto |
| 2026-06-10 | Cadencia configurable por usuario o por la IA (`schedule.managed_by`) | Flexibilidad para ajustar el ritmo según condiciones de mercado |
| 2026-06-11 | **Reorientar a herramienta de research/sandbox (opción A)**, no a "batir al mercado" | La validación OOS rigurosa (§11-§12) descartó edge en TA simple sobre 1h/4h en BTC/ETH; seguir buscando familias sería p-hacking. La infraestructura honesta ya construida vale como herramienta por sí misma |

---

## 3. Stack tecnológico recomendado

### APIs / Datos
- **CCXT** — librería unificada para 100+ exchanges (Python, Go, JS, Rust-bindings). Capa principal de datos y órdenes.
- **Binance API** — ejecución nativa cripto. Datos públicos sin auth + WebSocket en tiempo real. **Testnet gratis** para simular sin riesgo.
- **Alpaca** — si añades acciones/ETFs US. Paper trading nativo + datos históricos. Comisiones cero.
- **CoinAPI / Polygon.io** — (opcional) datos históricos tick-level profundos para backtesting serio.

### Lenguajes / código
- **Python** — investigación, señales, backtesting. Librerías: `ccxt`, `pandas`, `numpy`, `vectorbt` o `backtesting.py`, `ta` (indicadores), `pydantic`.
- **Rust** (o **Go** como alternativa más simple) — motor de ejecución de órdenes cuando pases a real. Latencia y seguridad de memoria.
- **WebSockets async** (`asyncio` + `websockets` / `ccxt.pro`) — datos en tiempo real.
- **DuckDB / Parquet** — almacenamiento rápido de datos históricos para backtest.

### Regla de oro de eficiencia
> Optimiza el **camino crítico** (recepción de datos → señal → orden), no todo el código.
> En cripto la latencia de red al exchange domina; un motor en Rust solo ayuda si el resto ya es eficiente.

---

## 4. Arquitectura (alto nivel)

```
                 ┌─────────────────────────┐
   Exchange  ───▶│  Data Layer (CCXT/WS)   │  OHLCV, orderbook, trades
   (Binance)     └───────────┬─────────────┘
                             ▼
                 ┌─────────────────────────┐
                 │  Signal / Strategy       │  indicadores + probabilidad/edge
                 └───────────┬─────────────┘
                             ▼
                 ┌─────────────────────────┐
                 │  Risk Manager            │  sizing, stop-loss, límites
                 └───────────┬─────────────┘
                             ▼
        ┌────────────────────┴────────────────────┐
        ▼                                          ▼
 ┌───────────────┐                        ┌──────────────────┐
 │ Paper / Sim   │   (Fase 1)             │ Live Execution   │ (Fase 2, Rust)
 │ Testnet       │                        │ Binance real     │
 └───────┬───────┘                        └────────┬─────────┘
         └──────────────┬────────────────────────-─┘
                        ▼
              ┌──────────────────┐
              │  Trade Journal    │  registro + métricas (memoria persistente)
              └──────────────────┘
```

---

## 5. Roadmap por fases

- [ ] **Fase 0 — Setup**: cuentas API (Binance testnet, Alpaca paper), repo, entorno Python.
- [ ] **Fase 1 — Datos**: descargar histórico, almacenar en Parquet/DuckDB, WebSocket en vivo.
- [ ] **Fase 2 — Backtesting**: motor de backtest + métricas (Sharpe, max drawdown, win rate).
- [ ] **Fase 3 — Señales**: indicadores + cálculo de probabilidad/edge por símbolo.
- [ ] **Fase 4 — Paper trading**: ejecución contra testnet, portfolio simulado.
- [ ] **Fase 5 — Gestión de riesgo**: sizing (Kelly/fracción fija), stops, límites de pérdida.
- [ ] **Fase 6 — Real**: extraer ejecución a Rust, claves de producción, monitoreo, alertas.

---

## 6. Skills del proyecto

Borradores en la carpeta `skills/` (instalar vía Ajustes → Capacidades):
- `market-data` — descargar y cachear datos de mercado.
- `backtest` — correr backtest de una estrategia y reportar métricas.
- `signal` — calcular indicadores y probabilidad/edge.
- `paper-trade` — ejecutar órdenes simuladas y actualizar portfolio.
- `risk-manager` — calcular tamaño de posición y stops.
- `trade-journal` — registrar operaciones y analizar rendimiento.

---

## 6b. Capa de automatización

Config central: **`automation_config.yaml`** (editable por el usuario o por la IA).

**Modos de decisión:**
- `recomendacion` — la IA propone y espera tu aprobación (por defecto, máximo control).
- `auto_testnet` — ejecuta solo en testnet/paper, sin pedir permiso.
- `auto_live` — ejecuta real, SOLO dentro de los límites de riesgo.

**Skills de automatización** (en `skills/`):
- `auto-trader` — orquestador del ciclo datos→predicción→riesgo→decisión.
- `forecast` — predicción con probabilidad y confianza.
- `notify` — envía recomendaciones, confirmaciones y alertas.
- `schedule-control` — cambia frecuencia/modo y gestiona el kill-switch.

**Reglas de seguridad no negociables:**
- El salto de `auto_testnet` → `auto_live` SIEMPRE requiere aprobación humana explícita.
- Kill-switch (`enabled: false`) detiene todo; se activa solo si se alcanza `max_daily_loss_pct`.
- La IA puede pausar o reducir riesgo de forma autónoma, nunca aumentarlo sobre los límites.
- Ciclo automático: pendiente de conectar a una **tarea programada** una vez exista el código.

## 7. Bitácora (Log)

| Fecha | Qué pasó / siguiente paso |
|-------|---------------------------|
| 2026-06-10 | Proyecto iniciado. Definido stack y mercado. Pendiente: crear cuentas API testnet. |
| 2026-06-10 | Añadida capa de automatización (3 modos + kill-switch) y skills auto-trader, forecast, notify, schedule-control. Pendiente: código + tarea programada. |
| 2026-06-11 | Auditoría de Fase 1: tests en verde, 5 brechas detectadas (C1-C5 en `PLAN.md`). Creados `PLAN.md` y `CLAUDE.md`. Mejoradas 9 skills: ahora referencian el código real de `src/`, guardrail de datos sintéticos, esquema correcto del journal y delimitación forecast/signal. Siguiente paso: correcciones P0 (C1-C5). |
| 2026-06-11 | **Fase 2 cerrada de verdad.** Detectado y corregido bug de paginación (el backfill nunca pasaba de ~1000 velas) y contaminación del store con datos sintéticos. Descargados 2 años reales (17.520 velas 1h) de BTC y ETH sin huecos. Backtest honesto del baseline: pierde ~99% en ambos (sin edge neto de costes). 16 tests en verde. Siguiente paso: Fase 3 (frenar sobre-trading con banda muerta/histéresis, validar features). |
| 2026-06-11 | **Fase 3 — diagnóstico (pasos 1-2).** Añadida `hysteresis_signal` (banda muerta) y `store.resample_ohlcv` (1h→4h). Barrido (`phase3.py` → `reports/phase3_sweep.md`): la histéresis recorta trades y mejora TODAS las métricas de forma monótona; 4h ≫ 1h. Pero walk-forward de las mejores celdas (BTC 4h enter=0.65, ETH 4h enter=0.70) muestra que el resultado positivo viene de UN solo régimen (tendencia mediados-2024) y pierde en lateral: **el momentum no tiene edge estable out-of-sample.** 18 tests en verde. Siguiente paso: filtro de régimen (operar momentum solo en tendencia; suprimir en lateral) o calibración de probabilidad. |
| 2026-06-11 | **Fase 3 — filtro de régimen ADX (paso 3).** Añadidos `backtest.adx` y `backtest.regime_signal` + `phase3_regime.py` → `reports/phase3_regime.md`. Resultado asimétrico: el filtro lleva a **ETH a ≈break-even** (Sharpe −0.17→+0.20, 3/4 segmentos positivos, mejora monótona con el umbral) pero **no rescata a BTC** (sigue −21% y 1/4). Sin edge positivo estable y simétrico → no se sustituye el baseline. Aviso de sobreajuste (solo 4 segmentos). 20 tests en verde. Siguiente: validación temporal real train/test, parámetros por activo, u otra familia de estrategia. Ver §11. |
| 2026-06-11 | **Fase 3 — validación OOS (paso 1). VEREDICTO: sobreajuste confirmado.** `phase3_validate.py` (walk-forward anclado, sin look-ahead, benchmark B&H) → `reports/phase3_validation.md`. El ADX **no se elige fuera de muestra** (ETH 3/4 folds eligen `adx_min=0`), los params son inestables y el único OOS "positivo" (ETH +5.4%) cuelga de un trimestre y es baja-exposición en mercado bajista, no alfa. BTC OOS −33%. **La familia momentum NO tiene edge OOS demostrable → NO pasar a Fase 4 con esta estrategia.** 21 tests en verde. Recomendación: cambiar de familia (reversión/breakout) con la misma maquinaria de validación, o aceptar "sin edge". Ver §11. |
| 2026-06-11 | **Fase 3 — reversión a la media + META-CONCLUSIÓN.** Motor OOS extraído a `src/validation.py` (reutilizable; reproduce momentum exacto). Nueva familia `mean_reversion_signal` validada con el mismo estándar (`phase3_meanrev.py` → `reports/phase3_meanrev.md`): **aún peor que momentum** (1h −44/−64%, 4h −12/−55%). **Conclusión: ni momentum ni reversión sobre velas 1h/4h tienen edge OOS en BTC/ETH.** Seguir probando familias = p-hacking. Decisión del usuario: (A) reorientar a herramienta de research/journal, o (B) cambiar de inputs (order book/on-chain/otros horizontes). 23 tests en verde. Recomiendo (A). Ver §12. |
| 2026-06-11 | **Pivote a herramienta (opción A) + Fase 4-5.** Visión reescrita (sandbox honesto, no "batir al mercado"). Dashboard: banner honesto + pestaña 🔬 Backtest & Validación OOS (verificada en navegador: reproduce los reportes CLI). **Fase 5:** utilidades de riesgo en `src/risk.py` (sizing fracción fija + Kelly fraccionado, stress test de gap, exposición y correlación) y pestaña 🛡️ Riesgo (verificada: sizing 2.0/200/0.20×, Kelly 16.7%→8.3%, corr BTC/ETH 0.82). 28 tests en verde. Fase 6 (real) CONGELADA. |
| 2026-06-11 | **Pulido UX:** backtest y validación OOS ahora conviven en pantalla (persistencia en `st.session_state` + expanders + botón Limpiar); una pulsación ya no borra el otro resultado. Verificado en navegador. Pendiente menor opcional: migrar `use_container_width` → `width=` (deprecado en Streamlit, hoy solo genera avisos en el log). |
| 2026-06-11 | **Multi-mercado + auditoría adversarial.** `src/marketdata.py` (yfinance) + `cross_asset.py`: validación OOS sobre 16 mercados (commodities/ETF/acciones/cripto), diario 2018-26. Un panel adversarial de 4 lentes cazó fallos en el reporte (argumento de azar incorrecto, potencia, ranking sesgado, precio negativo del WTI) → corregidos. **Veredicto verificado: ninguna estrategia técnica direccional en diario tiene edge demostrable; el líder es indistinguible del azar (nula empírica p=0.97); funcionan como overlay defensivo (74% vs 9% batir B&H en caídas/subidas), no como alfa.** Pendiente clave: prueba cross-sectional/market-neutral. 31 tests verdes. Ver §13. |
| 2026-06-11 | **Prueba LIMPIA alfa-vs-beta (cross-sectional market-neutral) + 2º panel adversarial.** `cross_sectional.py`. El panel cazó que la v1 medía dispersión de vol (mala especificación) y que el veredicto sobre-afirmaba → corregido a score estandarizado por vol + pesos inverse-vol + IC reportado. **Verificado: Sharpe OOS −0.42, IC[−1.38,+0.54], p-nula 0.59, beta +0.07 (neutralidad real). Sin alfa GRANDE detectable, pero infra-potenciado (no prueba cero alfa).** Cierra el hilo: sin edge técnico explotable en este universo; solo overlay defensivo. 34 tests verdes. Ver §13. |
| 2026-06-11 | **Consolidación en la herramienta + familia de VELAS JAPONESAS.** A pregunta de Oscar ("¿tenéis en cuenta la evaluación de tipos de velas?"): no se evaluaban → implementada `backtest.candlestick_signal` (envolventes, martillo, estrella fugaz con contexto EMA, hold configurable) y validada OOS (`candles_validate.py` → `reports/candlestick.md`): **0/6 mercados con ΔSharpe>0; Sharpe OOS −0.16…−1.31. Sin edge, consistente con la literatura.** Dashboard consolidado: selector **multi-mercado** (16 instrumentos, ppy por clase), gráficas Altair **estáticas** (el scroll ya no las mueve) con **zoom ➕/➖/⟲ + slider de tramo**, nueva pestaña **🧭 Decisiones & Research** (4 conclusiones validadas + tabla por mercado desde el JSON + visor de informes), estrategia de velas en la UI, y migración `use_container_width`→`width` (log sin avisos). Verificado en navegador. 37 tests verdes. |

---

## 11. Hallazgos Fase 3 — Señales (2026-06-11)

**Hipótesis del sobre-trading: CONFIRMADA parcialmente.** El baseline (bandas 0.55/0.45,
sin memoria) flipeaba posición casi cada vela y el coste lo destruía. Con banda muerta
(`hysteresis_signal`, entrar con convicción y mantener hasta cruzar el centro):

| Config | Retorno | Sharpe | Win | Trades | Coste acum. |
|--------|---------|--------|-----|--------|-------------|
| BTC 1h baseline | −99.0% | −5.18 | 22.6% | 1599 | 479% |
| BTC 1h histéresis 0.70 | −74.6% | −1.75 | 32.8% | 384 | 115% |
| BTC 4h baseline | −56.3% | −0.73 | 27.2% | 382 | 114% |
| BTC 4h histéresis 0.65 | −22.9% | −0.09 | 37.9% | 182 | 54% |
| ETH 4h histéresis 0.70 | −32.2% | −0.02 | 32.0% | 181 | 54% |

Dos palancas claras: **(a) operar más lento (4h)** y **(b) banda muerta con umbral alto**.
Ambas reducen el coste y suben win rate.

**Pero NO hay edge estable.** Walk-forward (4 segmentos) de las mejores celdas:
- BTC 4h enter=0.65: seg1 +33% (Sharpe 1.47) · seg2 −22% · seg3 −5% · seg4 −13%.
- ETH 4h enter=0.70: seg1 +49% (Sharpe 1.73) · seg2 −45% · seg3 +35% (Sharpe 1.34) · seg4 −15%.

El momentum gana en tendencia y pierde en lateral (firma típica). Per criterio de salida
Fase 3 (rama 2): **decisión documentada de seguir iterando.** Próxima hipótesis natural:
**filtro de régimen** (p.ej. solo tomar señales cuando la tendencia es fuerte / vol elevada;
plano en rango) para quedarse con los segmentos buenos y saltarse los malos. Solo se
sustituiría el baseline si el candidato lo supera out-of-sample en walk-forward.

### Filtro de régimen ADX (paso 3) — 2026-06-11

Añadidos `backtest.adx` (Wilder) y `backtest.regime_signal` (histéresis que solo inicia/
invierte posición cuando ADX ≥ umbral). Experimento controlado en 4h, enter=0.65, variando
solo `adx_min` (`phase3_regime.py` → `reports/phase3_regime.md`). Resultado **asimétrico**:

| | sin filtro | adx≥25 | adx≥30 | adx≥35 |
|---|---|---|---|---|
| **BTC** ret / Sharpe / seg>0 | −22.9% / −0.09 / 1·4 | −23.5% / −0.20 / 1·4 | −21.0% / −0.21 / 1·4 | −23.2% / −0.36 / 2·4 |
| **ETH** ret / Sharpe / seg>0 | −44.7% / −0.17 / 2·4 | −23.0% / +0.01 / 3·4 | −7.4% / +0.15 / 3·4 | −0.4% / +0.20 / 3·4 |

- **ETH:** el filtro ayuda de forma **monótona** — sube Sharpe (−0.17→+0.20), recorta la
  pérdida (−45%→break-even) y estabiliza (2/4→3/4 segmentos positivos). Sus tendencias son
  persistentes y el ADX las captura.
- **BTC:** el filtro **no rescata** — su segmento malo sigue negativo con cualquier umbral
  (1/4 positivos). Las pérdidas de BTC no son simple "ruido de rango".

**Conclusión honesta:** ni siquiera con 4h + histéresis + filtro ADX hay edge positivo
estable en AMBOS activos. ETH queda ≈break-even (prometedor); BTC sigue claramente negativo.
**Aviso de sobreajuste:** con solo 4 segmentos walk-forward, elegir `adx_min=35` para ETH es
casi optimización in-sample; la mejora monótona es más creíble que un punto suelto, pero NO
es validación out-of-sample real (misma ventana de 2 años). Para afirmarlo haría falta
optimizar en año 1 / testear en año 2, o más activos.

**Decisión:** no se sustituye el baseline (no supera de forma robusta y simétrica). El momentum
simple no tiene edge fiable. Caminos abiertos para la siguiente sesión: (a) split temporal real
train/test para validar el ADX sin sobreajuste; (b) parámetros por activo (ETH responde al ADX,
BTC no); (c) probar otra familia de estrategia (reversión a la media / breakout) en vez de
seguir exprimiendo momentum; (d) calibración de `probability`/`confidence` para Fase 5.

### Validación walk-forward OUT-OF-SAMPLE (paso 1) — 2026-06-11 · VEREDICTO

`phase3_validate.py` → `reports/phase3_validation.md`. Walk-forward anclado: año 1 = train
inicial; año 2 = 4 folds OOS con re-optimización en ventana expansiva; selección por Sharpe de
train, evaluación única en test; señal causal sobre serie completa + PnL aislado por ventana
(sin warm-up ni look-ahead); costes incluidos; benchmark buy & hold.

| Activo | OOS año 2 (encadenado) | Sharpe | MaxDD | Buy & hold año 2 | Params elegidos |
|--------|------------------------|--------|-------|------------------|-----------------|
| BTC | **−32.85%** | −0.94 | −41% | −42.99% | (0.60,25)×2 → (0.65,0)×2 |
| ETH | **+5.38%** | +0.36 | −41% | −40.97% | (0.70,0)×3 → (0.65,35) |

**Lectura 100% crítica — el OOS REFUTA la hipótesis del edge ADX. La etiqueta ✅ del script
(verdict mecánico: OOS>0 y >B&H) es un ARTEFACTO; los detalles la desmienten:**

1. **El filtro ADX NO fue elegido fuera de muestra.** En ETH, 3 de 4 folds eligieron
   `adx_min=0` (¡sin filtro!). La mejora que vimos in-sample con ADX alto era ajuste a la
   ventana: cuando se elige solo con el pasado, el optimizador lo descarta. La validación
   contradice directamente lo que veníamos a confirmar.
2. **No hay óptimo que optimizar.** Los Sharpe de TRAIN de los combos "ganadores" son ~0 o
   negativos (ETH fold1: train Sharpe −0.11). Se elige el menos malo de un conjunto malo.
3. **Parámetros INESTABLES** en ambos activos (saltan entre folds) → el "óptimo" es ruido.
4. **El +5.38% de ETH cuelga de UN fold** (fold2: +15.8%, en un trimestre en que ETH cayó
   −23% y la estrategia iba neta corta). Quitado ese trimestre, ETH OOS ≈ negativo. Es una
   apuesta direccional afortunada en un trimestre, no un edge repetible.
5. **"Batir buy & hold" engaña:** el año 2 fue bajista (ETH −41%, BTC −43%). Una estrategia
   long/short con MENOS exposición "gana" a comprar-y-aguantar en un mercado que cae, por beta
   reducida, no por alfa. En el fold1 alcista de ETH (+55% B&H) la estrategia solo hizo +6.7%:
   se perdió la subida. Eso es baja exposición, no habilidad.
6. **Riesgo inasumible** aun en el caso "bueno": MaxDD −41% para +5% de retorno anual.
7. **Sin poder estadístico:** 4 folds, 2 activos, 1 "positivo" ≈ lo esperable por azar.

**CONCLUSIÓN FIRME:** la familia momentum (baseline + histéresis + filtro ADX) **NO tiene edge
out-of-sample demostrable** en BTC ni ETH a 4h. El rigor cumplió su función: cazó el sobreajuste
que las métricas in-sample sugerían. **NO se debe pasar a paper trading (Fase 4) con esta
estrategia.** Recomendación: abandonar el momentum simple como núcleo y, en la próxima sesión,
(a) probar otra FAMILIA (reversión a la media / breakout con la misma maquinaria de validación
ya construida), o (b) aceptar formalmente "sin edge" y reorientar el objetivo del proyecto.
La maquinaria de Fase 2-3 (datos limpios, backtest honesto, walk-forward OOS, benchmark) queda
lista y reutilizable para evaluar cualquier candidato con el mismo estándar.

---

## 12. Reversión a la media — validación OOS (2026-06-11) · y META-CONCLUSIÓN

Motor de validación extraído a `src/validation.py` (reutilizable; reproduce exactamente los
números de momentum como regression check). Nueva familia `backtest.mean_reversion_signal`
(z-score con bandas, contrarian) barrida con el MISMO estándar OOS: `phase3_meanrev.py` →
`reports/phase3_meanrev.md`.

| Timeframe / activo | OOS año 2 | Sharpe | Buy & hold | Lectura |
|---|---|---|---|---|
| 1h BTC | −44.5% | −1.77 | −42.9% | peor que aguantar |
| 1h ETH | −64.3% | −1.75 | −41.0% | desastre (shortear cripto sobrecomprado en tendencia) |
| 4h BTC | −11.6% | −0.33 | −43.0% | negativo; "gana" a B&H solo por baja exposición |
| 4h ETH | −55.4% | −1.30 | −41.0% | peor que aguantar |

La reversión es **aún peor que el momentum**. El único caso no-catastrófico (4h BTC, params
ESTABLES `lb20/in2.5/out0.0` en los 4 folds) sigue en −11.6%: estabilidad de parámetros SIN
rentabilidad. A 1h la reversión se destruye (comprar suelos / vender techos en cripto con
tendencia es justo la apuesta equivocada).

**META-CONCLUSIÓN (lo importante de la Fase 3):** ni momentum ni reversión —las dos familias
canónicas de indicadores técnicos sobre velas OHLCV 1h/4h— muestran **edge positivo
out-of-sample** neto de costes en BTC/ETH. Los "mejores" resultados de ambas son solo
DEFENSIVOS (menor exposición en un año bajista), no alfa, y con drawdowns del 40%.

**Riesgo metodológico explícito:** seguir probando familias hasta que una pase 4 folds OOS
sería **p-hacking** (con suficientes intentos, una pasa por azar). NO se debe continuar
barriendo estrategias a ciegas. La conclusión honesta es que **el edge, si existe, no está en
indicadores técnicos simples sobre precio a 1h/4h.** Decisión que corresponde al usuario
(Oscar), dos caminos legítimos:
  - **(A) Reorientar el objetivo del proyecto:** la infraestructura construida (datos limpios
    2 años, backtest con costes, walk-forward OOS, benchmark, journal, paper broker) es
    valiosa como HERRAMIENTA de análisis/simulación/journal aunque no haya estrategia ganadora.
    Pivotar de "batir al mercado" a "sandbox honesto de research y gestión de riesgo".
  - **(B) Cambiar los INPUTS, no la estrategia:** si se cree que hay edge, buscarlo donde el
    precio-OHLCV no llega: otros datos (order book/microestructura, funding, on-chain,
    cross-asset, sentimiento), otros horizontes (tick o diario/semanal), con la misma validación
    OOS. Es un proyecto de research mayor, sin garantías.

Mi recomendación: **(A)** salvo que Oscar quiera asumir explícitamente el coste/riesgo de (B).
No recomiendo más familias de TA sobre las mismas velas.

---

## 13. Extensión MULTI-MERCADO + auditoría adversarial (2026-06-11)

A petición de Oscar se extendió el sandbox más allá de cripto. Nuevo `src/marketdata.py`
(yfinance: oro, petróleo, plata, índices/ETF, acciones) con el mismo esquema OHLCV; `ppy`
configurable para anualizar por clase (252 bolsa / 365 cripto). `cross_asset.py` corre la MISMA
validación OOS sobre **16 instrumentos**, diario 2018→2026 (`reports/cross_asset.md` + `.json`).

**Resultado y AUDITORÍA ADVERSARIAL.** El primer reporte concluía "sin edge" pero con un
argumento estadístico flojo. Un panel adversarial de 4 lentes (workflow `cross-asset-adversarial-review`)
lo auditó y obligó a corregirlo. Conclusión final **verificada y matizada**:

- **0/16** baten a buy & hold con Sharpe OOS > 0.5 estable. **7/16** Sharpe+ (≈ azar), **2/16**
  baten B&H en retorno (por beta defensiva).
- **Nula empírica** (mejor real vs mejor de 16 estrategias ALEATORIAS, 500 repeticiones):
  **p-valor del líder = 0.97** → el mejor resultado es indistinguible del (peor que el) azar.
- La media de los 64 Sharpe-por-fold OOS es **−0.12** (41% positivos): tras costes rinden
  **ligeramente bajo cero**, no "en torno a cero" (corrige el argumento erróneo "~8 por azar").
- **Potencia:** SE(Sharpe OOS) ≈ 0.49 → el test solo descarta edges **grandes** (Sharpe ≳ 0.8).
  NO puede descartar edges modestos (0.3-0.5). Por eso la afirmación honesta es **"sin edge
  GRANDE y estable detectable con 4 folds"**, no "sin edge" a secas.
- **Hallazgo de régimen (real):** estas técnicas baten a B&H en **74%** de folds bajistas vs
  **9%** de alcistas → funcionan como **overlay defensivo** (reducen drawdown en caídas), una
  capacidad real distinta de generar alfa. El "ganador" (ETH) lidera solo porque su B&H fue el
  peor (−45%), no por habilidad.
- **Datos:** WTI (`CL=F`) cotizó a precio negativo (−37.63, 2020-04-20) → `marketdata` ahora
  descarta `close<=0`. Los futuros `=F` son back-ajustados NO replicables y redundantes con sus
  ETF; marcados como tales (no cuentan como instrumentos operables distintos).

**Respuesta a "¿cuál mercado tiene más probabilidad de ganar?": ninguno de forma fiable** con
estas estrategias técnicas direccionales en diario; el que parece ganar lo hace por reducir
exposición en un mercado bajista (beta), no por alfa. La gran limitación pendiente: **no se ha
corrido la prueba LIMPIA alfa-vs-beta (cross-sectional / market-neutral long-short entre los 16)**,
que es lo único que separaría "las técnicas no sirven" de "el formato direccional/long-bias es el
problema". Es el siguiente experimento de mayor valor (junto a intradía y momentum estilo CTA con
vol-targeting conectando `src/risk.py` al backtest). 31 tests en verde.

### Prueba LIMPIA alfa-vs-beta: cross-sectional market-neutral (2026-06-11)

`cross_sectional.py`: estrategia dólar/riesgo-neutral (long top-k / short bottom-k por ranking
entre 13 activos replicables). Por construcción la exposición de mercado es ~0, así que un Sharpe
OOS positivo **sería alfa**, no beta. **Auditada por un 2º panel adversarial** (workflow
`cross-sectional-adversarial-audit`), que obligó a corregir dos cosas:
- La v1 (pesos igual-nocional + score de retorno crudo) **medía dispersión de volatilidad**, no
  ranking: la cartera quedaba corta de cripto/Tesla en su rally → −42% era un artefacto, no "el
  momentum no funciona". Corregido en v2: **score estandarizado por vol + pesos inverse-vol**
  (riesgo-neutral). Neutralidad confirmada por regresión: **beta = +0.07**.
- El veredicto "sin alfa" estaba **sobre-afirmado**. Corregido: se reporta el IC del Sharpe OOS.

**Resultado v2 (verificado):** Sharpe OOS **−0.42**, IC95% **[−1.38, +0.54]**, p-nula **0.59**
(indistinguible de rankings aleatorios), beta +0.07. La implementación es limpia (sin look-ahead,
verificado por traza) y la nula está sesgada A FAVOR de la estrategia, así que el negativo es
robusto frente a ella.

**Conclusión honesta y precisa (no sobre-afirmada):** ni siquiera la versión market-neutral bien
especificada muestra alfa OOS positivo; el punto-estimado es negativo y no supera al azar. **PERO**
con SE(Sharpe)≈0.49 y solo 13 activos heterogéneos (6 posiciones), el test está **infra-potenciado**:
el IC contiene valores hasta +0.54, así que esto demuestra "**sin alfa GRANDE detectable**", NO
"cero alfa". La prueba concluyente exigiría universos within-class amplios (S&P500 point-in-time,
top-50 cripto) — fuera del alcance de yfinance+13 tickers. 34 tests en verde.

**Cierre del hilo "¿qué mercado gana?":** tras 3 familias (momentum, reversión, cross-sectional
neutral), 16 mercados direccionales y la prueba limpia alfa-vs-beta, **no hay evidencia de edge
explotable con indicadores técnicos** en este universo/horizonte; lo único robusto es que estas
técnicas actúan como **overlay defensivo** (reducen drawdown en caídas). El proyecto se mantiene
como herramienta honesta (decisión A). Lo que queda abierto NO es "probar otra familia a ciegas"
(p-hacking), sino, si se quisiera, una prueba *bien potenciada* within-class — un proyecto de datos
mayor (membresías de índice point-in-time), no un experimento de sobremesa.

---

## 8. Riesgos y notas

- **Riesgo financiero**: no operes con dinero real hasta validar en paper trading con métricas positivas y estables.
- **Seguridad**: nunca subas claves API a git. Usa variables de entorno / `.env` + permisos mínimos (solo lectura/trade, sin retiros).
- **Aviso**: esto es información técnica, no asesoría financiera. Las probabilidades históricas no garantizan resultados futuros.

---

## 9. Avance Fase 1 (2026-06-10)

Esqueleto funcional entregado y probado:
- `src/`: config, data (CCXT/Binance, precios reales con respaldo sintético offline),
  forecast (baseline momentum+tendencia+RSI), risk, portfolio, broker (PaperBroker
  modelo PnL/margen + esqueleto LiveBroker), journal, engine (orquestador del ciclo).
- `dashboard.py` (Streamlit): portfolio, agregar saldo, conectar monederos/brokers
  (testnet), correr ciclo, aprobar operaciones, mercado y diario.
- `run.py`: ciclo por CLI para tareas programadas.
- `tests/test_core.py`: batería de pruebas (equity=cash+unrealized, PnL, modos,
  kill-switch, filtro de confianz
## 10. Correcciones P0 + Fase 2 (2026-06-11)

- Correcciones de seguridad C1-C5 aplicadas y verificadas con tests:
  C1 (no ejecutar con datos sintéticos), C2 (kill-switch pérdida diaria conectado al journal),
  C3 (take-profit), C4 (fecha vacía en journal + `today_pnl`), C5 (pytest sin fricción).
- Fase 2 entregada: `src/store.py` (histórico Parquet con dedup y detección de huecos),
  `src/backtest.py` + CLI `backtest.py` (señal vectorizada sin look-ahead, costes 0.1%+slippage,
  walk-forward y métricas: retorno, Sharpe, Sortino, max drawdown, win rate, profit factor).
- Suite: **13 tests en verde** (`pytest -q`).

### Cierre real de Fase 2 (2026-06-11)

Se detectó que el "backtest entregado" corría sobre datos **corruptos/sintéticos** (solo
~2000 velas de BTC, contaminadas con tramos a distintos niveles de precio). Causa raíz y
correcciones:

- **Bug de paginación:** `data.fetch_ohlcv` devolvía siempre las últimas N velas y
  `store.update_history` la llamaba en bucle pidiendo lo mismo → dedup → nunca pasaba de
  ~1000 velas. Arreglado: `fetch_ohlcv` acepta `since` (epoch ms) y `update_history` ahora
  hace **backfill paginando hacia delante** desde `now − total·tf` hasta el presente.
- **Contaminación del store:** `update_history` persistía el respaldo sintético cuando no
  había red. Arreglado: si `source != "binance"`, **no se guarda nada** (el histórico nunca
  se contamina). `save_ohlcv` además avisa de saltos de precio >50%.
- CLI `backtest.py`: añadidos `--fresh` (rehacer histórico limpio) y `--symbol A B` multi-símbolo.

**Histórico real descargado** (CCXT/Binance): BTC/USDT y ETH/USDT, 1h, **17.520 velas cada
uno = exactamente 2 años (2024-06-11 → 2026-06-11), 0 huecos, 0 faltantes.**

**Backtest del baseline sobre datos reales (honesto):**

| Símbolo | Retorno | Sharpe | MaxDD | Win rate | PF | Trades |
|---------|---------|--------|-------|----------|----|--------|
| BTC/USDT | −99.03% | −5.18 | −99.15% | 22.6% | 0.72 | 1599 |
| ETH/USDT | −98.90% | −3.26 | −99.17% | 24.1% | 0.84 | 1650 |

Walk-forward (4 segmentos) consistentemente negativo en ambos. **Conclusión honesta: el
baseline simple (momentum+tendencia+RSI a 1h) NO tiene edge neto de costes** — el coste
acumulado de fees+slippage se come el capital (479% en BTC). Esto es exactamente la
información que pide el criterio de salida de Fase 2 y alimenta la Fase 3 (banda muerta/
histéresis para frenar el sobre-trading, validar features, calibrar probabilidad).

- Suite: **16 tests en verde** (+2: paginación forward y rechazo de sintético). Sin bytes nulos.
- **Criterio de salida Fase 2: CUMPLIDO** — backtest reproducible con métricas honestas sobre
  ≥2 años de datos reales sin huecos, recargable con un comando (`python backtest.py --fresh --download 17520 --symbol BTC/USDT ETH/USDT`).

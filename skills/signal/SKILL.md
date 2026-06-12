---
name: signal
description: Analizar un símbolo con las familias de señal del proyecto (momentum, histéresis, régimen ADX, reversión a la media, patrones de velas) y reportar qué dicen — con su validez OOS medida. Usar cuando el usuario pida "señal", "qué dicen los indicadores", "hay edge en este par" o un análisis técnico de un símbolo.
---

# Skill: signal

Análisis ad-hoc por familias de señal. El ciclo automático usa `forecast`; esta skill
explora y compara estrategias sobre un símbolo concreto.

## Código real (usar, no reinventar) — familias en `src/backtest.py`
Todas con la misma interfaz `f(df) -> Series {-1, 0, 1}`:
- `baseline_signal` (momentum+tendencia+RSI, bandas 0.55/0.45) y su núcleo `prob_up`.
- `hysteresis_signal(enter, exit_)` — banda muerta contra el sobre-trading.
- `regime_signal(enter, adx_min)` + `adx` — momentum solo en tendencia.
- `mean_reversion_signal(lookback, entry_z, exit_z)` — contrarian por z-score.
- `candlestick_signal(hold, trend_span)` — envolventes, martillo, estrella fugaz con contexto EMA.

## VEREDICTO VIGENTE (comunicarlo siempre)
Las 5 familias fueron validadas con `src/validation.py::walk_forward_oos` en hasta
16 mercados: **ninguna tiene edge OOS demostrado** (nulas empíricas p=0.97 direccional,
p=0.59 market-neutral; velas 0/6). Lo único robusto: actúan como **overlay defensivo**
(baten a buy & hold en ~74% de tramos bajistas, ~9% de alcistas). Ver pestaña
🧭 Decisiones & Research del dashboard y `MEMORIA_PROYECTO.md` §11-§13.

## Procedimiento
1. Cargar datos reales (skill `market-data`); nunca sintéticos.
2. Calcular la(s) señal(es) pedidas y describir el estado actual (posición que tomaría cada familia).
3. Si se afirma cualquier capacidad predictiva → respaldarla con `walk_forward_oos`,
   no con el estado in-sample. Probabilidad sin validación OOS y tamaño de muestra no vale.

## Reglas
- La señal alimenta la gestión de riesgo; no es una orden ni una recomendación.
- No probar variantes hasta que una "funcione": eso es p-hacking (regla del proyecto).
- Información técnica, no asesoría financiera.

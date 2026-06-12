---
name: backtest
description: Correr backtests de una estrategia sobre datos históricos y validarla out-of-sample (retorno, Sharpe, max drawdown, win rate, profit factor). Usar cuando el usuario diga "backtest", "probar la estrategia", "cómo habría rendido", "validar", "simular sobre histórico" o pida métricas de una idea de trading.
---

# Skill: backtest

Evalúa una estrategia contra datos históricos y la VALIDA out-of-sample. El backtest
in-sample es optimista por naturaleza; el juez real es el walk-forward OOS.

## Código real (usar, no reinventar)
- Motor: `src/backtest.py::run_backtest` (costes 0.1%+0.05%, señal aplicada a la vela
  siguiente, clip de outliers, métricas en `BTMetrics`). Núcleo por ventanas:
  `metrics_from_position` (acepta `ppy` para anualizar: 252 bolsa / 365 cripto en diario).
- **Validación OOS** (obligatoria antes de cualquier conclusión): `src/validation.py::walk_forward_oos`
  — selección por Sharpe de train anclado, evaluación única en test, benchmark buy & hold,
  `verdict()` y `to_markdown()`.
- Familias de señal disponibles (todas `f(df) -> Series {-1,0,1}` en `src/backtest.py`):
  `baseline_signal`, `hysteresis_signal`, `regime_signal` (+`adx`), `mean_reversion_signal`,
  `candlestick_signal`. Núcleo de probabilidad: `prob_up`.
- CLIs: `python backtest.py --symbol A B --tf 1h|4h [--fresh --download N]` (cripto),
  `python cross_asset.py` (16 mercados diario), `python cross_sectional.py` (market-neutral),
  `python candles_validate.py` (velas). UI: pestaña "🔬 Backtest & Validación" del dashboard.

## Procedimiento
1. Cargar datos locales (skill `market-data`); jamás sintéticos (`source == "synthetic"`).
2. Ejecutar `run_backtest` para la vista in-sample y SIEMPRE `walk_forward_oos` para el veredicto.
3. Guardar reporte en `reports/` y anotar el resultado en `MEMORIA_PROYECTO.md`.

## Reglas críticas (evitar engañarse a uno mismo)
- **Sin look-ahead**: la señal en t solo usa datos ≤ t (el motor ya hace `shift(1)`).
- **Costes siempre**; comparar contra **buy & hold**; desconfiar de Sharpe > 3.
- **Multiple testing**: probar muchas variantes y quedarse con la mejor es p-hacking;
  declarar cuántas se probaron. Con 4 folds OOS el test solo descarta edges grandes
  (SE del Sharpe ≈ 0.5): "no detecté edge" ≠ "no hay edge".
- Contexto del proyecto: ninguna familia incluida tiene edge OOS demostrado
  (ver `reports/` y MEMORIA §11-§13). Un resultado in-sample bonito NO cambia eso.

## Salida esperada
Métricas + veredicto OOS honesto + ruta al reporte. Si no es robusto, decirlo claramente.

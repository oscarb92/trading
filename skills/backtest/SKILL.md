---
name: backtest
description: Correr backtests de una estrategia sobre datos históricos y reportar métricas de rendimiento (retorno, Sharpe, max drawdown, win rate, profit factor). Usar cuando el usuario diga "backtest", "probar la estrategia", "cómo habría rendido", "simular sobre histórico" o pida métricas de una idea de trading.
---

# Skill: backtest

Evalúa una estrategia contra datos históricos antes de arriesgar capital.

> Estado: el motor de backtest NO existe aún (Fase 2 de PLAN.md) y requiere primero
> la capa Parquet de Fase 1. No backtestear jamás sobre los datos sintéticos de respaldo.

## Cuándo usar
- Validar una regla/estrategia sobre datos pasados.
- Comparar variantes de parámetros.
- Generar métricas y curva de equity.

## Procedimiento
1. Cargar datos con la skill `market-data` (Parquet local).
2. Definir la estrategia como función `señal(df) -> {-1, 0, 1}` (corto/fuera/largo).
3. Usar `backtesting.py` o `vectorbt` para simular con: comisiones realistas (ej. 0.1%), slippage, y sin look-ahead bias.
4. Calcular métricas: retorno total y anualizado, **Sharpe**, **Sortino**, **max drawdown**, win rate, profit factor, nº de trades.
5. Guardar reporte (métricas + curva de equity) en `reports/`.
6. Anotar el resultado en `MEMORIA_PROYECTO.md`.

## Reglas críticas (evitar engañarse a uno mismo)
- **Sin look-ahead**: la señal en la vela t solo puede usar datos ≤ t.
- **Costes reales**: incluir comisiones y slippage siempre.
- **Out-of-sample**: separar datos de entrenamiento y prueba; no optimizar sobre todo el histórico.
- Desconfiar de Sharpe > 3 o curvas demasiado perfectas: suele ser overfitting o un bug.

## Salida esperada
Tabla de métricas + ruta al reporte. Si las métricas no son robustas, decirlo claramente.

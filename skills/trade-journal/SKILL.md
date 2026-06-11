---
name: trade-journal
description: Registrar cada operación (entrada, salida, motivo, resultado) en un diario persistente y analizar el rendimiento acumulado. Usar cuando el usuario diga "registrar operación", "cómo voy", "estadísticas de mi trading", "diario de trades" o tras cerrar cualquier posición.
---

# Skill: trade-journal

Memoria persistente de operaciones. Es lo que permite aprender y medir el progreso real.

## Cuándo usar
- Tras abrir o cerrar cualquier operación (paper o real).
- Para revisar rendimiento acumulado y patrones.

## Procedimiento
1. Registrar cada trade con `src/journal.py::log_trade` en `journal/trades.csv`. Esquema real:
   `fecha, symbol, evento (open/close), lado, qty, precio, fee, pnl, prob, confianza, modo, nota`.
   No inventar otro esquema; si falta un campo, ampliarlo en `journal.py` primero.
   Métricas acumuladas: `src/journal.py::metrics` (win rate, PnL total, wins/losses).
2. Tras cerrar, calcular y acumular: win rate, PnL total, mejor/peor trade, racha, drawdown.
3. Periódicamente, resumir aprendizajes y anotarlos en `MEMORIA_PROYECTO.md` (sección Bitácora).
4. Detectar patrones: ¿qué señales funcionan?, ¿en qué condiciones se pierde?

## Reglas
- Registrar TODA operación, incluidas las perdedoras (sesgo de supervivencia mata).
- Anotar el "motivo" de entrada: sin él no se puede aprender.
- Nunca borrar histórico; es la base de datos de aprendizaje del proyecto.

## Salida
Confirmación del registro + resumen de métricas acumuladas.

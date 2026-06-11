---
name: risk-manager
description: Calcular tamaño de posición, stop-loss/take-profit y aplicar límites de riesgo antes de enviar una orden. Usar cuando el usuario pregunte "cuánto invierto", "tamaño de posición", "dónde pongo el stop", "cuánto arriesgo" o antes de cualquier ejecución (paper o real).
---

# Skill: risk-manager

Decide CUÁNTO arriesgar. Es la última puerta antes de ejecutar una orden.

## Código real (usar, no reinventar)
`src/risk.py::size_position` ya implementa fracción fija, stop ~1.5×ATR, TP 1:1.5
y límites (`max_per_trade_pct`, `max_open_positions`, `max_daily_loss_pct`).
Ojo: el engine aún no le pasa la pérdida diaria real (corrección C2 en PLAN.md).

## Cuándo usar
- Antes de cada operación (paper o real).
- Para definir stops y límites de exposición.

## Procedimiento
1. Tomar la probabilidad/edge de la skill `signal` y el capital disponible.
2. Calcular tamaño de posición:
   - **Fracción fija** (recomendado al inicio): arriesgar 0.5–1% del capital por operación.
   - **Kelly fraccionado** (avanzado): usar ≤ ½ Kelly para reducir volatilidad.
3. Definir **stop-loss** (p. ej. múltiplo de ATR) y **take-profit** según ratio riesgo/beneficio (mínimo 1:1.5).
4. Aplicar límites duros: máx. exposición por activo, máx. pérdida diaria, nº máx. de posiciones abiertas.
5. Si la operación viola un límite, **rechazarla** y explicar por qué.

## Reglas
- Ninguna operación sin stop definido.
- Preservar capital > maximizar ganancia. Sobrevivir primero.
- Estos cálculos son técnicos, no asesoría financiera; el usuario decide.

## Salida
Tamaño de posición, precio de stop y de objetivo, y veredicto (aprobar/rechazar).

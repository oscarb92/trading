---
name: risk-manager
description: Calcular tamaño de posición, stops, Kelly fraccionado, stress test y exposición/correlación; aplicar límites de riesgo antes de cualquier orden. Usar cuando el usuario pregunte "cuánto invierto", "tamaño de posición", "dónde pongo el stop", "qué pasa si cae un 20%", "cuánto arriesgo" o antes de cualquier ejecución (paper).
---

# Skill: risk-manager

Decide CUÁNTO arriesgar. Es la última puerta antes de ejecutar una orden, y el conjunto
de utilidades informativas de la pestaña 🛡️ Riesgo del dashboard.

## Código real (usar, no reinventar) — todo en `src/risk.py`
- `size_position`: fracción fija, stop ~1.5×ATR, TP 1:1.5, límites (`max_per_trade_pct`,
  `max_open_positions`, `max_daily_loss_pct`). El engine YA le pasa la pérdida diaria real
  (`journal.today_pnl`, corrección C2 resuelta) y desactiva al alcanzar el límite (kill-switch).
- `size_from_risk`: sizing por riesgo fijo con **apalancamiento implícito** (avisar si >1×).
- `kelly_fraction` / `fractional_kelly` (≤ ½ Kelly, cap 20%): **si Kelly = 0, la apuesta
  óptima es NO apostar** — y con el forecast actual (sin edge, probabilidades descalibradas)
  Kelly basado en él sería ruina; no calcularlo con esas probabilidades.
- `stress_test_gap`: shock instantáneo (p.ej. −20%) sobre el portfolio, equity antes/después
  y stops cruzados (caso pesimista: el hueco salta los stops).
- `exposure` y `correlation_matrix`: exposición bruta/neta y correlación de retornos
  (BTC/ETH ≈ 0.82 → diversificación ilusoria entre cripto).

## Procedimiento
1. Tomar capital y propuesta; calcular tamaño con fracción fija (0.5–1% por trade).
2. Stop SIEMPRE definido; ratio mínimo 1:1.5; verificar límites duros de `automation_config.yaml`.
3. Si viola un límite → **rechazar** y explicar. La IA puede reducir riesgo, nunca aumentarlo.

## Reglas
- Preservar capital > maximizar ganancia. Sobrevivir primero.
- Cálculos técnicos, no asesoría financiera; el usuario decide.

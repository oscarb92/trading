---
name: paper-trade
description: Ejecutar órdenes simuladas contra el testnet del exchange y mantener un portfolio virtual. Usar cuando el usuario diga "simular operación", "paper trading", "abrir/cerrar posición simulada", "probar en testnet" o quiera operar sin dinero real.
---

# Skill: paper-trade

Ejecuta órdenes en un entorno simulado (testnet de Binance o motor local) y mantiene el estado del portfolio.

## Código real (usar, no reinventar)
`src/broker.py::PaperBroker` ya implementa apertura/cierre con precios reales,
fees (0.1%) y slippage; el estado persiste en `state/portfolio.json` (`src/portfolio.py`).

## Cuándo usar
- Probar la ejecución de señales sin riesgo real.
- Mantener un portfolio virtual con PnL.

## Procedimiento
1. Recibir la propuesta (skill `forecast`) y el tamaño/stops (skill `risk-manager`).
2. Ejecutar con el **motor local** `PaperBroker` (precios reales de mercado, fees+slippage
   simulados); es lo que usa el engine en `auto_testnet` y la aprobación manual del dashboard.
   El testnet de Binance vía `LiveBroker(testnet=True)` es opcional, solo para probar conexión.
3. Actualizar el portfolio (posición, efectivo, PnL realizado/no realizado) — `Portfolio.save()`.
4. Registrar cada operación con la skill `trade-journal`.

## Reglas
- Saldo simulado: `python run.py --deposit N` o pestaña 💼 Portfolio del dashboard.
- Modelo contable PnL/margen: equity = cash + PnL no realizado (no doble-contar notional).
- Si hay claves de testnet, en `.env`, nunca en git. Validar saldo y límites antes de la orden.
- El paper trading continuo corre con el ciclo EN-APP (toggle en la pestaña 🔄 Ciclo,
  solo mientras el dashboard está abierto).

## Salida
Confirmación de la operación simulada + estado actualizado del portfolio.

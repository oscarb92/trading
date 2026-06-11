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
1. Recibir la predicción (skill `forecast` — es la que usa el ciclo automático) y el tamaño (skill `risk-manager`).
2. Conectar a **Binance Testnet** vía CCXT con claves de testnet, o usar un motor de matching local sobre datos históricos/en vivo.
3. Enviar la orden (market/limit), registrar fills, comisiones simuladas y slippage.
4. Actualizar el portfolio: posición, efectivo, PnL realizado y no realizado.
5. Registrar cada operación con la skill `trade-journal`.

## Reglas
- Usar SIEMPRE el endpoint de testnet en esta fase (`ex.set_sandbox_mode(True)`).
- Claves de testnet ≠ claves reales. Guardarlas en `.env`, nunca en git.
- Validar saldo y límites antes de enviar la orden.

## Salida
Confirmación de la operación simulada + estado actualizado del portfolio.

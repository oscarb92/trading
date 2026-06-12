---
name: auto-trader
description: Orquestador del ciclo de trading automático — encadena datos → predicción → riesgo → decisión y ejecuta según el modo configurado (recomendación, auto_testnet o auto_live). Usar cuando el usuario diga "corre el ciclo", "automatiza", "que opere solo", "revisa el mercado y decide" o cuando lo dispare una tarea programada.
---

# Skill: auto-trader

Cerebro de la automatización. Lee `automation_config.yaml` y ejecuta UNA pasada del ciclo completo.

## Código real (usar, no reinventar)
El ciclo ya está implementado en `src/engine.py::run_cycle`. Ejecutar con:
`python run.py` (CLI) o desde la pestaña 🔄 Ciclo de `dashboard.py`.
**Tarea programada real:** "TradingApp-PaperCycle" (Programador de tareas de Windows,
cada hora, lanza `run_cycle.bat` → log en `logs/cycle.log`).
Esta skill orquesta y reporta; la lógica vive en `src/`.

> Contexto: el forecast baseline NO tiene edge OOS y sus probabilidades están
> descalibradas (skill negativo, ver `src/calibration.py`). El ciclo es una **demo de
> simulación** para ejercitar el flujo paper, no un generador de recomendaciones.

## Cuándo usar
- Cada vez que se dispara la tarea programada.
- Cuando el usuario pide correr el ciclo manualmente.

## Procedimiento (una pasada)
1. **Leer config** (`automation_config.yaml`). Si `enabled: false` → no hacer nada y avisar.
2. Para cada símbolo en `symbols`:
   a. Obtener datos (skill `market-data`).
   b. Generar predicción (skill `forecast`). Si `confianza < forecast.min_confidence` → descartar.
   c. Calcular tamaño y stops (skill `risk-manager`). Verificar límites de `risk`.
3. **Actuar según `mode`**:
   - `recomendacion` → enviar la propuesta con la skill `notify` y ESPERAR aprobación. No ejecutar.
   - `auto_testnet` → ejecutar con `paper-trade` (sandbox) sin pedir permiso.
   - `auto_live` → ejecutar real SOLO si pasa TODOS los límites; si no, rechazar y notificar.
4. Registrar todo con `trade-journal`.
5. Si `schedule.managed_by: ia`, evaluar si conviene ajustar la cadencia (skill `schedule-control`).

## Guardrails (obligatorios)
- Respetar SIEMPRE el kill-switch (`enabled`) y `max_daily_loss_pct` (el engine YA lee la
  pérdida diaria real de `journal.today_pnl` y se desactiva al alcanzarla — C2 resuelta).
- **Nunca ejecutar sobre datos sintéticos**: el engine solo ejecuta si `source == "binance"` (C1).
- `auto_live` está **CONGELADO** por diseño (sin edge OOS demostrado); jamás activarlo ni
  implementar `LiveBroker.open` sin aprobación humana explícita.
- Ante cualquier error o dato faltante: no operar, notificar.
- Toda ejecución en `auto_live` se registra antes y después.

## Salida
Resumen de la pasada: qué se evaluó, qué se decidió, qué se ejecutó o propuso.

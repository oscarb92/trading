---
name: auto-trader
description: Orquestador del ciclo de trading automático — encadena datos → predicción → riesgo → decisión y ejecuta según el modo configurado (recomendación, auto_testnet o auto_live). Usar cuando el usuario diga "corre el ciclo", "automatiza", "que opere solo", "revisa el mercado y decide" o cuando lo dispare una tarea programada.
---

# Skill: auto-trader

Cerebro de la automatización. Lee `automation_config.yaml` y ejecuta UNA pasada del ciclo completo.

## Código real (usar, no reinventar)
El ciclo ya está implementado en `src/engine.py::run_cycle`. Ejecutar con:
`python run.py` (CLI, ideal para tareas programadas) o desde `dashboard.py`.
Esta skill orquesta y reporta; la lógica vive en `src/`.

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
- Respetar SIEMPRE el kill-switch (`enabled`) y `max_daily_loss_pct` (si se alcanza, poner `enabled: false`).
- **Nunca ejecutar sobre datos sintéticos**: si `FetchResult.source == "synthetic"` (red caída), solo proponer con advertencia, jamás operar.
- Verificar la pérdida diaria real desde `journal/trades.csv` antes de abrir posiciones (corrección C2 de PLAN.md mientras no esté en el engine).
- `auto_live` nunca opera fuera de los límites de `risk`, sin excepción.
- Ante cualquier error o dato faltante: no operar, notificar.
- Toda ejecución en `auto_live` se registra antes y después.

## Salida
Resumen de la pasada: qué se evaluó, qué se decidió, qué se ejecutó o propuso.

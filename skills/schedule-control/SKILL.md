---
name: schedule-control
description: Leer y modificar la cadencia y el modo de la automatización en automation_config.yaml, ya sea por orden del usuario o por decisión de la IA según las condiciones del mercado. Usar cuando el usuario diga "cambia la frecuencia", "que revise cada 15 minutos", "pausa la automatización", "actívalo en automático", o cuando la IA deba ajustar el ritmo.
---

# Skill: schedule-control

Controla CUÁNDO y EN QUÉ MODO corre la automatización. Es el panel de mando.

## Cuándo usar
- El usuario pide cambiar frecuencia, modo o pausar/reanudar.
- `schedule.managed_by: ia` y las condiciones aconsejan ajustar el ritmo.

## Procedimiento
1. Leer la config con `src/config.py::load_config` y guardarla con `save_config` (preserva defaults y formato).
2. Aplicar el cambio solicitado:
   - **Frecuencia**: actualizar `schedule.cron` (validar formato cron).
   - **Modo**: cambiar `mode` entre `recomendacion` / `auto_testnet` / `auto_live`.
   - **Encender/apagar**: `enabled: true|false` (kill-switch).
3. Reflejar el cambio en la **tarea programada** real (crear/actualizar el schedule que dispara `auto-trader`).
4. Confirmar al usuario el nuevo estado y anotarlo en `MEMORIA_PROYECTO.md`.

## Ajuste autónomo (si managed_by: ia)
La IA puede subir la frecuencia con alta volatilidad/oportunidad, bajarla en mercados planos,
o **pausar** ante errores repetidos o volatilidad extrema. Cada ajuste autónomo se notifica.

## Reglas de seguridad (no negociables)
- La IA **nunca** cambia sola de `auto_testnet` a `auto_live`: ese salto requiere aprobación explícita del usuario.
- La IA puede pausar/bajar el riesgo de forma autónoma, pero nunca subirlo por encima de los límites de `risk`.
- Todo cambio queda registrado.

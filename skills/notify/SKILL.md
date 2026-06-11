---
name: notify
description: Enviar al usuario recomendaciones de operación, confirmaciones de ejecución y alertas (errores, kill-switch). Usar cuando el modo sea "recomendacion" y haya que pedir aprobación, o cuando ocurra cualquier evento que el usuario deba conocer.
---

# Skill: notify

Canal de comunicación entre la automatización y el usuario.

## Cuándo usar
- Modo `recomendacion`: presentar la propuesta y pedir aprobación.
- Tras una ejecución automática (confirmación).
- Ante errores, límites alcanzados o activación del kill-switch.

## Procedimiento
1. Leer `notifications.channel` y `notify_on` de la config.
2. Componer un mensaje claro y accionable. Para una recomendación incluir:
   - símbolo y lado (largo/corto),
   - predicción + probabilidad + confianza,
   - tamaño propuesto, stop-loss y objetivo,
   - razón resumida,
   - acción requerida: **Aprobar / Rechazar / Ajustar**.
3. En modo `recomendacion`, NO ejecutar hasta recibir aprobación explícita.
4. Registrar la notificación y la respuesta en `trade-journal`.

## Reglas
- Mensajes cortos y sin ambigüedad: el usuario debe poder decidir en segundos.
- Las alertas críticas (kill-switch, error) se envían siempre, ignorando filtros.

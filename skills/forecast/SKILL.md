---
name: forecast
description: Generar la predicción del baseline (dirección, probabilidad, confianza) que consume el ciclo automático, y explicar su (falta de) fiabilidad medida. Usar cuando el usuario pida "predicción", "qué va a pasar con", "pronóstico", "probabilidad de subida" o cuando el ciclo necesite una previsión.
---

# Skill: forecast

Produce la PREDICCIÓN que alimenta el ciclo (engine). Distinta de `signal`: `forecast` es
la salida formal del baseline; `signal` es análisis ad-hoc por familias de estrategia.

## Código real (usar, no reinventar)
- `src/forecast.py::predict` (momentum+tendencia+RSI → dirección, probabilidad, confianza).
  Réplica vectorizada del núcleo en `src/backtest.py::prob_up` — si se toca una, sincronizar la otra.
- **Calibración MEDIDA:** `src/calibration.py::reliability` (curva de fiabilidad + Brier).

## VEREDICTO VIGENTE (no opcional al comunicar)
Las probabilidades del baseline están **descalibradas con skill NEGATIVO** (BTC 1h −12.6%,
BTC 4h −23.1%, ETH 1h −18.0%, ETH 4h −30.1%): la frecuencia observada se queda en ~50%
diga lo que diga el modelo. Por tanto:
- **NUNCA** presentar `probability`/`confidence` como probabilidades reales.
- **NUNCA** usarlas para sizing (Kelly) ni como filtro de "confianza" con significado.
- Toda salida al usuario debe etiquetarlas como *score sin calibrar* (la pestaña Ciclo
  del dashboard ya lo hace con su banner y el expander de calibración).

## Procedimiento
1. Cargar datos reales (skill `market-data`); si `source == "synthetic"`, solo proponer con advertencia.
2. Llamar a `forecast.predict` y devolver dirección + score, SIEMPRE con el descargo de calibración.
3. Si el usuario quiere una probabilidad fiable: explicar que requiere un modelo nuevo
   validado con `walk_forward_oos` y calibrado con `reliability` — hoy no existe.

## Aviso
Información técnica, no asesoría financiera. El baseline no tiene edge OOS demostrado.

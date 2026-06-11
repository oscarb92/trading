---
name: signal
description: Calcular indicadores técnicos y estimar la probabilidad/edge de un movimiento para un símbolo. Usar cuando el usuario pida "señal", "probabilidad de subida", "qué dicen los indicadores", "hay edge en este par" o quiera una recomendación de entrada/salida basada en datos.
---

# Skill: signal

Convierte datos de mercado en una señal accionable con una estimación de probabilidad.

> Rol vs `forecast`: esta skill es para análisis ad-hoc cuando el usuario pregunta por un
> símbolo. El ciclo automático usa `forecast` (`src/forecast.py`). Reutilizar ese código
> como base para no duplicar lógica de indicadores.

## Cuándo usar
- Evaluar si hay edge en un símbolo ahora mismo.
- Generar la señal que consumen `paper-trade` o `risk-manager`.

## Procedimiento
1. Cargar datos recientes (skill `market-data`).
2. Calcular indicadores con `ta` o `pandas-ta`: medias (EMA), RSI, MACD, ATR, bandas de Bollinger, volumen.
3. Combinar en una regla o modelo. Para "probabilidad" usar:
   - Frecuencia histórica condicionada (p. ej. "tras esta señal, % de velas siguientes al alza"), o
   - Un modelo simple (regresión logística / gradient boosting) sobre features, con validación temporal.
4. Devolver: dirección (`largo`/`corto`/`fuera`), **probabilidad estimada**, y el **edge esperado** (prob × payoff − coste).
5. Ser explícito sobre la incertidumbre y el tamaño de muestra.

## Reglas
- Una probabilidad sin tamaño de muestra ni validación out-of-sample no vale: reportarlos siempre.
- No confundir correlación histórica con predicción garantizada.
- La señal alimenta la gestión de riesgo, no es una orden directa.

## Aviso
Información técnica, no asesoría financiera.

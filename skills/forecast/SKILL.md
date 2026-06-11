---
name: forecast
description: Generar una predicción del movimiento futuro de un símbolo con su probabilidad y nivel de confianza, en un horizonte dado. Usar cuando el usuario pida "predicción", "qué va a pasar con", "pronóstico", "probabilidad de subida en las próximas horas" o cuando el ciclo automático necesite una previsión.
---

# Skill: forecast

Produce la PREDICCIÓN que alimenta la decisión. Distinta de `signal`: `forecast` es la
predicción formal que consume el ciclo automático (engine); `signal` es análisis ad-hoc
de indicadores/edge cuando el usuario pregunta por un símbolo.

## Código real (usar, no reinventar)
Baseline implementado en `src/forecast.py::predict` (momentum+tendencia+RSI →
dirección, probabilidad, confianza). Sus probabilidades NO están validadas aún:
no presentarlas como fiables hasta pasar el backtesting de Fase 2.

## Cuándo usar
- Antes de decidir una operación (manual o automática).
- Para responder "¿qué probabilidad hay de X en el horizonte Y?".

## Procedimiento
1. Cargar datos (skill `market-data`) y construir features: retornos, volatilidad (ATR), momentum (RSI/MACD), volumen, régimen de mercado.
2. Aplicar un modelo de predicción:
   - **Base**: frecuencia histórica condicionada (qué pasó tras estados similares).
   - **Avanzado**: clasificador (regresión logística / gradient boosting) o modelo de series temporales, con **validación temporal** (walk-forward), nunca aleatoria.
3. Devolver para el horizonte `forecast.horizon`:
   - dirección esperada (alza/baja/lateral),
   - **probabilidad** estimada,
   - **confianza** (calibrada; p. ej. tamaño de muestra + estabilidad del modelo),
   - rango esperado (intervalo).
4. Si la confianza < `forecast.min_confidence`, marcar como "sin operar".

## Reglas anti-autoengaño
- Validación temporal obligatoria; nada de mirar el futuro.
- Reportar siempre incertidumbre y tamaño de muestra.
- Una predicción NO es una garantía; es una apuesta con probabilidad.

## Aviso
Información técnica, no asesoría financiera.

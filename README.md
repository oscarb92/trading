# Trading App — Fase 1 (simulación con precios reales)

Esqueleto funcional: datos reales (CCXT/Binance), predicción base, gestión de
riesgo, motor de paper trading con saldo simulado, diario y **dashboard**.

## Instalación

```bash
cd trading-app
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Arrancar el dashboard

```bash
streamlit run dashboard.py
```

Se abre en el navegador. Desde ahí puedes:
1. **Agregar saldo** simulado (pestaña Portfolio).
2. **Conectar monederos/brokers** en testnet (pestaña Monederos).
3. **Correr el ciclo** y aprobar operaciones (pestaña Ciclo).
4. Ver **mercado** (precios reales) y el **diario** de operaciones.

## Correr el ciclo sin interfaz (para tareas programadas)

```bash
python run.py                 # una pasada con la config actual
python run.py --deposit 1000  # agregar saldo simulado
```

## Modos (en `automation_config.yaml` o desde el dashboard)

| Modo | Qué hace |
|------|----------|
| `recomendacion` | Propone operaciones y esperas tu aprobación. |
| `auto_testnet` | Ejecuta solo en paper (precios reales, saldo simulado). |
| `auto_live` | Real — **bloqueado en Fase 1** hasta validar. |

El interruptor `enabled` es el kill-switch: si está en `false`, no opera en modo automático.

## Estructura

```
trading-app/
  automation_config.yaml   # config de automatización (modo, schedule, riesgo)
  dashboard.py             # interfaz Streamlit
  run.py                   # ciclo por línea de comandos
  src/
    config.py  data.py  forecast.py  risk.py
    portfolio.py  broker.py  journal.py  engine.py
  skills/                  # definiciones de skills (instalar en Ajustes → Capacidades)
  state/  journal/  data/  # se crean al usar la app
```

## Seguridad

- Claves SIEMPRE de testnet/paper en esta fase, sin permiso de retiro.
- `.env` y `state/` están en `.gitignore`: no subas claves ni estado.
- El paso de testnet → real exige cambiar a `auto_live` con aprobación explícita (Fase 6).

> Información técnica, no asesoría financiera. La simulación con datos históricos
> o en vivo no garantiza resultados futuros.

## Notas sobre el modelo de predicción

`src/forecast.py` es un **baseline** honesto (momentum + tendencia + RSI → probabilidad
y confianza). Sirve para validar el flujo completo. En la Fase 3 se sustituye por un
modelo con validación temporal (walk-forward) y backtesting riguroso.

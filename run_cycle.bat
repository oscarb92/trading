@echo off
rem Lanzador del ciclo de paper trading para el Programador de tareas de Windows.
rem Corre UNA pasada (datos -> forecast -> riesgo -> decision) y la registra en logs\cycle.log.
rem Pausar: deshabilitar la tarea "TradingApp-PaperCycle" en el Programador de tareas,
rem o apagar el kill-switch (enabled: false) en el dashboard / automation_config.yaml.
cd /d "%~dp0"
if not exist logs mkdir logs
echo ===== %date% %time% ===== >> logs\cycle.log
python run.py >> logs\cycle.log 2>&1

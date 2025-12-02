@echo off
title ROBOT DE MANTENIMIENTO SIGB
color 0A

echo ==========================================
echo      INICIANDO ROBOT AUTOMATICO SIGB
echo ==========================================
echo.

:: 1. Navegar a la carpeta del proyecto
cd /d "C:\Users\fitot\OneDrive\Escritorio\Biblioteca-SIGB"

:: 2. Activar el entorno virtual
call .venv\Scripts\activate

:: 3. Ejecutar Robot de Limpieza (Cancela reservas no retiradas)
echo [1/3] Procesando reservas vencidas...
python manage.py procesar_vencidos
echo.

:: 4. Ejecutar Robot Preventivo (Avisa devoluciones de mañana)
echo [2/3] Enviando alertas preventivas...
python manage.py alerta_preventiva
echo.

:: 5. Ejecutar Robot de Cobranza (Avisa a los morosos) <-- ESTE FALTABA
echo [3/3] Enviando correos de cobranza por atraso...
python manage.py alerta_atrasos
echo.

echo ==========================================
echo          PROCESO FINALIZADO
echo ==========================================

:: Esperar 10 segundos para leer resultados
timeout /t 10
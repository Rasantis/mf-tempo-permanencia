@echo off

rem ====================================================================================================
rem Mais Fluxo Vehicle Counter
rem Criado por: Diorgenes de Abreu <diorgenes.abreu@maisfluxo.com.br>
rem Data: 2024-08-12 11h00min
rem ====================================================================================================

rem Parâmetros
set camera=camera2
set url="rtsp://admin:mf6538dm@192.168.1.12:554/cam/realmonitor?channel=1&subtype=0"
set app_dir=C:\Users\maisfluxo\Desktop\executavel
title MaisFluxo_PixForce_DesenharArea_TempoPermanencia_%camera%
cls

rem Execução App
cd %app_dir%
python.exe desenhar_area.py --source %url% --output %app_dir%\area\%camera%_area_tp.json
exit
@echo off

rem ====================================================================================================
rem Mais Fluxo Vehicle Counter
rem Criado por: Diorgenes de Abreu <diorgenes.abreu@maisfluxo.com.br>
rem Data: 2024-08-12 11h00min
rem ====================================================================================================

rem Parâmetros
set app_dir=C:\Users\maisfluxo\Desktop\executavel
set days_keep=120
title MaisFluxo_PixForce_ExportTempoPermanencia
cls

rem Execução App
cd %app_dir%
python.exe api_tempopermanencia.py --db_path %app_dir%\yolo8.db
exit
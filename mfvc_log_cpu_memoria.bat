@echo off

rem ====================================================================================================
rem Mais Fluxo Vehicle Counter
rem Criado por: Diorgenes de Abreu <diorgenes.abreu@maisfluxo.com.br>
rem Data: 2024-08-12 11h00min
rem ====================================================================================================

rem Parâmetros
set app_dir=C:\Users\maisfluxo\Desktop\executavel
title MaisFluxo_PixForce_Memoria_Log
cls

rem Execução App
cd %app_dir%
python.exe log_cpu_memoria.py
exit
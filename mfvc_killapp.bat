@echo off

rem ====================================================================================================
rem Mais Fluxo Vehicle Counter
rem Criado por: Diorgenes de Abreu <diorgenes.abreu@maisfluxo.com.br>
rem Data: 2024-08-28 09h00min
rem ====================================================================================================

title MaisFluxo_PixForce_VehicleCounter_KillApp
cls

rem Finaliza Execução App
taskkill /f /t /im "yolo8.exe"
taskkill /f /t /im "python.exe"
taskkill /f /t /im "cmd.exe"
exit
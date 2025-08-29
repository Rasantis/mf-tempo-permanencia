@echo off

rem ====================================================================================================
rem Mais Fluxo Vehicle Counter
rem Criado por: Diorgenes de Abreu <diorgenes.abreu@maisfluxo.com.br>
rem Data: 2024-08-28 09h00min
rem ====================================================================================================

title MaisFluxo_DeleteTemp
cls

rem Deleta Arquivos Temporarios
del /s /q /f %temp%\*.*
del /s /q /f %temp%\*.*
exit
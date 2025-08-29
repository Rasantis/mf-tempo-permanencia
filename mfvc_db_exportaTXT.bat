@echo off

rem ====================================================================================================
rem Mais Fluxo Vehicle Counter
rem Criado por: Diorgenes de Abreu <diorgenes.abreu@maisfluxo.com.br>
rem Data: 2024-08-12 11h00min
rem ====================================================================================================

rem Parâmetros
set empresa=1724
set app_dir=C:\Users\maisfluxo\Desktop\executavel
set txt_dir=C:\MaisFluxoLocal\RetornoTXT
set days_keep=120
title MaisFluxo_PixForce_ExportTXT
cls

rem Execução App
cd %app_dir%
python.exe dbexport_halfhour.py --client_code %empresa% --db_path %app_dir%\yolo8.db --output_directory %txt_dir% --days_to_keep %days_keep%
exit
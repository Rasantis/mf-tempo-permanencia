@echo off

rem ====================================================================================================
rem Mais Fluxo Vehicle Counter
rem Criado por: Diorgenes de Abreu <diorgenes.abreu@maisfluxo.com.br>
rem Data: 2024-08-02 16h00min
rem ====================================================================================================

rem Parâmetros
set camera=camera1
set app_dir=C:\Users\maisfluxo\Desktop\executavel
set video_dir=D:\PixForce\videos
set url="rtsp://admin:mf6538dm@192.168.1.11:554/cam/realmonitor?channel=1&subtype=0"
title MaisFluxo_PixForce_VehicleCounter_%camera%
cls

:loop
rem Execução App
cd %app_dir%
python.exe yolo16_v4.py --video_path %url% --model_path %app_dir%\modelo_mf_imgsz1280.pt --config_path %app_dir%\config\%camera%_config.json --area_config_path %app_dir%\area\%camera%_area.json --db_path %app_dir%\yolo8.db --output_dir %video_dir%\%camera% --save_video true --video_interval 30 --output_width 640 --output_height 358 --permanencia_config_path %app_dir%\area\%camera%_area_tp.json

IF %ERRORLEVEL% EQU 0 ( 
  echo OK
) ELSE ( 
  goto loop
)

exit
@echo off
title MaisFluxo - Delete Videos, TXT e Logs
cls
rem Vídeos
FORFILES /S /p D:\PixForce\videos\ /d -30 /m *.avi /c "CMD /C DEL /F /S @FILE /Q"
FORFILES /S /p C:\Users\mfmonitor\AppData\Roaming\iSpy\WebServerRoot\Media\video\ /d -60 /m *.mp4 /c "CMD /C DEL /F /S @FILE /Q"

rem TXT
FORFILES /S /p C:\MaisFluxoLocal\Historico\ /d -120 /m *.txt /c "CMD /C DEL /F /S @FILE /Q"

rem LOGS
FORFILES /S /p C:\MaisFluxoLocal\PastaAplicacao\log\ /d -90 /m *.log /c "CMD /C DEL /F /S @FILE /Q"
FORFILES /S /p C:\MaisFluxoLocal\snapshot\log\ /d -60 /m *.log /c "CMD /C DEL /F /S @FILE /Q"

exit
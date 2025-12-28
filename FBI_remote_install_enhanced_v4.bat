@echo off
setlocal EnableExtensions
chcp 65001 >nul

REM Drag-drop file/folder onto this .bat. If nothing was dropped, use current folder.
set TARGET=%~1
if "%TARGET%"=="" set TARGET=.

echo.
echo ==========================================================
echo   FBI Remote Install (Enhanced v4 - IP history picker)
echo ==========================================================
echo Target: %TARGET%
echo.
echo Once running:
echo   R + Enter = re-send URLs
echo   Q + Enter = quit
echo.

python servefiles_enhanced_v4.py "%TARGET%" --ack-wait 2 --retries 5 --retry-delay 1 --chunk-kb 256

echo.
echo Press any key to close...
pause >nul

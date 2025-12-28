@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%"
set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=."
set "PYEXE="
where py >nul 2>nul && set "PYEXE=py -3"
if not defined PYEXE where python3 >nul 2>nul && set "PYEXE=python3"
if not defined PYEXE where python >nul 2>nul && set "PYEXE=python"
if not defined PYEXE (
  echo Python is not installed.
  echo https://www.python.org/downloads/windows/
  echo https://apps.microsoft.com/search?query=python
  pause
  exit /b
)
echo FBI Remote Installer Enhanced
%PYEXE% "%SCRIPT_DIR%servefiles.py" "%TARGET%"
popd
pause

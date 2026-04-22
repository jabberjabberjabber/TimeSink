@echo off
setlocal

set "ROOT=%~dp0"
set "PYDIR=%ROOT%python"
set "PYTHON=%PYDIR%\python.exe"

if not exist "%PYTHON%" call :install_python
if errorlevel 1 pause & exit /b 1

"%PYTHON%" -m pip install Pillow -q --disable-pip-version-check
"%PYTHON%" "%ROOT%launcher.py"
goto :eof

:: ─────────────────────────────────────────────────────────────────────────────
:install_python
echo Downloading Python 3.11.9...
curl -L --progress-bar -o "%TEMP%\timesink-python.exe" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
if errorlevel 1 echo Download failed. & exit /b 1

echo Installing Python (this takes about a minute)...
"%TEMP%\timesink-python.exe" /quiet InstallAllUsers=0 TargetDir="%PYDIR%" PrependPath=0 Include_launcher=0 Include_test=0 Include_doc=0
if errorlevel 1 echo Installation failed. & exit /b 1
del "%TEMP%\timesink-python.exe"
echo Python ready.
exit /b 0

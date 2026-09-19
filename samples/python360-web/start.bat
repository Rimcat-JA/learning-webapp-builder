@echo off
setlocal
cd /d "%~dp0"
title Python 360 - Local Practice
echo Starting Python 360...
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys;sys.exit(0 if sys.version_info >= (3,8) else 1)" >nul 2>nul
  if not errorlevel 1 goto run_py
)
where node >nul 2>nul
if not errorlevel 1 goto run_node
where python >nul 2>nul
if not errorlevel 1 (
  python -c "import sys;sys.exit(0 if sys.version_info >= (3,8) else 1)" >nul 2>nul
  if not errorlevel 1 goto run_python
)
where python3 >nul 2>nul
if not errorlevel 1 (
  python3 -c "import sys;sys.exit(0 if sys.version_info >= (3,8) else 1)" >nul 2>nul
  if not errorlevel 1 goto run_python3
)
echo.
echo Python 3.8+ or Node.js 18+ is required.
echo Install either runtime, then double-click start.bat again.
echo No pip install or npm install is required to run this app.
echo See README.md for details.
pause
exit /b 1
:run_py
py -3 "%~dp0server.py" %*
goto finished
:run_python
python "%~dp0server.py" %*
goto finished
:run_python3
python3 "%~dp0server.py" %*
goto finished
:run_node
node "%~dp0server.mjs" %*
:finished
set "app_exit=%errorlevel%"
if not "%app_exit%"=="0" (
  echo.
  echo The app could not start. See the message above.
  pause
)
exit /b %app_exit%

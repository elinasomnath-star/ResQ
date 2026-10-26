@echo off
setlocal
for %%I in ("%~dp0..") do set "RESQ_ROOT=%%~fI"
set "UV_CACHE_DIR=%RESQ_ROOT%\.uv-cache"
set "PYTHONPATH=%RESQ_ROOT%\src;%RESQ_ROOT%\.deps;%PYTHONPATH%"
set "RESQ_PYTHON="

where python >nul 2>nul
if not errorlevel 1 (
  python -c "import sys,rasterio,shapely,sklearn,ortools; raise SystemExit(sys.version_info[:2] != (3,11))" >nul 2>nul
  if not errorlevel 1 set "RESQ_PYTHON=python"
)

if not defined RESQ_PYTHON (
where uv >nul 2>nul
if not errorlevel 1 (
  pushd "%SystemDrive%\"
  for /f "usebackq delims=" %%P in (`uv python find --managed-python 3.11`) do set "RESQ_PYTHON=%%P"
  popd
)
)

if not defined RESQ_PYTHON (
  where py >nul 2>nul
  if not errorlevel 1 set "RESQ_PYTHON=py"
)

if not defined RESQ_PYTHON (
  echo Python 3.11 or uv was not found. Install Python 3.11 or uv, then install requirements.txt.
  exit /b 1
)

if "%RESQ_PYTHON%"=="py" (
  py -3.11 -m resq.phase2 %*
) else (
  "%RESQ_PYTHON%" -m resq.phase2 %*
)
exit /b %ERRORLEVEL%

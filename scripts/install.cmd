@echo off
REM glyphboost installer for Windows
REM Creates a local venv with rapidocr + onnxruntime (CPU only).
REM Usage: install.cmd [--mirror pypi.tuna.tsinghua.edu.cn/simple]
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0.."
set "MIRROR="

:parse
if "%~1"=="" goto afterparse
if /i "%~1"=="--mirror" (
  set "MIRROR=%~2"
  shift
  shift
  goto parse
)
echo unknown option: %~1
exit /b 1
:afterparse

set "PY=python"
where python >nul 2>nul
if errorlevel 1 (
  echo python not found in PATH. Install Python 3.10+ from python.org first.
  exit /b 1
)

set "VENV=%SCRIPT_DIR%\.venv"
if not exist "%VENV%" (
  echo [1/3] creating venv at %VENV% ...
  python -m venv "%VENV%"
) else (
  echo [1/3] venv already exists, reusing
)

set "PIP_ARGS="
if not "%MIRROR%"=="" set "PIP_ARGS=-i https://%MIRROR%"

echo [2/3] installing rapidocr + onnxruntime ^(CPU^) ...
"%VENV%\Scripts\python.exe" -m pip install --quiet %PIP_ARGS% rapidocr onnxruntime
if errorlevel 1 (
  echo install failed. try a mirror: install.cmd --mirror mirrors.aliyun.com/pypi/simple/
  exit /b 1
)

echo [3/3] verifying ...
"%VENV%\Scripts\python.exe" -c "from rapidocr import RapidOCR; import cv2, numpy; print('glyphboost deps OK:', 'cv2', cv2.__version__, '| numpy', numpy.__version__)"
if errorlevel 1 exit /b 1

echo done. run: %VENV%\Scripts\python.exe %SCRIPT_DIR%\scripts\glyphboost.py IMAGE.png
endlocal

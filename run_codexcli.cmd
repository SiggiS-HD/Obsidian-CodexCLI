@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem CodexCLI launcher for DEV+PROD.
rem - For local repos, prefers repo-local venv if present.
rem - For UNC/NAS repos, prefers a stable local venv under %LOCALAPPDATA%\%CODEXCLI_VENV%\CodexCLI.
rem - Provides clear errors when paths are wrong (common when copying to NAS).

rem Local venv base folder (user-specific). Adjust this if you use a different Obsidian/Vault environment.
rem You can also override it per-call by setting CODEXCLI_VENV before invoking this script.
if not defined CODEXCLI_VENV set "CODEXCLI_VENV=Siggiverse"

set "CODEXCLI_HOME=%~dp0"
set "MAIN_PY=%~dp0main.py"

if not exist "%MAIN_PY%" (
  echo [CodexCLI] ERROR: main.py nicht gefunden.
  echo [CodexCLI] Erwartet: "%MAIN_PY%"
  exit /b 2
)

set "LOCAL_VENV_PATH=%LOCALAPPDATA%\%CODEXCLI_VENV%\CodexCLI\.venv"
set "LOCAL_PYTHON_EXE=%LOCAL_VENV_PATH%\Scripts\python.exe"
set "REPO_PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
set "PYTHON_EXE="

rem UNC paths typically mean the repo lives on a NAS; prefer the local per-user venv there.
if "%CODEXCLI_HOME:~0,2%"=="\\" (
  call :use_local_venv
  if defined PYTHON_EXE goto have_python
  call :use_repo_venv
  if defined PYTHON_EXE (
    echo [CodexCLI] Hinweis: Repo-.venv auf UNC/NAS gefunden. Lokale venv waere robuster.
    goto have_python
  )
) else (
  call :use_repo_venv
  if defined PYTHON_EXE goto have_python
  call :use_local_venv
  if defined PYTHON_EXE goto have_python
)

call :bootstrap_local_venv
if exist "%LOCAL_PYTHON_EXE%" (
  set "PYTHON_EXE=%LOCAL_PYTHON_EXE%"
  goto have_python
)

echo [CodexCLI] ERROR: Keine passende Python-venv gefunden.
echo [CodexCLI] Geprueft:
echo   - "%LOCALAPPDATA%\%CODEXCLI_VENV%\CodexCLI\.venv\Scripts\python.exe"
echo   - "%~dp0.venv\Scripts\python.exe"
echo [CodexCLI] Hinweis: CODEXCLI_VENV ist aktuell "%CODEXCLI_VENV%". Passe diese Variable an, falls du eine andere Umgebung nutzt.
exit /b 2

:have_python

rem OpenAI API key fallback mapping for image generation.
rem Direct access to Obsidian keyring entries is not possible from this script.
rem If OPENAI_API_KEY is not set, accept alternative env names and map them.
if not defined OPENAI_API_KEY (
  if defined CODEXCLI_OPENAI_API_KEY set "OPENAI_API_KEY=%CODEXCLI_OPENAI_API_KEY%"
)
if not defined OPENAI_API_KEY (
  if defined OBSIDIAN_OPENAI_API_KEY set "OPENAI_API_KEY=%OBSIDIAN_OPENAI_API_KEY%"
)

rem Default OCR env (only if not already set)
if not defined CODEXCLI_TESSERACT_CMD (
  if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    set "CODEXCLI_TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe"
  )
)

if not defined CODEXCLI_OCR_LANG (
  set "CODEXCLI_OCR_LANG=deu+eng"
)

rem Best-effort Poppler autodetect when not provided.
if not defined CODEXCLI_POPPLER_PATH (
  for /f "usebackq delims=" %%P in (`where pdftoppm 2^>nul`) do (
    echo %%P | findstr /I /C:"\\WinGet\\Packages\\oschwartz10612.Poppler" >nul && (
      for %%D in ("%%P") do set "CODEXCLI_POPPLER_PATH=%%~dpD"
      goto poppler_done
    )
    echo %%P | findstr /I /C:"\\poppler-" >nul && (
      for %%D in ("%%P") do set "CODEXCLI_POPPLER_PATH=%%~dpD"
      goto poppler_done
    )
  )
)
:poppler_done

rem Prefer Poppler tools (pdftoppm) from CODEXCLI_POPPLER_PATH over other providers (Xpdf/MiKTeX).
rem This avoids ambiguous environments where 'where pdftoppm' finds multiple binaries.
if defined CODEXCLI_POPPLER_PATH (
  set "PATH=%CODEXCLI_POPPLER_PATH%;%PATH%"
)

if "%~1"=="" (
  echo [CodexCLI] Usage:
  echo   "%~nx0" append "<note.md>"
  echo   "%~nx0" update_summary "<note.md>"
  echo   "%~nx0" fix_latex "<note.md>"
  echo.
  echo [CodexCLI] Hinweis: Im Obsidian Shell Command den Note-Pfad i.d.R. in Anfuehrungszeichen setzen.
  exit /b 1
)

"%PYTHON_EXE%" "%MAIN_PY%" %*
exit /b %ERRORLEVEL%

:use_local_venv
if exist "%LOCAL_PYTHON_EXE%" set "PYTHON_EXE=%LOCAL_PYTHON_EXE%"
exit /b 0

:use_repo_venv
if exist "%REPO_PYTHON_EXE%" set "PYTHON_EXE=%REPO_PYTHON_EXE%"
exit /b 0

:bootstrap_local_venv
rem Create a stable local venv and install requirements when running from NAS/UNC.
rem This is intentionally minimal and only triggers when the local venv is missing.

echo [CodexCLI] Hinweis: Lokale venv fehlt. Bootstrappe venv + requirements...
echo [CodexCLI] Ziel: "%LOCAL_VENV_PATH%"

set "BASE_PYTHON="
where py >nul 2>nul && set "BASE_PYTHON=py"
if not defined BASE_PYTHON (
  where python >nul 2>nul && set "BASE_PYTHON=python"
)

if not defined BASE_PYTHON (
  echo [CodexCLI] ERROR: Konnte weder "py" noch "python" finden.
  echo [CodexCLI] Installiere Python 3.12 und stelle sicher, dass es im PATH ist.
  exit /b 2
)

rem Ensure parent folder exists
if not exist "%LOCALAPPDATA%\%CODEXCLI_VENV%\CodexCLI" (
  mkdir "%LOCALAPPDATA%\%CODEXCLI_VENV%\CodexCLI" >nul 2>nul
)

"%BASE_PYTHON%" -m venv "%LOCAL_VENV_PATH%"
if errorlevel 1 (
  echo [CodexCLI] ERROR: venv-Erstellung fehlgeschlagen.
  exit /b 2
)

if not exist "%LOCAL_PYTHON_EXE%" (
  echo [CodexCLI] ERROR: venv wurde erstellt, aber python.exe wurde nicht gefunden.
  echo [CodexCLI] Erwartet: "%LOCAL_PYTHON_EXE%"
  exit /b 2
)

"%LOCAL_PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 (
  echo [CodexCLI] ERROR: pip Upgrade fehlgeschlagen.
  exit /b 2
)

if not exist "%CODEXCLI_HOME%requirements.txt" (
  echo [CodexCLI] ERROR: requirements.txt nicht gefunden.
  echo [CodexCLI] Erwartet: "%CODEXCLI_HOME%requirements.txt"
  exit /b 2
)

"%LOCAL_PYTHON_EXE%" -m pip install -r "%CODEXCLI_HOME%requirements.txt"
if errorlevel 1 (
  echo [CodexCLI] ERROR: pip install -r requirements.txt fehlgeschlagen.
  exit /b 2
)

echo [CodexCLI] Bootstrap abgeschlossen.
exit /b 0

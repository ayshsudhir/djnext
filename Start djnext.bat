@echo off
REM Double-click to start djnext on Windows. First run installs everything (a few minutes).
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version >nul 2>nul || (
  echo Python 3 is needed: install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
if not exist ".venv\Scripts\djnext.exe" (
  echo First start: installing djnext ^(only happens once^)...
  %PY% -m venv .venv || goto fail
  ".venv\Scripts\python.exe" -m pip install --upgrade pip -q
  ".venv\Scripts\pip.exe" install -e . -q || goto fail
)
".venv\Scripts\djnext.exe" app
exit /b 0
:fail
echo Install failed. Send a screenshot of this window to whoever shared djnext with you.
pause
exit /b 1

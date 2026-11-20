@echo off
setlocal EnableExtensions DisableDelayedExpansion
REM Development Opportunity Finder - Windows starter. Double-click it.
REM   start-windows.bat /check         non-interactive preflight: build .venv, install packages, run the setup check, exit
REM   start-windows.bat /which-python  only show which Python it would use, then exit
REM What it runs, in order (nothing is sent anywhere except pip downloading the packages in requirements.txt):
REM   1) refuses to run from inside the zip or a temporary folder
REM   2) finds Python 3.10+ : EBRE_PYTHON if you set it, then py -3, then every "python" / "python3" on PATH
REM      (each one is version-checked, including the Microsoft Store stubs in \WindowsApps\), then the usual install folders
REM   3) makes a private .venv folder here and installs requirements.txt into it
REM   4) runs scripts\doctor.py (setup check, saved to setup_check.txt in this folder)
REM   5) checks for Git Bash and Claude Code, then starts Claude Code in this folder
REM If Windows shows "Windows protected your PC" (SmartScreen): click "More info", then "Run anyway".
set "CHECK=0"
set "WHICH=0"
if /i "%~1"=="/check" set "CHECK=1"
if /i "%~1"=="--check" set "CHECK=1"
if /i "%~1"=="/which-python" set "WHICH=1"
if /i "%~1"=="--which-python" set "WHICH=1"
if "%WHICH%"=="1" set "CHECK=1"
echo ==================================================================
echo  Development Opportunity Finder - setup
echo  You need: Python 3.10 or newer, and Claude Code.
echo  Claude Code needs a PAID Claude plan (Pro, Max, Team or Enterprise)
echo  or an Anthropic Console account with API billing. The free Claude
echo  plan does not include Claude Code.
echo ==================================================================
set "HERE=%~dp0"
echo Folder: %HERE%
REM Refuse to run from the zip preview or a temporary folder.
if /i not "%HERE:\AppData\Local\Temp\=%"=="%HERE%" goto inzip
if /i not "%HERE:.zip\=%"=="%HERE%" goto inzip
cd /d "%HERE%"
if not "%errorlevel%"=="0" goto badfolder
REM Keep the Python install manager (py) from stopping at a first-run question or installing on its own.
set "PYTHON_MANAGER_FIRST_RUN=false"
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"
set "PYTHON_MANAGER_CONFIRM=false"
set "PY="
if defined EBRE_PYTHON call :try "%EBRE_PYTHON%"
call :try py -3
for /f "delims=" %%P in ('where python 2^>nul') do call :try "%%P"
for /f "delims=" %%P in ('where python3 2^>nul') do call :try "%%P"
if "%EBRE_PATH_ONLY%"=="1" goto searched
for /d %%D in ("%LOCALAPPDATA%\Python\pythoncore-3.*") do call :try "%%~D\python.exe"
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do call :try "%%~D\python.exe"
for /d %%D in ("%ProgramFiles%\Python3*") do call :try "%%~D\python.exe"
:searched
if defined PY goto havepy
goto nopython

:havepy
echo Python: %PY%
if "%WHICH%"=="1" exit /b 0
set "GITBASH="
if defined CLAUDE_CODE_GIT_BASH_PATH set "GITBASH=1"
if exist "%ProgramFiles%\Git\bin\bash.exe" set "GITBASH=1"
if exist "%LOCALAPPDATA%\Programs\Git\bin\bash.exe" set "GITBASH=1"
if defined GITBASH echo Git Bash: found
if not defined GITBASH echo Note: Git for Windows - Git Bash - was not found. Claude Code then runs commands in PowerShell, which this kit also supports. Optional install: https://git-scm.com/downloads/win
set "FIRST=0"
if exist ".venv\Scripts\python.exe" goto venvok
set "FIRST=1"
echo First run: creating .venv and installing packages, a few minutes on a slow connection...
%PY% -m venv ".venv" <nul
if not "%errorlevel%"=="0" goto venvfail
:venvok
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt <nul
if not "%errorlevel%"=="0" goto pipfail
set "DOCARGS=--quiet-ok --no-claude-ok"
if "%FIRST%"=="1" set "DOCARGS=--online --no-claude-ok"
if "%CHECK%"=="1" set "DOCARGS=--online --no-claude-ok"
".venv\Scripts\python.exe" scripts\doctor.py %DOCARGS%
set "DOC=%errorlevel%"
echo Setup check saved to: %HERE%setup_check.txt
if "%CHECK%"=="1" goto checkdone
call ".venv\Scripts\activate.bat"
where claude >nul 2>nul
if not "%errorlevel%"=="0" goto noclaude
echo Starting Claude Code in this folder. Say: run the demo
claude
exit /b 0

:noclaude
echo.
echo Packages are ready, but Claude Code is not installed - the 'claude' command.
echo FIX: install it from https://claude.com/claude-code - it needs a paid Claude plan - then double-click this file again.
echo Meanwhile you can try the demo without Claude: .venv\Scripts\python.exe scripts\run_pipeline.py --demo
pause
exit /b 0

:checkdone
echo Preflight finished - exit %DOC%.
exit /b %DOC%

:inzip
echo PROBLEM: this is running from inside the zip or a temporary folder.
echo FIX: Right-click the zip ^> Extract All first. Extract to C:\EBRE-Land, then double-click start-windows.bat in that folder.
if "%CHECK%"=="0" pause
exit /b 1

:badfolder
echo PROBLEM: Windows could not open this folder.
echo FIX: move the whole folder to C:\EBRE-Land, then double-click start-windows.bat there.
if "%CHECK%"=="0" pause
exit /b 1

:nopython
echo PROBLEM: Python 3.10 or newer was not found.
echo Checked: py -3, every python / python3 on PATH, including the Microsoft Store shortcuts, and the usual install folders.
echo FIX: install Python from https://www.python.org/downloads/
echo IMPORTANT: on the first installer screen tick "Add python.exe to PATH", then double-click this file again.
if "%CHECK%"=="0" pause
exit /b 1

:venvfail
echo PROBLEM: could not create .venv with %PY%.
echo FIX: reinstall Python from https://www.python.org/downloads/ then double-click this file again.
if "%CHECK%"=="0" pause
exit /b 1

:pipfail
echo PROBLEM: package install failed.
echo FIX: connect to the internet and double-click this file again.
if "%CHECK%"=="0" pause
exit /b 1

REM ---- version-check one Python candidate; stdin comes from nul so nothing can wait for an answer
:try
if defined PY goto :eof
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" <nul >nul 2>nul
if not "%errorlevel%"=="0" goto :eof
set PY=%*
goto :eof

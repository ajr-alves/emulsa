@echo off
rem Builds the Windows installer: dist\EmulsaSetup-<version>.exe
rem Needs Python 3.11+ (python.org) and Inno Setup 6 (jrsoftware.org/isinfo.php).
rem Full output of every step goes to build.log next to this file.
setlocal
cd /d "%~dp0"
set LOG=%~dp0build.log
echo Emulsa build started %date% %time% > "%LOG%"

if not exist .venv (
  echo Creating a virtual environment...
  python -m venv .venv >> "%LOG%" 2>&1 || goto :fail
)
call .venv\Scripts\activate.bat

echo Installing requirements...
python -m pip install --upgrade pip >> "%LOG%" 2>&1
pip install -r requirements.txt pyinstaller >> "%LOG%" 2>&1 || goto :fail

for /f %%v in ('python -c "import emulsa; print(emulsa.__version__)"') do set VERSION=%%v
echo Building Emulsa %VERSION%

echo Running tests...
python -m unittest discover -s tests -q >> "%LOG%" 2>&1 || goto :fail

echo Building Emulsa.exe...
pyinstaller --noconfirm --clean packaging\emulsa.spec >> "%LOG%" 2>&1 || goto :fail

echo Checking the app starts...
dist\Emulsa\Emulsa.exe --self-test >> "%LOG%" 2>&1 || goto :fail

rem Inno Setup installs to Program Files, or to your user folder when installed "for me only"
set ISCC=
for %%p in ("%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe") do (
  if not defined ISCC if exist %%p set ISCC=%%p
)
if not defined ISCC (
  echo.
  echo Emulsa.exe is ready in dist\Emulsa. Install Inno Setup 6 to also build the installer.
  echo RESULT: app-only >> "%LOG%"
  goto :end
)
echo Building the installer...
%ISCC% "/DAppVersion=%VERSION%" packaging\installer.iss >> "%LOG%" 2>&1 || goto :fail
echo.
echo Done: dist\EmulsaSetup-%VERSION%.exe
echo RESULT: ok dist\EmulsaSetup-%VERSION%.exe >> "%LOG%"
goto :end

:fail
echo.
echo The build stopped. The details are in build.log.
echo RESULT: failed >> "%LOG%"
call :maybe_pause
exit /b 1

:end
call :maybe_pause
endlocal
exit /b 0

:maybe_pause
rem keep the window open when build.bat was double-clicked, so you can read the result
echo %cmdcmdline% | findstr /i /c:"%~nx0" >nul && pause
exit /b 0

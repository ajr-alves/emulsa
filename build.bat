@echo off
rem Builds the Windows installer: dist\EmulsaSetup-0.1.0.exe
rem Needs Python 3.11+ (python.org) and Inno Setup 6 (jrsoftware.org/isinfo.php).
setlocal
cd /d "%~dp0"

if not exist .venv (
  echo Creating a virtual environment...
  python -m venv .venv || goto :fail
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller || goto :fail

echo Running tests...
python -m unittest discover -s tests -q || goto :fail

echo Building Emulsa.exe...
pyinstaller --noconfirm --clean packaging\emulsa.spec || goto :fail

set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
  echo.
  echo Emulsa.exe is ready in dist\Emulsa. Install Inno Setup 6 to also build the installer.
  goto :end
)
echo Building the installer...
%ISCC% packaging\installer.iss || goto :fail
echo.
echo Done: dist\EmulsaSetup-0.1.0.exe
goto :end

:fail
echo.
echo The build stopped because of the error above.
exit /b 1

:end
endlocal

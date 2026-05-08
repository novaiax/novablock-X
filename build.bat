@echo off
REM Build NovaBlock.exe
REM Requires: Python 3.10+, then `pip install -r requirements.txt pyinstaller`
REM Set NOVABLOCK_RESEND_KEY before running for the key to be embedded.

setlocal

if not "%NOVABLOCK_RESEND_KEY%"=="" (
    echo ================================================
    echo Personal build — embedding your Resend key
    echo ================================================
    > novablock\_keys.py echo RESEND_KEY = "%NOVABLOCK_RESEND_KEY%"
    if not "%NOVABLOCK_FROM_EMAIL%"=="" (
        >> novablock\_keys.py echo FROM_EMAIL = "%NOVABLOCK_FROM_EMAIL%"
    )
) else (
    echo ================================================
    echo Distributable build — wizard will ask the user for a Resend key
    echo ================================================
    if exist novablock\_keys.py del novablock\_keys.py
)

echo ================================================
echo Cleaning previous builds...
echo ================================================
if exist build rd /s /q build
if exist dist rd /s /q dist

echo ================================================
echo Installing dependencies...
echo ================================================
pip install -r requirements.txt pyinstaller || goto :error

echo ================================================
echo Building NovaBlock.exe...
echo ================================================
pyinstaller novablock.spec --clean --noconfirm || goto :error

echo.
echo ================================================
echo BUILD OK
echo ================================================
echo.
echo Executable: %CD%\dist\NovaBlock.exe
echo.
goto :eof

:error
echo.
echo ================================================
echo BUILD FAILED
echo ================================================
exit /b 1

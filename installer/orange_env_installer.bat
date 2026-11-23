@echo off
setlocal EnableExtensions
REM Relaunch inside "cmd /k" so the window stays open even if cmd aborts on an unexpected error.
if not "%~1"=="--inner" cmd /k ""%~f0" --inner" & exit /b

REM =====================================================================
REM  Conda environment installer for Orange + SpectroChemPy (MCR-ALS).
REM  Windows 10/11 only. Installs Orange3, PyQt, numpy, scikit-learn and
REM  SpectroChemPy; launches Orange Canvas at the end.
REM  Logs every step to install_log.txt next to this script.
REM
REM  STYLE NOTES:
REM  - Keep every IF single-line ("if COND goto :label", or
REM    "if COND set "FAILMSG=..." & goto :failed"). A multi-line
REM    parenthesized IF block can corrupt how cmd.exe parses the file.
REM  - On an error, jump to :failed with goto, never with call: an
REM    "exit /b" inside a called subroutine only leaves the subroutine,
REM    and the script would continue with the next step.
REM  - Keep log and popup messages free of special characters: no
REM    parentheses, ampersands, pipes, angle brackets, carets, quotes,
REM    apostrophes or percent signs.
REM
REM  If this closes instantly with no message, run it from an already
REM  open Command Prompt instead of double-clicking, so a crash can't
REM  auto-close the window: cd /d "%~dp0" && orange_env_installer.bat
REM =====================================================================

set "ENV_NAME=orange_env" & REM Conda environment name
set "PYVER=3.10.14" & REM Python version
set "ORANGE_VER=3.36.2" & REM Orange3 version
set "NUMPY_VER=1.26.4" & REM numpy version, pinned before pip runs
set "SKLEARN_VER=1.3.2" & REM scikit-learn version
set "PYQT_VER=5.15.10" & REM PyQt version
set "SCP_VER=0.6.9" & REM SpectroChemPy version, installed via pip
set "MINI_URL=https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"
set "MINI_EXE=%~dp0miniconda_installer.exe"
set "LOGFILE=%~dp0install_log.txt"
set "CONSTRAINTS=%~dp0pip_constraints.txt"
set "SPEC_VER=0.6.13" & REM Orange-Spectroscopy, optional, example workflow only
set "INSTALL_SPEC=1" & REM 1 = try to install it at the end, 0 = skip
set "SPEC_CONSTRAINTS=%~dp0spec_constraints.txt"
set "STEP=0/8 Start"
set "FAILMSG="

echo ===================================================== > "%LOGFILE%"
echo Orange environment installer log >> "%LOGFILE%"
echo Started: %DATE% %TIME% >> "%LOGFILE%"
echo ===================================================== >> "%LOGFILE%"

call :log ""
call :log "======================================================"
call :log "  Orange + SpectroChemPy environment installer"
call :log "======================================================"
call :log ""
call :log "Log file: %LOGFILE%"
call :log "Packages installed: orange3, pyqt, numpy, scikit-learn, spectrochempy"
call :log "Optional last step: orange-spectroscopy - example workflow only, not fatal if it fails"
call :log "Packages skipped on purpose: pycifrw, xraylarch"
call :log ""

REM --- [1/8] Preflight -----------------------------------------------------
set "STEP=1/8 Preflight"
call :log "[1/8] Preflight checks..."

for %%I in ("%LOCALAPPDATA%") do set "LOCALSHORT=%%~sI"
set "CONDA_ROOT=%LOCALSHORT%\Miniconda3"

if not "%CONDA_ROOT%"=="%CONDA_ROOT: =%" set "FAILMSG=The install path contains spaces: %CONDA_ROOT%. Install Miniconda manually to a path with no spaces, for example C:\Miniconda3, then run this script again." & goto :failed

set "CONDABAT=%CONDA_ROOT%\condabin\conda.bat"
set "ENV_DIR=%CONDA_ROOT%\envs\%ENV_NAME%"
set "PYEXE=%ENV_DIR%\python.exe"

tasklist /FI "IMAGENAME eq orange-canvas.exe" 2>nul | find /I "orange-canvas.exe" >nul
if errorlevel 1 goto :canvas_not_running
call :log "WARNING: Orange Canvas appears to be running. Close it now, or removing the old environment will fail."
pause
:canvas_not_running

call :log "Install target: %CONDA_ROOT%"

REM --- [2/8] Miniconda ------------------------------------------------------
set "STEP=2/8 Miniconda"
call :log "[2/8] Checking for Miniconda..."
if exist "%CONDABAT%" goto :miniconda_present

call :log "Downloading Miniconda..."
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%MINI_URL%' -OutFile '%MINI_EXE%'" >>"%LOGFILE%" 2>&1
if errorlevel 1 set "FAILMSG=Miniconda download failed. Check your internet connection." & goto :failed

call :log "Installing Miniconda silently..."
start /wait "" "%MINI_EXE%" /InstallationType=JustMe /AddToPath=0 /RegisterPython=0 /S /D=%CONDA_ROOT%
if not exist "%CONDABAT%" set "FAILMSG=Miniconda did not install at %CONDA_ROOT%." & goto :failed
goto :miniconda_done

:miniconda_present
call :log "Miniconda already present."

:miniconda_done

REM --- [3/8] Remove previous environment -------------------------------------
set "STEP=3/8 Remove previous environment"
call :log "[3/8] Removing previous environment if present..."
if not exist "%ENV_DIR%" goto :no_previous_env

call "%CONDABAT%" env remove -n %ENV_NAME% -y >>"%LOGFILE%" 2>&1
if exist "%ENV_DIR%" rmdir /s /q "%ENV_DIR%" 2>nul
if exist "%ENV_DIR%" set "FAILMSG=Could not remove the previous environment at %ENV_DIR%. Close Orange, Spyder or any Python console that uses it and try again." & goto :failed
call :log "Previous environment removed."
goto :env_removal_done

:no_previous_env
call :log "No previous environment found."

:env_removal_done

REM --- [4/8] Create environment -----------------------------------------------
set "STEP=4/8 Create environment"
call :log "[4/8] Creating environment %ENV_NAME% with Python %PYVER%..."
call "%CONDABAT%" create -y -n %ENV_NAME% --override-channels -c conda-forge python=%PYVER% >>"%LOGFILE%" 2>&1
if errorlevel 1 set "FAILMSG=Environment creation failed." & goto :failed
if not exist "%PYEXE%" set "FAILMSG=The environment was created but python.exe is missing." & goto :failed
call :log "Environment created."

REM --- [5/8] Core packages ------------------------------------------------------
set "STEP=5/8 Core packages"
call :log "[5/8] Installing Orange, PyQt, numpy and scikit-learn. This can take several minutes."
call "%CONDABAT%" install -y -n %ENV_NAME% --override-channels -c conda-forge orange3=%ORANGE_VER% numpy=%NUMPY_VER% scikit-learn=%SKLEARN_VER% pyqt=%PYQT_VER% >>"%LOGFILE%" 2>&1
if errorlevel 1 set "FAILMSG=Package installation failed." & goto :failed
call :log "Core packages installed."

REM Pin setuptools below 81: newer versions dropped pkg_resources, which Orange needs at startup.
call :log "Pinning setuptools to a version that still ships pkg_resources, required by Orange..."
"%PYEXE%" -m pip install --no-input --disable-pip-version-check "setuptools<81" >>"%LOGFILE%" 2>&1
if errorlevel 1 set "FAILMSG=Could not pin setuptools." & goto :failed
"%PYEXE%" -c "import pkg_resources" >>"%LOGFILE%" 2>&1
if errorlevel 1 set "FAILMSG=setuptools was pinned but pkg_resources still cannot be imported." & goto :failed
call :log "setuptools pinned and pkg_resources verified importable."

REM --- [6/8] Freeze what conda resolved -------------------------------------------
set "STEP=6/8 Freeze versions"
call :log "[6/8] Freezing the versions conda resolved, so pip cannot silently change them..."
"%PYEXE%" -c "import numpy, scipy, sklearn, setuptools; open(r'%CONSTRAINTS%', 'w').write(f'numpy=={numpy.__version__}\nscipy=={scipy.__version__}\nscikit-learn=={sklearn.__version__}\nsetuptools=={setuptools.__version__}\n')" >>"%LOGFILE%" 2>&1
if errorlevel 1 set "FAILMSG=Could not read the resolved package versions." & goto :failed
call :log "Versions frozen to pip_constraints.txt."

REM --- [7/8] SpectroChemPy ---------------------------------------------------------
set "STEP=7/8 SpectroChemPy"
call :log "[7/8] Installing SpectroChemPy %SCP_VER%..."
"%PYEXE%" -m pip install --no-input --disable-pip-version-check -c "%CONSTRAINTS%" spectrochempy==%SCP_VER% >>"%LOGFILE%" 2>&1
if errorlevel 1 set "FAILMSG=pip could not install spectrochempy without changing the versions conda fixed. This is a real dependency conflict, not a network issue." & goto :failed
call :log "SpectroChemPy installed."

REM --- [8/8] Verify -------------------------------------------------------------
set "STEP=8/8 Verify"
call :log "[8/8] Verifying the installation..."
"%PYEXE%" -c "import numpy, scipy, sklearn, Orange, spectrochempy as scp; ver = getattr(scp, 'version', getattr(scp, '__version__', 'unknown')); missing = [n for n in ('MCRALS', 'EFA', 'SIMPLISMA') if not hasattr(scp, n)]; print('numpy        ', numpy.__version__); print('scikit-learn ', sklearn.__version__); print('Orange       ', Orange.__version__); print('spectrochempy', ver); print('missing tools', missing); raise SystemExit(1 if missing else 0)" >>"%LOGFILE%" 2>&1
if errorlevel 1 set "FAILMSG=The environment installed but failed verification." & goto :failed
call :log "Verification passed: MCRALS, EFA and SIMPLISMA are all available."

REM --- [Optional] Orange-Spectroscopy, a failure here is NOT fatal -------------
REM  Only needed for the example workflow: Spectra and Normalization widgets.
REM  All installed versions are frozen first, so pip can only ADD packages:
REM  if Orange-Spectroscopy needs a different version of anything, pip stops
REM  before changing the environment.
set "STEP=Optional Orange-Spectroscopy"
set "SPEC_STATUS=skipped because INSTALL_SPEC=0"
if not "%INSTALL_SPEC%"=="1" goto :spec_done
call :log "[Optional] Installing Orange-Spectroscopy %SPEC_VER% for the example workflow..."
"%PYEXE%" -m pip list --format=freeze --disable-pip-version-check >"%SPEC_CONSTRAINTS%" 2>>"%LOGFILE%"
if errorlevel 1 goto :spec_failed
"%PYEXE%" -m pip install --no-input --disable-pip-version-check -c "%SPEC_CONSTRAINTS%" Orange-Spectroscopy==%SPEC_VER% >>"%LOGFILE%" 2>&1
if errorlevel 1 goto :spec_failed
"%PYEXE%" -c "import Orange, spectrochempy, orangecontrib.spectroscopy" >>"%LOGFILE%" 2>&1
if errorlevel 1 goto :spec_failed
set "SPEC_STATUS=installed"
call :log "Orange-Spectroscopy installed."
goto :spec_done
:spec_failed
set "SPEC_STATUS=NOT installed, see log. Install it later from the Orange Add-ons menu"
call :log "WARNING: Orange-Spectroscopy could not be installed. The MCR-ALS widgets still work."
:spec_done

if exist "%MINI_EXE%" del /q "%MINI_EXE%"

REM --- Success -------------------------------------------------------------------
call :log ""
call :log "======================================================"
call :log "  INSTALLATION SUCCESSFUL"
call :log "======================================================"
call :log "  Environment: %ENV_DIR%"
call :log "  Orange-Spectroscopy: %SPEC_STATUS%"
call :log "  Skipped on purpose: pycifrw, xraylarch"
call :log ""
call :log "  To open Orange later, run these two lines in a Command Prompt:"
call :log "    %CONDABAT% activate %ENV_NAME%"
call :log "    python -m Orange.canvas"
call :log "======================================================"
call :log ""

set "PATH=%ENV_DIR%;%ENV_DIR%\Library\bin;%ENV_DIR%\Library\mingw-w64\bin;%ENV_DIR%\Library\usr\bin;%ENV_DIR%\Scripts;%PATH%"

if exist "%ENV_DIR%\Scripts\orange-canvas.exe" goto :launch_exe
start "" "%ENV_DIR%\pythonw.exe" -m Orange.canvas
goto :launched

:launch_exe
start "" "%ENV_DIR%\Scripts\orange-canvas.exe"

:launched
call :log "Orange Canvas launched. You can close this window."
call :popup "Orange installer" "INSTALLATION SUCCESSFUL. Environment: %ENV_DIR%. To open Orange later: %CONDABAT% activate %ENV_NAME%, then python -m Orange.canvas" "Information"
pause
exit /b 0

REM --- Failure: reached only with goto, so exit /b ends the whole script --------
:failed
call :log ""
call :log "======================================================"
call :log "  INSTALLATION FAILED at step %STEP% - see install_log.txt"
call :log "======================================================"
call :log "  %FAILMSG%"
call :log "  Log file: %LOGFILE%"
call :log "  Review that file, or send it along if you need help fixing this."
call :log ""
call :popup "Orange installer" "INSTALLATION FAILED at step %STEP% - see install_log.txt next to the installer. %FAILMSG%" "Error"
pause
exit /b 1

REM --- Subroutines -----------------------------------------------------------------
:log
REM  No parenthesized block here: the message is expanded before the block
REM  is parsed, so a closing parenthesis in the text would close the block
REM  early and abort the whole script without a message.
REM  Redirection goes first so a message ending in a digit is not read as
REM  a stream number.
if "%~1"=="" goto :log_blank
echo %~1
>>"%LOGFILE%" echo %~1
goto :eof
:log_blank
echo.
>>"%LOGFILE%" echo.
goto :eof

:popup
REM  Windows message box. %~1 = title, %~2 = message, %~3 = Information or Error.
REM  Waits until the user clicks OK. If PowerShell is blocked, it is skipped
REM  silently and the console message is still there.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName PresentationFramework; [void][System.Windows.MessageBox]::Show('%~2', '%~1', 'OK', '%~3')" >nul 2>&1
goto :eof

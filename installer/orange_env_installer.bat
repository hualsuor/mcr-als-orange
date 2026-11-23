@echo off
setlocal EnableExtensions

REM =====================================================================
REM  Conda environment installer for Orange + SpectroChemPy (MCR-ALS).
REM  Windows 10/11 only. Installs Orange3, PyQt, numpy, scikit-learn and
REM  SpectroChemPy; launches Orange Canvas at the end.
REM  Logs every step to install_log.txt next to this script.
REM
REM  STYLE NOTE: keep every IF below single-line ("if COND goto :label"
REM  or "if COND call :sub"). A multi-line parenthesized IF block can
REM  corrupt how cmd.exe parses the rest of the file, even unreached.
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
set "SPEC_VER=0.6.13" & REM Orange-Spectroscopy (optional, example workflow only)
set "INSTALL_SPEC=1" & REM 1 = try to install it at the end, 0 = skip
set "SPEC_CONSTRAINTS=%~dp0spec_constraints.txt"

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
call :log "Optional last step: orange-spectroscopy (example workflow only, not fatal if it fails)"
call :log "Packages skipped on purpose: pycifrw, xraylarch"
call :log ""

REM --- [1/8] Preflight -----------------------------------------------------
call :log "[1/8] Preflight checks..."

for %%I in ("%LOCALAPPDATA%") do set "LOCALSHORT=%%~sI"
set "CONDA_ROOT=%LOCALSHORT%\Miniconda3"

if not "%CONDA_ROOT%"=="%CONDA_ROOT: =%" call :fail "The install path contains spaces: %CONDA_ROOT% -- the Miniconda installer cannot handle that. Install Miniconda manually to a path with no spaces, for example C:\Miniconda3, then re-run this script."

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
call :log "[2/8] Checking for Miniconda..."
if exist "%CONDABAT%" goto :miniconda_present

call :log "Downloading Miniconda..."
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%MINI_URL%' -OutFile '%MINI_EXE%'" >>"%LOGFILE%" 2>&1
if errorlevel 1 call :fail "Miniconda download failed. Check your internet connection. See the log for details."

call :log "Installing Miniconda silently..."
start /wait "" "%MINI_EXE%" /InstallationType=JustMe /AddToPath=0 /RegisterPython=0 /S /D=%CONDA_ROOT%
if not exist "%CONDABAT%" call :fail "Miniconda did not install at %CONDA_ROOT%."
goto :miniconda_done

:miniconda_present
call :log "Miniconda already present."

:miniconda_done

REM --- [3/8] Remove previous environment -------------------------------------
call :log "[3/8] Removing previous environment if present..."
if not exist "%ENV_DIR%" goto :no_previous_env

call "%CONDABAT%" env remove -n %ENV_NAME% -y >>"%LOGFILE%" 2>&1
if exist "%ENV_DIR%" rmdir /s /q "%ENV_DIR%" 2>nul
if exist "%ENV_DIR%" call :fail "Could not remove the previous environment at %ENV_DIR%. This is almost always because Orange, Spyder, or a Python console is still using it. Close them and try again."
call :log "Previous environment removed."
goto :env_removal_done

:no_previous_env
call :log "No previous environment found."

:env_removal_done

REM --- [4/8] Create environment -----------------------------------------------
call :log "[4/8] Creating environment %ENV_NAME% with Python %PYVER%..."
call "%CONDABAT%" create -y -n %ENV_NAME% --override-channels -c conda-forge python=%PYVER% >>"%LOGFILE%" 2>&1
if errorlevel 1 call :fail "Environment creation failed. See %LOGFILE% for details."
if not exist "%PYEXE%" call :fail "The environment was created but python.exe is missing."
call :log "Environment created."

REM --- [5/8] Core packages ------------------------------------------------------
call :log "[5/8] Installing Orange, PyQt, numpy and scikit-learn. This can take several minutes."
call "%CONDABAT%" install -y -n %ENV_NAME% --override-channels -c conda-forge orange3=%ORANGE_VER% numpy=%NUMPY_VER% scikit-learn=%SKLEARN_VER% pyqt=%PYQT_VER% >>"%LOGFILE%" 2>&1
if errorlevel 1 call :fail "Package installation failed. See %LOGFILE% for details."
call :log "Core packages installed."

REM Pin setuptools<81: newer versions dropped pkg_resources, which Orange needs at startup.
call :log "Pinning setuptools to a version that still ships pkg_resources (required by Orange)..."
"%PYEXE%" -m pip install --no-input --disable-pip-version-check "setuptools<81" >>"%LOGFILE%" 2>&1
if errorlevel 1 call :fail "Could not pin setuptools. See %LOGFILE% for details."
"%PYEXE%" -c "import pkg_resources" >>"%LOGFILE%" 2>&1
if errorlevel 1 call :fail "setuptools was pinned but pkg_resources still cannot be imported. See %LOGFILE% for details."
call :log "setuptools pinned and pkg_resources verified importable."

REM --- [6/8] Freeze what conda resolved -------------------------------------------
call :log "[6/8] Freezing the versions conda resolved, so pip cannot silently change them..."
"%PYEXE%" -c "import numpy, scipy, sklearn, setuptools; open(r'%CONSTRAINTS%', 'w').write(f'numpy=={numpy.__version__}\nscipy=={scipy.__version__}\nscikit-learn=={sklearn.__version__}\nsetuptools=={setuptools.__version__}\n')" >>"%LOGFILE%" 2>&1
if errorlevel 1 call :fail "Could not read the resolved package versions. See %LOGFILE%."
call :log "Versions frozen to pip_constraints.txt."

REM --- [7/8] SpectroChemPy ---------------------------------------------------------
call :log "[7/8] Installing SpectroChemPy %SCP_VER%..."
"%PYEXE%" -m pip install --no-input --disable-pip-version-check -c "%CONSTRAINTS%" spectrochempy==%SCP_VER% >>"%LOGFILE%" 2>&1
if errorlevel 1 call :fail "pip could not install spectrochempy without changing the versions conda fixed. This is a real dependency conflict, not a network issue. See %LOGFILE% for the full pip output."
call :log "SpectroChemPy installed."

REM --- [8/8] Verify and launch ----------------------------------------------------
call :log "[8/8] Verifying the installation..."
"%PYEXE%" -c "import numpy, scipy, sklearn, Orange, spectrochempy as scp; ver = getattr(scp, 'version', getattr(scp, '__version__', 'unknown')); missing = [n for n in ('MCRALS', 'EFA', 'SIMPLISMA') if not hasattr(scp, n)]; print('numpy        ', numpy.__version__); print('scikit-learn ', sklearn.__version__); print('Orange       ', Orange.__version__); print('spectrochempy', ver); print('missing tools', missing); raise SystemExit(1 if missing else 0)" >>"%LOGFILE%" 2>&1
if errorlevel 1 call :fail "The environment installed but failed verification. See %LOGFILE%."
call :log "Verification passed: MCRALS, EFA and SIMPLISMA are all available."

REM --- [Optional] Orange-Spectroscopy (a failure here is NOT fatal) ----------
REM  Only needed for the example workflow (Spectra and Normalization widgets).
REM  All installed versions are frozen first, so pip can only ADD packages:
REM  if Orange-Spectroscopy needs a different version of anything, pip stops
REM  before changing the environment.
set "SPEC_STATUS=skipped (INSTALL_SPEC=0)"
if not "%INSTALL_SPEC%"=="1" goto :spec_done
call :log "[Optional] Installing Orange-Spectroscopy %SPEC_VER% (example workflow only)..."
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
set "SPEC_STATUS=NOT installed (see log) - install it later from the Orange Add-ons menu"
call :log "WARNING: Orange-Spectroscopy could not be installed. The MCR-ALS widgets still work."
:spec_done

if exist "%MINI_EXE%" del /q "%MINI_EXE%"

call :log ""
call :log "======================================================"
call :log "  Installation completed successfully."
call :log "  Environment: %ENV_DIR%"
call :log "  Orange-Spectroscopy: %SPEC_STATUS%"
call :log "  Skipped on purpose: pycifrw, xraylarch"
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
pause
exit /b 0

:log
if "%~1"=="" (
  echo.
  echo. >>"%LOGFILE%"
) else (
  echo %~1
  echo %~1 >>"%LOGFILE%"
)
goto :eof

:fail
call :log ""
call :log "***** INSTALLATION FAILED *****"
call :log "%~1"
call :log ""
call :log "Full details were written to:"
call :log "  %LOGFILE%"
call :log "Review that file, or send it along if you need help fixing this."
call :log ""
pause
exit /b 1

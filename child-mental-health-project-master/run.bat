@echo off
where conda >nul 2>nul
if %errorlevel% neq 0 (
    echo Anaconda is not installed or not in PATH.
    echo Please install Anaconda from https://www.anaconda.com/download
    echo After installation, you may need to restart your computer.
    pause
    exit /b 1
)

:: If we get here, conda is installed
echo Anaconda is installed, proceeding...

:: Check if emotion-detection environment exists
conda env list | find "emotion-detection" >nul 2>nul
if %errorlevel% neq 0 (
    echo emotion-detection environment not found.
    echo Creating environment from environment.yml...
    conda env create -f environment.yml
    if %errorlevel% neq 0 (
        echo Failed to create environment.
        pause
        exit /b 1
    )
    echo Environment created successfully.
) else (
    echo emotion-detection environment found.
)

:: Activate environment and run the app
echo Activating emotion-detection environment...
call conda activate emotion-detection
if %errorlevel% neq 0 (
    echo Failed to activate environment.
    pause
    exit /b 1
)

echo Running application...
python app.py
if %errorlevel% neq 0 (
    echo Application failed to start.
    pause
    exit /b 1
)

pause
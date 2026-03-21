@echo off
echo Starting C_manager - C盘守护者...
echo.

REM Start Python backend
start /B cmd /c "conda activate C_manager && python -m src.api.server"

REM Wait for backend to start
timeout /t 2 /nobreak > nul

REM Start frontend dev server
cd frontend
start /B cmd /c "npm run dev"
cd ..

REM Wait and open browser
timeout /t 3 /nobreak > nul
start http://localhost:5173

echo C_manager is running!
echo Backend: http://localhost:8765
echo Frontend: http://localhost:5173
echo Press any key to stop.
pause > nul

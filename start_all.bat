@echo off
echo Starting Braein AI GIS...

:: Start Unified Backend (all services on port 8000)
start "Backend: Unified API (8000)" cmd /k "cd /d backend && .\lulc\.venv\Scripts\activate && python main.py"

:: Start Frontend
start "Frontend: Vite App" cmd /k "cd frontend && npm run dev"

echo All services launched!
pause

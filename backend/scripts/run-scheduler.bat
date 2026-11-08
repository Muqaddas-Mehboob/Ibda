@echo off
cd /d "%~dp0.."
call .venv\Scripts\activate.bat
python manage.py process_scheduled_posts --loop --interval 60
pause

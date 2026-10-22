@echo off
cd /d D:\Ibda\backend
call .venv\Scripts\activate.bat
python manage.py migrate
pause
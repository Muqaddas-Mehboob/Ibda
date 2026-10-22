@echo off
cd /d D:\Ibda\backend
call .venv\Scripts\activate.bat
python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print('Database connected:', connection.vendor)"
pause
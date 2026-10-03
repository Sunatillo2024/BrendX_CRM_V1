@echo off
echo ============================================
echo  BrandX POS - Backend Setup Script
echo ============================================
echo.

cd /d "%~dp0backend"

echo [1/6] Creating virtual environment...
python -m venv venv

echo [2/6] Activating virtual environment...
call venv\Scripts\activate.bat

echo [3/6] Installing dependencies...
pip install -r requirements.txt

echo [4/6] Creating MySQL database...
mysql -u root -p159632 -e "CREATE DATABASE IF NOT EXISTS brandx CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

echo [5/6] Running migrations...
python manage.py migrate

echo [6/6] Done! Now run: python manage.py createsuperuser
echo       Then start server with: python manage.py runserver
echo.
pause

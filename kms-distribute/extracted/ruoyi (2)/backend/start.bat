@echo off
python -m daphne -b 0.0.0.0 -p 8000 application.asgi:application


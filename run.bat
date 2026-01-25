@echo off
setlocal

set ROOT_DIR=%~dp0
cd /d %ROOT_DIR%

if not exist venv (
  py -m venv venv
)

call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m src.web_app

endlocal

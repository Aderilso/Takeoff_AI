@echo off
chcp 65001 >nul
echo ========================================
echo Takeoff AI Multi v2 - Inicializando...
echo ========================================

REM Verificar se Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao encontrado. Instale Python 3.8+ primeiro.
    pause
    exit /b 1
)

REM Criar ambiente virtual se não existir
if not exist "venv" (
    echo Criando ambiente virtual...
    python -m venv venv
)

REM Ativar ambiente virtual
echo Ativando ambiente virtual...
call venv\Scripts\activate.bat

REM Instalar dependências
echo Instalando dependencias...
pip install -r requirements.txt

REM Criar diretórios necessários
if not exist "config" mkdir config
if not exist "out" mkdir out

REM Verificar se .env existe
if not exist "config\.env" (
    echo AVISO: Arquivo config\.env nao encontrado.
    echo Copie config\env_template.txt para config\.env e configure sua API key.
    echo.
)

REM Executar aplicação
echo.
echo Iniciando aplicacao...
echo Acesse: http://localhost:8501
echo.
streamlit run app/app.py

pause

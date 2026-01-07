#!/bin/bash

# Скрипт для установки systemd сервиса для FunPay Big Deal Manager

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция для вывода сообщений
info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка, что скрипт запущен от root
if [ "$EUID" -ne 0 ]; then 
    error "Пожалуйста, запустите скрипт с правами root (sudo)"
    exit 1
fi

# Определение пути к проекту
# Если скрипт запущен из директории проекта, используем текущую директорию
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Проверка наличия main.py
if [ ! -f "$SCRIPT_DIR/main.py" ]; then
    error "Файл main.py не найден в $SCRIPT_DIR"
    exit 1
fi

# Проверка наличия venv
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    error "Виртуальное окружение venv не найдено в $SCRIPT_DIR"
    exit 1
fi

PROJECT_DIR="$SCRIPT_DIR"
SERVICE_NAME="funpay-bigdeal-manager"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PYTHON_PATH="$PROJECT_DIR/venv/bin/python"
MAIN_SCRIPT="$PROJECT_DIR/main.py"

info "Установка сервиса для FunPay Big Deal Manager"
info "Директория проекта: $PROJECT_DIR"
info "Имя сервиса: $SERVICE_NAME"

# Создание systemd unit файла
info "Создание systemd unit файла..."

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=FunPay Big Deal Manager Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
ExecStart=$PYTHON_PATH $MAIN_SCRIPT
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

info "Systemd unit файл создан: $SERVICE_FILE"

# Перезагрузка systemd daemon
info "Перезагрузка systemd daemon..."
systemctl daemon-reload

# Включение сервиса для автозапуска
info "Включение сервиса для автозапуска..."
systemctl enable "$SERVICE_NAME"

info "Сервис успешно установлен!"
echo ""
info "Доступные команды:"
echo "  Запуск сервиса:     sudo systemctl start $SERVICE_NAME"
echo "  Остановка сервиса:  sudo systemctl stop $SERVICE_NAME"
echo "  Статус сервиса:     sudo systemctl status $SERVICE_NAME"
echo "  Логи сервиса:       sudo journalctl -u $SERVICE_NAME -f"
echo "  Отключение автозапуска: sudo systemctl disable $SERVICE_NAME"
echo ""

# Спрашиваем, запустить ли сервис сейчас
read -p "Запустить сервис сейчас? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    info "Запуск сервиса..."
    systemctl start "$SERVICE_NAME"
    sleep 2
    systemctl status "$SERVICE_NAME" --no-pager
fi


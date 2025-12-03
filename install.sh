#!/bin/bash
set -e

# Определяем путь к проекту (каталог, где лежит install.sh)
WORKDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "Установка в $WORKDIR"

# Проверка наличия uv
if ! command -v uv &> /dev/null; then
    echo "Ошибка: uv не найден. Установите uv: https://docs.astral.sh/uv/"
    exit 1
fi

# Создание lock-файла и окружения
echo "Скачивание зависимостей..."
cd "$WORKDIR"
uv lock
uv sync

# Подготовка systemd unit-файла
SERVICE_PATH="/etc/systemd/system/c40.service"

echo "Установка systemd unit в $SERVICE_PATH"

sudo cp "$WORKDIR/c40.service" "$SERVICE_PATH"

# Заменяем %WORKDIR% на реальный путь
sudo sed -i "s|%WORKDIR%|$WORKDIR|g" "$SERVICE_PATH"

# Активация сервиса
echo "Активация systemd сервиса..."
sudo systemctl daemon-reload
sudo systemctl enable c40.service
sudo systemctl restart c40.service

echo "Установка завершена!"
echo "Статус сервиса: sudo systemctl status c40.service"
echo "Логи:          journalctl -u c40.service -f"

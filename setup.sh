#!/bin/bash
set -e

CMDLINE="/boot/firmware/cmdline.txt"
CONFIG="/boot/firmware/config.txt"

echo "=== RPI INTERFACE CONFIGURATION SCRIPT (idempotent) ==="

#
# 1. Удаление console=serial0,115200 из cmdline.txt
#
echo "[1] Проверка cmdline.txt..."

CURRENT_CMDLINE=$(cat "$CMDLINE")

if echo "$CURRENT_CMDLINE" | grep -q "console=serial0,115200"; then
    NEW_CMDLINE=$(echo "$CURRENT_CMDLINE" \
        | sed 's/console=serial0,115200//g' \
        | tr -s ' ' \
        | sed 's/^ //; s/ $//')
    echo "$NEW_CMDLINE" | sudo tee "$CMDLINE" >/dev/null
    echo " - console=serial0,115200 удалён"
else
    echo " - Ничего менять не нужно"
fi


#
# 2. enable_uart=1 в config.txt
#
echo "[2] Проверка enable_uart..."

if grep -qE '^enable_uart=1$' "$CONFIG"; then
    echo " - UART уже включён"
else
    # Удаляем возможные старые enable_uart=X (если есть)
    sudo sed -i 's/^enable_uart=.*/enable_uart=1/' "$CONFIG"
    # Если строки не было — добавим
    if ! grep -qE '^enable_uart=1$' "$CONFIG"; then
        echo "enable_uart=1" | sudo tee -a "$CONFIG" >/dev/null
    fi
    echo " - UART включён"
fi


#
# 3. Отключение hciuart.service
#
echo "[3] Отключение hciuart.service..."

if systemctl is-enabled hciuart.service >/dev/null 2>&1; then
    sudo systemctl disable hciuart.service >/dev/null 2>&1 || true
    echo " - hciuart отключён"
else
    echo " - Уже отключён"
fi


#
# 4. Включение I2C
#
echo "[4] Проверка I2C..."

if grep -q '^dtparam=i2c_arm=on' "$CONFIG"; then
    echo " - I2C уже включён"
else
    # Удалим возможный dtparam=i2c_arm=off
    sudo sed -i 's/^dtparam=i2c_arm=off/dtparam=i2c_arm=on/' "$CONFIG"
    # Если строки не было — добавим
    if ! grep -q '^dtparam=i2c_arm=on' "$CONFIG"; then
        echo "dtparam=i2c_arm=on" | sudo tee -a "$CONFIG" >/dev/null
    fi
    echo " - I2C включён"
fi


#
# 5. Включение 1-Wire
#
echo "[5] Проверка 1-Wire..."

if grep -q '^dtoverlay=w1-gpio' "$CONFIG"; then
    echo " - 1-Wire уже включён"
else
    echo "dtoverlay=w1-gpio" | sudo tee -a "$CONFIG" >/dev/null
    echo " - 1-Wire включён"
fi


echo "=== Готово. Перезапуск рекомендуется. ==="
echo "Перезагрузить сейчас? (y/n)"
read -r ans

if [[ "$ans" == "y" ]]; then
    sudo reboot
fi

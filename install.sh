#!/bin/bash
set -euo pipefail

###############################################################################
# One-shot installer for Raspberry Pi + project c40
#
# Usage:
#   curl -fsSL https://…/install_c40.sh | sudo bash
#
# What it does:
#   • Updates system
#   • Enables I²C, 1-Wire, UART tweaks
#   • Installs required OS packages
#   • Installs python3, uv dependency manager
#   • Clones c40 repository
#   • Installs python dependencies via uv
#   • Sets up systemd
#   • Offers reboot (or skip)
###############################################################################

# ——————————————————————————————————————————————————————————————————
# 0) Variables
# ——————————————————————————————————————————————————————————————————

WORKDIR="/opt/c40"
REPO="https://github.com/nodax-hub/c40.git"
SERVICE_NAME="c40.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"
CMDLINE="/boot/firmware/cmdline.txt"
CONFIG="/boot/firmware/config.txt"

echo
echo "=== C40 Project One-Shot Installer ==="
echo

# ——————————————————————————————————————————————————————————————————
# 1) System update & base packages
# ——————————————————————————————————————————————————————————————————

echo "[1/9] Updating system and installing base packages..."
apt update
apt upgrade -y

apt install -y \
    python3 python3-pip python3-venv \
    git curl i2c-tools wiringpi \
    build-essential

echo " - System updated and base packages installed."
echo

# ——————————————————————————————————————————————————————————————————
# 2) Enable interfaces in firmware
# ——————————————————————————————————————————————————————————————————

echo "[2/9] Enabling interfaces: I²C, 1-Wire, UART tweaks..."

# (A) Remove console=serial0,115200
if grep -q "console=serial0,115200" "$CMDLINE"; then
    sed -i 's/console=serial0,115200//g' "$CMDLINE"
    sed -i 's/  / /g' "$CMDLINE"
    echo "   - Removed serial console param"
else
    echo "   - Serial console not present/already removed"
fi

# (B) UART enable
if grep -qE '^enable_uart=1$' "$CONFIG"; then
    echo "   - UART already enabled"
else
    sed -i 's/^enable_uart=.*/enable_uart=1/' "$CONFIG" || true
    if ! grep -q "^enable_uart=1$" "$CONFIG"; then
        echo "enable_uart=1" >> "$CONFIG"
    fi
    echo "   - UART enabled"
fi

# (C) I2C
if grep -q '^dtparam=i2c_arm=on' "$CONFIG"; then
    echo "   - I2C already enabled"
else
    sed -i 's/^dtparam=i2c_arm=off/dtparam=i2c_arm=on/' "$CONFIG" || true
    if ! grep -q '^dtparam=i2c_arm=on' "$CONFIG"; then
        echo "dtparam=i2c_arm=on" >> "$CONFIG"
    fi
    echo "   - I2C enabled"
fi

# (D) 1-Wire
if grep -q '^dtoverlay=w1-gpio' "$CONFIG"; then
    echo "   - 1-Wire already enabled"
else
    echo "dtoverlay=w1-gpio" >> "$CONFIG"
    echo "   - 1-Wire enabled"
fi

echo " - Firmware configuration updated."
echo

# ——————————————————————————————————————————————————————————————————
# 3) Install uv (dependency manager)
# ——————————————————————————————————————————————————————————————————

echo "[3/9] Installing uv (Python dependency manager)..."

# ensure pip up to date before installing uv
python3 -m pip install --upgrade pip

if ! command -v uv >/dev/null 2>&1; then
    python3 -m pip install uv
    echo " - uv installed"
else
    echo " - uv already present"
fi

echo

# ——————————————————————————————————————————————————————————————————
# 4) Clone project repo
# ——————————————————————————————————————————————————————————————————

echo "[4/9] Cloning repository into $WORKDIR..."

if [ -d "$WORKDIR" ]; then
    echo "   - Removing existing directory"
    rm -rf "$WORKDIR"
fi

git clone "$REPO" "$WORKDIR"
echo " - Repository cloned."
echo

# ——————————————————————————————————————————————————————————————————
# 5) Install Python dependencies via uv
# ——————————————————————————————————————————————————————————————————

echo "[5/9] Installing Python dependencies via uv..."

cd "$WORKDIR"

if [ ! -f "pyproject.toml" ]; then
    echo " !!! pyproject.toml not found — cannot install dependencies using uv"
    exit 1
fi

uv lock || true
uv sync

echo " - Dependencies installed via uv."
echo

# ——————————————————————————————————————————————————————————————————
# 6) Setup systemd service
# ——————————————————————————————————————————————————————————————————

echo "[6/9] Setting up systemd service..."

if [ ! -f "$WORKDIR/$SERVICE_NAME" ]; then
    echo " !!! $SERVICE_NAME not found in project root!"
    exit 1
fi

cp "$WORKDIR/$SERVICE_NAME" "$SERVICE_PATH"
sed -i "s|%WORKDIR%|$WORKDIR|g" "$SERVICE_PATH"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo " - systemd service installed and started."
echo

# ——————————————————————————————————————————————————————————————————
# 7) Post-install tips
# ——————————————————————————————————————————————————————————————————

echo "[7/9] Post-install system checks (manual):"
echo "   • Verify I2C: sudo i2cdetect -y 1"
echo "   • Verify 1-Wire: ls /sys/bus/w1/devices/"
echo "   • Check service status: sudo systemctl status $SERVICE_NAME"
echo

# ——————————————————————————————————————————————————————————————————
# 8) Request reboot
# ——————————————————————————————————————————————————————————————————

echo "[8/9] Ready for reboot."
read -p "Reboot now? (y/N): " answer
case "$answer" in
  [yY]|[yY][eE][sS])
    echo "Rebooting..."
    reboot
    ;;
  *)
    echo "Skipping reboot. Manual reboot recommended."
    ;;
esac

echo
echo "=== Installation finished ==="

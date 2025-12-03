Для конфигурации устройства:

```bash
chmod +x setup.sh
./setup.sh
```

Для установки и запуска демона сервиса:

```bash
chmod +x install.sh
./install.sh
```

Схема подключения:
```
Raspberry Pi 4B
────────────────────────────────────────

 UART0:
  pin  8  → TXD (GPIO14)
  pin 10  → RXD (GPIO15)

 I2C (дальномер VL53L0X):
  pin  3  → SDA (GPIO2)
  pin  5  → SCL (GPIO3)
  pin  1  → 3.3V
  pin  6  → GND

 1-Wire (температура DS18B20):
  pin  7  → GPIO4 (DQ, через резистор 4.7k к 3.3V)
  pin  1  → 3.3V
  pin  6  → GND

 Концевики:
  Recomend schema ↓

  pin  1 → 3.3V
  pin  6 → GND (общий)

  pin 15 → GPIO22
  pin 16 → GPIO23
  pin 18 → GPIO24
  pin 22 → GPIO25

Каждый вход:
  3.3V ---[концевик]--- GPIO22/23/24/25
  pull-down включён программно
```
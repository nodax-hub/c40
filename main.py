#!/usr/bin/env -S uv run --python 3.11
# /// script
# dependencies = ["w1thermsensor", "pigpio", "colorlog", "smbus2", "pymavlink", "pyserial"]
# requires-python = ">=3.10"
# ///

import logging
import queue
import statistics
import struct
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import pigpio
import smbus2
# -----------------------------
# ЛОГГЕР
# -----------------------------
from colorlog import ColoredFormatter
from pymavlink import mavutil
from w1thermsensor import W1ThermSensor


def setup_logger(level=logging.INFO):
    logger = logging.getLogger("system")
    logger.setLevel(level)

    handler = logging.StreamHandler()
    formatter = ColoredFormatter(
        "%(log_color)s[%(asctime)s] %(levelname)s: %(message)s",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "white",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red"
        }
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


logger = setup_logger(logging.INFO)


# ------------------------------------------------------------
# 1. Концевик
# ------------------------------------------------------------
class LimitSwitchSensor(threading.Thread):
    def __init__(self, pi, gpio, pud=pigpio.PUD_DOWN, invert_state_mode=False, interval=0.01):
        super().__init__(daemon=True)
        self._pi = pi
        self._pin = gpio
        self._interval = interval
        self._stop = threading.Event()
        self._state = None
        self._invert_state_mode = invert_state_mode

        try:
            self._pi.set_mode(self._pin, pigpio.INPUT)
            self._pi.set_pull_up_down(self._pin, pud)
        except Exception as e:
            logger.error(f"GPIO init failed on pin {self._pin}: {e}")

    def get_state(self):
        if self._state is None:
            return False
        return (not self._state) if self._invert_state_mode else self._state

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                self._state = self._pi.read(self._pin)
            except Exception as e:
                logger.error(f"LimitSwitchSensor read error (pin {self._pin}): {e}")
            time.sleep(self._interval)


# ------------------------------------------------------------
# 2. Дальномер VL53L0X
# ------------------------------------------------------------
class VL53L0X:
    REG_SYSRANGE_START = 0x00
    REG_INTERRUPT_STATUS = 0x14
    REG_RESULT_RANGE_HIGH = 0x1E
    REG_RESULT_RANGE_LOW = 0x1F
    REG_IDENTIFICATION_MODEL_ID = 0xC0

    def __init__(self, bus=1, address=0x29):
        self.bus = smbus2.SMBus(bus)
        self.addr = address

    def write_reg(self, reg, val):
        self.bus.write_byte_data(self.addr, reg, val)

    def read_reg(self, reg):
        return self.bus.read_byte_data(self.addr, reg)

    def read_two_bytes(self, reg):
        hi = self.read_reg(reg)
        lo = self.read_reg(reg + 1)
        return (hi << 8) | lo

    def init(self):
        model_id = self.read_reg(self.REG_IDENTIFICATION_MODEL_ID)
        if model_id not in (0xEE, 0xCC, 0xAA):
            raise RuntimeError(f"VL53L0X not detected. model_id={hex(model_id)}")

        self.write_reg(self.REG_SYSRANGE_START, 0x01)
        logger.info("VL53L0X initialized")

    def get_distance(self):
        while True:
            status = self.read_reg(self.REG_INTERRUPT_STATUS)
            if status & 0x07:
                break
            time.sleep(0.002)

        dist_mm = self.read_two_bytes(self.REG_RESULT_RANGE_HIGH)
        self.write_reg(self.REG_SYSRANGE_START, 0x01)
        return dist_mm


class DistanceSensor(threading.Thread):
    def __init__(self, sensor=None, interval=0.05, filter_size=40):
        super().__init__(daemon=True)

        if sensor is None:
            vl53 = VL53L0X()
            try:
                vl53.init()
            except Exception as e:
                logger.error(f"VL53L0X init failed: {e}")
            self._sensor = vl53
        else:
            self._sensor = sensor

        self._interval = interval
        self._stop = threading.Event()
        self._raw_distance = None
        self._distance = None
        self._window = deque(maxlen=filter_size)

    def get_distance(self):
        return self._distance

    def get_raw_distance(self):
        return self._raw_distance

    def is_in_range(self, low, high):
        if self._distance is None:
            return False
        return low < self._distance < high

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                d = self._sensor.get_distance()
                self._raw_distance = d
                self._window.append(d)
                if self._window:
                    self._distance = statistics.median(self._window)

            except Exception as e:
                logger.error(f"DistanceSensor error: {e}")

            time.sleep(self._interval)


# ------------------------------------------------------------
# 3. Температура
# ------------------------------------------------------------
class TempSensor(threading.Thread):
    def __init__(self, sensor=None, interval=1.0):
        super().__init__(daemon=True)
        self._sensor = sensor or W1ThermSensor()
        self._temp = None
        self._interval = interval
        self._stop = threading.Event()

    def get_temp(self):
        return self._temp

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                self._temp = self._sensor.get_temperature()
            except Exception as e:
                logger.error(f"TempSensor error: {e}")
            time.sleep(self._interval)


# ------------------------------------------------------------
# Структуры данных
# ------------------------------------------------------------
@dataclass
class DeliverySensors:
    socket1: bool
    socket2: bool
    socket3: bool
    socket4: bool
    socket5: bool
    temperatureSensor: float


class PaketManager:
    bf = "<Bf"
    packet_size = 32

    @classmethod
    def encode(cls, s: DeliverySensors) -> bytes:
        flags = (
                (1 if s.socket1 else 0)
                | ((1 if s.socket2 else 0) << 1)
                | ((1 if s.socket3 else 0) << 2)
                | ((1 if s.socket4 else 0) << 3)
                | ((1 if s.socket5 else 0) << 4)
        )

        core = struct.pack(cls.bf, flags, s.temperatureSensor)
        return core + bytes(cls.packet_size - len(core))

    @classmethod
    def to_channels(cls, sensors: DeliverySensors):
        pkg = cls.encode(sensors)
        return list(struct.unpack("<16H", pkg))


# ------------------------------------------------------------
# Mavlink
# ------------------------------------------------------------
class MavlinkConnectionService:
    def __init__(self, device="/dev/serial0", source_system=255, source_component=10):
        self.device = device
        self.source_system = source_system
        self.source_component = source_component
        self.conn = None
        self.running = True
        self.queue = queue.Queue()

        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def send_sensors(self, data: DeliverySensors):
        self.queue.put(data)

    def _connect(self):
        return mavutil.mavlink_connection(
            device=self.device,
            source_system=self.source_system,
            source_component=self.source_component,
        )

    def _send_channels(self, sensors: DeliverySensors):
        arr = PaketManager.to_channels(sensors)
        padded = arr + [0] * (16 - len(arr))
        try:
            self.conn.mav.servo_output_raw_send(0, 1, *padded)
        except Exception as e:
            logger.error(f"MAV send error: {e}")
            raise

    def _worker(self):
        while self.running:
            try:
                logger.info("Connecting MAVLink...")
                self.conn = self._connect()
                self.conn.wait_heartbeat(timeout=5)
                logger.info("MAVLink connected")

                while self.running:
                    try:
                        sensors = self.queue.get(timeout=0.1)
                        self._send_channels(sensors)
                    except queue.Empty:
                        continue
                    except Exception:
                        break

            except Exception as e:
                logger.error(f"MAV worker connection error: {e}")
                time.sleep(1)

            time.sleep(1)

    def stop(self):
        self.running = False
        if self.conn:
            try:
                self.conn.close()
            except:
                pass


# ------------------------------------------------------------
# Дверь/защелки
# ------------------------------------------------------------
from enum import Enum
from typing import List, Deque


class LatchState(Enum):
    OPEN = "open"
    CLOSED = "closed"
    ERROR = "error"


maxsize: int = 10


@dataclass
class Latch:
    # Очереди для фильтрации каждого канала
    _open_queue: Deque[bool] = field(default_factory=lambda: deque(maxlen=maxsize))
    _close_queue: Deque[bool] = field(default_factory=lambda: deque(maxlen=maxsize))

    def set_state(self, open_limit: bool, close_limit: bool):
        """
        Сеттер состояния: добавляет новые значения в очереди.
        """
        self._open_queue.append(open_limit)
        self._close_queue.append(close_limit)

    @property
    def open_limit(self) -> bool:
        """
        Вычисляет устойчивое состояние open_limit на основе очереди.
        Возвращает большинство значений.
        """
        if not self._open_queue:
            return False

        true_count = sum(self._open_queue)
        false_count = len(self._open_queue) - true_count
        return true_count >= false_count

    @property
    def close_limit(self) -> bool:
        """
        Аналогично open_limit.
        """
        if not self._close_queue:
            return False

        true_count = sum(self._close_queue)
        false_count = len(self._close_queue) - true_count
        return true_count >= false_count

    def get_state(self) -> "LatchState":
        """
        Возвращает итоговое состояние на основе фильтрованных значений.
        """
        o = self.open_limit
        c = self.close_limit

        if o and not c:
            return LatchState.OPEN
        elif not o and c:
            return LatchState.CLOSED

        return LatchState.ERROR


@dataclass
class Door:
    latches: List[Latch]

    def get_state(self) -> LatchState:
        states = [l.get_state() for l in self.latches]
        if any(s == LatchState.ERROR for s in states):
            return LatchState.ERROR
        if len(set(states)) != 1:
            return LatchState.ERROR
        return states[0]


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
if __name__ == "__main__":
    pi = pigpio.pi()
    if not pi.connected:
        logger.error("pigpio не подключён")
        exit(1)

    conn = MavlinkConnectionService()

    limit_switchers = {
        'close_limit1': LimitSwitchSensor(pi, gpio=22, invert_state_mode=True),
        'close_limit2': LimitSwitchSensor(pi, gpio=23, invert_state_mode=True),

        'open_limit1': LimitSwitchSensor(pi, gpio=24, invert_state_mode=True),
        'open_limit2': LimitSwitchSensor(pi, gpio=25, invert_state_mode=True),
    }

    distance_sensor = DistanceSensor()
    temp_sensor = TempSensor()

    for s in limit_switchers.values():
        s.start()

    distance_sensor.start()
    temp_sensor.start()

    l1 = Latch()
    l2 = Latch()

    door = Door([l1, l2])

    try:
        while True:
            switchers_states = {k: v.get_state() for k, v in limit_switchers.items()}

            l1.set_state(switchers_states["open_limit1"], switchers_states["close_limit1"])
            l2.set_state(switchers_states["open_limit2"], switchers_states["close_limit2"])

            dist = distance_sensor.get_distance()
            temp = temp_sensor.get_temp()

            in_range = distance_sensor.is_in_range(50, 350)
            # Формируем пакет

            sockets = [l1.close_limit, l2.close_limit, l1.open_limit, l2.open_limit] + [in_range]
            packet = DeliverySensors(*sockets, temperatureSensor=temp)

            logger.info(f"temp={temp}, dist={dist}, {packet=}")
            logger.info(f"{l1=} {l2=} door={door.get_state().value}")

            conn.send_sensors(packet)
            time.sleep(0.1)

    except KeyboardInterrupt:
        pass
    finally:
        for s in limit_switchers.values():
            s.stop()
        distance_sensor.stop()
        temp_sensor.stop()
        pi.stop()

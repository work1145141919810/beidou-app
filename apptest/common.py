import binascii
import time
import logging
import serial
import os
import serial.tools.list_ports
from datetime import datetime, timezone, timedelta

# ========== 配置 ==========
CONFIG = {
    "source_user_id": "4216808",
    "target_user_id": "4216804",
    "freq_point": 2,
    "ack_req": 1,
    "encode_type": 2,
    "send_freq": 0,
    "default_baud": 115200,
    "relay_baud": 115200,
    "retry_count": 3,
    "retry_delay": 5.0,
    "relay_addr": 0x11,
    "relay_read_timeout": 1.5,
    "relay_silence_gap": 0.05,
    "relay_cmd_interval": 0.3,
    "relay_retry_delay": 0.5,
    "relay_post_send_wait": 0.2,
    "temp_baud": 9600,
    "temp_read_timeout": 1.0,
    "temp_query_interval": 180,
    "enable_gui": True,
    "beijing_offset": 8,
    "exit_flag_file": "beidou_exit.flag",
    "relay_response_timeout": 180,
    "temp_response_timeout": 180,
}

# ---------- 设备自动匹配规则 ----------
# 可根据实际 VID/PID 或描述关键字调整
DEVICE_MATCH_RULES = {
    "beidou": {
        # 示例：FTDI 芯片
        "vid": 0x0403,
        "pid": 0x6001,
        # 若 VID/PID 不匹配，可使用描述关键字
        "description_keywords": ["USB Serial", "FTDI"]
    },
    "relay": {
        "description_keywords": ["USB-SERIAL", "CH340", "CP210"]
    },
    "temp": {
        "description_keywords": ["USB-SERIAL", "CH340", "CP210"]
    }
}

# ========== 日志 ==========
def setup_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    return logging.getLogger('beidou')

log = setup_logging()

# ========== 退出标志 ==========
def set_exit_flag():
    flag_path = CONFIG.get("exit_flag_file", "beidou_exit.flag")
    try:
        with open(flag_path, 'w') as f:
            f.write("exit")
    except Exception as e:
        log.error(f"设置退出标志失败: {e}")

def clear_exit_flag():
    flag_path = CONFIG.get("exit_flag_file", "beidou_exit.flag")
    try:
        if os.path.exists(flag_path):
            os.remove(flag_path)
    except Exception as e:
        log.error(f"清除退出标志失败: {e}")

def check_exit_flag():
    flag_path = CONFIG.get("exit_flag_file", "beidou_exit.flag")
    return os.path.exists(flag_path)

# ========== 自动探测串口 ==========
def auto_detect_port(device_type: str) -> str:
    """
    根据设备类型自动探测串口号
    返回第一个匹配的端口名，若未找到返回 None
    """
    rule = DEVICE_MATCH_RULES.get(device_type)
    if not rule:
        log.warning(f"未定义设备类型 '{device_type}' 的匹配规则")
        return None

    candidates = []
    for port in serial.tools.list_ports.comports():
        # 检查 VID/PID
        if rule.get("vid") and port.vid == rule["vid"] and port.pid == rule["pid"]:
            candidates.append(port.device)
            continue
        # 检查描述关键字
        if rule.get("description_keywords"):
            desc = (port.description or "").lower()
            for kw in rule["description_keywords"]:
                if kw.lower() in desc:
                    candidates.append(port.device)
                    break

    if len(candidates) == 1:
        log.info(f"自动识别 {device_type} -> {candidates[0]}")
        return candidates[0]
    elif len(candidates) > 1:
        log.warning(f"发现多个匹配 {device_type} 的端口: {candidates}，请手动选择")
    else:
        log.info(f"未自动匹配到 {device_type} 端口")
    return None

def get_all_ports_info():
    """返回所有可用串口的信息列表，用于 GUI 选择"""
    ports = []
    for p in serial.tools.list_ports.comports():
        desc = f"{p.device} - {p.description}"
        if p.manufacturer:
            desc += f" ({p.manufacturer})"
        ports.append((p.device, desc))
    return ports

# ========== CRC 校验 ==========
def calc_modbus_crc(data: bytes) -> bytes:
    crc = 0xFFFF
    poly = 0xA001
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ poly
            else:
                crc >>= 1
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])

def verify_modbus_crc(data: bytes) -> bool:
    if len(data) < 4:
        return False
    calc_crc = calc_modbus_crc(data[:-2])
    return calc_crc == data[-2:]

def is_relay_command(data: bytes) -> bool:
    if len(data) != 10:
        return False
    if data[0] != 0x11:
        return False
    if data[1] not in (0x0F, 0x05):
        return False
    return verify_modbus_crc(data)

def is_temp_command(data: bytes) -> bool:
    if len(data) != 8:
        return False
    if data[0] != 0x01:
        return False
    if data[1] != 0x03:
        return False
    return verify_modbus_crc(data)

def is_temp_response(data: bytes) -> bool:
    if len(data) < 5:
        return False
    if data[0] != 0x01:
        return False
    if data[1] != 0x03:
        return False
    return verify_modbus_crc(data)

def parse_temp_value(data: bytes) -> float:
    if len(data) < 5:
        return 0.0
    byte_count = data[2]
    if byte_count >= 2 and len(data) >= 5:
        raw = (data[3] << 8) | data[4]
        return raw / 10.0
    return 0.0

# ========== NMEA 校验和 ==========
def calc_nmea_checksum(nmea_body: str) -> str:
    cs = 0
    for c in nmea_body:
        cs ^= ord(c)
    return f"{cs:02X}"

# ========== 数据转换 ==========
def hex2bytes(hex_str: str) -> bytes:
    return binascii.unhexlify(hex_str.replace(" ", ""))

def bytes2hex(data: bytes) -> str:
    return " ".join([f"{b:02X}" for b in data])

def decode_serial_data(data: bytes):
    if not data:
        return "", "none"
    for enc in ('gbk', 'utf-8'):
        try:
            return data.decode(enc).strip(), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode('ascii', errors='replace').strip(), 'ascii'

# ========== 北斗报文构建 ==========
def build_cctcq_msg(target_id: str, freq_point: int, ack: int, encode_type: int, freq: int, payload_hex: str):
    body = f"{target_id},{freq_point},{ack},{encode_type},{payload_hex},{freq}"
    full = f"$CCTCQ,{body}"
    cs = calc_nmea_checksum(full[1:])
    return f"{full}*{cs}\r\n"

def build_cctxa_msg(target_id: str, freq_point: int, ack: int, payload_hex: str):
    payload_bytes = hex2bytes(payload_hex)
    payload_len = len(payload_bytes)
    body = f"{target_id},{freq_point},{ack},{payload_len},{payload_hex}"
    full = f"$CCTXA,{body}"
    cs = calc_nmea_checksum(full[1:])
    return f"{full}*{cs}\r\n"

# ========== Modbus 指令预定义 ==========
RELAY_CMD = {
    "all_close": hex2bytes("11 0F 00 00 00 04 01 0F 7F 9E"),
    "all_open":  hex2bytes("11 0F 00 00 00 04 01 00 3F 9A"),
}
TEMP_CMD = hex2bytes("01 03 00 00 00 02 C4 0B")

# ========== 频点映射 ==========
FREQ_TO_CMD = {
    10: "all_close",
    11: "all_open",
}
CMD_TO_FREQ = {v: k for k, v in FREQ_TO_CMD.items()}

# ========== Modbus 指令校验 ==========
def is_valid_modbus_command(data: bytes) -> bool:
    if len(data) < 5 or len(data) > 256:
        return False
    slave_addr = data[0]
    if slave_addr == 0x00 or slave_addr > 0xF7:
        return False
    if slave_addr == 0xD1:
        return False
    func_code = data[1]
    valid_func_codes = {
        0x01, 0x02, 0x03, 0x04, 0x05, 0x06,
        0x0F, 0x10, 0x11, 0x14, 0x15, 0x16,
        0x17, 0x18, 0x2B, 0x2C, 0x2D, 0x2E,
        0x2F, 0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47
    }
    if func_code not in valid_func_codes:
        return False
    if data[-2] == 0x00 and data[-1] == 0x00:
        return False
    return True

# ========== A225 解析 ==========
def parse_a225_location(data: bytes) -> list:
    if len(data) < 5 or data[0] != 0xD1 or data[1] != 0x35:
        return None

    num_points = data[2]
    if num_points == 0:
        return []

    points = []
    pos = 3
    for _ in range(num_points):
        if pos + 1 + 3 + 3 + 4 + 4 + 2 + 2 + 2 > len(data):
            break
        status = data[pos]
        pos += 1
        year = data[pos] + 2000
        month = data[pos+1]
        day = data[pos+2]
        pos += 3
        hour = data[pos]
        minute = data[pos+1]
        second = data[pos+2]
        pos += 3
        lng_raw = int.from_bytes(data[pos:pos+4], 'big', signed=True)
        lng = lng_raw / 1_000_000.0
        pos += 4
        lat_raw = int.from_bytes(data[pos:pos+4], 'big', signed=True)
        lat = lat_raw / 1_000_000.0
        pos += 4
        alt_raw = int.from_bytes(data[pos:pos+2], 'big', signed=True)
        alt = alt_raw / 10.0
        pos += 2
        speed_raw = int.from_bytes(data[pos:pos+2], 'big', signed=True)
        speed = speed_raw / 100.0
        pos += 2
        heading = int.from_bytes(data[pos:pos+2], 'big', signed=False)
        pos += 2

        dt_utc = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
        points.append({
            'status': status,
            'datetime_utc': dt_utc,
            'lng': lng,
            'lat': lat,
            'alt': alt,
            'speed': speed,
            'heading': heading
        })
    if len(data) > pos:
        checksum = data[-1]
        calc = 0
        for b in data[:-1]:
            calc ^= b
        if calc != checksum:
            log.warning("A225 校验和不匹配，但仍返回解析结果")
    return points

def format_location_for_display(points, beijing_offset=8):
    lines = []
    for p in points:
        dt_beijing = p['datetime_utc'] + timedelta(hours=beijing_offset)
        line = (f"时间(北京): {dt_beijing.strftime('%Y-%m-%d %H:%M:%S')} | "
                f"经度: {p['lng']:.6f}° | 纬度: {p['lat']:.6f}° | "
                f"海拔: {p['alt']:.1f}m | 速度: {p['speed']:.2f}m/s | "
                f"方向: {p['heading']}°")
        lines.append(line)
    return "\n".join(lines)

def encode_location_to_text(points, beijing_offset=8):
    parts = []
    for p in points:
        dt_beijing = p['datetime_utc'] + timedelta(hours=beijing_offset)
        time_str = dt_beijing.strftime('%Y%m%d%H%M%S')
        part = f"{time_str},{p['lng']:.6f},{p['lat']:.6f},{p['alt']:.1f},{p['speed']:.2f},{p['heading']}"
        parts.append(part)
    return ";".join(parts)
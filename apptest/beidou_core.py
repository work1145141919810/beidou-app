# beidou_core.py
"""
北斗短报文业务逻辑核心类，不依赖GUI和具体串口实现。
通过回调函数与外部交互，可移植到PC或Android。
"""
import time
from typing import Callable, Optional, List, Dict
from common import (
    CONFIG, build_cctcq_msg, RELAY_CMD, TEMP_CMD,
    bytes2hex, hex2bytes, is_temp_response, parse_temp_value,
    parse_a225_location, format_location_for_display, log
)

class BeidouController:
    def __init__(self, source_id: str = None, target_id: str = None):
        """
        初始化控制器
        :param source_id: 本机用户ID（发送方）
        :param target_id: 目标用户ID（接收方，即远端设备）
        """
        self.source_id = source_id or CONFIG.get('source_user_id', '4216808')
        self.target_id = target_id or CONFIG.get('target_user_id', '4216804')
        self.freq_point = CONFIG.get('freq_point', 2)
        self.ack_req = CONFIG.get('ack_req', 1)
        self.encode_type = CONFIG.get('encode_type', 2)

        # 状态变量
        self._relay_closed: Optional[bool] = None   # True=闭合, False=断开
        self._latest_temp: Optional[float] = None
        self._auto_temp_control: bool = True

        # 回调函数（由外部注入）
        self.on_log: Callable[[str], None] = None             # 日志信息
        self.on_temp_updated: Callable[[float], None] = None  # 温度更新
        self.on_relay_response: Callable[[str, bool], None] = None  # (指令名, 成功)
        self.on_location: Callable[[List[Dict]], None] = None # 定位点列表

        # 串口发送函数（外部提供，例如 ser.write）
        self.send_serial: Callable[[bytes], bool] = None

        log.info(f"BeidouController 初始化: 本机={self.source_id}, 目标={self.target_id}")

    # ---------- 对外发送接口 ----------
    def send_relay_command(self, cmd_name: str) -> bool:
        """发送继电器指令（all_close / all_open），返回是否发送成功（不代表执行成功）"""
        if cmd_name not in RELAY_CMD:
            self._log(f"[错误] 未知继电器指令: {cmd_name}")
            return False
        cmd_bytes = RELAY_CMD[cmd_name]
        cmd_hex = bytes2hex(cmd_bytes).replace(" ", "")
        nmea_msg = build_cctcq_msg(
            target_id=self.target_id,
            freq_point=self.freq_point,
            ack=self.ack_req,
            encode_type=self.encode_type,
            freq=0,
            payload_hex=cmd_hex
        )
        self._log(f"[发送] 继电器指令: {cmd_name}")
        return self._send_nmea(nmea_msg)

    def send_temp_query(self) -> bool:
        """发送温度查询指令"""
        temp_hex = bytes2hex(TEMP_CMD).replace(" ", "")
        nmea_msg = build_cctcq_msg(
            target_id=self.target_id,
            freq_point=self.freq_point,
            ack=self.ack_req,
            encode_type=self.encode_type,
            freq=0,
            payload_hex=temp_hex
        )
        self._log("[温度] 发送温度查询指令")
        return self._send_nmea(nmea_msg)

    def _send_nmea(self, nmea_msg: str) -> bool:
        """内部：通过串口发送NMEA报文"""
        if not self.send_serial:
            self._log("[错误] 未设置 send_serial 回调，无法发送")
            return False
        try:
            self.send_serial(nmea_msg.encode('ascii'))
            return True
        except Exception as e:
            self._log(f"[错误] 发送失败: {e}")
            return False

    # ---------- 数据解析入口（外部收到NMEA时调用） ----------
    def parse_received_nmea(self, line: str):
        """处理从北斗接收到的NMEA行（主要是BDTCI）"""
        if not line.startswith('$BDTCI') or '*' not in line:
            return
        body = line.split('*')[0]
        fields = body.split(',')
        if len(fields) < 8:
            return
        sender = fields[1]
        receiver = fields[2]
        # 只处理从目标设备回传的数据（即：发送方是目标ID，接收方是本机）
        if sender != self.target_id or receiver != self.source_id:
            return
        payload_hex = fields[7]
        try:
            data = hex2bytes(payload_hex)
        except:
            self._log("[警告] 载荷hex解码失败")
            return

        # 1. 检查是否为温度响应（Modbus 0x01 0x03）
        if is_temp_response(data):
            temp = parse_temp_value(data)
            self._latest_temp = temp
            self._log(f"[温度] 更新: {temp:.1f}°C")
            if self.on_temp_updated:
                self.on_temp_updated(temp)
            # 自动温控
            if self._auto_temp_control:
                self._auto_control(temp)
            return

        # 2. 检查是否为继电器反馈（文本格式 RELAY:cmd:status）
        try:
            text = data.decode('utf-8')
            if text.startswith('RELAY:'):
                parts = text.split(':')
                if len(parts) >= 3:
                    cmd_name = parts[1]
                    status = parts[2]
                    success = (status == '成功')
                    self._log(f"[接收] 继电器反馈: {cmd_name} -> {status}")
                    if self.on_relay_response:
                        self.on_relay_response(cmd_name, success)
                    # 更新内部状态
                    if success:
                        if cmd_name == 'all_close':
                            self._relay_closed = True
                        elif cmd_name == 'all_open':
                            self._relay_closed = False
                return
        except UnicodeDecodeError:
            pass

        # 3. 检查是否为 A225 定位数据
        if len(data) >= 5 and data[0] == 0xD1 and data[1] == 0x35:
            points = parse_a225_location(data)
            if points:
                self._log(f"[定位] 收到 {len(points)} 个定位点")
                if self.on_location:
                    self.on_location(points)
                return

        self._log(f"[警告] 未识别的载荷: {bytes2hex(data)}")

    # ---------- 自动温控逻辑 ----------
    def _auto_control(self, temp: float):
        """根据温度自动控制继电器（需内部状态已知）"""
        if self._relay_closed is None:
            self._log("[警告] 自动温控: 继电器状态未知，不操作")
            return
        if temp >= 27.0 and self._relay_closed is not False:
            self._log(f"[高温] 自动温控: 温度 {temp:.1f}°C >= 27，断开继电器")
            self.send_relay_command('all_open')
        elif temp < 24.0 and self._relay_closed is not True:
            self._log(f"[低温] 自动温控: 温度 {temp:.1f}°C < 24，闭合继电器")
            self.send_relay_command('all_close')
        else:
            self._log(f"[正常] 自动温控: 温度 {temp:.1f}°C 在保持区间 (24~27)，当前继电器: {'闭合' if self._relay_closed else '断开'}")

    # ---------- 状态查询 ----------
    def get_relay_state(self) -> Optional[bool]:
        return self._relay_closed

    def get_latest_temp(self) -> Optional[float]:
        return self._latest_temp

    def set_auto_temp_control(self, enable: bool):
        self._auto_temp_control = enable

    # ---------- 内部日志 ----------
    def _log(self, msg: str):
        if self.on_log:
            self.on_log(msg)
        else:
            print(f"[Core] {msg}")
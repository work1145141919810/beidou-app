import argparse
import serial
import serial.tools.list_ports
import time
import threading
from collections import deque
from common import (build_cctcq_msg, RELAY_CMD, TEMP_CMD, bytes2hex, decode_serial_data,
                    CONFIG, log, hex2bytes, is_temp_response, parse_temp_value, calc_nmea_checksum,
                    parse_a225_location, format_location_for_display, encode_location_to_text,
                    set_exit_flag, clear_exit_flag, auto_detect_port)
import datetime

class BeidouSender:
    def __init__(self, port: str = None, baud=115200, log_callback=None):
        clear_exit_flag()
        if port is None:
            raise ValueError("必须指定串口名称")
        self.ser = serial.Serial(port=port, baudrate=baud, timeout=1)
        log.info(f"发送端北斗串口打开成功: {port} {baud}")
        log.info(f"本机地址: {CONFIG['source_user_id']}, 目标地址: {CONFIG['target_user_id']}")
        self.source_user_id = CONFIG["source_user_id"]
        self.target_user_id = CONFIG["target_user_id"]
        self.freq_point = CONFIG["freq_point"]
        self.ack_req = CONFIG["ack_req"]
        self.encode_type = CONFIG["encode_type"]
        self.retry_count = CONFIG["retry_count"]
        self.retry_delay = CONFIG["retry_delay"]
        self.send_timeout = 30.0
        self.temp_query_interval = CONFIG.get('temp_query_interval', 180)

        self.relay_response_timeout = CONFIG.get('relay_response_timeout', 300)
        self.temp_response_timeout = CONFIG.get('temp_response_timeout', 300)

        self.write_lock = threading.Lock()
        self.temp_event = threading.Event()
        self.relay_event = threading.Event()
        self.temp_response = None
        self.relay_response = None
        self.response_lock = threading.Lock()

        self._latest_temp = None
        self._temp_updated = threading.Event()
        self._listener_running = False
        self._temp_timer_running = False

        self.auto_temp_control = True
        self._relay_closed = None
        self._auto_control_lock = threading.Lock()
        self._payload_cache = []
        self._cache_max = 10
        self._cache_timeout = 5

        self.log_callback = log_callback or (lambda msg: log.info(msg))

        # 指令队列
        self.cmd_queue = deque()
        self.cmd_worker_stop = False
        self.cmd_worker_thread = threading.Thread(target=self._cmd_worker_loop, daemon=True)
        self.cmd_worker_thread.start()
        log.info("指令工作者线程已启动")

        self._enable_bdtci_output()

        self.gui = None  # 不再使用GUI

    def _cmd_worker_loop(self):
        log.info("指令工作者开始运行")
        while not self.cmd_worker_stop:
            try:
                try:
                    cmd_name, event, result_container = self.cmd_queue.popleft()
                except IndexError:
                    time.sleep(0.05)
                    continue
                success = self._execute_relay_cmd(cmd_name)
                result_container[0] = success
                event.set()
            except Exception as e:
                log.error(f"指令工作者异常: {e}")
                time.sleep(1)
        log.info("指令工作者已停止")

    def _execute_relay_cmd(self, cmd_name: str) -> bool:
        cmd_bytes = RELAY_CMD[cmd_name]
        cmd_hex = bytes2hex(cmd_bytes).replace(" ", "")
        nmea_msg = build_cctcq_msg(
            target_id=self.target_user_id,
            freq_point=self.freq_point,
            ack=self.ack_req,
            encode_type=self.encode_type,
            freq=0,
            payload_hex=cmd_hex
        )
        print(f"\n【待发送北斗报文】{nmea_msg.strip()}")
        print(f"【Modbus继电器指令】{bytes2hex(cmd_bytes)} ({cmd_name})")
        status_msg = f"继电器指令已发送（{cmd_name}），等待北斗回执确认..."
        self._display(status_msg, highlight=True)

        for attempt in range(1, self.retry_count + 1):
            if attempt > 1:
                log.info(f"第 {attempt} 次重试...")
                time.sleep(self.retry_delay)
            if not self._send_command(nmea_msg):
                continue
            resp = self._wait_for_response('relay', timeout=self.relay_response_timeout)
            if resp is not None:
                try:
                    text = resp.decode('utf-8')
                    if text.startswith('RELAY:'):
                        parts = text.split(':')
                        if len(parts) >= 3:
                            status = parts[2]
                            if status == '成功':
                                success_msg = f"✅ 继电器指令执行成功：{cmd_name}"
                                self._display(success_msg, highlight=True)
                                log.info("✓ 继电器指令执行成功")
                                if cmd_name == "all_close":
                                    self._relay_closed = True
                                elif cmd_name == "all_open":
                                    self._relay_closed = False
                                return True
                            else:
                                fail_msg = f"❌ 继电器指令执行失败：{cmd_name} (状态: {status})"
                                self._display(fail_msg, highlight=True)
                                log.warning(f"继电器指令执行失败: {status}")
                                return False
                    elif '成功' in text or 'Y' in text.upper():
                        success_msg = f"✅ 继电器指令执行成功：{cmd_name} (响应: {text[:50]})"
                        self._display(success_msg, highlight=True)
                        log.info("✓ 继电器指令执行成功")
                        if cmd_name == "all_close":
                            self._relay_closed = True
                        elif cmd_name == "all_open":
                            self._relay_closed = False
                        return True
                    else:
                        warn_msg = f"⚠️ 收到未知响应: {text[:50]}"
                        self._display(warn_msg, highlight=True)
                        log.warning(warn_msg)
                except Exception as e:
                    log.warning(f"响应解析失败: {e}")
            else:
                timeout_msg = f"⏰ 继电器指令 {cmd_name} 执行超时（{self.relay_response_timeout}s）"
                self._display(timeout_msg, highlight=True)
                log.warning(timeout_msg)

        log.error(f"继电器指令发送失败，已重试 {self.retry_count} 次")
        fail_msg = f"❌ 继电器指令 {cmd_name} 最终失败（重试{self.retry_count}次）"
        self._display(fail_msg, highlight=True)
        return False

    def send_relay_cmd_async(self, cmd_name: str):
        event = threading.Event()
        result_container = [False]
        self.cmd_queue.append((cmd_name, event, result_container))
        log.info(f"指令 {cmd_name} 已入队")

    def send_relay_cmd_sync(self, cmd_name: str, timeout: float = None) -> bool:
        event = threading.Event()
        result_container = [False]
        self.cmd_queue.append((cmd_name, event, result_container))
        if timeout is None:
            timeout = self.relay_response_timeout + 60
        event.wait(timeout)
        return result_container[0]

    def send_relay_cmd(self, cmd_name: str) -> bool:
        return self.send_relay_cmd_sync(cmd_name)

    def send_temp_cmd(self):
        temp_hex = bytes2hex(TEMP_CMD).replace(" ", "")
        nmea_msg = build_cctcq_msg(
            target_id=self.target_user_id,
            freq_point=self.freq_point,
            ack=self.ack_req,
            encode_type=self.encode_type,
            freq=0,
            payload_hex=temp_hex
        )
        print(f"\n{'='*40}")
        print(f"【温度采集指令】{nmea_msg.strip()}")
        print(f"【Modbus温度指令】{bytes2hex(TEMP_CMD)}")
        log.info("⏰ 温度采集触发")

        self._temp_updated.clear()
        if not self._send_command(nmea_msg):
            log.error("温度指令发送失败")
            return

        resp = self._wait_for_response('temp', timeout=self.temp_response_timeout)
        if resp is not None and is_temp_response(resp):
            temp = parse_temp_value(resp)
            self._latest_temp = temp
            self._temp_updated.set()
            temp_msg = f"🌡️ 当前远端温度：{temp:.1f}°C"
            self._display(temp_msg, highlight=True)
            self._auto_control_temp_async(temp)
        else:
            warn_msg = f"⚠️ 温度采集超时或无有效响应（超时{self.temp_response_timeout}s）"
            self._display(warn_msg, highlight=True)
            log.warning(warn_msg)

    def _enable_bdtci_output(self):
        commands = [
            "CCRMO,BDTCI,2,2",
            "CCRMO,BDTCI,2,1",
            "CCRMO,BDTCI,2,0",
        ]
        for body in commands:
            cs = calc_nmea_checksum(body)
            cmd = f"${body}*{cs}\r\n"
            try:
                with self.write_lock:
                    self.ser.write(cmd.encode())
                log.info(f"发送 BDTCI 使能命令: {cmd.strip()}")
                time.sleep(0.3)
            except Exception as e:
                log.warning(f"使能命令发送失败: {e}")

    def _send_command(self, nmea_msg: str) -> bool:
        try:
            with self.write_lock:
                self.ser.reset_input_buffer()
                self.ser.write(nmea_msg.encode("ascii"))
                self.ser.flush()
            log.info(f"已发送 {len(nmea_msg)} 字节到北斗设备")
            return True
        except Exception as e:
            log.error(f"发送失败: {e}")
            return False

    def _wait_for_response(self, resp_type: str, timeout: float) -> bytes:
        if resp_type == 'temp':
            event = self.temp_event
        elif resp_type == 'relay':
            event = self.relay_event
        else:
            return None

        event.clear()
        with self.response_lock:
            if resp_type == 'temp':
                self.temp_response = None
            else:
                self.relay_response = None

        if event.wait(timeout):
            with self.response_lock:
                if resp_type == 'temp':
                    return self.temp_response
                else:
                    return self.relay_response
        else:
            log.warning(f"等待 {resp_type} 响应超时 ({timeout}s)")
            return None

    def _auto_control_temp_async(self, temp: float):
        if not self.auto_temp_control:
            return
        with self._auto_control_lock:
            if temp >= 27.0 and self._relay_closed is not False:
                log.info(f"自动温控: 温度 {temp:.1f}°C >= 27，发送断开指令（异步）")
                threading.Thread(target=self.send_relay_cmd_async, args=("all_open",), daemon=True).start()
            elif temp < 24.0 and self._relay_closed is not True:
                log.info(f"自动温控: 温度 {temp:.1f}°C <= 24，发送闭合指令（异步）")
                threading.Thread(target=self.send_relay_cmd_async, args=("all_close",), daemon=True).start()
            else:
                log.debug(f"自动温控: 温度 {temp:.1f}°C 在保持区间，当前状态: {'闭合' if self._relay_closed else '断开' if self._relay_closed is not None else '未知'}")

    def _is_duplicate_payload(self, payload_hex: str) -> bool:
        now = time.time()
        self._payload_cache = [item for item in self._payload_cache if now - item['time'] < self._cache_timeout]
        for item in self._payload_cache:
            if item['payload'] == payload_hex:
                return True
        self._payload_cache.append({'payload': payload_hex, 'time': now})
        if len(self._payload_cache) > self._cache_max:
            self._payload_cache = self._payload_cache[-self._cache_max:]
        return False

    def _parse_received_payload(self, line: str):
        if not line.startswith('$BDTCI') or '*' not in line:
            return
        body = line.split('*')[0]
        fields = body.split(',')
        if len(fields) < 8:
            return
        sender = fields[1]
        receiver = fields[2]
        if sender != self.target_user_id or receiver != self.source_user_id:
            return

        payload_hex = fields[7]
        if self._is_duplicate_payload(payload_hex):
            log.debug(f"重复载荷，忽略: {payload_hex[:20]}...")
            return

        log.info(f"解析 BDTCI: {line.strip()[:100]}")
        try:
            data = hex2bytes(payload_hex)
            log.info(f"载荷字节({len(data)}字节): {bytes2hex(data)}")

            if is_temp_response(data):
                temp = parse_temp_value(data)
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                msg = f"[{timestamp}] [温度] {temp:.1f}°C (原始: {bytes2hex(data)})"
                self._display(msg, highlight=True)
                with self.response_lock:
                    self.temp_response = data
                self.temp_event.set()
                return

            try:
                text = data.decode('utf-8')
                if text.startswith('RELAY:'):
                    parts = text.split(':')
                    if len(parts) >= 3:
                        cmd = parts[1] if len(parts) > 1 else "未知指令"
                        status = parts[2]
                        if status == '成功':
                            display_msg = f"✅ 继电器执行反馈：{cmd} -> 成功"
                        else:
                            display_msg = f"❌ 继电器执行反馈：{cmd} -> {status}"
                    else:
                        display_msg = f"📡 继电器反馈: {text}"
                    self._display(display_msg, highlight=True)
                    log.info(f"★ 收到继电器执行反馈: {display_msg}")
                    with self.response_lock:
                        self.relay_response = data
                    self.relay_event.set()
                    return

                if text.startswith('POS:'):
                    log.info("★ 收到回传的定位数据")
                    self._display(f"[远端回传定位] {text[4:]}")
                    return

                if 'BDFKI' in text or 'BDOBD' in text:
                    with self.response_lock:
                        self.relay_response = data
                    self.relay_event.set()
                    return
            except UnicodeDecodeError:
                pass

            if len(data) >= 5 and data[0] == 0xD1 and data[1] == 0x35:
                log.info("★ 识别为 A225 原始定位数据")
                points = parse_a225_location(data)
                if points:
                    display_text = format_location_for_display(points, beijing_offset=CONFIG.get('beijing_offset', 8))
                    self._display(display_text)
                return

            log.warning("未识别的载荷")
        except Exception as e:
            log.warning(f"数据解析异常: {e}")

    def _display(self, text: str, highlight: bool = False):
        if highlight:
            self.log_callback(f"\n{'='*40}\n{text}\n{'='*40}\n")
        else:
            self.log_callback(text)

    def _listener_loop(self):
        log.info("后台 BDTCI 监听线程已启动")
        while self._listener_running:
            try:
                if self.ser.in_waiting:
                    chunk = self.ser.read(self.ser.in_waiting)
                    if chunk:
                        start_marker = b'$'
                        pos = 0
                        while True:
                            idx = chunk.find(start_marker, pos)
                            if idx == -1:
                                break
                            end = chunk.find(b'\r\n', idx)
                            if end == -1:
                                end = chunk.find(b'\n', idx)
                            if end == -1:
                                end = len(chunk)
                            else:
                                end += len(b'\r\n') if chunk.find(b'\r\n', idx) != -1 else 1
                            line_bytes = chunk[idx:end].strip()
                            if line_bytes and b'*' in line_bytes:
                                try:
                                    line_str = line_bytes.decode('ascii')
                                    self._parse_received_payload(line_str)
                                except UnicodeDecodeError:
                                    pass
                            pos = end
                else:
                    time.sleep(0.1)
            except Exception as e:
                log.error(f"监听线程异常: {e}")
                time.sleep(1)

    def start_listener(self):
        if self._listener_running:
            return
        self._listener_running = True
        t = threading.Thread(target=self._listener_loop, daemon=True)
        t.start()

    def stop_listener(self):
        self._listener_running = False

    def start_temp_timer(self):
        if self._temp_timer_running:
            log.info("温度采集定时器已在运行")
            return
        self._temp_timer_running = True
        def timer_loop():
            log.info(f"⏰ 温度采集定时器已启动 (间隔 {self.temp_query_interval}s)")
            try:
                self.send_temp_cmd()
            except Exception as e:
                log.error(f"初始温度采集异常: {e}")
            while self._temp_timer_running:
                slept = 0
                while slept < self.temp_query_interval and self._temp_timer_running:
                    time.sleep(0.5)
                    slept += 0.5
                if not self._temp_timer_running:
                    break
                log.info(f"⏰ 温度采集定时触发 (间隔 {self.temp_query_interval}s)")
                try:
                    self.send_temp_cmd()
                except Exception as e:
                    log.error(f"温度采集异常: {e}")
            log.info("✓ 温度采集定时器已停止")
        t = threading.Thread(target=timer_loop, daemon=True)
        t.start()

    def stop_temp_timer(self):
        if not self._temp_timer_running:
            log.info("温度采集定时器未在运行")
            return False
        self._temp_timer_running = False
        log.info("⏹ 正在停止温度采集定时器...")
        time.sleep(0.6)
        log.info("✓ 温度采集定时器已停止")
        return True

    def is_temp_timer_running(self):
        return self._temp_timer_running

    def close(self):
        self.cmd_worker_stop = True
        if self.cmd_worker_thread.is_alive():
            self.cmd_worker_thread.join(timeout=2)
        self.stop_listener()
        self.stop_temp_timer()
        set_exit_flag()
        time.sleep(0.2)
        self.ser.close()
        log.info("发送端串口已关闭")
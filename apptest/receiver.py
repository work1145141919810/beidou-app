import argparse
import binascii
import serial
import serial.tools.list_ports
import time
import threading
from datetime import datetime
from common import (bytes2hex, decode_serial_data, CONFIG, log, hex2bytes, is_valid_modbus_command,
                    is_relay_command, is_temp_command, is_temp_response, parse_temp_value,
                    build_cctcq_msg, FREQ_TO_CMD, RELAY_CMD, TEMP_CMD, calc_nmea_checksum,
                    parse_a225_location, format_location_for_display, encode_location_to_text,
                    check_exit_flag, clear_exit_flag, auto_detect_port, set_exit_flag)

class BeidouReceiver:
    def __init__(self, beidou_port: str = None, relay_port: str = None, temp_port: str = None,
                 bd_baud=115200, relay_baud=115200, temp_baud=9600, log_callback=None):
        clear_exit_flag()
        if beidou_port is None or relay_port is None:
            raise ValueError("必须指定北斗和继电器串口")
        # 直接使用传入端口
        self.ser_bd = serial.Serial(beidou_port, baudrate=bd_baud, timeout=0.5)
        self.ser_relay = serial.Serial(relay_port, baudrate=relay_baud, timeout=0.5)
        self.ser_temp = serial.Serial(temp_port, baudrate=temp_baud, timeout=0.5) if temp_port else None
        log.info(f"接收端北斗:{beidou_port}({bd_baud}) 继电器:{relay_port}({relay_baud})"
                 f"{' 温度传感器:' + temp_port + '(' + str(temp_baud) + ')' if temp_port else ''}")
        log.info(f"本机地址: {CONFIG['target_user_id']}, 期望发送方: {CONFIG['source_user_id']}")
        self.last_processed_bdtci_key = None
        self.last_relay_cmd_time = 0.0
        self.freq_point = CONFIG['freq_point']
        self.ack_req = CONFIG['ack_req']
        self.encode_type = CONFIG['encode_type']

        self.log_callback = log_callback or (lambda msg: log.info(msg))

        self.gui = None  # 移除GUI

        self._enable_bdtci_output()

    def _enable_bdtci_output(self):
        body = "CCRMO,BDTCI,2,2"
        cs = calc_nmea_checksum(body)
        cmd = f"${body}*{cs}\r\n"
        try:
            self.ser_bd.write(cmd.encode())
            log.info("已发送 BDTCI 输出使能命令")
            time.sleep(0.2)
        except Exception as e:
            log.warning(f"使能 BDTCI 输出失败（可忽略）: {e}")

    def _read_lines(self, timeout=2.0) -> list:
        deadline = time.time() + timeout
        lines = []
        buf = b''
        while time.time() < deadline:
            ch = self.ser_bd.read(1)
            if ch:
                buf += ch
                if b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    lines.append(line)
            else:
                if lines:
                    time.sleep(0.05)
                else:
                    time.sleep(0.1)
        if buf:
            lines.append(buf)
        return lines

    def _decode_bdtci_payload(self, payload_hex: str) -> bytes:
        if not payload_hex:
            return None
        payload_hex = payload_hex.strip()
        try:
            raw = hex2bytes(payload_hex)
        except (binascii.Error, ValueError):
            log.warning(f"载荷 hex 解码失败: {payload_hex[:40]}")
            return None
        log.info(f"BDTCI 载荷({len(raw)}字节): {bytes2hex(raw)}")
        if is_valid_modbus_command(raw):
            log.info(f"✓ 载荷即为有效 Modbus 指令: {bytes2hex(raw)}")
            return raw
        if raw[0] == 0xD1:
            log.info("检测到 D1 结构 (BDCP编码), 尝试 BDCP 解码...")
            decoded = self._bdcp_d1_decode(raw)
            if decoded and is_valid_modbus_command(decoded):
                log.info(f"✓ BDCP 解码成功: {bytes2hex(decoded)}")
                return decoded
            else:
                log.warning("BDCP 解码失败")
        for start in range(len(raw)):
            for end in range(start + 5, min(start + 20, len(raw))):
                test = raw[start:end]
                if is_valid_modbus_command(test):
                    log.info(f"✓ 搜索找到 Modbus: {bytes2hex(test)}")
                    return test
        log.warning("所有解码策略均失败")
        return None

    def _bdcp_d1_decode(self, raw: bytes) -> bytes:
        if len(raw) < 5 or raw[0] != 0xD1:
            return None
        frame_len = raw[1]
        encode_type = raw[2]
        block_count = raw[3]
        log.info(f"D1 帧: len={frame_len}, type={encode_type}, blocks={block_count + 1}")
        blocks_data = []
        pos = 4
        for block_idx in range(block_count + 1):
            if pos >= len(raw):
                break
            if raw[pos] == 0x1A:
                pos += 4
                if block_idx < block_count:
                    next_1a = raw.find(b'\x1A', pos)
                    if next_1a == -1:
                        next_1a = len(raw) - 1
                    block_data = raw[pos:next_1a]
                    pos = next_1a
                else:
                    block_data = raw[pos:len(raw) - 1]
                    pos = len(raw) - 1
                blocks_data.append(block_data)
            else:
                break
        if not blocks_data:
            log.warning("D1 结构中未找到任何数据块")
            return None
        all_data = b''.join(blocks_data)
        log.info(f"合并块数据({len(all_data)}字节): {bytes2hex(all_data)}")
        strategies = [
            ('pair_hi_hi', self._nibble_pair_decode(all_data, 'hi_hi')),
            ('pair_lo_lo', self._nibble_pair_decode(all_data, 'lo_lo')),
            ('pair_hi_lo', self._nibble_pair_decode(all_data, 'hi_lo')),
            ('pair_lo_hi', self._nibble_pair_decode(all_data, 'lo_hi')),
            ('xor', self._pair_xor(all_data)),
            ('block_xor', self._block_xor(all_data)),
            ('swap', self._swap_nibbles(all_data)),
            ('alt_xor', self._alt_xor(all_data)),
        ]
        for name, result in strategies:
            if result and is_valid_modbus_command(result):
                log.info(f"✓ BDCP 解码成功 ({name}): {bytes2hex(result)}")
                return result
        if len(all_data) >= 5 and is_valid_modbus_command(all_data[:10]):
            return all_data[:10]
        return None

    def _nibble_pair_decode(self, data: bytes, mode: str) -> bytes:
        result = []
        for i in range(0, len(data) - 1, 2):
            even, odd = data[i], data[i + 1]
            if mode == 'hi_hi':
                result.append(((even >> 4) << 4) | (odd >> 4))
            elif mode == 'lo_lo':
                result.append(((even & 0x0F) << 4) | (odd & 0x0F))
            elif mode == 'hi_lo':
                result.append(((even >> 4) << 4) | (odd & 0x0F))
            elif mode == 'lo_hi':
                result.append(((even & 0x0F) << 4) | (odd >> 4))
        return bytes(result) if result else None

    def _pair_xor(self, data: bytes) -> bytes:
        result = [data[i] ^ data[i + 1] for i in range(0, len(data) - 1, 2)]
        return bytes(result) if result else None

    def _alt_xor(self, data: bytes) -> bytes:
        result = []
        for i in range(0, len(data) - 1, 2):
            a, b = data[i], data[i + 1]
            result.append(a ^ b ^ 0x55)
        return bytes(result) if result else None

    def _block_xor(self, data: bytes) -> bytes:
        n = len(data)
        half = n // 2
        b1 = data[:half]
        b2 = data[half:]
        if len(b2) < len(b1):
            b1 = b1[:len(b2)]
        result = [b1[i] ^ b2[i] for i in range(len(b1))]
        return bytes(result) if result else None

    def _swap_nibbles(self, data: bytes) -> bytes:
        result = []
        for i in range(0, len(data) - 1, 2):
            b1, b2 = data[i], data[i + 1]
            result.append(((b2 >> 4) & 0x0F) | ((b1 << 4) & 0xF0))
        return bytes(result) if result else None

    def send_modbus_to_relay(self, modbus_cmd: bytes):
        log.info(f"▶ 发送 Modbus 指令: {bytes2hex(modbus_cmd)}")
        gap = CONFIG.get("relay_cmd_interval", 0.3)
        elapsed = time.time() - self.last_relay_cmd_time
        if elapsed < gap:
            wait = gap - elapsed
            log.debug(f"  指令间隔保护，等待 {wait:.3f}s")
            time.sleep(wait)

        post_send = CONFIG.get("relay_post_send_wait", 0.2)
        silence = CONFIG.get("relay_silence_gap", 0.05)
        total_timeout = CONFIG.get("relay_read_timeout", 1.5)
        retry_delay = CONFIG.get("relay_retry_delay", 0.5)

        for attempt in range(3):
            self.ser_relay.reset_input_buffer()
            self.ser_relay.write(modbus_cmd)
            self.ser_relay.flush()
            time.sleep(post_send)

            resp = b''
            deadline = time.time() + total_timeout
            last_data_time = time.time()
            while time.time() < deadline:
                if self.ser_relay.in_waiting:
                    chunk = self.ser_relay.read(self.ser_relay.in_waiting)
                    if chunk:
                        resp += chunk
                        last_data_time = time.time()
                else:
                    if resp and (time.time() - last_data_time) > silence:
                        break
                    time.sleep(0.01)

            self.last_relay_cmd_time = time.time()

            if resp:
                log.info(f"✓ 继电器响应 (尝试{attempt+1}, {len(resp)}字节): {bytes2hex(resp)}")
                self._send_relay_feedback(modbus_cmd, resp)
                return resp
            else:
                if attempt < 2:
                    log.warning(f"⚠ 尝试 {attempt+1} 无响应，{retry_delay}s 后重试...")
                    time.sleep(retry_delay)
                else:
                    log.warning("⚠⚠ 继电器连续 3 次无响应")
                    self._send_relay_feedback(modbus_cmd, None)
        return None

    def _send_relay_feedback(self, cmd: bytes, resp: bytes):
        cmd_name = "未知指令"
        for name, rel_cmd in RELAY_CMD.items():
            if rel_cmd == cmd:
                cmd_name = name
                break

        if resp:
            status = "成功"
            msg = f"[继电器] {cmd_name} 执行{status} (响应: {bytes2hex(resp)})"
        else:
            status = "失败"
            msg = f"[继电器] {cmd_name} 执行{status} (无响应)"

        log.info(f"📡 {msg}")
        self.log_callback(msg)   # 替换 self.gui.append

        text_payload = f"RELAY:{cmd_name}:{status}"
        payload_hex = text_payload.encode('utf-8').hex()
        try:
            nmea_msg = build_cctcq_msg(
                target_id=CONFIG['source_user_id'],
                freq_point=self.freq_point,
                ack=self.ack_req,
                encode_type=2,
                freq=0,
                payload_hex=payload_hex
            )
            self.ser_bd.write(nmea_msg.encode('ascii'))
            log.info(f"↩ 继电器反馈已回传: {text_payload}")
        except Exception as e:
            log.warning(f"继电器反馈回传失败: {e}")

    def query_temp_sensor(self, cmd: bytes) -> bytes:
        if not self.ser_temp:
            log.warning("⚠ 温度传感器串口未配置")
            return None
        log.info(f"▶ 查询温度传感器: {bytes2hex(cmd)}")
        self.ser_temp.reset_input_buffer()
        self.ser_temp.write(cmd)
        self.ser_temp.flush()
        time.sleep(0.2)

        resp = b''
        deadline = time.time() + CONFIG.get('temp_read_timeout', 1.0)
        last_data_time = time.time()
        while time.time() < deadline:
            if self.ser_temp.in_waiting:
                chunk = self.ser_temp.read(self.ser_temp.in_waiting)
                if chunk:
                    resp += chunk
                    last_data_time = time.time()
            else:
                if resp and (time.time() - last_data_time) > 0.05:
                    break
                time.sleep(0.01)

        if resp:
            log.info(f"✓ 温度传感器响应 ({len(resp)}字节): {bytes2hex(resp)}")
            if is_temp_response(resp):
                temp = parse_temp_value(resp)
                log.debug(f"🌡️ 当前温度: {temp}°C")
            return resp
        else:
            log.warning("⚠ 温度传感器无响应")
            return None

    def send_temp_data_back(self, temp_data: bytes):
        temp_hex = bytes2hex(temp_data).replace(" ", "")
        if is_temp_response(temp_data):
            temp = parse_temp_value(temp_data)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            msg = f"[{timestamp}] [温度采集] {temp:.1f}°C (原始: {bytes2hex(temp_data)})"
            log.info(msg)
            self.log_callback(msg)
        else:
            msg = f"温度数据非标准响应: {bytes2hex(temp_data)}"
            log.warning(msg)
            self.log_callback(msg)

        nmea_msg = build_cctcq_msg(
            target_id=CONFIG['source_user_id'],
            freq_point=self.freq_point,
            ack=self.ack_req,
            encode_type=self.encode_type,
            freq=0,
            payload_hex=temp_hex
        )
        self.ser_bd.write(nmea_msg.encode('ascii'))
        log.info(f"★ 温度数据已回传: {nmea_msg.strip()}")

    def handle_a225_location(self, raw: bytes, sender: str, receiver: str):
        points = parse_a225_location(raw)
        if not points:
            log.warning("A225 解析失败")
            return

        log.info(f"✅ 解析到 {len(points)} 个定位点")
        display_text = format_location_for_display(points, beijing_offset=CONFIG.get('beijing_offset', 8))
        for line in display_text.split('\n'):
            log.info(line)
            self.log_callback(line)   # 替换 self.gui.append

        if sender != self.ser_bd.port or receiver != self.ser_bd.port:
            text_payload = encode_location_to_text(points, beijing_offset=CONFIG.get('beijing_offset', 8))
            full_payload = f"POS:{text_payload}"
            payload_hex = full_payload.encode('utf-8').hex()

            max_hex_len = 180
            if len(payload_hex) > max_hex_len:
                payload_hex = payload_hex[:max_hex_len]
                log.warning("回传数据被截断")

            nmea_msg = build_cctcq_msg(
                target_id=CONFIG['source_user_id'],
                freq_point=self.freq_point,
                ack=self.ack_req,
                encode_type=2,
                freq=0,
                payload_hex=payload_hex
            )
            self.ser_bd.write(nmea_msg.encode('ascii'))
            log.info(f"↩ 已回传定位数据，长度 {len(payload_hex)//2} 字节")
        else:
            log.debug("本地回环数据，不重复回传")

    def _process_bdtci_payload(self, sender: str, receiver: str, bd_freq: int, payload_hex: str):
        payload_len = len(payload_hex) // 2
        log.info(f"BDTCI: 发送方={sender}, 接收方={receiver}, freq={bd_freq}, 载荷={payload_len}字节")

        try:
            raw = hex2bytes(payload_hex)
        except Exception as e:
            log.error(f"hex2bytes 失败: {e}")
            raw = None

        if raw:
            log.info(f"载荷原始字节: {bytes2hex(raw)}")
            if len(raw) >= 5:
                log.info(f"首字节: 0x{raw[0]:02X}, 次字节: 0x{raw[1]:02X}")

        if raw and len(raw) >= 5 and raw[0] == 0xD1 and raw[1] == 0x35:
            log.info(f"  ↗ A225 遥测数据，非回传方向，跳过")
            return

        if raw:
            try:
                text = raw.decode('utf-8')
                if text.startswith('POS:'):
                    log.info("★ 收到回传的定位数据（忽略，避免循环）")
                    return
            except UnicodeDecodeError:
                pass

        if payload_len > 10:
            log.info(f"  ↗ 载荷过长 ({payload_len}字节 > 10), 判定为遥测数据，跳过")
            return

        if bd_freq is not None and bd_freq in FREQ_TO_CMD:
            cmd_name = FREQ_TO_CMD[bd_freq]
            if cmd_name in RELAY_CMD and is_relay_command(RELAY_CMD[cmd_name]):
                log.info(f"★ 通过 freq={bd_freq} 识别命令: {cmd_name}")
                self.send_modbus_to_relay(RELAY_CMD[cmd_name])
                return

        decoded = self._decode_bdtci_payload(payload_hex)
        if decoded:
            if is_relay_command(decoded):
                log.info(f"★ 继电器指令校验通过: {bytes2hex(decoded)}")
                self.send_modbus_to_relay(decoded)
            elif is_temp_command(decoded):
                log.info(f"★ 温度采集指令校验通过: {bytes2hex(decoded)}")
                temp_resp = self.query_temp_sensor(decoded)
                if temp_resp:
                    self.send_temp_data_back(temp_resp)
                else:
                    log.warning("✗ 温度传感器无数据，无法回传")
            else:
                log.warning(f"✗ 载荷未通过指令校验 (freq={bd_freq}, 载荷={payload_len}字节)")
        else:
            log.warning(f"✗ 载荷解码失败 (freq={bd_freq}, 载荷={payload_len}字节)")

    def _display_parsed_bdtci(self, sender: str, receiver: str, freq: int, payload_hex: str, direction: str):
        payload_len = len(payload_hex) // 2
        show_hex = payload_hex[:16] + ("..." if len(payload_hex) > 16 else "")
        line = (f"[BDTCI] {direction} | 发送方:{sender} 接收方:{receiver} "
                f"频点:{freq} 长度:{payload_len} 载荷:{show_hex}")
        self.log_callback(line)
        log.info(line)

    def _handle_bdtci(self, text: str):
        body, _ = text.split('*', 1)
        fields = body.split(',')
        if len(fields) < 8:
            return

        sender = fields[1]
        receiver = fields[2]
        try:
            bd_freq = int(fields[5])
        except (ValueError, IndexError):
            bd_freq = None
        payload_hex = fields[7]

        # 无条件解析 A225 并显示（不回传）
        try:
            raw = hex2bytes(payload_hex)
            if len(raw) >= 5 and raw[0] == 0xD1 and raw[1] == 0x35:
                points = parse_a225_location(raw)
                if points:
                    display_text = format_location_for_display(points, beijing_offset=CONFIG.get('beijing_offset', 8))
                    log.info(f"✅ 解析到 {len(points)} 个定位点（来自 {sender}）")
                    for line in display_text.split('\n'):
                        log.info(line)
                        self.log_callback(line)   # 替换 self.gui.append
                    # 已显示，直接返回
                    return
        except Exception as e:
            log.debug(f"A225 解析尝试失败: {e}")

        # 方向判断和指令处理
        expected_target = CONFIG['target_user_id']
        expected_source = CONFIG['source_user_id']

        is_to_sender = (sender == expected_target and receiver == expected_source)
        is_from_sender = (sender == expected_source and receiver == expected_target)
        if is_to_sender:
            direction = "回传方向"
        elif is_from_sender:
            direction = "指令方向"
        else:
            direction = f"其他 (s={sender}, r={receiver})"
        self._display_parsed_bdtci(sender, receiver, bd_freq, payload_hex, direction)

        if is_to_sender:
            log.info(f"  [窗口显示] {sender}→{receiver} (回传方向)")
            return

        if not is_from_sender:
            log.debug(f"  ↗ 非本机相关消息，跳过 (sender={sender}, receiver={receiver})")
            return

        TEMP_INSTRUCTION_HEX = "010300000002C40B"
        if payload_hex.upper() == TEMP_INSTRUCTION_HEX:
            log.info("★ 温度采集指令，跳过重复检查")
            self._process_bdtci_payload(sender, receiver, bd_freq, payload_hex)
            return

        key = f"{sender}_{bd_freq}_{payload_hex}"
        if key == self.last_processed_bdtci_key:
            log.info("  ↗ 重复消息，跳过")
            return
        self.last_processed_bdtci_key = key

        self._process_bdtci_payload(sender, receiver, bd_freq, payload_hex)

    def _handle_bdibd(self, text: str):
        body, _ = text.split('*', 1)
        fields = body.split(',')
        if len(fields) < 8:
            return
        msg_id = fields[1]
        status = fields[7]
        sender = fields[6] if len(fields) > 6 else "?"
        receiver = fields[4] if len(fields) > 4 else "?"
        expected_source = CONFIG['source_user_id']
        expected_target = CONFIG['target_user_id']

        if sender != expected_source or receiver != expected_target:
            return

        if status == '0':
            log.info(f"✓ BDIBD 用户指令确认: msg_id={msg_id}, 发送方={sender}, 接收方={receiver}")
        elif status == '3':
            log.info(f"  ↻ 设备自动通信 (status=3, msg_id={msg_id})")
        else:
            log.info(f"  入站通知: msg_id={msg_id}, status={status}")

    def loop_listen_beidou(self):
        log.info("=" * 60)
        log.info("接收端启动（直接监听 BDTCI，并过滤载荷特征）")
        log.info(f"  本机地址: {CONFIG['target_user_id']}")
        log.info(f"  期望发送方: {CONFIG['source_user_id']}")
        log.info(f"  继电器波特率: {CONFIG['relay_baud']}")
        log.info("=" * 60)
        self.ser_bd.reset_input_buffer()

        while True:
            if check_exit_flag():
                log.info("收到退出信号，receiver 即将退出")
                clear_exit_flag()
                break

            try:
                lines = self._read_lines(timeout=1.0)
                if not lines:
                    time.sleep(0.3)
                    continue

                for line in lines:
                    print(f"\n【北斗收到报文(十六进制)】{bytes2hex(line)}")
                    text, enc = decode_serial_data(line)
                    print(f"【北斗收到报文({enc})】{text}")

                    if not text.startswith('$'):
                        log.debug("收到非NMEA数据")
                        continue

                    if text.startswith('$BDTCI'):
                        self._handle_bdtci(text)
                        continue

                    if text.startswith('$BDIBD'):
                        self._handle_bdibd(text)
                        continue

                    if text.startswith('$BDFKI'):
                        body, _ = text.split('*', 1)
                        fields = body.split(',')
                        if len(fields) >= 4:
                            log.info(f"  [BDFKI] 类型={fields[2]}, 结果={fields[3]}")
                        continue

                    if text.startswith('$BDOBD'):
                        body, _ = text.split('*', 1)
                        fields = body.split(',')
                        if len(fields) >= 6:
                            log.info(f"  [BDOBD] msg_id={fields[1]}, 发送方={fields[3]}")
                        continue

                    log.info(f"  其他: {text[:80]}")

            except serial.SerialException as e:
                log.error(f"串口读取异常: {e}")
                time.sleep(1)
            except Exception as e:
                log.error(f"未知异常: {type(e).__name__}: {e}")
                time.sleep(1)

    def close(self):
        self.ser_bd.close()
        self.ser_relay.close()
        if self.ser_temp:
            self.ser_temp.close()
        clear_exit_flag()
        log.info("接收端串口已关闭")
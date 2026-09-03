"""
继电器 RS485 通信诊断工具
用于测试继电器模块是否能正确响应 Modbus 指令
"""
import sys
import time
import serial

# Modbus CRC16 计算
def calc_modbus_crc(data):
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

def bytes2hex(data):
    return " ".join([f"{b:02X}" for b in data])

def test_relay(port, baud=9600):
    """测试继电器通信"""
    print(f"连接继电器端口: {port}, 波特率: {baud}")
    
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=1.0)
    except serial.SerialException as e:
        print(f"❌ 串口打开失败: {e}")
        return False
    
    print(f"✓ 串口已打开")
    
    # 测试1: 读取线圈状态 (功能码 0x01)
    # 从站地址 0x11, 读取线圈 0x0000~0x0003 (4个继电器)
    print("\n" + "=" * 60)
    print("测试1: 读取继电器状态")
    slave_addr = 0x11
    func_code = 0x01
    start_addr = 0x0000
    quantity = 0x0004
    
    cmd = bytes([slave_addr, func_code]) + start_addr.to_bytes(2, 'big') + quantity.to_bytes(2, 'big')
    crc = calc_modbus_crc(cmd)
    full_cmd = cmd + crc
    
    print(f"发送: {bytes2hex(full_cmd)}")
    ser.reset_input_buffer()
    ser.write(full_cmd)
    
    time.sleep(0.5)
    resp = b''
    if ser.in_waiting:
        resp = ser.read(ser.in_waiting)
    
    if resp:
        print(f"✓ 收到响应: {bytes2hex(resp)}")
        if len(resp) >= 5:
            resp_slave = resp[0]
            resp_func = resp[1]
            print(f"  从站: 0x{resp_slave:02X}, 功能码: 0x{resp_func:02X}")
            if resp_func == func_code:
                byte_count = resp[2]
                print(f"  字节数: {byte_count}")
                coil_data = resp[3:3+byte_count]
                print(f"  线圈数据: {bytes2hex(coil_data)}")
                # 解析线圈状态
                for i, b in enumerate(coil_data):
                    for bit in range(4):
                        if b & (1 << bit):
                            print(f"  继电器 {i*8+bit}: ON")
                        else:
                            print(f"  继电器 {i*8+bit}: OFF")
        return True
    else:
        print("❌ 无响应!")
        print("可能原因:")
        print("  1. 波特率不匹配 (继电器通常使用 9600)")
        print("  2. Modbus 地址错误 (通常为 1 或 16)")
        print("  3. RS485 A/B 线接反")
        print("  4. 继电器模块未上电")
        
        # 尝试不同的波特率
        for test_baud in [9600, 19200, 38400, 57600, 115200]:
            if test_baud != baud:
                print(f"\n尝试波特率 {test_baud}...")
                ser.baudrate = test_baud
                ser.reset_input_buffer()
                ser.write(full_cmd)
                time.sleep(0.3)
                if ser.in_waiting:
                    resp = ser.read(ser.in_waiting)
                    if resp:
                        print(f"✓ 波特率 {test_baud} 成功! 响应: {bytes2hex(resp)}")
                        ser.close()
                        return True
        
        # 尝试不同的从站地址
        print(f"\n尝试不同的从站地址...")
        for test_addr in [0x01, 0x02, 0x10, 0x16]:
            if test_addr != slave_addr:
                test_cmd = bytes([test_addr, func_code]) + start_addr.to_bytes(2, 'big') + quantity.to_bytes(2, 'big')
                crc = calc_modbus_crc(test_cmd)
                full = test_cmd + crc
                ser.baudrate = baud
                ser.reset_input_buffer()
                ser.write(full)
                time.sleep(0.3)
                if ser.in_waiting:
                    resp = ser.read(ser.in_waiting)
                    if resp:
                        print(f"✓ 从站 0x{test_addr:02X} 成功! 响应: {bytes2hex(resp)}")
                        ser.close()
                        return True
                else:
                    print(f"  从站 0x{test_addr:02X}: 无响应")
        
        ser.close()
        return False

if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "COM2"
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else 9600
    
    success = test_relay(port, baud)
    print("\n" + ("=" * 60))
    print(f"测试结果: {'✓ 成功' if success else '❌ 失败'}")
"""
BDCP D1 编码分析脚本 - 独立版本
目的：逆向 BDCP D1 编码算法
"""
import binascii

def hex2bytes(hex_str):
    return binascii.unhexlify(hex_str.replace(" ", ""))

def bytes2hex(data):
    return " ".join([f"{b:02X}" for b in data])

# 已知数据：原始 Modbus 指令 -> BDCP 编码后的载荷
ORIG_ALL_CLOSE = hex2bytes("11 0F 00 00 00 04 01 0F 7F 9E")
ORIG_ALL_OPEN  = hex2bytes("11 0F 00 00 00 04 01 00 3F 9A")

# BDCP 编码后的载荷（来自 BDTCI 消息）
ENC_ALL_CLOSE = hex2bytes("D1 35 02 01 1A 07 1E 09 35 02 07 33 2C 71 02 6D 56 7E 02 C7 00 00 00 FB 01 1A 07 1E 09 36 02 07 33 2C 20 02 6D 56 40 02 F1 00 00 00 FB BC")
ENC_ALL_OPEN  = hex2bytes("D1 35 02 01 1A 07 1E 06 35 2C 07 33 2C AF 02 6D 56 BA 02 CD 00 00 00 43 01 1A 07 1E 06 36 2C 07 33 2C F3 02 6D 56 B8 02 B6 00 00 00 47 C4")

print("=" * 60)
print("1. 基本结构分析")
print("=" * 60)
print(f"原始指令长度: {len(ORIG_ALL_CLOSE)} 字节")
print(f"编码载荷长度: {len(ENC_ALL_CLOSE)} 字节")
print(f"比率: {len(ENC_ALL_CLOSE) / len(ORIG_ALL_CLOSE):.2f} : 1")

print(f"\n原始指令 (all_close): {bytes2hex(ORIG_ALL_CLOSE)}")
print(f"原始指令 (all_open):  {bytes2hex(ORIG_ALL_OPEN)}")

diff_positions = []
for i in range(len(ORIG_ALL_CLOSE)):
    if ORIG_ALL_CLOSE[i] != ORIG_ALL_OPEN[i]:
        diff_positions.append(i)
print(f"\n原始指令差异位置: {diff_positions}")
for p in diff_positions:
    print(f"  字节[{p}]: {ORIG_ALL_CLOSE[p]:02X} vs {ORIG_ALL_OPEN[p]:02X}")

print(f"\n编码载荷 (all_close): {bytes2hex(ENC_ALL_CLOSE)}")
print(f"编码载荷 (all_open):  {bytes2hex(ENC_ALL_OPEN)}")

min_len = min(len(ENC_ALL_CLOSE), len(ENC_ALL_OPEN))
enc_diff_positions = []
for i in range(min_len):
    if ENC_ALL_CLOSE[i] != ENC_ALL_OPEN[i]:
        enc_diff_positions.append(i)
print(f"\n编码载荷差异位置数量: {len(enc_diff_positions)}")

print("\n" + "=" * 60)
print("2. D1 帧结构分析")
print("=" * 60)

def parse_d1_frame(data):
    if data[0] != 0xD1:
        return None
    result = {
        'marker': data[0],
        'frame_len': data[1],
        'encode_type': data[2],
        'block_count': data[3],
        'blocks': []
    }
    pos = 4
    for block_idx in range(result['block_count'] + 1):
        if pos >= len(data):
            break
        if data[pos] == 0x1A:
            block_header = data[pos:pos+4]
            pos += 4
            if block_idx < result['block_count']:
                next_1a = data.find(b'\x1A', pos)
                if next_1a == -1:
                    next_1a = len(data) - 1
                block_data = data[pos:next_1a]
                pos = next_1a
            else:
                block_data = data[pos:len(data)-1]
                pos = len(data) - 1
            result['blocks'].append({
                'header': block_header,
                'data': block_data,
                'data_len': len(block_data)
            })
        else:
            break
    result['checksum'] = data[-1] if data else None
    return result

frame_close = parse_d1_frame(ENC_ALL_CLOSE)
frame_open = parse_d1_frame(ENC_ALL_OPEN)

if frame_close:
    print(f"\nall_close 帧:")
    print(f"  frame_len={frame_close['frame_len']} (0x{frame_close['frame_len']:02X})")
    print(f"  encode_type={frame_close['encode_type']}")
    print(f"  block_count={frame_close['block_count']} (共{frame_close['block_count']+1}个块)")
    print(f"  checksum=0x{frame_close['checksum']:02X}")
    for i, block in enumerate(frame_close['blocks']):
        print(f"\n  块 {i}:")
        print(f"    头: {bytes2hex(block['header'])}")
        print(f"    数据({block['data_len']}字节): {bytes2hex(block['data'])}")
        print(f"    数据字节数/原始字节: {block['data_len'] / 5:.1f} (假设5字节/块)")

if frame_open:
    print(f"\nall_open 帧:")
    for i, block in enumerate(frame_open['blocks']):
        print(f"\n  块 {i}:")
        print(f"    头: {bytes2hex(block['header'])}")
        print(f"    数据({block['data_len']}字节): {bytes2hex(block['data'])}")

print("\n" + "=" * 60)
print("3. 从编码数据中提取所有块数据")
print("=" * 60)

all_enc_close = b''.join(b['data'] for b in frame_close['blocks'])
all_enc_open = b''.join(b['data'] for b in frame_open['blocks'])
print(f"all_close 编码数据({len(all_enc_close)}字节): {bytes2hex(all_enc_close)}")
print(f"all_open  编码数据({len(all_enc_open)}字节): {bytes2hex(all_enc_open)}")

print("\n" + "=" * 60)
print("4. 尝试: 每3字节编码1个原始字节")
print("=" * 60)

def try_3to1_decode(enc_data, original):
    """尝试将编码数据按3字节一组解码为1字节"""
    results = []
    num_groups = min(len(enc_data) // 3, len(original))
    for i in range(num_groups):
        b0, b1, b2 = enc_data[i*3], enc_data[i*3+1], enc_data[i*3+2]
        # 尝试多种3->1策略
        decoded = []
        # 策略1: 取b0的高4位 + b1的高4位
        decoded.append(((b0 >> 4) << 4) | (b1 >> 4))
        # 策略2: 取b0的低4位 + b1的低4位
        decoded.append(((b0 & 0x0F) << 4) | (b1 & 0x0F))
        # 策略3: b0 ^ b1
        decoded.append(b0 ^ b1)
        # 策略4: b2 (直接用第三个字节)
        decoded.append(b2)
        # 策略5: (b0 + b1 + b2) / 3
        decoded.append((b0 + b1 + b2) // 3)
        # 策略6: 交织: (b0低4位<<4) | b2高4位
        decoded.append(((b0 & 0x0F) << 4) | (b2 >> 4))
        
        results.append(decoded)
    
    # 检查每种策略的匹配数
    for strat_idx in range(6):
        match_count = sum(1 for i in range(num_groups) if results[i][strat_idx] == original[i])
        print(f"  策略{strat_idx+1}: {match_count}/{num_groups} 匹配")
        if match_count == num_groups:
            print(f"    ✅ 完美匹配! 解码结果: {bytes2hex(bytes([r[strat_idx] for r in results]))}")

print("\nall_close:")
try_3to1_decode(all_enc_close, ORIG_ALL_CLOSE)
print("\nall_open:")
try_3to1_decode(all_enc_open, ORIG_ALL_OPEN)

print("\n" + "=" * 60)
print("5. 尝试: 每4字节编码1个原始字节")
print("=" * 60)

def try_4to1_decode(enc_data, original):
    num_groups = min(len(enc_data) // 4, len(original))
    for strat in ['nibble_pair', 'xor', 'interleave', 'add_avg']:
        results = []
        for i in range(num_groups):
            b0, b1, b2, b3 = enc_data[i*4:i*4+4]
            if strat == 'nibble_pair':
                # (b0高4位<<4)|(b1高4位), 或 (b0低4位<<4)|(b1低4位), ...
                v1 = ((b0 >> 4) << 4) | (b1 >> 4)
                v2 = ((b0 & 0x0F) << 4) | (b1 & 0x0F)
                v3 = ((b2 >> 4) << 4) | (b3 >> 4)
                v4 = ((b2 & 0x0F) << 4) | (b3 & 0x0F)
                results.extend([v1, v2, v3, v4])
            elif strat == 'xor':
                results.append(b0 ^ b1)
                results.append(b2 ^ b3)
                results.append(b0 ^ b2)
                results.append(b1 ^ b3)
            elif strat == 'interleave':
                # 交错组合
                results.append(((b0 >> 4) << 4) | (b2 & 0x0F))
                results.append(((b1 >> 4) << 4) | (b3 & 0x0F))
                results.append(((b0 & 0x0F) << 4) | (b2 >> 4))
                results.append(((b1 & 0x0F) << 4) | (b3 >> 4))
            elif strat == 'add_avg':
                results.append((b0 + b1) // 2)
                results.append((b2 + b3) // 2)
                results.append((b0 + b2) // 2)
                results.append((b1 + b3) // 2)
        
        # 检查哪个位置匹配
        for offset in range(4):
            match = sum(1 for i in range(num_groups) if results[i*4+offset] == original[i])
            if match == num_groups:
                print(f"  策略{strat} offset={offset}: {match}/{num_groups} ✅ 完美!")
                decoded = bytes([results[i*4+offset] for i in range(num_groups)])
                print(f"    结果: {bytes2hex(decoded)}")
            elif match >= num_groups * 0.7:
                print(f"  策略{strat} offset={offset}: {match}/{num_groups}")

print("\nall_close:")
try_4to1_decode(all_enc_close, ORIG_ALL_CLOSE)
print("\nall_open:")
try_4to1_decode(all_enc_open, ORIG_ALL_OPEN)

print("\n" + "=" * 60)
print("6. 尝试: 每2字节编码1个字节 (nibble展开逆向)")
print("=" * 60)

def try_2to1_decode(enc_data, original):
    num_groups = min(len(enc_data) // 2, len(original) * 2)
    results = []
    for i in range(num_groups):
        b0, b1 = enc_data[i*2], enc_data[i*2+1]
        results.append(((b0 >> 4) << 4) | (b1 >> 4))  # 高4位组合
        results.append(((b0 & 0x0F) << 4) | (b1 & 0x0F))  # 低4位组合
        results.append(((b0 >> 4) << 4) | (b1 & 0x0F))  # b0高+b1低
        results.append(((b0 & 0x0F) << 4) | (b1 >> 4))  # b0低+b1高
    
    # 取前len(original)个结果进行检查
    for off in range(4):
        subset = [results[i*4+off] for i in range(len(original))]
        match = sum(1 for i in range(len(original)) if subset[i] == original[i])
        if match >= len(original) * 0.8:
            print(f"  offset={off}: {match}/{len(original)} 匹配")
            if match == len(original):
                print(f"    ✅ 结果: {bytes2hex(bytes(subset))}")

print("\nall_close:")
try_2to1_decode(all_enc_close, ORIG_ALL_CLOSE)
print("\nall_open:")
try_2to1_decode(all_enc_open, ORIG_ALL_OPEN)

print("\n" + "=" * 60)
print("7. 分析: 检查编码数据中是否存在原始字节的直接副本")
print("=" * 60)

def find_original_in_encoded(enc_data, original):
    for byte_val in original:
        positions = [i for i, b in enumerate(enc_data) if b == byte_val]
        print(f"  原始字节 0x{byte_val:02X} 出现在编码数据位置: {positions[:10]}")

print("\nall_close:")
find_original_in_encoded(all_enc_close, ORIG_ALL_CLOSE)
print("\nall_open:")
find_original_in_encoded(all_enc_open, ORIG_ALL_OPEN)

print("\n" + "=" * 60)
print("8. 分析: 检查编码数据中是否存在原始字节的 nibble 模式")
print("=" * 60)

def analyze_nibble_patterns(enc_data, original):
    """检查原始字节的每个 nibble 是否出现在编码数据的某个位置"""
    print("\n  原始字节 nibble 分析:")
    for byte_idx, b in enumerate(original):
        hi_nib = (b >> 4) & 0x0F
        lo_nib = b & 0x0F
        
        # 检查编码数据中哪些字节的低4位等于 hi_nib
        hi_matches = [i for i, e in enumerate(enc_data) if (e & 0x0F) == hi_nib]
        # 检查编码数据中哪些字节的低4位等于 lo_nib
        lo_matches = [i for i, e in enumerate(enc_data) if (e & 0x0F) == lo_nib]
        
        print(f"    字节[{byte_idx}]=0x{b:02X} (hi={hi_nib}, lo={lo_nib}):")
        print(f"      hi nibble 在编码数据低4位中的位置: {hi_matches[:8]}")
        print(f"      lo nibble 在编码数据低4位中的位置: {lo_matches[:8]}")

print("\nall_close:")
analyze_nibble_patterns(all_enc_close, ORIG_ALL_CLOSE)

print("\n" + "=" * 60)
print("9. 新发现: 检查编码数据中 0x00 的位置")
print("=" * 60)

# 两个原始指令都包含多个 0x00 字节
# 查看编码数据中 0x00 出现的位置
print("\nall_close 编码数据中 0x00 出现位置:", [i for i, b in enumerate(all_enc_close) if b == 0])
print("all_open  编码数据中 0x00 出现位置:", [i for i, b in enumerate(all_enc_open) if b == 0])

# 两个指令的 0x00 出现在相同位置吗？
# 原始: 0x00 在位置 2,3,4 (两个指令都是)
# 编码: 0x00 应该出现在 2*3=6, 3*3=9, 4*3=12 或类似位置

print("\n" + "=" * 60)
print("10. 最终分析: 检查每个编码字节的低4位")
print("=" * 60)

# 如果编码使用 "nibble + 0x30" 方式
# 那么编码字节的低4位应该 = 原始 nibble
def check_low_nibble(enc_data, original):
    orig_nibbles = []
    for b in original:
        orig_nibbles.append((b >> 4) & 0x0F)
        orig_nibbles.append(b & 0x0F)
    
    enc_low_nibbles = [b & 0x0F for b in enc_data[:len(orig_nibbles)]]
    
    print("\n  原始 nibbles vs 编码字节低4位:")
    for i in range(min(len(orig_nibbles), len(enc_low_nibbles))):
        match = "✓" if orig_nibbles[i] == enc_low_nibbles[i] else "✗"
        print(f"    [{i:2d}] orig_nibble={orig_nibbles[i]} enc_low={enc_low_nibbles[i]} {match}")
    
    # 统计匹配数
    matches = sum(1 for i in range(min(len(orig_nibbles), len(enc_low_nibbles))) 
                  if orig_nibbles[i] == enc_low_nibbles[i])
    print(f"\n  总匹配: {matches}/{min(len(orig_nibbles), len(enc_low_nibbles))}")

print("\nall_close:")
check_low_nibble(all_enc_close, ORIG_ALL_CLOSE)
print("\nall_open:")
check_low_nibble(all_enc_open, ORIG_ALL_OPEN)

print("\n" + "=" * 60)
print("11. 方案: 使用 encode_type=3 并发送自定义编码")
print("=" * 60)
print("""
基于以上分析，BDCP D1 编码不是简单的 nibble 映射。
它很可能使用了某种块级编码（如 RS 编码或 LDPC）。

实用方案:
1. 发送端使用 encode_type=3 (BDCP 预编码)
2. 在发送端先实现 BDCP D1 编码
3. 接收端实现 BDCP D1 解码

但由于我们没有 BDCP 编码规范，建议采用以下变通方案:

方案A: 使用 encode_type=0 (原始二进制) + 固定载荷
- 发送端发送原始 Modbus 指令作为载荷
- 接收端从 BDTCI 载荷中提取数据
- 由于 BDCP 编码改变了载荷，此方案需要解码

方案B: 使用载荷长度编码命令
- 每种命令使用不同长度的载荷
- 但 BDTCI 载荷长度由 BDCP 编码决定，不可控

方案C: 使用 payload 内容本身的特征
- 每种命令使用不同的 magic bytes
- 接收端通过 magic bytes 识别命令
- 即使 BDCP 编码改变了字节值，某些结构性特征可能保留

方案D: 放弃载荷传输，改用其他通道
- 利用 BDIBD 的 msg_id 或其他字段编码命令
- 需要验证这些字段是否可控
""")

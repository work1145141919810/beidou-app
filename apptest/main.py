# main.py
"""
Kivy 桌面测试主程序，使用 pyserial 进行实际串口通信。
在 Android 上需替换为 usbserial4a。
"""
import threading
import time
import serial
import serial.tools.list_ports
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.popup import Popup

from beidou_core import BeidouController
from common import log, CONFIG

# ---------- 字体配置 ----------
# 请根据您的系统修改字体路径
# 常用中文字体：
#   Windows: "C:/Windows/Fonts/msyh.ttc"  (微软雅黑)
#            "C:/Windows/Fonts/simsun.ttc" (宋体)
#   macOS:   "/System/Library/Fonts/PingFang.ttc"
#   Linux:   需安装文泉驿等字体，路径如 "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
CHINESE_FONT = "C:/Windows/Fonts/msyh.ttc"

class BeidouApp(App):
    def build(self):
        # 界面布局
        self.root_layout = BoxLayout(orientation='vertical', spacing=8, padding=10)

        # ---- 顶部：端口选择与连接 ----
        self.top_layout = BoxLayout(size_hint_y=None, height=40, spacing=10)
        self.port_label = Label(
            text='串口: 未连接',
            size_hint_x=0.6,
            font_name=CHINESE_FONT
        )
        self.btn_connect = Button(
            text='选择串口并连接',
            size_hint_x=0.4,
            font_name=CHINESE_FONT
        )
        self.btn_connect.bind(on_press=self.on_connect)
        self.top_layout.add_widget(self.port_label)
        self.top_layout.add_widget(self.btn_connect)
        self.root_layout.add_widget(self.top_layout)

        # ---- 中间：控制按钮 ----
        self.btn_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)
        self.btn_close = Button(text='闭合继电器', font_name=CHINESE_FONT)
        self.btn_close.bind(on_press=lambda x: self.controller.send_relay_command('all_close') if self.controller else None)
        self.btn_open = Button(text='断开继电器', font_name=CHINESE_FONT)
        self.btn_open.bind(on_press=lambda x: self.controller.send_relay_command('all_open') if self.controller else None)
        self.btn_temp = Button(text='查询温度', font_name=CHINESE_FONT)
        self.btn_temp.bind(on_press=lambda x: self.controller.send_temp_query() if self.controller else None)
        self.btn_auto = Button(text='自动温控: 启用', font_name=CHINESE_FONT)
        self.btn_auto.bind(on_press=self.toggle_auto_temp)
        self.btn_layout.add_widget(self.btn_close)
        self.btn_layout.add_widget(self.btn_open)
        self.btn_layout.add_widget(self.btn_temp)
        self.btn_layout.add_widget(self.btn_auto)
        self.root_layout.add_widget(self.btn_layout)

        # ---- 日志显示区域 ----
        self.log_label = Label(
            text='等待连接...\n',
            halign='left',
            valign='top',
            font_size='12sp',
            font_name=CHINESE_FONT
        )
        self.log_label.bind(size=self.log_label.setter('text_size'))
        self.scroll_view = ScrollView()
        self.scroll_view.add_widget(self.log_label)
        self.root_layout.add_widget(self.scroll_view)

        # 初始化控制器（暂不连接）
        self.controller = None
        self.ser = None
        self.listener_thread = None
        self.running = False

        Window.bind(on_request_close=self.on_close)

        return self.root_layout

    # ---------- 事件处理 ----------
    def on_connect(self, instance):
        """弹出串口选择对话框，连接北斗串口"""
        ports = serial.tools.list_ports.comports()
        if not ports:
            self.show_popup("错误", "未检测到可用串口，请插入USB设备")
            return
        # 简单选择：取第一个可用串口（可扩展为下拉列表）
        port = ports[0].device
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.ser = serial.Serial(port, baudrate=115200, timeout=0.5)
            self.port_label.text = f'串口: {port}'
            self.append_log(f"[成功] 已连接 {port}")
            # 初始化控制器
            self.controller = BeidouController()
            self.controller.send_serial = self.ser.write
            # 绑定回调
            self.controller.on_log = self.append_log
            self.controller.on_temp_updated = self.on_temp_update
            self.controller.on_relay_response = self.on_relay_response
            self.controller.on_location = self.on_location

            # 启动监听线程
            self.running = True
            self.listener_thread = threading.Thread(target=self._listener_loop, daemon=True)
            self.listener_thread.start()
            self.append_log("[监听] 线程已启动")
        except Exception as e:
            self.show_popup("连接失败", f"无法打开串口: {e}")

    def toggle_auto_temp(self, instance):
        if not self.controller:
            return
        current = self.controller._auto_temp_control
        self.controller.set_auto_temp_control(not current)
        self.btn_auto.text = f'自动温控: {"启用" if not current else "禁用"}'
        self.append_log(f"自动温控 {'启用' if not current else '禁用'}")

    # ---------- 回调：界面更新 ----------
    def append_log(self, msg: str):
        """线程安全地向日志追加文本"""
        Clock.schedule_once(lambda dt: self._do_append_log(msg))

    def _do_append_log(self, msg):
        current = self.log_label.text
        new_text = current + msg + '\n'
        self.log_label.text = new_text
        # 滚动到底部
        self.scroll_view.scroll_y = 0

    def on_temp_update(self, temp: float):
        Clock.schedule_once(lambda dt: self._do_temp_update(temp))

    def _do_temp_update(self, temp):
        self.append_log(f"[温度] {temp:.1f}°C")

    def on_relay_response(self, cmd: str, success: bool):
        Clock.schedule_once(lambda dt: self._do_relay_response(cmd, success))

    def _do_relay_response(self, cmd, success):
        status = "成功" if success else "失败"
        self.append_log(f"[接收] 继电器 {cmd} 执行{status}")

    def on_location(self, points):
        Clock.schedule_once(lambda dt: self._do_location(points))

    def _do_location(self, points):
        from common import format_location_for_display
        display = format_location_for_display(points, beijing_offset=CONFIG.get('beijing_offset', 8))
        self.append_log(f"[定位] 信息:\n{display}")

    # ---------- 串口监听线程 ----------
    def _listener_loop(self):
        """后台持续读取北斗串口数据，并交给控制器解析"""
        while self.running and self.ser and self.ser.is_open:
            try:
                if self.ser.in_waiting:
                    line = self.ser.readline().decode('ascii', errors='ignore').strip()
                    if line:
                        # 将原始数据交给控制器处理
                        if self.controller:
                            self.controller.parse_received_nmea(line)
                else:
                    time.sleep(0.05)
            except Exception as e:
                log.error(f"监听线程异常: {e}")
                time.sleep(1)

    # ---------- 辅助弹窗 ----------
    def show_popup(self, title, message):
        popup = Popup(
            title=title,
            content=Label(text=message, font_name=CHINESE_FONT),
            size_hint=(0.8, 0.4)
        )
        popup.open()

    # ---------- 退出处理 ----------
    def on_close(self, *args):
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()
        return False  # 允许窗口关闭

    def on_stop(self):
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()

if __name__ == '__main__':
    BeidouApp().run()
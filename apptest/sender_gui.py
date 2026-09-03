# sender_gui.py
import threading
import serial.tools.list_ports
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.dropdown import DropDown
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.core.window import Window

from sender import BeidouSender

CHINESE_FONT = "C:/Windows/Fonts/msyh.ttc"

class SenderApp(App):
    def build(self):
        self.root_layout = BoxLayout(orientation='vertical', spacing=8, padding=10)

        # ---- 顶部：串口选择 ----
        self.top_layout = BoxLayout(size_hint_y=None, height=40, spacing=10)
        self.port_label = Label(text='请选择串口', font_name=CHINESE_FONT)
        self.btn_select = Button(text='选择串口', font_name=CHINESE_FONT)
        self.btn_select.bind(on_press=self.show_port_dropdown)
        self.top_layout.add_widget(self.port_label)
        self.top_layout.add_widget(self.btn_select)
        self.root_layout.add_widget(self.top_layout)

        # ---- 控制按钮 ----
        self.btn_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)
        self.btn_close = Button(text='闭合继电器', font_name=CHINESE_FONT, disabled=True)
        self.btn_close.bind(on_press=lambda x: self.sender.send_relay_cmd_async('all_close') if self.sender else None)
        self.btn_open = Button(text='断开继电器', font_name=CHINESE_FONT, disabled=True)
        self.btn_open.bind(on_press=lambda x: self.sender.send_relay_cmd_async('all_open') if self.sender else None)
        self.btn_temp = Button(text='查询温度', font_name=CHINESE_FONT, disabled=True)
        self.btn_temp.bind(on_press=lambda x: self.sender.send_temp_cmd() if self.sender else None)
        self.btn_auto = Button(text='自动温控: 启用', font_name=CHINESE_FONT, disabled=True)
        self.btn_auto.bind(on_press=self.toggle_auto)
        self.btn_layout.add_widget(self.btn_close)
        self.btn_layout.add_widget(self.btn_open)
        self.btn_layout.add_widget(self.btn_temp)
        self.btn_layout.add_widget(self.btn_auto)
        self.root_layout.add_widget(self.btn_layout)

        # ---- 日志显示 ----
        self.log_label = Label(text='', halign='left', valign='top', font_name=CHINESE_FONT)
        self.log_label.bind(size=self.log_label.setter('text_size'))
        self.scroll = ScrollView()
        self.scroll.add_widget(self.log_label)
        self.root_layout.add_widget(self.scroll)

        self.sender = None
        self.selected_port = None
        self.running = False

        return self.root_layout

    def show_port_dropdown(self, instance):
        ports = serial.tools.list_ports.comports()
        if not ports:
            popup = Popup(title='错误', content=Label(text='未检测到串口', font_name=CHINESE_FONT), size_hint=(0.6, 0.3))
            popup.open()
            return
        dropdown = DropDown()
        for p in ports:
            btn = Button(text=f'{p.device} - {p.description}', size_hint_y=None, height=40, font_name=CHINESE_FONT)
            btn.bind(on_release=lambda btn: dropdown.select(btn.text))
            dropdown.add_widget(btn)
        dropdown.bind(on_select=lambda instance, x: self.on_port_selected(x))
        dropdown.open(instance)

    def on_port_selected(self, selection):
        port = selection.split(' - ')[0]
        self.selected_port = port
        self.port_label.text = f'串口: {port}'
        self.connect_serial(port)

    def connect_serial(self, port):
        try:
            self.sender = BeidouSender(port=port, baud=115200, log_callback=self.append_log)
            self.sender.start_listener()
            self.running = True
            self.btn_close.disabled = False
            self.btn_open.disabled = False
            self.btn_temp.disabled = False
            self.btn_auto.disabled = False
            self.append_log(f"已连接到 {port}")
        except Exception as e:
            self.append_log(f"连接失败: {e}")

    def toggle_auto(self, instance):
        if self.sender:
            self.sender.auto_temp_control = not self.sender.auto_temp_control
            self.btn_auto.text = f'自动温控: {"启用" if self.sender.auto_temp_control else "禁用"}'

    def append_log(self, msg):
        Clock.schedule_once(lambda dt: self._do_append(msg))

    def _do_append(self, msg):
        current = self.log_label.text
        self.log_label.text = current + msg + '\n'
        self.scroll.scroll_y = 0

    def on_stop(self):
        self.running = False
        if self.sender:
            self.sender.close()

if __name__ == '__main__':
    SenderApp().run()
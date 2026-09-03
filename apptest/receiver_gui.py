# receiver_gui.py
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

from receiver import BeidouReceiver

CHINESE_FONT = "C:/Windows/Fonts/msyh.ttc"

class ReceiverApp(App):
    def build(self):
        self.root_layout = BoxLayout(orientation='vertical', spacing=8, padding=10)

        # ---- 三个串口选择 ----
        self.port_labels = {}
        self.port_buttons = {}
        for label, key in [('北斗串口', 'bd'), ('继电器串口', 'relay'), ('温度串口(可选)', 'temp')]:
            layout = BoxLayout(size_hint_y=None, height=40, spacing=5)
            lbl = Label(text=f'{label}: 未选', font_name=CHINESE_FONT, size_hint_x=0.6)
            btn = Button(text='选择', font_name=CHINESE_FONT, size_hint_x=0.4)
            btn.bind(on_press=lambda instance, k=key: self.show_port_dropdown(k))
            layout.add_widget(lbl)
            layout.add_widget(btn)
            self.root_layout.add_widget(layout)
            self.port_labels[key] = lbl
            self.port_buttons[key] = btn

        # ---- 启动按钮 ----
        self.btn_start = Button(text='启动接收', font_name=CHINESE_FONT, size_hint_y=None, height=50)
        self.btn_start.bind(on_press=self.start_receiver)
        self.root_layout.add_widget(self.btn_start)

        # ---- 日志显示 ----
        self.log_label = Label(text='', halign='left', valign='top', font_name=CHINESE_FONT)
        self.log_label.bind(size=self.log_label.setter('text_size'))
        self.scroll = ScrollView()
        self.scroll.add_widget(self.log_label)
        self.root_layout.add_widget(self.scroll)

        self.selected_ports = {'bd': None, 'relay': None, 'temp': None}
        self.receiver = None
        self.running = False

        return self.root_layout

    def show_port_dropdown(self, key):
        ports = serial.tools.list_ports.comports()
        if not ports:
            popup = Popup(title='错误', content=Label(text='未检测到串口', font_name=CHINESE_FONT), size_hint=(0.6,0.3))
            popup.open()
            return
        dropdown = DropDown()
        for p in ports:
            btn = Button(text=f'{p.device} - {p.description}', size_hint_y=None, height=40, font_name=CHINESE_FONT)
            btn.bind(on_release=lambda btn, k=key: dropdown.select((k, btn.text)))
            dropdown.add_widget(btn)
        dropdown.bind(on_select=lambda instance, data: self.on_port_selected(data[0], data[1]))
        dropdown.open(self.port_buttons[key])

    def on_port_selected(self, key, selection):
        port = selection.split(' - ')[0]
        self.selected_ports[key] = port
        self.port_labels[key].text = f'{key}: {port}'

    def start_receiver(self, instance):
        if not self.selected_ports['bd'] or not self.selected_ports['relay']:
            popup = Popup(title='错误', content=Label(text='北斗和继电器串口必须选择', font_name=CHINESE_FONT), size_hint=(0.6,0.3))
            popup.open()
            return
        try:
            self.receiver = BeidouReceiver(
                beidou_port=self.selected_ports['bd'],
                relay_port=self.selected_ports['relay'],
                temp_port=self.selected_ports['temp'],
                log_callback=self.append_log
            )
            self.running = True
            self.btn_start.disabled = True
            self.append_log("接收端已启动，开始监听...")
            threading.Thread(target=self.receiver.loop_listen_beidou, daemon=True).start()
        except Exception as e:
            self.append_log(f"启动失败: {e}")

    def append_log(self, msg):
        Clock.schedule_once(lambda dt: self._do_append(msg))

    def _do_append(self, msg):
        current = self.log_label.text
        self.log_label.text = current + msg + '\n'
        self.scroll.scroll_y = 0

    def on_stop(self):
        self.running = False
        if self.receiver:
            self.receiver.close()

if __name__ == '__main__':
    ReceiverApp().run()
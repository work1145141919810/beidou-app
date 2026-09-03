import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
from queue import Queue
import threading
import serial.tools.list_ports
from common import log

class LocationDisplay:
    """定位数据显示窗口（单例模式）"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LocationDisplay, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.root = tk.Tk()
        self.root.title("北斗远端数据接收显示")
        self.root.geometry("750x560")

        # 按钮区域
        self.btn_frame = ttk.Frame(self.root, padding=8)
        self.btn_frame.pack(fill=tk.X)

        self.btn_all_close = ttk.Button(self.btn_frame, text="四路继电器全部闭合", width=22, command=self._on_all_close)
        self.btn_all_close.grid(row=0, column=0, padx=6, pady=4)

        self.btn_all_open = ttk.Button(self.btn_frame, text="四路继电器全部断开", width=22, command=self._on_all_open)
        self.btn_all_open.grid(row=0, column=1, padx=6, pady=4)

        self.btn_temp = ttk.Button(self.btn_frame, text="启动温度采集", width=22, command=self._on_temp_toggle)
        self.btn_temp.grid(row=0, column=2, padx=6, pady=4)

        self.btn_help = ttk.Button(self.btn_frame, text="帮助", width=22, command=self._on_help)
        self.btn_help.grid(row=0, column=3, padx=6, pady=4)

        self.btn_quit = ttk.Button(self.btn_frame, text="退出程序", width=22, command=self._on_quit)
        self.btn_quit.grid(row=0, column=4, padx=6, pady=4)

        # 文本显示区域
        self.text_area = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, font=("Consolas", 10))
        self.text_area.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.text_area.configure(state=tk.NORMAL)
        self.text_area.bind("<Key>", lambda e: "break" if e.keysym not in ("c", "a") or not (e.state & 0x4) else None)
        self.text_area.insert(tk.END, "===== 北斗数据接收显示 =====\n")
        self.text_area.insert(tk.END, "点击上方按钮执行操作，等待接收数据...\n\n")
        self.queue = Queue()
        self._running = True
        self._visible = False

        # 按钮回调函数（由 sender 注册）
        self._cb_all_close = None
        self._cb_all_open = None
        self._cb_temp_start = None
        self._cb_temp_stop = None
        self._cb_quit = None
        self._temp_running = False

        self.root.after(100, self._update_loop)

    def _update_loop(self):
        try:
            changed = False
            while not self.queue.empty():
                line = self.queue.get_nowait()
                self.text_area.insert(tk.END, line + "\n")
                changed = True
            if changed:
                self.text_area.see(tk.END)
        except:
            pass
        if self._running:
            self.root.after(100, self._update_loop)

    # ===== 按钮回调 =====
    def _on_all_close(self):
        self.append("[GUI] 点击：四路继电器全部闭合")
        if self._cb_all_close:
            threading.Thread(target=self._cb_all_close, daemon=True).start()

    def _on_all_open(self):
        self.append("[GUI] 点击：四路继电器全部断开")
        if self._cb_all_open:
            threading.Thread(target=self._cb_all_open, daemon=True).start()

    def _on_temp_toggle(self):
        if self._temp_running:
            self.append("[GUI] 点击：停止温度采集")
            if self._cb_temp_stop:
                threading.Thread(target=self._cb_temp_stop, daemon=True).start()
            self.set_temp_running(False)
        else:
            self.append("[GUI] 点击：启动温度采集")
            if self._cb_temp_start:
                threading.Thread(target=self._cb_temp_start, daemon=True).start()
            self.set_temp_running(True)

    def _on_help(self):
        help_text = (
            "【北斗远端数据接收与发送控制程序】\n\n"
            "功能简介：\n"
            "  • 通过北斗短报文远程控制继电器（全部闭合/断开）\n"
            "  • 定时采集远端温度传感器数据\n"
            "  • 自动温控：温度 ≥ 27℃ 自动断开继电器，≤ 24℃ 自动闭合\n"
            "  • 接收并显示远端定位信息（A225协议）\n"
            "  • 回传数据可视化显示（GUI）\n\n"
            "使用方法：\n"
            "  1. 确保北斗串口已连接且波特率正确（默认115200）\n"
            "  2. 启动程序后，点击“启动温度采集”开始周期性采集\n"
            "  3. 点击“四路继电器全部闭合/断开”手动控制继电器\n"
            "  4. 自动温控默认启用，无需额外操作\n"
            "  5. 退出程序请点击“退出程序”或关闭窗口\n\n"
            "注意事项：\n"
            "  • 继电器和温度传感器需通过RS485连接到接收端\n"
            "  • 北斗模块需正确配置并处于收发状态\n"
            "  • 帮助信息可在任意时刻查看"
        )
        messagebox.showinfo("程序帮助", help_text)

    def _on_quit(self):
        self.append("[GUI] 点击：退出程序")
        if self._cb_quit:
            try:
                self.root.after(0, self.root.quit)
            except:
                pass
            threading.Thread(target=self._cb_quit, daemon=True).start()
        else:
            try:
                self.root.quit()
                self.root.destroy()
            except:
                pass

    # ===== 对外接口 =====
    def register_callbacks(self, all_close=None, all_open=None,
                           temp_start=None, temp_stop=None, quit=None):
        self._cb_all_close = all_close
        self._cb_all_open = all_open
        self._cb_temp_start = temp_start
        self._cb_temp_stop = temp_stop
        self._cb_quit = quit

    def set_temp_running(self, running: bool):
        self._temp_running = running
        try:
            self.root.after(0, self._update_temp_btn_text)
        except:
            pass

    def _update_temp_btn_text(self):
        if self._temp_running:
            self.btn_temp.configure(text="停止温度采集")
        else:
            self.btn_temp.configure(text="启动温度采集")

    def show(self):
        if self._visible:
            return
        self._visible = True
        try:
            self.root.after(0, lambda: (self.root.deiconify(), self.root.lift(), self.root.focus_force()))
        except:
            pass

    def append(self, text):
        self.queue.put(text)
        if not self._visible:
            self.show()

    def close(self):
        self._running = False
        try:
            self.root.after(0, self.root.destroy)
        except:
            pass

    def run_gui(self):
        self.root.mainloop()

    def run_gui_in_thread(self):
        t = threading.Thread(target=self._gui_thread_main, daemon=True)
        t.start()

    def _gui_thread_main(self):
        try:
            self.root.mainloop()
        except:
            pass


def select_ports_gui(port_configs):
    """
    弹出串口选择对话框，显示设备详细信息
    port_configs: 列表，每个元素 dict{'label':显示名, 'key':配置键, 'required':True/False}
    返回字典 {key: port_device}，若取消返回 None
    """
    import tkinter.messagebox as msgbox

    ports_info = []
    for p in serial.tools.list_ports.comports():
        desc = f"{p.device} - {p.description}"
        if p.manufacturer:
            desc += f" ({p.manufacturer})"
        ports_info.append((p.device, desc))

    if not ports_info:
        root = tk.Tk()
        root.withdraw()
        msgbox.showerror("错误", "未检测到可用串口")
        root.destroy()
        return None

    root = tk.Tk()
    root.title("串口选择")
    root.geometry("480x350")
    root.resizable(False, False)

    result = [None]
    combos = {}

    ttk.Label(root, text="请选择串口（显示设备描述以辅助识别）", font=("Microsoft YaHei", 11, "bold")).grid(
        row=0, column=0, columnspan=2, padx=10, pady=(10, 5))

    for i, cfg in enumerate(port_configs, start=1):
        ttk.Label(root, text=cfg['label']).grid(
            row=i, column=0, padx=10, pady=6, sticky='w')

        choices = [desc for _, desc in ports_info]
        if not cfg.get('required', True):
            choices = ['(跳过)'] + choices

        initial = choices[0] if choices else ''
        var = tk.StringVar(value=initial)
        combo = ttk.Combobox(root, textvariable=var, values=choices,
                             width=40, state='readonly')
        combo.grid(row=i, column=1, padx=10, pady=6)
        combos[cfg['key']] = (var, cfg.get('required', True))

    def on_ok():
        result[0] = {}
        for key, (var, required) in combos.items():
            val = var.get()
            if not required and val == '(跳过)':
                result[0][key] = None
            else:
                # 从描述中提取端口名
                for dev, desc in ports_info:
                    if desc == val:
                        result[0][key] = dev
                        break
                else:
                    result[0][key] = None
        root.destroy()

    def on_cancel():
        result[0] = None
        root.destroy()

    btn_frame = ttk.Frame(root)
    btn_frame.grid(row=len(port_configs) + 1, column=0, columnspan=2, pady=10)
    ttk.Button(btn_frame, text="确定", command=on_ok).pack(side=tk.LEFT, padx=15)
    ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=15)

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()

    return result[0]
import time
import threading
import queue
import socket
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from ping3 import ping

# ---------- 轻量级图表 ----------
# 字体配置：使用开源免费字体
CHART_TITLE_FONT = ('Noto Sans CJK SC', 12, 'bold')
CHART_LABEL_FONT = ('Noto Sans CJK SC', 10)
CHART_TICK_FONT = ('Liberation Sans', 9)
CHART_LEGEND_FONT = ('Liberation Sans', 9)
class SimpleChart(tk.Toplevel):
    """使用 tkinter.Canvas 绘制的延迟图表"""
    def __init__(self, parent, timestamps, latencies, host):
        super().__init__(parent)
        self.title(f"Ping 结果 - {host}")
        self.geometry("800x500")
        self.timestamps = timestamps
        self.latencies = latencies
        self.host = host

        self.canvas = tk.Canvas(self, bg='white', highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)

        self.bind('<Configure>', lambda e: self.draw_chart())

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=5)
        ttk.Button(btn_frame, text="保存为图片", command=self.save_chart).pack(side="right")

    def draw_chart(self):
        """绘制延迟曲线"""
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 100 or h < 100:
            return

        margin = {'top': 40, 'right': 40, 'bottom': 60, 'left': 60}
        chart_w = w - margin['left'] - margin['right']
        chart_h = h - margin['top'] - margin['bottom']

        # 筛选有效数据
        valid = [(i, ts, lat) for i, (ts, lat) in enumerate(zip(self.timestamps, self.latencies)) if lat is not None]
        loss_idx = [i for i, lat in enumerate(self.latencies) if lat is None]

        if not valid and not loss_idx:
            self.canvas.create_text(w//2, h//2, text="无数据", font=('Liberation Sans', 14))
            return

        all_lats = [lat for _, _, lat in valid] if valid else [0]
        max_lat = max(all_lats) * 1.2 if all_lats else 100
        if max_lat == 0:
            max_lat = 1.0
        max_idx = len(self.latencies) - 1

        # 标题
        self.canvas.create_text(w//2, 20, text=f"Ping 监控 - {self.host}", font=CHART_TITLE_FONT)

        # 坐标轴
        self.canvas.create_line(margin['left'], margin['top'], margin['left'], h - margin['bottom'], width=2)
        self.canvas.create_line(margin['left'], h - margin['bottom'], w - margin['right'], h - margin['bottom'], width=2)

        # Y轴标签、网格线
        for i in range(6):
            y_val = max_lat * i / 5
            y_pos = h - margin['bottom'] - (chart_h * i / 5)
            self.canvas.create_text(margin['left'] - 10, y_pos, text=f"{y_val:.2f}", anchor="e", font=CHART_TICK_FONT)
            if i > 0:
                self.canvas.create_line(margin['left'], y_pos, w - margin['right'], y_pos, fill='#E0E0E0', dash=(4, 4))

        self.canvas.create_text(20, h//2, text="延迟 (ms)", angle=90, font=CHART_LABEL_FONT)

        # 绘制曲线和数据点
        if valid:
            points = []
            for idx, ts, lat in valid:
                x = margin['left'] + (idx / max_idx) * chart_w if max_idx > 0 else margin['left']
                y = h - margin['bottom'] - (lat / max_lat) * chart_h
                points.extend([x, y])
                color = '#2196F3' if lat < 100 else '#FF9800' if lat < 300 else '#F44336'
                self.canvas.create_oval(x-3, y-3, x+3, y+3, fill=color, outline=color)
            if len(points) >= 4:
                self.canvas.create_line(points, fill='#2196F3', width=2)

        # 丢包标记
        for idx in loss_idx:
            x = margin['left'] + (idx / max_idx) * chart_w if max_idx > 0 else margin['left']
            y = h - margin['bottom'] - chart_h * 0.1
            self.canvas.create_text(x, y, text="✕", fill='red', font=('Liberation Sans', 12, 'bold'))

        # X轴标签
        for pos, idx in [(0, 0), (max_idx//2, max_idx//2), (max_idx, max_idx)]:
            x = margin['left'] + (idx / max_idx) * chart_w if max_idx > 0 else margin['left']
            self.canvas.create_text(x, h - margin['bottom'] + 20, text=self.timestamps[idx].strftime('%H:%M:%S'), font=CHART_TICK_FONT)

        # 图例
        self.canvas.create_oval(w - margin['right'] - 80, margin['top'] + 5, w - margin['right'] - 75, margin['top'] + 10, fill='#2196F3')
        self.canvas.create_text(w - margin['right'] - 60, margin['top'] + 8, text="延迟", anchor="w", font=CHART_LEGEND_FONT)
        self.canvas.create_text(w - margin['right'] - 20, margin['top'] + 8, text="✕ 丢包", fill='red', font=CHART_LEGEND_FONT)

        # 统计信息
        total = len(self.latencies)
        loss = len(loss_idx)
        avg_lat = sum(lat for _, _, lat in valid) / len(valid) if valid else 0
        self.canvas.create_text(w//2, h - 15, text=f"总包: {total} | 丢包: {loss} ({loss/total*100:.1f}%) | 平均延迟: {avg_lat:.1f}ms",
                                font=('Liberation Sans', 10, 'bold'), fill='#333')

    def save_chart(self):
        """保存为 PostScript 文件"""
        path = filedialog.asksaveasfilename(
            defaultextension=".ps",
            filetypes=[("PostScript", "*.ps"), ("所有文件", "*.*")],
            initialfile=f"ping_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        if path:
            self.canvas.postscript(file=path, colormode="color")
            messagebox.showinfo("保存成功", f"图表已保存至:\n{path}")


# ---------- 带超时保存对话框 ----------
class SaveDialog:
    def __init__(self, parent, timeout=15):
        self.parent = parent
        self.timeout = timeout
        self.result = None
        self.dialog = None
        self.timer_id = None

    def show(self):
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("图表未保存")
        self.dialog.geometry("400x180")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 400) // 2
        y = (self.dialog.winfo_screenheight() - 180) // 2
        self.dialog.geometry(f"+{x}+{y}")

        ttk.Label(self.dialog, text="当前有未保存的图表窗口，是否保存？",
                  font=('Noto Sans CJK SC', 10), wraplength=350).pack(pady=20)

        self.countdown_var = tk.StringVar(value=f"超时自动放弃保存: {self.timeout}秒")
        ttk.Label(self.dialog, textvariable=self.countdown_var, foreground='red').pack(pady=5)

        btn_frame = ttk.Frame(self.dialog)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="保存", command=self.on_save, width=12).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="不保存", command=self.on_discard, width=12).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="取消", command=self.on_cancel, width=12).pack(side="left", padx=10)

        self.remaining = self.timeout
        self._countdown()
        self.dialog.wait_window()
        return self.result

    def _countdown(self):
        if self.remaining > 0 and self.result is None:
            self.countdown_var.set(f"超时自动放弃保存: {self.remaining}秒")
            self.remaining -= 1
            self.timer_id = self.dialog.after(1000, self._countdown)
        elif self.remaining <= 0 and self.result is None:
            self.result = 'timeout'
            self.dialog.destroy()

    def on_save(self):
        self.result = 'save'
        self.dialog.after_cancel(self.timer_id)
        self.dialog.destroy()

    def on_discard(self):
        self.result = 'discard'
        self.dialog.after_cancel(self.timer_id)
        self.dialog.destroy()

    def on_cancel(self):
        self.result = 'cancel'
        self.dialog.after_cancel(self.timer_id)
        self.dialog.destroy()


# ---------- 工具函数 ----------
def ping_host(host, timeout=2, size=56):
    """对目标主机执行一次 ping（host 可以是域名或 IP）"""
    try:
        rtt = ping(host, timeout=timeout, unit='ms', size=size)
        if rtt is None:
            return None, "超时"
        # rtt == 0.0 是合法值（例如 ping 本机），应视为成功
        return rtt, ""
    except socket.gaierror:
        return None, "解析失败"
    except Exception as e:
        return None, f"错误: {e}"

def sleep_with_check(seconds, stop_event):
    """分段睡眠，期间检查停止事件；返回 False 表示被中断"""
    step = 0.1
    steps = int(seconds / step)
    for _ in range(steps):
        if stop_event and stop_event.is_set():
            return False
        time.sleep(step)
    return True

def collect_data(host, count, interval, size, duration=None, callback=None, stop_event=None):
    """
    收集 ping 数据线程函数
    :param duration: 持续时间（秒），如果指定，则在该时间后自动停止（即使 count 为 None 或未达到次数）
    """
    start_time = time.time()
    i = 0
    while not (stop_event and stop_event.is_set()):
        # 检查持续时间
        if duration is not None and (time.time() - start_time) >= duration:
            break
        # 检查次数
        if count is not None and count > 0 and i >= count:
            break

        now = datetime.now()
        rtt, err = ping_host(host, size=size)
        if callback:
            callback((now, rtt, err))
        i += 1

        # 等待下一个间隔（期间可被停止）
        if not sleep_with_check(interval, stop_event):
            break

    if callback:
        callback(None)   # 发送结束信号


# ---------- 主应用程序 ----------
class PingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Ping 工具")
        self.root.geometry("600x600")
        self.root.resizable(True, True)

        self.host = tk.StringVar(value="www.bing.com")
        self.size = tk.StringVar(value="56")
        self.interval = tk.DoubleVar(value=1.0)

        # 模式相关变量
        self.mode = tk.StringVar(value="count")  # "count" 或 "duration"
        self.count = tk.StringVar(value="30")
        self.duration = tk.StringVar(value="")    # 秒数

        self.ping_thread = None
        self.stop_event = threading.Event()
        self.data_queue = queue.Queue()
        self.after_id = None

        self.timestamps = []
        self.latencies = []
        self.total_pings = 0
        self.loss_count = 0
        self.stats_var = tk.StringVar(value="总包: 0 | 丢包: 0 | 丢包率: 0.00%")

        self.chart_window = None

        self.create_widgets()

    def create_widgets(self):
        # 输入框架
        frame_in = ttk.LabelFrame(self.root, text="参数设置", padding=10)
        frame_in.pack(fill="x", padx=10, pady=5)

        # 主机
        ttk.Label(frame_in, text="目标主机:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(frame_in, textvariable=self.host, width=30).grid(row=0, column=1, sticky="w", padx=5, pady=3)

        # 包大小
        ttk.Label(frame_in, text="包大小 (字节):").grid(row=1, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(frame_in, textvariable=self.size, width=10).grid(row=1, column=1, sticky="w", padx=5, pady=3)

        # 间隔
        ttk.Label(frame_in, text="间隔 (秒):").grid(row=2, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(frame_in, textvariable=self.interval, width=10).grid(row=2, column=1, sticky="w", padx=5, pady=3)

        # 模式选择
        mode_frame = ttk.Frame(frame_in)
        mode_frame.grid(row=3, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Radiobutton(mode_frame, text="次数模式", variable=self.mode, value="count",
                        command=self.on_mode_change).pack(side="left", padx=5)
        ttk.Radiobutton(mode_frame, text="持续时间模式", variable=self.mode, value="duration",
                        command=self.on_mode_change).pack(side="left", padx=5)

        # 次数输入
        self.count_label = ttk.Label(frame_in, text="Ping 次数 (0或空=无限):")
        self.count_label.grid(row=4, column=0, sticky="w", padx=5, pady=3)
        self.count_entry = ttk.Entry(frame_in, textvariable=self.count, width=10)
        self.count_entry.grid(row=4, column=1, sticky="w", padx=5, pady=3)

        # 持续时间输入
        self.duration_label = ttk.Label(frame_in, text="持续时间 (秒):")
        self.duration_entry = ttk.Entry(frame_in, textvariable=self.duration, width=10)

        # 初始状态：次数模式可见，持续时间不可见
        self.duration_label.grid_remove()
        self.duration_entry.grid_remove()

        # 按钮
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=5)

        self.start_btn = ttk.Button(btn_frame, text="开始 Ping", command=self.start_ping)
        self.start_btn.pack(side="left", padx=5)

        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self.stop_ping, state="disabled")
        self.stop_btn.pack(side="left", padx=5)

        # 输出区域
        out_frame = ttk.LabelFrame(self.root, text="实时输出", padding=5)
        out_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.output = scrolledtext.ScrolledText(out_frame, wrap="word", height=12)
        self.output.pack(fill="both", expand=True)

        # 状态栏
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill="x", padx=10, pady=(0,5))
        ttk.Label(status_frame, textvariable=self.stats_var,
                  font=('Liberation Sans', 10, 'bold'), foreground='blue').pack(side="left")

    def on_mode_change(self):
        """模式切换时显示/隐藏对应的输入框"""
        if self.mode.get() == "count":
            self.count_label.grid()
            self.count_entry.grid()
            self.duration_label.grid_remove()
            self.duration_entry.grid_remove()
        else:
            self.count_label.grid_remove()
            self.count_entry.grid_remove()
            self.duration_label.grid()
            self.duration_entry.grid()

    def start_ping(self):
        # 主机校验
        host = self.host.get().strip()
        if not host:
            messagebox.showerror("错误", "请输入目标主机")
            return

        # 包大小校验：必须为正整数
        size_str = self.size.get().strip()
        if not size_str:
            messagebox.showerror("错误", "包大小不能为空")
            return
        try:
            size = int(size_str)
            if size <= 0:
                messagebox.showerror("错误", "包大小必须为正整数")
                return
        except ValueError:
            messagebox.showerror("错误", "包大小必须为整数")
            return

        # 间隔校验
        try:
            interval = self.interval.get()
            if interval <= 0:
                messagebox.showerror("错误", "间隔必须为正数")
                return
        except:
            messagebox.showerror("错误", "间隔必须为数字")
            return

        # 根据模式获取参数
        count = None
        duration = None
        if self.mode.get() == "count":
            count_str = self.count.get().strip()
            if count_str == "":
                count = None  # 空字符串表示无限
            else:
                try:
                    count = int(count_str)
                    if count < 0:
                        messagebox.showerror("错误", "次数不能为负数")
                        return
                    if count == 0:
                        count = None  # 0 也表示无限
                except ValueError:
                    messagebox.showerror("错误", "次数必须为整数")
                    return
        else:  # duration mode
            dur_str = self.duration.get().strip()
            if dur_str == "":
                messagebox.showerror("错误", "请输入持续时间")
                return
            try:
                duration = float(dur_str)
                if duration <= 0:
                    messagebox.showerror("错误", "持续时间必须为正数")
                    return
            except ValueError:
                messagebox.showerror("错误", "持续时间必须为数字")
                return
            count = None  # 次数模式设为无限

        # 提前解析域名
        try:
            ip = socket.gethostbyname(host)
            self.output.insert(tk.END, f"目标 {host} 解析为 {ip}\n")
            self.output.see(tk.END)
        except Exception as e:
            messagebox.showerror("错误", f"域名解析失败: {e}")
            return

        # 清空旧数据
        self.timestamps.clear()
        self.latencies.clear()
        self.output.delete(1.0, tk.END)
        self.data_queue = queue.Queue()
        self.total_pings = 0
        self.loss_count = 0
        self.stats_var.set("总包: 0 | 丢包: 0 | 丢包率: 0.00%")

        self.stop_event.clear()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        # 启动线程
        self.ping_thread = threading.Thread(
            target=collect_data,
            args=(ip, count, interval, size),
            kwargs={'duration': duration, 'callback': self.data_queue.put, 'stop_event': self.stop_event},
            daemon=True
        )
        self.ping_thread.start()

        self.after_id = self.root.after(100, self.poll_queue)

    def poll_queue(self):
        try:
            while True:
                item = self.data_queue.get_nowait()
                if item is None:
                    self.ping_finished()
                    return
                ts, rtt, err = item
                self.timestamps.append(ts)
                self.latencies.append(rtt)

                self.total_pings += 1
                if rtt is None:
                    self.loss_count += 1
                loss_rate = (self.loss_count / self.total_pings) * 100
                self.stats_var.set(f"总包: {self.total_pings} | 丢包: {self.loss_count} | 丢包率: {loss_rate:.2f}%")

                status = f"{rtt:.2f} ms" if rtt is not None else (err or "丢包")
                self.output.insert(tk.END, f"{ts.strftime('%H:%M:%S')} - {status}\n")
                self.output.see(tk.END)

        except queue.Empty:
            pass

        if self.ping_thread and self.ping_thread.is_alive():
            self.after_id = self.root.after(100, self.poll_queue)
        else:
            self.ping_finished()

    def ping_finished(self):
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

        if not self.timestamps:
            return

        # 处理已存在的图表窗口
        if self.chart_window and self.chart_window.winfo_exists():
            dlg = SaveDialog(self.root, timeout=15)
            res = dlg.show()
            if res == 'save':
                self.chart_window.save_chart()
                self.chart_window.destroy()
            elif res in ('discard', 'timeout'):
                self.chart_window.destroy()
            elif res == 'cancel':
                self.output.insert(tk.END, "操作已取消，未生成新图表\n")
                self.output.see(tk.END)
                return

        # 创建新图表
        self.chart_window = SimpleChart(self.root, self.timestamps, self.latencies, self.host.get())

    def stop_ping(self):
        if self.stop_event:
            self.stop_event.set()


if __name__ == "__main__":
    root = tk.Tk()
    app = PingApp(root)
    root.mainloop()

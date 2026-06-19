"""
Integrated Communication Panel
Page 1: TNPC communication panel
Page 2: GW INSTEK PSU 20-76 current source control panel
Page 3: Teledyne LeCroy HDO6104A oscilloscope control panel

说明：
1. 这个版本不会再因为缺少 tnpc_core.py / tnpc_power.py 直接崩溃。
2. 如果当前目录里有 tnpc_core.py 和 tnpc_power.py，会自动使用你的原始 ManualPage / ScanPage / PowerPanel。
3. 如果没有这两个文件，第一页会显示占位页面，串口连接、紧急停止按钮和后续页面仍可正常打开。
"""

import sys
import time
import re
import csv
import struct
import threading
from pathlib import Path
from datetime import datetime

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QComboBox,
    QPushButton,
    QTabWidget,
    QMessageBox,
    QShortcut,
    QLineEdit,
    QTextEdit,
    QSizePolicy,
    QCheckBox,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
)

try:
    import serial
    import serial.tools.list_ports
except Exception:
    serial = None

try:
    import pyvisa
except Exception:
    pyvisa = None


# ============================================================
# Optional GW INSTEK PSU 20-76 current source page
# ============================================================

CURRENT_SOURCE_PAGE_OK = True
CURRENT_SOURCE_IMPORT_ERROR = ""

try:
    from psu_20_76_current_gui import PSU2076CurrentSource
except Exception as e:
    CURRENT_SOURCE_PAGE_OK = False
    CURRENT_SOURCE_IMPORT_ERROR = str(e)

    class PSU2076CurrentSource(QWidget):
        def __init__(self):
            super().__init__()
            layout = QVBoxLayout(self)
            label = QLabel(
                "电流源控制页面加载失败。\n"
                "请确认 psu_20_76_current_gui.py 与本程序放在同一文件夹，"
                "并已安装 pyvisa、pyserial、PyQt5。\n\n"
                f"错误信息：{CURRENT_SOURCE_IMPORT_ERROR}"
            )
            label.setWordWrap(True)
            layout.addWidget(label)

        def close_page(self):
            pass


# ============================================================
# Optional TNPC modules
# ============================================================

TNPC_MODULES_OK = True
TNPC_IMPORT_ERROR = ""

try:
    from tnpc_core import (
        ManualPage, ScanPage, BAUDRATE, send_command,
        CMD_STOP_PWM, CMD_SET_MODE, CMD_SET_CARRIER, CMD_SET_CMP_L,
        CMD_SET_CMP_H, CMD_SET_DEADTIME, CMD_APPLY, CMD_START_PWM,
        FREQ2CARRIER, MODE_TRAPEZOIDAL, MODE_TRIANGULAR
    )
    from tnpc_power import PowerPanel
except Exception as e:
    TNPC_MODULES_OK = False
    TNPC_IMPORT_ERROR = str(e)

    BAUDRATE = 115200
    CMD_STOP_PWM = 0
    CMD_SET_MODE = 0x05
    CMD_SET_CARRIER = 0x01
    CMD_SET_CMP_L = 0x02
    CMD_SET_CMP_H = 0x03
    CMD_SET_DEADTIME = 0x04
    CMD_APPLY = 0x10
    CMD_START_PWM = 0x21
    FREQ2CARRIER = 50e6
    MODE_TRAPEZOIDAL = 0
    MODE_TRIANGULAR = 1

    def send_command(ser, cmd, value=0):
        if ser and getattr(ser, "is_open", False):
            # 占位 STOP 命令。真实协议请使用 tnpc_core.py 里的 send_command。
            ser.write(bytes([cmd & 0xFF, value & 0xFF]))

    class ManualPage(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            msg = QTextEdit()
            msg.setReadOnly(True)
            msg.setText(
                "Manual Control 页面未加载。\n\n"
                "原因：没有找到 tnpc_core.py。\n\n"
                "解决方法：\n"
                "把 tnpc_core.py 和 tnpc_power.py 放到本文件同一目录，"
                "然后重新运行本程序。"
            )
            layout.addWidget(msg)

        def set_connected(self, connected):
            pass

    class ScanPage(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.scan_thread = None
            layout = QVBoxLayout(self)
            msg = QTextEdit()
            msg.setReadOnly(True)
            msg.setText(
                "Auto Scan 页面未加载。\n\n"
                "原因：没有找到 tnpc_core.py。\n\n"
                "解决方法：\n"
                "把 tnpc_core.py 和 tnpc_power.py 放到本文件同一目录，"
                "然后重新运行本程序。"
            )
            layout.addWidget(msg)

        def set_connected(self, connected):
            pass

    class PowerPanel(QGroupBox):
        def __init__(self, parent=None):
            super().__init__("Power Panel")
            layout = QVBoxLayout(self)
            label = QLabel(
                "电源面板未加载：没有找到 tnpc_power.py。\n"
                "如需完整电源控制，请把 tnpc_power.py 放到本文件同一目录。"
            )
            label.setWordWrap(True)
            layout.addWidget(label)

        def emergency_off(self):
            pass

        def disconnect_all(self):
            pass


# ============================================================
# Shared helpers
# ============================================================

def extract_float(text: str) -> float:
    match = re.search(r"[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?", str(text))
    if not match:
        raise ValueError(f"无法从返回值中解析数字: {text}")
    return float(match.group(0))


def fmt(value: float) -> str:
    return f"{value:.6g}"


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def normalize_image_data(data: bytes):
    png_magic = b"\x89PNG\r\n\x1a\n"
    jpg_magic = b"\xff\xd8"

    png_index = data.find(png_magic)
    if png_index >= 0:
        return data[png_index:], "png"

    jpg_index = data.find(jpg_magic)
    if jpg_index >= 0:
        return data[jpg_index:], "jpg"

    return data, "png"


def append_csv_row(file_path: Path, header: list, row: list):
    ensure_dir(file_path.parent)
    file_exists = file_path.exists()

    with open(file_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(header)
        writer.writerow(row)


def clean_number_text(text: str):
    if text is None:
        return ""

    match = re.search(r"[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?", str(text))
    if not match:
        return str(text).strip()

    return match.group(0)


def parse_past_last_value(resp: str):
    parts = [p.strip() for p in str(resp).split(",")]
    for i, p in enumerate(parts):
        if p.upper() == "LAST" and i + 1 < len(parts):
            return clean_number_text(parts[i + 1])
    return clean_number_text(resp)


def mean_of_wave(values):
    nums = []
    for v in values:
        try:
            nums.append(float(v))
        except Exception:
            pass

    if not nums:
        return ""

    return f"{sum(nums) / len(nums):.8g}"


def chinese_group_name(index: int) -> str:
    """把 1~10 转成 第一组~第十组，超过范围时退回 第N组。"""
    names = {
        1: "第一组",
        2: "第二组",
        3: "第三组",
        4: "第四组",
        5: "第五组",
        6: "第六组",
        7: "第七组",
        8: "第八组",
        9: "第九组",
        10: "第十组",
    }
    return names.get(int(index), f"第{int(index)}组")


# ============================================================
# Page 1: TNPC communication panel
# ============================================================

class CoreParameterDialog(QDialog):
    """输入并保存磁芯参数：原边匝数、副边匝数、Ae、Le。"""

    def __init__(self, parent=None, values=None):
        super().__init__(parent)
        self.setWindowTitle("输入磁芯参数")
        self.setMinimumWidth(360)
        self.values = values or {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.primary_turns_input = QLineEdit(str(self.values.get("primary_turns", "")))
        self.secondary_turns_input = QLineEdit(str(self.values.get("secondary_turns", "")))
        self.ae_input = QLineEdit(str(self.values.get("ae", "")))
        self.le_input = QLineEdit(str(self.values.get("le", "")))

        self.primary_turns_input.setPlaceholderText("例如：20")
        self.secondary_turns_input.setPlaceholderText("例如：10")
        self.ae_input.setPlaceholderText("单位：mm²，例如：125")
        self.le_input.setPlaceholderText("单位：mm，例如：60")

        form.addRow("原边匝数 Np：", self.primary_turns_input)
        form.addRow("副边匝数 Ns：", self.secondary_turns_input)
        form.addRow("磁芯截面积 Ae：", self.ae_input)
        form.addRow("有效磁路长度 Le：", self.le_input)

        layout.addLayout(form)

        note = QLabel("说明：Ae 默认按 mm² 输入，Le 默认按 mm 输入。")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        try:
            primary_turns = int(self.primary_turns_input.text().strip())
            secondary_turns = int(self.secondary_turns_input.text().strip())
            ae = float(self.ae_input.text().strip())
            le = float(self.le_input.text().strip())

            if primary_turns <= 0 or secondary_turns <= 0:
                raise ValueError("原边匝数和副边匝数必须大于 0")
            if ae <= 0 or le <= 0:
                raise ValueError("Ae 和 Le 必须大于 0")

            self.values = {
                "primary_turns": primary_turns,
                "secondary_turns": secondary_turns,
                "ae": ae,
                "le": le,
            }
            super().accept()
        except Exception as e:
            QMessageBox.warning(self, "参数错误", str(e))

    def get_values(self):
        return dict(self.values)


class TNPCPage(QWidget):
    message_signal = pyqtSignal(str)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.ser = None
        self.core_params = {
            "primary_turns": "",
            "secondary_turns": "",
            "ae": "",
            "le": "",
        }
        self.message_signal.connect(self.set_status)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        top_bar = QHBoxLayout()

        core_group = QGroupBox("Core Parameters")
        core_layout = QVBoxLayout(core_group)
        core_layout.setContentsMargins(10, 10, 10, 10)

        self.core_param_btn = QPushButton("输入磁芯参数")
        self.core_param_btn.clicked.connect(self.open_core_parameter_dialog)
        self.core_param_label = QLabel("磁芯参数：未设置")
        self.core_param_label.setWordWrap(True)

        core_layout.addWidget(self.core_param_btn)
        core_layout.addWidget(self.core_param_label)
        top_bar.addWidget(core_group, 2)

        serial_group = QGroupBox("Serial Port (DSP)")
        sl = QHBoxLayout(serial_group)
        sl.setContentsMargins(10, 10, 10, 10)

        self.port_combo = QComboBox()
        self.refresh_ports()

        sl.addWidget(QLabel("COM:"))
        sl.addWidget(self.port_combo, 1)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_ports)
        sl.addWidget(self.refresh_btn)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        sl.addWidget(self.connect_btn)

        top_bar.addWidget(serial_group, 3)

        self.estop_btn = QPushButton("EMERGENCY STOP (Esc)")
        self.estop_btn.setStyleSheet(
            "background-color: #c0392b; color: white; "
            "font-weight: bold; font-size: 14px; padding: 8px;"
        )
        self.estop_btn.clicked.connect(self.emergency_stop)
        top_bar.addWidget(self.estop_btn, 1)

        layout.addLayout(top_bar)

        self.power_panel = PowerPanel(self)
        layout.addWidget(self.power_panel)

        self.tabs = QTabWidget()
        self.manual_page = ManualPage(self)
        self.scan_page = ScanPage(self)

        self.tabs.addTab(self.manual_page, "Manual Control")
        self.tabs.addTab(self.scan_page, "Auto Scan")
        layout.addWidget(self.tabs, 1)

        self.status_label = QLabel("Disconnected")
        self.status_label.setFrameStyle(QLabel.Panel | QLabel.Sunken)
        self.status_label.setMinimumHeight(26)
        layout.addWidget(self.status_label)

        if not TNPC_MODULES_OK:
            self.message_signal.emit(f"TNPC 子模块未加载：{TNPC_IMPORT_ERROR}")

    def open_core_parameter_dialog(self):
        dlg = CoreParameterDialog(self, self.core_params)
        if dlg.exec_() == QDialog.Accepted:
            self.core_params = dlg.get_values()
            self.update_core_parameter_label()
            self.sync_core_params_to_child_pages()
            self.message_signal.emit(
                "磁芯参数已设置："
                f"Np={self.core_params['primary_turns']}, "
                f"Ns={self.core_params['secondary_turns']}, "
                f"Ae={self.core_params['ae']} mm², "
                f"Le={self.core_params['le']} mm"
            )

    def update_core_parameter_label(self):
        if not self.core_params.get("primary_turns"):
            self.core_param_label.setText("磁芯参数：未设置")
            return

        self.core_param_label.setText(
            "磁芯参数："
            f"Np={self.core_params['primary_turns']}, "
            f"Ns={self.core_params['secondary_turns']}, "
            f"Ae={self.core_params['ae']} mm², "
            f"Le={self.core_params['le']} mm"
        )

    def sync_core_params_to_child_pages(self):
        # 先把参数挂到第一页子页面上，后续若自动测量/保存需要使用，可直接读取 core_params。
        for page in (getattr(self, "manual_page", None), getattr(self, "scan_page", None)):
            if page is None:
                continue
            if hasattr(page, "set_core_params"):
                try:
                    page.set_core_params(dict(self.core_params))
                    continue
                except Exception:
                    pass
            try:
                page.core_params = dict(self.core_params)
            except Exception:
                pass

        # 同步到第二页电流源控制页面，用于 Idc 与 Hdc 的换算。
        try:
            current_page = getattr(self.main_window, "current_source_page", None)
            if current_page is not None and hasattr(current_page, "set_core_params"):
                current_page.set_core_params(dict(self.core_params))
        except Exception:
            pass

    def get_core_params(self):
        return dict(self.core_params)

    def statusBar(self):
        """给 tnpc_core.ManualPage/ScanPage 提供和 QMainWindow 一样的 statusBar 接口。"""
        return self.main_window.statusBar()

    def set_status(self, msg):
        self.status_label.setText(msg)
        self.main_window.statusBar().showMessage(msg)

    def refresh_ports(self):
        self.port_combo.clear()

        if serial is None:
            self.port_combo.addItem("pyserial not installed", None)
            return

        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.port_combo.addItem(f"{p.device} - {p.description}", p.device)

    def toggle_connection(self):
        if serial is None:
            QMessageBox.warning(self, "Error", "未安装 pyserial，请先安装：pip install pyserial")
            return

        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None
            self.connect_btn.setText("Connect")
            self.manual_page.set_connected(False)
            self.scan_page.set_connected(False)
            self.message_signal.emit("Disconnected")
        else:
            port = self.port_combo.currentData()
            if not port:
                QMessageBox.warning(self, "Error", "No COM port selected")
                return

            try:
                self.ser = serial.Serial(port, BAUDRATE, timeout=0.5)
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                self.connect_btn.setText("Disconnect")
                self.manual_page.set_connected(True)
                self.scan_page.set_connected(True)
                self.message_signal.emit(f"Connected: {port} @ {BAUDRATE} baud")
            except Exception as e:
                QMessageBox.critical(self, "Connection Error", str(e))

    def emergency_stop(self):
        if getattr(self.scan_page, "scan_thread", None) is not None:
            try:
                if self.scan_page.scan_thread.isRunning():
                    self.scan_page.scan_thread.stop()
            except Exception:
                pass

        try:
            self.power_panel.emergency_off()
        except Exception:
            pass

        if self.ser and self.ser.is_open:
            try:
                send_command(self.ser, CMD_STOP_PWM, 0)
            except Exception:
                pass

        self.message_signal.emit("EMERGENCY STOP triggered")

    def close_page(self):
        if hasattr(self, "scan_page") and hasattr(self.scan_page, "scan_thread"):
            if self.scan_page.scan_thread:
                try:
                    if self.scan_page.scan_thread.isRunning():
                        self.scan_page.scan_thread.stop()
                        self.scan_page.scan_thread.wait()
                except Exception:
                    pass

        try:
            self.power_panel.disconnect_all()
        except Exception:
            pass

        if self.ser and self.ser.is_open:
            self.ser.close()


# ============================================================
# Page 3: Oscilloscope instrument class
# ============================================================

class LecroyScope:
    def __init__(self):
        self.rm = None
        self.inst = None
        self.addr = None
        self.lock = threading.Lock()

    def list_resources(self):
        if pyvisa is None:
            raise RuntimeError("未安装 pyvisa，请先安装：pip install pyvisa")

        if self.rm is None:
            try:
                self.rm = pyvisa.ResourceManager("@ivi")
            except Exception:
                self.rm = pyvisa.ResourceManager()
        return self.rm.list_resources()

    def connect(self, addr: str):
        if pyvisa is None:
            raise RuntimeError("未安装 pyvisa，请先安装：pip install pyvisa")

        # USB-TMC 设备在本机上只有 NI-VISA(@ivi) 稳定，pyvisa-py 后端
        # 开 USB 会话常常立刻失效（Invalid session handle）。每次连接重建
        # ResourceManager，避免复用已失效的旧 RM。
        try:
            self.rm = pyvisa.ResourceManager("@ivi")
        except Exception:
            self.rm = pyvisa.ResourceManager()

        self.addr = addr
        self.inst = self.rm.open_resource(addr)
        self.inst.timeout = 30000
        self.inst.chunk_size = 1024 * 1024
        self.inst.write_termination = "\n"
        self.inst.read_termination = "\n"
        self.inst.send_end = True

        # 握手阶段直接用底层 inst 调用，绕开 write/query 的自动重连包装，
        # 避免连接失败时反复递归重连。
        with self.lock:
            self.inst.write("COMM_HEADER OFF")
            idn = self.inst.query("*IDN?").strip()
        return idn

    def disconnect(self):
        with self.lock:
            if self.inst is not None:
                try:
                    self.inst.close()
                finally:
                    self.inst = None

    def reconnect(self, addr: str = None):
        """
        重新打开示波器 VISA 会话。
        自动扫频线程开始时会调用一次，避免旧线程/旧会话导致
        Invalid session handle。
        """
        if addr is None:
            addr = self.addr
        if not addr:
            raise RuntimeError("没有可用的示波器 VISA 地址，无法重连")

        try:
            self.disconnect()
        except Exception:
            pass

        return self.connect(addr)

    def is_connected(self):
        return self.inst is not None

    def check_alive(self):
        """
        简单确认当前 VISA 会话是否仍有效。
        """
        if self.inst is None:
            return False
        try:
            _ = self.query("*IDN?")
            return True
        except Exception:
            return False

    @staticmethod
    def _is_session_error(err: Exception) -> bool:
        """判断异常是否属于 VISA 会话失效（可通过重连自愈）。"""
        text = str(err).lower()
        keywords = (
            "invalid session",
            "the resource might be closed",
            "vi_error_inv_object",
            "vi_error_inv_session",
            "vi_error_conn_lost",
            "session handle",
        )
        return any(k in text for k in keywords)

    def write(self, cmd: str):
        if self.inst is None:
            raise RuntimeError("示波器未连接")
        try:
            with self.lock:
                self.inst.write(cmd)
        except Exception as e:
            if self._is_session_error(e) and self.addr:
                # 会话失效：自动重连一次后重试
                self.reconnect(self.addr)
                with self.lock:
                    self.inst.write(cmd)
            else:
                raise

    def query(self, cmd: str) -> str:
        if self.inst is None:
            raise RuntimeError("示波器未连接")
        try:
            with self.lock:
                return self.inst.query(cmd).strip()
        except Exception as e:
            if self._is_session_error(e) and self.addr:
                self.reconnect(self.addr)
                with self.lock:
                    return self.inst.query(cmd).strip()
            raise

    def save_screen_image(self, save_dir: Path) -> str:
        if self.inst is None:
            raise RuntimeError("示波器未连接")

        ensure_dir(save_dir)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        with self.lock:
            old_timeout = self.inst.timeout
            old_read_termination = self.inst.read_termination
            old_chunk_size = self.inst.chunk_size

            try:
                self.inst.timeout = 60000
                self.inst.read_termination = None
                self.inst.chunk_size = 10 * 1024 * 1024

                self.inst.write("HCSU DEV, PNG, AREA, DSOWINDOW, PORT, NET")
                time.sleep(0.5)
                self.inst.write("SCDP")
                raw = self.inst.read_raw()

                image_data, ext = normalize_image_data(raw)
                file_path = save_dir / f"HDO6104A_screen_{timestamp}.{ext}"

                with open(file_path, "wb") as f:
                    f.write(image_data)

                return str(file_path)

            finally:
                self.inst.timeout = old_timeout
                self.inst.read_termination = old_read_termination
                self.inst.chunk_size = old_chunk_size

    def read_waveform_values(self, channel: str, points: int):
        if self.inst is None:
            raise RuntimeError("示波器未连接")

        channel = channel.upper().strip()
        if channel not in ("C1", "C2", "C3", "C4"):
            raise ValueError("channel 必须是 C1、C2、C3 或 C4")

        points = int(points)
        if points <= 0:
            raise ValueError("波形点数必须大于 0")

        with self.lock:
            old_timeout = self.inst.timeout
            old_read_termination = self.inst.read_termination
            old_chunk_size = self.inst.chunk_size

            try:
                self.inst.timeout = 60000
                self.inst.read_termination = None
                self.inst.chunk_size = 20 * 1024 * 1024

                self.inst.write("COMM_FORMAT DEF9,WORD,BIN")
                self.inst.write("COMM_ORDER LO")
                self.inst.write(f"WFSU SP,0,NP,{points},FP,0,SN,0")
                time.sleep(0.1)

                self.inst.write(f"{channel}:WF?")
                raw = self.inst.read_raw()

                values = self._parse_waveform_y_values(raw)
                if len(values) >= points:
                    return values[:points]
                return values + [""] * (points - len(values))

            finally:
                self.inst.timeout = old_timeout
                self.inst.read_termination = old_read_termination
                self.inst.chunk_size = old_chunk_size


    def read_waveform_xy(self, channel: str, points: int = 20000):
        """
        读取指定通道波形，返回时间数组 times 和瞬时值数组 values。
        后续用于截取一个周期并重采样成固定点数。
        """
        if self.inst is None:
            raise RuntimeError("示波器未连接")

        channel = channel.upper().strip()
        if channel not in ("C1", "C2", "C3", "C4"):
            raise ValueError("channel 必须是 C1、C2、C3 或 C4")

        points = int(points)
        if points <= 0:
            raise ValueError("波形点数必须大于 0")

        with self.lock:
            old_timeout = self.inst.timeout
            old_read_termination = self.inst.read_termination
            old_chunk_size = self.inst.chunk_size

            try:
                self.inst.timeout = 60000
                self.inst.read_termination = None
                self.inst.chunk_size = 20 * 1024 * 1024

                self.inst.write("COMM_FORMAT DEF9,WORD,BIN")
                self.inst.write("COMM_ORDER LO")
                self.inst.write(f"WFSU SP,0,NP,{points},FP,0,SN,0")
                time.sleep(0.1)

                self.inst.write(f"{channel}:WF?")
                raw = self.inst.read_raw()

                return self._parse_waveform_xy(raw)

            finally:
                self.inst.timeout = old_timeout
                self.inst.read_termination = old_read_termination
                self.inst.chunk_size = old_chunk_size

    def _parse_waveform_xy(self, raw: bytes):
        """
        解析 LeCroy WAVEDESC，返回：
        times: 时间数组，单位 s
        values: 通道瞬时值数组
        """
        desc_pos = raw.find(b"WAVEDESC")
        if desc_pos < 0:
            raise RuntimeError("没有在返回数据中找到 WAVEDESC")

        endian = "<"

        def i16(offset):
            return struct.unpack_from(endian + "h", raw, desc_pos + offset)[0]

        def i32(offset):
            return struct.unpack_from(endian + "i", raw, desc_pos + offset)[0]

        def f32(offset):
            return struct.unpack_from(endian + "f", raw, desc_pos + offset)[0]

        def f64(offset):
            return struct.unpack_from(endian + "d", raw, desc_pos + offset)[0]

        comm_type = i16(32)

        wave_descriptor = i32(36)
        user_text = i32(40)
        res_desc1 = i32(44)
        trigtime_array = i32(48)
        ristime_array = i32(52)
        res_array1 = i32(56)
        wave_array_1 = i32(60)

        wave_array_count = i32(116)
        first_valid = i32(124)
        last_valid = i32(128)

        vertical_gain = f32(156)
        vertical_offset = f32(160)

        # LeCroy WAVEDESC 常用偏移
        horiz_interval = f32(176)
        horiz_offset = f64(180)

        data_start = (
            desc_pos
            + wave_descriptor
            + user_text
            + res_desc1
            + trigtime_array
            + ristime_array
            + res_array1
        )
        data_end = data_start + wave_array_1

        if data_end > len(raw):
            raise RuntimeError("波形数据长度异常，读取的数据不完整")

        data_bytes = raw[data_start:data_end]

        if comm_type == 0:
            raw_values = list(struct.unpack_from(f"{len(data_bytes)}b", data_bytes, 0))
        else:
            n = len(data_bytes) // 2
            raw_values = list(struct.unpack_from(endian + f"{n}h", data_bytes, 0))

        if wave_array_count > 0 and wave_array_count <= len(raw_values):
            raw_values = raw_values[:wave_array_count]

        valid_start = 0
        if 0 <= first_valid < last_valid < len(raw_values):
            valid_start = first_valid
            raw_values = raw_values[first_valid:last_valid + 1]

        values = [vertical_gain * value - vertical_offset for value in raw_values]
        times = [horiz_offset + (valid_start + i) * horiz_interval for i in range(len(values))]

        return times, values

    def read_channel_frequency(self, channel: str):
        """
        读取指定通道频率。
        如果该通道没接信号或不是稳定周期波形，示波器可能返回 FREQ,UNDEF。
        """
        channel = channel.upper().strip()
        resp = self.query(f"{channel}:PAVA? FREQ")
        freq = extract_float(resp)
        if freq <= 0:
            raise RuntimeError(f"{channel} 频率无效：{resp}")
        return freq

    def interpolate_waveform(self, times, values, target_times):
        """
        对波形做线性插值，把一个周期重采样成固定点数。
        """
        import bisect

        if len(times) < 2 or len(values) < 2:
            raise RuntimeError("波形点数太少，无法插值")

        result = []

        for t in target_times:
            if t <= times[0]:
                result.append(values[0])
                continue

            if t >= times[-1]:
                result.append(values[-1])
                continue

            idx = bisect.bisect_left(times, t)

            t0 = times[idx - 1]
            t1 = times[idx]
            y0 = values[idx - 1]
            y1 = values[idx]

            if t1 == t0:
                result.append(y0)
            else:
                k = (t - t0) / (t1 - t0)
                result.append(y0 + k * (y1 - y0))

        return result

    def read_one_period_waveform(
        self,
        channel: str,
        output_points: int = 1024,
        source_points: int = 20000,
        frequency: float = None
    ):
        """
        读取指定通道一个周期内的瞬时值，并重采样为 output_points 个点。

        如果 frequency=None，则从本通道读取频率。
        如果传入 frequency，则使用外部给定频率。
        这样 CH2 可以使用 CH1 的频率，避免 C2 没接时 FREQ 返回 UNDEF。
        """
        if frequency is None:
            frequency = self.read_channel_frequency(channel)

        if frequency <= 0:
            raise RuntimeError(f"频率无效：{frequency}")

        period = 1.0 / frequency

        times, values = self.read_waveform_xy(channel, points=source_points)

        total_time = times[-1] - times[0]
        if total_time < period:
            raise RuntimeError(
                f"{channel} 当前采集窗口不足一个周期。"
                f"当前窗口约 {total_time:.6g}s，一个周期约 {period:.6g}s。"
                f"请把示波器 Time/Div 调大一点，保证采集窗口内至少有一个完整周期。"
            )

        start_time = times[0] + (total_time - period) / 2.0

        if output_points <= 1:
            output_points = 1024

        step = period / (output_points - 1)
        target_times = [start_time + i * step for i in range(output_points)]

        one_period_values = self.interpolate_waveform(times, values, target_times)

        return frequency, period, one_period_values

    def _parse_waveform_y_values(self, raw: bytes):
        desc_pos = raw.find(b"WAVEDESC")
        if desc_pos < 0:
            raise RuntimeError("没有在返回数据中找到 WAVEDESC")

        endian = "<"

        def i16(offset):
            return struct.unpack_from(endian + "h", raw, desc_pos + offset)[0]

        def i32(offset):
            return struct.unpack_from(endian + "i", raw, desc_pos + offset)[0]

        def f32(offset):
            return struct.unpack_from(endian + "f", raw, desc_pos + offset)[0]

        comm_type = i16(32)
        wave_descriptor = i32(36)
        user_text = i32(40)
        res_desc1 = i32(44)
        trigtime_array = i32(48)
        ristime_array = i32(52)
        res_array1 = i32(56)
        wave_array_1 = i32(60)
        wave_array_count = i32(116)
        first_valid = i32(124)
        last_valid = i32(128)
        vertical_gain = f32(156)
        vertical_offset = f32(160)

        data_start = (
            desc_pos
            + wave_descriptor
            + user_text
            + res_desc1
            + trigtime_array
            + ristime_array
            + res_array1
        )
        data_end = data_start + wave_array_1

        if data_end > len(raw):
            raise RuntimeError("波形数据长度异常，读取的数据不完整")

        data_bytes = raw[data_start:data_end]

        if comm_type == 0:
            raw_values = list(struct.unpack_from(f"{len(data_bytes)}b", data_bytes, 0))
        else:
            n = len(data_bytes) // 2
            raw_values = list(struct.unpack_from(endian + f"{n}h", data_bytes, 0))

        if wave_array_count > 0 and wave_array_count <= len(raw_values):
            raw_values = raw_values[:wave_array_count]

        if 0 <= first_valid < last_valid < len(raw_values):
            raw_values = raw_values[first_valid:last_valid + 1]

        return [vertical_gain * value - vertical_offset for value in raw_values]

    def read_channel_mean_value(self, channel: str):
        try:
            resp = self.query(f"{channel}:PAVA? MEAN")
            parts = [p.strip() for p in resp.split(",")]
            if len(parts) >= 2:
                return clean_number_text(parts[1])
            return clean_number_text(resp)
        except Exception:
            return ""

    def read_custom_measure_last(self, p_number: int):
        try:
            resp = self.query(f"PAST? CUST,P{int(p_number)}")
            return parse_past_last_value(resp)
        except Exception:
            return ""

    def read_summary_measurements(self):
        temperature = self.read_custom_measure_last(1)
        frequency = self.read_custom_measure_last(2)
        dc_bias = self.read_custom_measure_last(3)
        power_loss = self.read_custom_measure_last(4)
        return temperature, frequency, dc_bias, power_loss


    def set_channel_vdiv(self, channel: str, vdiv):
        """
        设置通道垂直档位 V/Div。
        手动输入时先转成数字，再发送给示波器，避免直接发送字符串导致部分格式不识别。
        """
        channel = channel.upper().strip()
        if channel not in ("C1", "C2", "C3", "C4"):
            raise ValueError("channel 必须是 C1、C2、C3 或 C4")

        value = extract_float(str(vdiv))
        if value <= 0:
            raise ValueError("V/Div 必须大于 0")

        self.write(f"{channel}:VDIV {fmt(value)}")
        time.sleep(0.1)
        return self.query(f"{channel}:VDIV?")

    def set_channel_attenuation(self, channel: str, attenuation):
        """
        设置通道探头比例 / 衰减倍率。
        例如：1、10、100。
        LeCroy 常用命令：C1:ATTN 10 / C1:ATTN?
        """
        channel = channel.upper().strip()
        if channel not in ("C1", "C2", "C3", "C4"):
            raise ValueError("channel 必须是 C1、C2、C3 或 C4")

        value = str(attenuation).strip()
        if not value:
            raise ValueError("探头比例不能为空")

        # 先转成数字，避免输入无效字符
        numeric_value = extract_float(value)
        if numeric_value <= 0:
            raise ValueError("探头比例必须大于 0")

        self.write(f"{channel}:ATTN {fmt(numeric_value)}")

        try:
            return self.query(f"{channel}:ATTN?")
        except Exception:
            # 有些固件可能设置成功但查询失败，返回设置值用于界面显示
            return fmt(numeric_value)

    def get_channel_attenuation(self, channel: str):
        """
        读取通道探头比例 / 衰减倍率。
        """
        channel = channel.upper().strip()
        if channel not in ("C1", "C2", "C3", "C4"):
            raise ValueError("channel 必须是 C1、C2、C3 或 C4")

        return self.query(f"{channel}:ATTN?")


# ============================================================
# Page 3 helper: automatic scan setting dialog
# ============================================================

class ScopeScanSettingsDialog(QDialog):
    """示波器自动测量扫描设置窗口。"""

    ITEM_LABELS = {
        "frequency": "频率",
        "voltage": "电压",
        "duty_p": "duty_P",
        "duty_n": "duty_N",
        "hdc": "直流偏置",
    }

    ITEM_UNITS = {
        "frequency": "kHz",
        "voltage": "V",
        "duty_p": "",
        "duty_n": "",
        "hdc": "A/m",
    }

    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.setWindowTitle("扫描设置")
        self.setMinimumWidth(520)
        self.config = dict(config or {})

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.waveform_combo = QComboBox()
        self.waveform_combo.addItems(["梯形波", "三角波"])
        self.waveform_combo.setCurrentText(self.config.get("waveform_label", "梯形波"))

        self.scan_item_combo = QComboBox()
        self.refresh_scan_item_options()
        self.scan_item_combo.setCurrentText(self.ITEM_LABELS.get(self.config.get("scan_item", "frequency"), "频率"))

        form.addRow("波形类型：", self.waveform_combo)
        form.addRow("扫描项：", self.scan_item_combo)
        layout.addLayout(form)

        range_group = QGroupBox("扫描范围")
        range_layout = QGridLayout(range_group)
        self.scan_start_edit = QLineEdit(str(self.config.get("scan_start", 50)))
        self.scan_stop_edit = QLineEdit(str(self.config.get("scan_stop", 500)))
        self.scan_step_edit = QLineEdit(str(self.config.get("scan_step", 50)))
        self.scan_unit_label = QLabel("")

        range_layout.addWidget(QLabel("起始："), 0, 0)
        range_layout.addWidget(self.scan_start_edit, 0, 1)
        range_layout.addWidget(QLabel("终止："), 0, 2)
        range_layout.addWidget(self.scan_stop_edit, 0, 3)
        range_layout.addWidget(QLabel("步长："), 1, 0)
        range_layout.addWidget(self.scan_step_edit, 1, 1)
        range_layout.addWidget(QLabel("单位："), 1, 2)
        range_layout.addWidget(self.scan_unit_label, 1, 3)
        layout.addWidget(range_group)

        fixed_group = QGroupBox("其他参数固定值")
        fixed_layout = QGridLayout(fixed_group)

        self.fixed_freq_khz_edit = QLineEdit(str(self.config.get("fixed_freq_khz", 50)))
        self.fixed_voltage_edit = QLineEdit(str(self.config.get("fixed_voltage", 10)))
        self.fixed_dp_edit = QLineEdit(str(self.config.get("fixed_dp", 0.2)))
        self.fixed_dn_edit = QLineEdit(str(self.config.get("fixed_dn", 0.2)))
        self.fixed_hdc_edit = QLineEdit(str(self.config.get("fixed_hdc", 0)))
        self.deadtime_ns_edit = QLineEdit(str(self.config.get("deadtime_ns", 50)))

        fixed_layout.addWidget(QLabel("频率 kHz："), 0, 0)
        fixed_layout.addWidget(self.fixed_freq_khz_edit, 0, 1)
        fixed_layout.addWidget(QLabel("电压 V："), 0, 2)
        fixed_layout.addWidget(self.fixed_voltage_edit, 0, 3)

        fixed_layout.addWidget(QLabel("duty_P："), 1, 0)
        fixed_layout.addWidget(self.fixed_dp_edit, 1, 1)
        fixed_layout.addWidget(QLabel("duty_N："), 1, 2)
        fixed_layout.addWidget(self.fixed_dn_edit, 1, 3)

        fixed_layout.addWidget(QLabel("直流偏置 Hdc A/m："), 2, 0)
        fixed_layout.addWidget(self.fixed_hdc_edit, 2, 1)
        fixed_layout.addWidget(QLabel("死区 ns："), 2, 2)
        fixed_layout.addWidget(self.deadtime_ns_edit, 2, 3)

        layout.addWidget(fixed_group)

        wait_group = QGroupBox("等待时间")
        wait_layout = QGridLayout(wait_group)
        self.first_wait_edit = QLineEdit(str(self.config.get("first_group_wait_s", 1.0)))
        self.group_wait_edit = QLineEdit(str(self.config.get("group_wait_s", 2.0)))
        wait_layout.addWidget(QLabel("第一组等待时间 s："), 0, 0)
        wait_layout.addWidget(self.first_wait_edit, 0, 1)
        wait_layout.addWidget(QLabel("每组等待时间 s："), 0, 2)
        wait_layout.addWidget(self.group_wait_edit, 0, 3)
        layout.addWidget(wait_group)

        self.note_label = QLabel(
            "说明：三角波只扫描 duty_P，duty_N 自动按 1-duty_P 处理；"
            "只有扫描项为直流偏置时才使用第二页电流源，其他扫描项 Hdc 默认为 0。"
        )
        self.note_label.setWordWrap(True)
        layout.addWidget(self.note_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.waveform_combo.currentTextChanged.connect(self.on_waveform_changed)
        self.scan_item_combo.currentTextChanged.connect(self.on_scan_item_changed)
        self.on_waveform_changed(self.waveform_combo.currentText())
        self.on_scan_item_changed(self.scan_item_combo.currentText())

    def refresh_scan_item_options(self):
        current = self.scan_item_combo.currentText() if hasattr(self, "scan_item_combo") else ""
        waveform = self.waveform_combo.currentText() if hasattr(self, "waveform_combo") else self.config.get("waveform_label", "梯形波")
        items = ["频率", "电压", "duty_P", "直流偏置"]
        if waveform != "三角波":
            items.insert(3, "duty_N")
        self.scan_item_combo.blockSignals(True)
        self.scan_item_combo.clear()
        self.scan_item_combo.addItems(items)
        if current in items:
            self.scan_item_combo.setCurrentText(current)
        elif self.ITEM_LABELS.get(self.config.get("scan_item", "frequency"), "频率") in items:
            self.scan_item_combo.setCurrentText(self.ITEM_LABELS.get(self.config.get("scan_item", "frequency"), "频率"))
        else:
            self.scan_item_combo.setCurrentText("duty_P")
        self.scan_item_combo.blockSignals(False)

    def on_waveform_changed(self, _text):
        self.refresh_scan_item_options()
        tri = self.waveform_combo.currentText() == "三角波"
        if tri:
            self.note_label.setText("说明：三角波模式下不额外扫描 duty_N，程序自动令 duty_N = 1-duty_P。")
        else:
            self.note_label.setText("说明：梯形波需要满足 duty_P + duty_N ≤ 1。")
        self.on_scan_item_changed(self.scan_item_combo.currentText())

    def update_fixed_field_states(self):
        """扫描项对应的固定参数在“其他参数固定值”中置灰，避免重复输入。"""
        scan_key = self.key_from_label(self.scan_item_combo.currentText())
        tri = self.waveform_combo.currentText() == "三角波"
        field_map = {
            "frequency": self.fixed_freq_khz_edit,
            "voltage": self.fixed_voltage_edit,
            "duty_p": self.fixed_dp_edit,
            "duty_n": self.fixed_dn_edit,
            "hdc": self.fixed_hdc_edit,
        }
        for key, edit in field_map.items():
            enabled = (key != scan_key)
            if key == "duty_n" and tri:
                enabled = False
            edit.setEnabled(enabled)
            if key == scan_key:
                edit.setToolTip("该参数为当前扫描项，由扫描范围/步长决定")
            elif key == "duty_n" and tri:
                edit.setToolTip("三角波模式下 duty_N 自动按 1-duty_P 处理")
            else:
                edit.setToolTip("")

    def on_scan_item_changed(self, label):
        key = self.key_from_label(label)
        unit = self.ITEM_UNITS.get(key, "")
        self.scan_unit_label.setText(unit if unit else "无量纲")
        defaults = {
            "frequency": (50, 500, 50),
            "voltage": (10, 50, 10),
            "duty_p": (0.1, 0.5, 0.1),
            "duty_n": (0.1, 0.5, 0.1),
            "hdc": (0, 1000, 100),
        }
        # 只在用户刚切换扫描项时给出合理默认值；不强制覆盖已有输入。
        if not self.scan_start_edit.text().strip() or not self.scan_stop_edit.text().strip() or not self.scan_step_edit.text().strip():
            a, b, c = defaults.get(key, (0, 1, 0.1))
            self.scan_start_edit.setText(str(a))
            self.scan_stop_edit.setText(str(b))
            self.scan_step_edit.setText(str(c))
        self.update_fixed_field_states()

    def key_from_label(self, label):
        for key, text in self.ITEM_LABELS.items():
            if text == label:
                return key
        return "frequency"

    def read_float(self, edit, name):
        try:
            return float(edit.text().strip())
        except Exception:
            raise ValueError(f"{name} 必须是数字")

    def accept(self):
        try:
            waveform_label = self.waveform_combo.currentText()
            scan_item = self.key_from_label(self.scan_item_combo.currentText())
            if waveform_label == "三角波" and scan_item == "duty_n":
                raise ValueError("三角波只需要扫描 duty_P，不需要额外扫描 duty_N")

            scan_start = self.read_float(self.scan_start_edit, "扫描起始值")
            scan_stop = self.read_float(self.scan_stop_edit, "扫描终止值")
            scan_step = abs(self.read_float(self.scan_step_edit, "扫描步长"))
            if scan_step <= 0:
                raise ValueError("扫描步长必须大于 0")

            fixed_freq_khz = self.read_float(self.fixed_freq_khz_edit, "固定频率")
            fixed_voltage = self.read_float(self.fixed_voltage_edit, "固定电压")
            fixed_dp = self.read_float(self.fixed_dp_edit, "固定 duty_P")
            fixed_dn = self.read_float(self.fixed_dn_edit, "固定 duty_N")
            fixed_hdc = self.read_float(self.fixed_hdc_edit, "固定直流偏置 Hdc")
            # 当扫描项不是“直流偏置”时，固定直流偏置强制默认为 0，
            # 扫描过程中不会开启第二页电流源。
            if scan_item != "hdc":
                fixed_hdc = 0.0
                self.fixed_hdc_edit.setText("0")

            deadtime_ns = self.read_float(self.deadtime_ns_edit, "死区时间")
            first_group_wait_s = self.read_float(self.first_wait_edit, "第一组等待时间")
            group_wait_s = self.read_float(self.group_wait_edit, "每组等待时间")

            if fixed_freq_khz <= 0:
                raise ValueError("频率必须大于 0")
            if fixed_voltage < 0:
                raise ValueError("电压不能小于 0")
            if fixed_hdc < 0:
                raise ValueError("直流偏置 Hdc 不能小于 0")
            if deadtime_ns < 0:
                raise ValueError("死区时间不能小于 0")
            if first_group_wait_s < 0 or group_wait_s < 0:
                raise ValueError("等待时间不能小于 0")

            # 当前点合法性在实际扫描列表中还会逐点校验，这里先做固定值基本检查。
            if fixed_dp <= 0 or fixed_dp >= 1:
                raise ValueError("duty_P 应在 0~1 之间")
            if waveform_label != "三角波":
                if fixed_dn <= 0 or fixed_dn >= 1:
                    raise ValueError("duty_N 应在 0~1 之间")
                if fixed_dp + fixed_dn > 1:
                    raise ValueError("固定 duty_P + duty_N 不能大于 1")

            new_config = {
                "waveform_label": waveform_label,
                "waveform": "triangle" if waveform_label == "三角波" else "trapezoid",
                "scan_item": scan_item,
                "scan_start": scan_start,
                "scan_stop": scan_stop,
                "scan_step": scan_step,
                "fixed_freq_khz": fixed_freq_khz,
                "fixed_voltage": fixed_voltage,
                "fixed_dp": fixed_dp,
                "fixed_dn": fixed_dn,
                "fixed_hdc": fixed_hdc,
                "deadtime_ns": deadtime_ns,
                "first_group_wait_s": first_group_wait_s,
                "group_wait_s": group_wait_s,
            }

            checker = getattr(self.parent(), "check_scope_scan_device_connections", None)
            if callable(checker):
                ok, error_text, warning_text = checker(new_config)
                if not ok:
                    QMessageBox.critical(self, "连接错误", error_text)
                    return
                if warning_text:
                    ret = QMessageBox.question(
                        self,
                        "连接提示",
                        warning_text + "\n\n这些未连接项可忽略，仍然保存扫描设置并继续吗？",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes
                    )
                    if ret != QMessageBox.Yes:
                        return

            self.config = new_config
            super().accept()
        except Exception as e:
            QMessageBox.warning(self, "扫描设置错误", str(e))

    def get_config(self):
        return dict(self.config)

# ============================================================
# Page 3: Oscilloscope UI
# ============================================================

class ScopePage(QWidget):
    message_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    field_signal = pyqtSignal(str, str)
    auto_finished_signal = pyqtSignal()
    auto_status_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    DEFAULT_ADDR = "USB0::0x05FF::0x1023::3566N52467::INSTR"
    SCREEN_SAVE_DIR = Path(r"D:\桌面")
    REALTIME_SAVE_DIR = Path(r"D:\桌面\示波器实时数据")

    VOLTAGE_CHANNEL = "C1"
    CURRENT_CHANNEL = "C2"
    DEFAULT_WAVE_POINTS = 1024

    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.scope = LecroyScope()
        self.is_logging = False
        self.logging_thread = None
        self.auto_sweep_running = False

        self.message_signal.connect(self.set_message)
        self.status_signal.connect(self.set_status)
        self.field_signal.connect(self.set_field_value)
        self.auto_finished_signal.connect(self.on_auto_sweep_finished)
        self.error_signal.connect(self.show_error_box)

        self.scope_scan_config = self.default_scope_scan_config()
        self.fields = {}
        self.init_ui()
        self.auto_status_signal.connect(self.auto_status_label.setText)
        self.refresh_resources()

    def init_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(10, 10, 10, 10)
        main.setSpacing(8)

        # VISA connection
        conn = QGroupBox("示波器连接设置")
        gl = QGridLayout(conn)

        self.resource_combo = QComboBox()
        self.resource_combo.setEditable(True)
        self.resource_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.resource_combo.setEditText(self.DEFAULT_ADDR)

        self.refresh_btn = QPushButton("刷新资源")
        self.refresh_btn.clicked.connect(self.refresh_resources)
        self.connect_btn = QPushButton("连接示波器")
        self.connect_btn.clicked.connect(self.connect_scope)
        self.disconnect_btn = QPushButton("断开连接")
        self.disconnect_btn.clicked.connect(self.disconnect_scope)

        self.scope_status = QLabel("未连接")
        self.scope_status.setStyleSheet("color: blue;")

        gl.addWidget(QLabel("VISA 地址："), 0, 0)
        gl.addWidget(self.resource_combo, 0, 1)
        gl.addWidget(self.refresh_btn, 0, 2)
        gl.addWidget(self.connect_btn, 0, 3)
        gl.addWidget(self.disconnect_btn, 0, 4)
        gl.addWidget(QLabel("连接状态："), 1, 0)
        gl.addWidget(self.scope_status, 1, 1, 1, 4)
        gl.setColumnStretch(1, 1)
        main.addWidget(conn)

        # Run and save
        run = QGroupBox("运行控制 / 屏幕保存")
        rl = QGridLayout(run)

        self.run_btn = QPushButton("Run")
        self.run_btn.clicked.connect(self.run_scope)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_scope)
        self.auto_btn = QPushButton("Auto Setup")
        self.auto_btn.clicked.connect(self.auto_setup)
        self.read_btn = QPushButton("读取当前状态")
        self.read_btn.clicked.connect(self.read_status)
        self.screen_btn = QPushButton("保存屏幕图")
        self.screen_btn.clicked.connect(self.save_screen_image)

        rl.addWidget(self.run_btn, 0, 0)
        rl.addWidget(self.stop_btn, 0, 1)
        rl.addWidget(self.auto_btn, 0, 2)
        rl.addWidget(self.read_btn, 0, 3)
        rl.addWidget(self.screen_btn, 0, 4)
        rl.addWidget(QLabel(r"屏幕图保存路径：D:\桌面"), 1, 0, 1, 5)
        main.addWidget(run)

        # CSV one-shot saving
        csv_box = QGroupBox("保存 CSV")
        cl = QGridLayout(csv_box)

        self.log_dir_edit = QLineEdit(str(self.REALTIME_SAVE_DIR))
        self.log_points_edit = QLineEdit(str(self.DEFAULT_WAVE_POINTS))

        self.save_ch1_check = QCheckBox("保存 CH1 电压")
        self.save_ch1_check.setChecked(True)
        self.save_ch2_check = QCheckBox("保存 CH2 电流")
        self.save_ch2_check.setChecked(False)

        self.once_log_btn = QPushButton("保存一次")
        self.once_log_btn.clicked.connect(self.save_realtime_record_once)

        cl.addWidget(QLabel("保存文件夹："), 0, 0)
        cl.addWidget(self.log_dir_edit, 0, 1, 1, 6)

        cl.addWidget(QLabel("点数："), 1, 0)
        cl.addWidget(self.log_points_edit, 1, 1)
        cl.addWidget(self.save_ch1_check, 1, 2)
        cl.addWidget(self.save_ch2_check, 1, 3)
        cl.addWidget(self.once_log_btn, 1, 4)

        cl.addWidget(QLabel("说明：CH2 没接时请不要勾选 CH2。勾选 CH1+CH2 时，CH2 使用 CH1 周期基准。"), 2, 0, 1, 7)

        cl.setColumnStretch(1, 1)
        cl.setColumnStretch(6, 1)
        main.addWidget(csv_box)

        # Auto scan and save
        auto_box = QGroupBox("自动扫描测量 / 自动保存")
        al = QGridLayout(auto_box)

        self.auto_root_dir_edit = QLineEdit(r"D:\桌面")
        self.auto_scan_settings_btn = QPushButton("扫描设置")
        self.auto_scan_settings_btn.clicked.connect(self.open_scope_scan_settings)
        self.auto_scan_summary_label = QLabel("")
        self.auto_scan_summary_label.setWordWrap(True)

        self.auto_save_ch1_check = QCheckBox("保存 CH1 电压")
        self.auto_save_ch1_check.setChecked(True)
        self.auto_save_ch2_check = QCheckBox("保存 CH2 电流")
        self.auto_save_ch2_check.setChecked(True)

        self.auto_start_btn = QPushButton("开始自动测量")
        self.auto_start_btn.clicked.connect(self.start_auto_sweep_measure)
        self.auto_stop_btn = QPushButton("停止自动测量")
        self.auto_stop_btn.clicked.connect(self.stop_auto_sweep_measure)
        self.auto_stop_btn.setEnabled(False)

        self.auto_status_label = QLabel("未开始")
        self.auto_status_label.setFrameStyle(QLabel.Panel | QLabel.Sunken)

        al.addWidget(QLabel("根目录："), 0, 0)
        al.addWidget(self.auto_root_dir_edit, 0, 1, 1, 7)

        al.addWidget(self.auto_scan_settings_btn, 1, 0)
        al.addWidget(self.auto_scan_summary_label, 1, 1, 1, 7)

        al.addWidget(self.auto_save_ch1_check, 2, 0, 1, 2)
        al.addWidget(self.auto_save_ch2_check, 2, 2, 1, 2)
        al.addWidget(self.auto_start_btn, 2, 4)
        al.addWidget(self.auto_stop_btn, 2, 5)
        al.addWidget(self.auto_status_label, 3, 0, 1, 8)

        al.addWidget(
            QLabel("流程：按“扫描设置”配置波形、扫描项、范围/步长、固定参数和等待时间 → 自动逐点设置 TNPC/电压源/电流源 → 示波器 Auto Setup → 等待 → 保存屏幕图和 CSV。"),
            4, 0, 1, 8
        )

        al.setColumnStretch(1, 1)
        al.setColumnStretch(7, 1)
        main.addWidget(auto_box)
        self.update_scope_scan_summary()

        # Horizontal
        horizontal = QGroupBox("水平控制")
        hl = QGridLayout(horizontal)

        self.add_field(hl, "tdiv", "Time/Div：", "1E-3", 0, 0)
        hl.addWidget(QPushButton("设置"), 0, 2)
        hl.itemAtPosition(0, 2).widget().clicked.connect(self.set_tdiv)

        self.add_field(hl, "tdiv_step", "倍率：", "2", 0, 3)
        hl.addWidget(QPushButton("变快 / ÷倍率"), 0, 5)
        hl.itemAtPosition(0, 5).widget().clicked.connect(self.tdiv_faster)
        hl.addWidget(QPushButton("变慢 / ×倍率"), 0, 6)
        hl.itemAtPosition(0, 6).widget().clicked.connect(self.tdiv_slower)

        self.add_field(hl, "trdl", "Delay：", "0", 1, 0)
        hl.addWidget(QPushButton("设置"), 1, 2)
        hl.itemAtPosition(1, 2).widget().clicked.connect(self.set_trdl)

        self.add_field(hl, "trdl_step", "步进：", "1E-4", 1, 3)
        hl.addWidget(QPushButton("左移 / 减小"), 1, 5)
        hl.itemAtPosition(1, 5).widget().clicked.connect(lambda: self.move_trdl(-1))
        hl.addWidget(QPushButton("右移 / 增大"), 1, 6)
        hl.itemAtPosition(1, 6).widget().clicked.connect(lambda: self.move_trdl(1))
        hl.addWidget(QPushButton("Delay 归零"), 1, 7)
        hl.itemAtPosition(1, 7).widget().clicked.connect(self.zero_trdl)
        main.addWidget(horizontal)

        # CH controls
        ch1 = QGroupBox("CH1 控制")
        ch1l = QGridLayout(ch1)
        self.build_ch1_controls(ch1l)
        main.addWidget(ch1)

        ch2 = QGroupBox("CH2 控制")
        ch2l = QGridLayout(ch2)
        self.build_ch2_controls(ch2l)
        main.addWidget(ch2)

        self.message_label = QLabel("就绪")
        self.message_label.setFrameStyle(QLabel.Panel | QLabel.Sunken)
        self.message_label.setMinimumHeight(26)
        main.addWidget(self.message_label)

        main.addStretch(1)

    def default_scope_scan_config(self):
        return {
            "waveform_label": "梯形波",
            "waveform": "trapezoid",
            "scan_item": "frequency",
            "scan_start": 50.0,
            "scan_stop": 500.0,
            "scan_step": 50.0,
            "fixed_freq_khz": 50.0,
            "fixed_voltage": 10.0,
            "fixed_dp": 0.2,
            "fixed_dn": 0.2,
            "fixed_hdc": 0.0,
            "deadtime_ns": 50.0,
            "first_group_wait_s": 1.0,
            "group_wait_s": 2.0,
        }

    def get_scan_device_states(self):
        scope_connected = False
        try:
            scope_connected = bool(self.scope and self.scope.is_connected())
        except Exception:
            scope_connected = False

        dsp_connected = False
        try:
            ser = getattr(getattr(self.main_window, "tnpc_page", None), "ser", None)
            dsp_connected = bool(ser is not None and getattr(ser, "is_open", False))
        except Exception:
            dsp_connected = False

        voltage_connected = False
        try:
            panel = getattr(getattr(self.main_window, "tnpc_page", None), "power_panel", None)
            voltage_connected = bool(panel is not None and hasattr(panel, "both_connected") and panel.both_connected())
        except Exception:
            voltage_connected = False

        current_connected = False
        current_core_ok = False
        try:
            page = getattr(self.main_window, "current_source_page", None)
            current_connected = bool(page is not None and getattr(page, "inst", None) is not None)
            if current_connected and hasattr(page, "refresh_core_params"):
                page.refresh_core_params(show_message=False)
            if page is not None and hasattr(page, "has_valid_core_params"):
                current_core_ok = bool(page.has_valid_core_params(show_message=False))
        except Exception:
            current_connected = False
            current_core_ok = False

        return {
            "scope": scope_connected,
            "dsp": dsp_connected,
            "voltage": voltage_connected,
            "current": current_connected,
            "current_core": current_core_ok,
        }

    def required_device_for_scan_item(self, scan_item):
        if scan_item in ("frequency", "duty_p", "duty_n"):
            return "dsp"
        if scan_item == "voltage":
            return "voltage"
        if scan_item == "hdc":
            return "current"
        return None

    def check_scope_scan_device_connections(self, cfg):
        """扫描设置确认时检查设备连接。扫描项对应设备未连接时报错，其他未连接设备只警告。"""
        scan_item = cfg.get("scan_item", "frequency")
        required = self.required_device_for_scan_item(scan_item)
        states = self.get_scan_device_states()
        names = {
            "scope": "示波器",
            "dsp": "TNPC/DSP 串口",
            "voltage": "两台 Chroma 电压源",
            "current": "GW INSTEK 电流源",
            "current_core": "第一页磁芯参数",
        }
        missing = []
        if not states["scope"]:
            missing.append("示波器")
        if not states["dsp"]:
            missing.append("TNPC/DSP 串口")
        if not states["voltage"]:
            missing.append("两台 Chroma 电压源")
        # 只有扫描项为“直流偏置”时，电流源和磁芯参数才是必要检查项。
        # 非直流偏置扫描中，直流偏置固定为 0，电流源不参与扫描。
        if scan_item == "hdc":
            if not states["current"]:
                missing.append("GW INSTEK 电流源")
            if states["current"] and not states["current_core"]:
                missing.append("第一页磁芯参数")

        if required == "current":
            if (not states["current"]) or (not states["current_core"]):
                return (
                    False,
                    "当前扫描项为“直流偏置”，必须先连接第二页电流源，并在第一页输入有效磁芯参数。\n\n"
                    "当前未连接/未就绪：" + ("、".join(missing) if missing else "无"),
                    ""
                )
        elif required and not states.get(required, False):
            item_label = ScopeScanSettingsDialog.ITEM_LABELS.get(scan_item, scan_item)
            return (
                False,
                f"当前扫描项为“{item_label}”，必须先连接 {names.get(required, required)}。\n\n"
                "当前未连接/未就绪：" + ("、".join(missing) if missing else "无"),
                ""
            )

        warnings = []
        if missing:
            warnings.append("当前未连接/未就绪：" + "、".join(missing))
        if scan_item != "voltage" and not states["voltage"]:
            warnings.append("未连接电压源时，非电压扫描会跳过固定电压设置，仅保存示波器结果。")
        # 非直流偏置扫描不需要电流源：直流偏置固定为 0，扫描过程中不打开电流源。
        if scan_item not in ("frequency", "duty_p", "duty_n") and not states["dsp"]:
            warnings.append("未连接 TNPC/DSP 时，非频率/duty 扫描会跳过 PWM 固定参数设置。")
        if not states["scope"]:
            warnings.append("未连接示波器时可以保存扫描设置，但开始自动测量前仍需连接示波器。")

        unique_warnings = []
        for w in warnings:
            if w and w not in unique_warnings:
                unique_warnings.append(w)
        return True, "", "\n".join(unique_warnings)

    def open_scope_scan_settings(self):
        dialog = ScopeScanSettingsDialog(self, self.scope_scan_config)
        if dialog.exec_() == QDialog.Accepted:
            self.scope_scan_config = dialog.get_config()
            self.update_scope_scan_summary()
            self.message_signal.emit("扫描设置已更新")

    def update_scope_scan_summary(self):
        if not hasattr(self, "auto_scan_summary_label"):
            return
        cfg = getattr(self, "scope_scan_config", self.default_scope_scan_config())
        label_map = ScopeScanSettingsDialog.ITEM_LABELS
        unit_map = ScopeScanSettingsDialog.ITEM_UNITS
        item = cfg.get("scan_item", "frequency")
        unit = unit_map.get(item, "")
        unit_text = f" {unit}" if unit else ""
        fixed_parts = []
        if item != "frequency":
            fixed_parts.append(f"频率={cfg.get('fixed_freq_khz')}kHz")
        if item != "voltage":
            fixed_parts.append(f"电压={cfg.get('fixed_voltage')}V")
        if item != "duty_p":
            fixed_parts.append(f"duty_P={cfg.get('fixed_dp')}")
        if cfg.get("waveform") != "triangle" and item != "duty_n":
            fixed_parts.append(f"duty_N={cfg.get('fixed_dn')}")
        if item != "hdc":
            fixed_parts.append(f"Hdc={cfg.get('fixed_hdc')}A/m")
        fixed_text = "，".join(fixed_parts) if fixed_parts else "无"
        text = (
            f"波形：{cfg.get('waveform_label', '梯形波')}；"
            f"扫描项：{label_map.get(item, item)}；"
            f"范围：{cfg.get('scan_start')} → {cfg.get('scan_stop')}，步长 {cfg.get('scan_step')}{unit_text}；"
            f"固定参数：{fixed_text}；"
            f"等待：第一组 {cfg.get('first_group_wait_s')}s，每组 {cfg.get('group_wait_s')}s"
        )
        self.auto_scan_summary_label.setText(text)

    def add_field(self, layout, key, label, default, row, col):
        layout.addWidget(QLabel(label), row, col)
        edit = QLineEdit(default)
        edit.setFixedWidth(110)
        layout.addWidget(edit, row, col + 1)
        self.fields[key] = edit
        return edit

    def build_ch1_controls(self, layout):
        self.add_field(layout, "ch1_deskew", "Deskew：", "0", 0, 0)
        btn = QPushButton("设置")
        btn.clicked.connect(self.set_ch1_deskew)
        layout.addWidget(btn, 0, 2)
        self.add_field(layout, "ch1_deskew_step", "步进：", "1E-9", 0, 3)
        btn = QPushButton("延后 / 增大")
        btn.clicked.connect(lambda: self.move_ch1_deskew(1))
        layout.addWidget(btn, 0, 5)
        btn = QPushButton("提前 / 减小")
        btn.clicked.connect(lambda: self.move_ch1_deskew(-1))
        layout.addWidget(btn, 0, 6)
        btn = QPushButton("归零")
        btn.clicked.connect(self.zero_ch1_deskew)
        layout.addWidget(btn, 0, 7)

        self.add_field(layout, "ch1_ofst", "Offset：", "0", 1, 0)
        btn = QPushButton("设置")
        btn.clicked.connect(self.set_ch1_offset)
        layout.addWidget(btn, 1, 2)
        self.add_field(layout, "ch1_ofst_step", "步进：", "0.1", 1, 3)
        btn = QPushButton("上移 / 增大")
        btn.clicked.connect(lambda: self.move_ch1_offset(1))
        layout.addWidget(btn, 1, 5)
        btn = QPushButton("下移 / 减小")
        btn.clicked.connect(lambda: self.move_ch1_offset(-1))
        layout.addWidget(btn, 1, 6)
        btn = QPushButton("归零")
        btn.clicked.connect(self.zero_ch1_offset)
        layout.addWidget(btn, 1, 7)

        ch1_vdiv_edit = self.add_field(layout, "ch1_vdiv", "V/Div：", "0.5", 2, 0)
        ch1_vdiv_edit.returnPressed.connect(self.set_ch1_vdiv)
        btn = QPushButton("设置")
        btn.clicked.connect(self.set_ch1_vdiv)
        layout.addWidget(btn, 2, 2)
        self.add_field(layout, "ch1_vdiv_step", "倍率：", "2", 2, 3)
        btn = QPushButton("放大 / ÷倍率")
        btn.clicked.connect(self.ch1_vdiv_smaller)
        layout.addWidget(btn, 2, 5)
        btn = QPushButton("缩小 / ×倍率")
        btn.clicked.connect(self.ch1_vdiv_larger)
        layout.addWidget(btn, 2, 6)

        self.add_field(layout, "ch1_attn", "探头比例：", "1", 3, 0)
        btn = QPushButton("设置")
        btn.clicked.connect(self.set_ch1_attenuation)
        layout.addWidget(btn, 3, 2)
        btn = QPushButton("1X")
        btn.clicked.connect(lambda: self.quick_set_attenuation("ch1_attn", "C1", 1))
        layout.addWidget(btn, 3, 3)
        btn = QPushButton("10X")
        btn.clicked.connect(lambda: self.quick_set_attenuation("ch1_attn", "C1", 10))
        layout.addWidget(btn, 3, 4)
        btn = QPushButton("100X")
        btn.clicked.connect(lambda: self.quick_set_attenuation("ch1_attn", "C1", 100))
        layout.addWidget(btn, 3, 5)

    def build_ch2_controls(self, layout):
        self.add_field(layout, "ch2_ofst", "Offset：", "0", 0, 0)
        btn = QPushButton("设置")
        btn.clicked.connect(self.set_ch2_offset)
        layout.addWidget(btn, 0, 2)
        self.add_field(layout, "ch2_ofst_step", "步进：", "0.1", 0, 3)
        btn = QPushButton("上移 / 增大")
        btn.clicked.connect(lambda: self.move_ch2_offset(1))
        layout.addWidget(btn, 0, 5)
        btn = QPushButton("下移 / 减小")
        btn.clicked.connect(lambda: self.move_ch2_offset(-1))
        layout.addWidget(btn, 0, 6)
        btn = QPushButton("归零")
        btn.clicked.connect(self.zero_ch2_offset)
        layout.addWidget(btn, 0, 7)

        ch2_vdiv_edit = self.add_field(layout, "ch2_vdiv", "V/Div：", "0.5", 1, 0)
        ch2_vdiv_edit.returnPressed.connect(self.set_ch2_vdiv)
        btn = QPushButton("设置")
        btn.clicked.connect(self.set_ch2_vdiv)
        layout.addWidget(btn, 1, 2)
        self.add_field(layout, "ch2_vdiv_step", "倍率：", "2", 1, 3)
        btn = QPushButton("放大 / ÷倍率")
        btn.clicked.connect(self.ch2_vdiv_smaller)
        layout.addWidget(btn, 1, 5)
        btn = QPushButton("缩小 / ×倍率")
        btn.clicked.connect(self.ch2_vdiv_larger)
        layout.addWidget(btn, 1, 6)

        self.add_field(layout, "ch2_attn", "探头比例：", "1", 2, 0)
        btn = QPushButton("设置")
        btn.clicked.connect(self.set_ch2_attenuation)
        layout.addWidget(btn, 2, 2)
        btn = QPushButton("1X")
        btn.clicked.connect(lambda: self.quick_set_attenuation("ch2_attn", "C2", 1))
        layout.addWidget(btn, 2, 3)
        btn = QPushButton("10X")
        btn.clicked.connect(lambda: self.quick_set_attenuation("ch2_attn", "C2", 10))
        layout.addWidget(btn, 2, 4)
        btn = QPushButton("100X")
        btn.clicked.connect(lambda: self.quick_set_attenuation("ch2_attn", "C2", 100))
        layout.addWidget(btn, 2, 5)

    def set_message(self, msg):
        self.message_label.setText(msg)

    def set_status(self, msg):
        self.scope_status.setText(msg)

    def set_field_value(self, key, value):
        if key in self.fields:
            self.fields[key].setText(value)

    def value(self, key):
        return self.fields[key].text().strip()

    def run_task(self, func):
        def wrapper():
            try:
                func()
            except Exception as e:
                err = str(e)
                self.message_signal.emit(f"错误：{err}")
                # GUI 操作必须回到主线程，绝不能在子线程里弹 QMessageBox，
                # 否则会触发 "Cannot set parent" 并导致窗口卡死无响应。
                self.error_signal.emit(err)

        threading.Thread(target=wrapper, daemon=True).start()

    def show_error_box(self, err: str):
        """在主线程显示错误弹窗（由 error_signal 触发）。"""
        QMessageBox.critical(self, "错误", err)

    def require_connected(self):
        if not self.scope.is_connected():
            raise RuntimeError("请先连接示波器")

    def refresh_resources(self):
        try:
            resources = self.scope.list_resources()
            self.resource_combo.clear()
            for r in resources:
                self.resource_combo.addItem(r)
            if resources:
                usb_resources = [r for r in resources if str(r).startswith("USB")]
                self.resource_combo.setEditText(usb_resources[0] if usb_resources else resources[0])
            else:
                self.resource_combo.setEditText(self.DEFAULT_ADDR)
            self.message_signal.emit(f"识别到资源：{resources}")
        except Exception as e:
            self.resource_combo.setEditText(self.DEFAULT_ADDR)
            self.message_signal.emit(f"刷新资源失败：{e}")

    def connect_scope(self):
        addr = self.resource_combo.currentText().strip()

        def task():
            idn = self.scope.connect(addr)
            self.status_signal.emit(f"已连接：{idn}")
            self.message_signal.emit(f"连接成功：{idn}")
            self.read_status_no_thread()

        self.run_task(task)

    def disconnect_scope(self):
        try:
            self.is_logging = False
            self.scope.disconnect()
            self.status_signal.emit("已断开连接")
            self.message_signal.emit("已断开连接")
        except Exception as e:
            self.message_signal.emit(f"断开失败：{e}")

    def run_scope(self):
        def task():
            self.require_connected()
            self.scope.write("TRMD AUTO")
            mode = self.scope.query("TRMD?")
            self.message_signal.emit(f"Run 已执行，Trigger Mode = {mode}")

        self.run_task(task)

    def stop_scope(self):
        def task():
            self.require_connected()
            self.scope.write("STOP")
            mode = self.scope.query("TRMD?")
            self.message_signal.emit(f"Stop 已执行，Trigger Mode = {mode}")

        self.run_task(task)

    def auto_setup(self):
        def task():
            self.require_connected()
            self.message_signal.emit("正在执行 Auto Setup，请稍等...")
            self.scope.write("C1:ASET")
            time.sleep(3)
            self.message_signal.emit("Auto Setup 已发送")
            self.read_status_no_thread()

        self.run_task(task)

    def save_screen_image(self):
        def task():
            self.require_connected()
            self.message_signal.emit("正在保存当前屏幕图到 D:\\桌面，请稍等...")
            file_path = self.scope.save_screen_image(self.SCREEN_SAVE_DIR)
            self.message_signal.emit(f"屏幕图已保存：{file_path}")

        self.run_task(task)

    def get_realtime_file_paths(self, save_dir=None, prefix: str = ""):
        if save_dir is None:
            save_dir = Path(self.log_dir_edit.text().strip())
        else:
            save_dir = Path(save_dir)

        ensure_dir(save_dir)

        prefix = str(prefix).strip()
        if prefix:
            voltage_file = save_dir / "电压.csv"
            current_file = save_dir / "电流.csv"
            summary_file = save_dir / "测量数据.csv"
        else:
            voltage_file = save_dir / "voltage_waveform.csv"
            current_file = save_dir / "current_waveform.csv"
            summary_file = save_dir / "temperature_frequency_dc_bias_power_loss.csv"

        return voltage_file, current_file, summary_file

    def save_one_realtime_record(
        self,
        save_dir=None,
        prefix: str = "",
        save_ch1=None,
        save_ch2=None,
        points=None,
        forced_base_freq=None
    ):
        self.require_connected()

        if save_ch1 is None:
            save_ch1 = self.save_ch1_check.isChecked()
        if save_ch2 is None:
            save_ch2 = self.save_ch2_check.isChecked()

        if not save_ch1 and not save_ch2:
            raise RuntimeError("请至少勾选一个要保存的通道：CH1 或 CH2")

        if points is None:
            try:
                points = int(float(self.log_points_edit.text().strip()))
            except Exception:
                points = self.DEFAULT_WAVE_POINTS

        if points <= 0:
            points = self.DEFAULT_WAVE_POINTS

        voltage_file, current_file, summary_file = self.get_realtime_file_paths(
            save_dir=save_dir,
            prefix=prefix
        )

        saved_files = []
        base_freq = forced_base_freq

        if save_ch1:
            # CH1 作为电压通道，并作为周期基准。
            if base_freq is None:
                base_freq = self.scope.read_channel_frequency(self.VOLTAGE_CHANNEL)

            voltage_freq, voltage_period, voltage_wave = self.scope.read_one_period_waveform(
                channel=self.VOLTAGE_CHANNEL,
                output_points=points,
                source_points=max(20000, points * 10),
                frequency=base_freq
            )

            voltage_header = ["频率_Hz", "周期_s"] + [f"V点{i}" for i in range(1, points + 1)]
            append_csv_row(voltage_file, voltage_header, [voltage_freq, voltage_period] + voltage_wave)
            saved_files.append(str(voltage_file))

        if save_ch2:
            # CH1 同时保存时，CH2 使用 CH1/外部给定周期基准；
            # 只保存 CH2 且没有外部频率时，才尝试读取 C2 自己的频率。
            if base_freq is None:
                base_freq = self.scope.read_channel_frequency(self.CURRENT_CHANNEL)

            current_freq, current_period, current_wave = self.scope.read_one_period_waveform(
                channel=self.CURRENT_CHANNEL,
                output_points=points,
                source_points=max(20000, points * 10),
                frequency=base_freq
            )

            current_header = ["频率_Hz", "周期_s"] + [f"I点{i}" for i in range(1, points + 1)]
            append_csv_row(current_file, current_header, [current_freq, current_period] + current_wave)
            saved_files.append(str(current_file))

        temperature, frequency, dc_bias, power_loss = self.scope.read_summary_measurements()
        summary_header = ["温度", "频率", "直流偏置", "功率损耗"]
        append_csv_row(summary_file, summary_header, [temperature, frequency, dc_bias, power_loss])
        saved_files.append(str(summary_file))

        return saved_files

    def save_realtime_record_once(self):
        def task():
            self.require_connected()
            self.message_signal.emit("正在保存一次 CSV 数据...")
            saved_files = self.save_one_realtime_record()
            self.message_signal.emit("保存完成：" + "；".join(saved_files))

        self.run_task(task)

    def is_invalid_scope_session_error(self, err: Exception) -> bool:
        """
        判断是否是示波器 VISA 会话失效。
        常见报错：Invalid session handle. The resource might be closed.
        """
        msg = str(err)
        return (
            "Invalid session handle" in msg
            or "VI_ERROR_INV_OBJECT" in msg
            or "The resource might be closed" in msg
        )

    def reopen_scope_session_for_auto_worker(self, scope_addr: str):
        """
        在自动测量后台线程中重新打开示波器会话。
        这样可以避免连接示波器的线程和自动测量线程不同导致的
        VISA session handle 失效问题。
        """
        if not scope_addr:
            scope_addr = self.scope.addr or self.DEFAULT_ADDR

        idn = self.scope.reconnect(scope_addr)
        self.status_signal.emit(f"已连接：{idn}")
        self.message_signal.emit(f"自动测量已重新连接示波器：{idn}")
        return idn

    def run_scope_operation_with_retry(self, scope_addr: str, description: str, func):
        """
        执行一次示波器操作；如果遇到 Invalid session handle，
        自动重连示波器并重试一次。
        """
        try:
            return func()
        except Exception as e:
            if not self.is_invalid_scope_session_error(e):
                raise

            self.message_signal.emit(f"{description} 时示波器会话失效，正在重连并重试...")
            self.auto_status_signal.emit("示波器 VISA 会话失效，正在重连...")
            self.reopen_scope_session_for_auto_worker(scope_addr)
            return func()

    def build_auto_frequency_list(self, start_khz: float, end_khz: float, groups: int):
        if groups <= 1:
            return [start_khz * 1000.0]
        step = (end_khz - start_khz) / (groups - 1)
        return [(start_khz + i * step) * 1000.0 for i in range(groups)]

    def build_linear_scan_values(self, start_value: float, stop_value: float, step_abs: float):
        step_abs = abs(float(step_abs))
        if step_abs <= 0:
            raise ValueError("扫描步长必须大于 0")
        if start_value == stop_value:
            return [float(start_value)]
        direction = 1 if stop_value > start_value else -1
        step = direction * step_abs
        values = []
        value = float(start_value)
        eps = step_abs * 1e-9
        if direction > 0:
            while value <= stop_value + eps:
                values.append(round(value, 10))
                value += step
        else:
            while value >= stop_value - eps:
                values.append(round(value, 10))
                value += step
        if values and abs(values[-1] - stop_value) > eps:
            values.append(float(stop_value))
        return values

    def validate_pwm_point(self, point: dict):
        freq_khz = float(point["freq_khz"])
        dp = float(point["duty_p"])
        is_triangle = point.get("waveform") == "triangle"
        dn = (1.0 - dp) if is_triangle else float(point["duty_n"])

        if freq_khz <= 0:
            raise ValueError("频率必须大于 0")
        if dp <= 0 or dp >= 1:
            raise ValueError(f"duty_P={dp} 不合法，应在 0~1 之间")
        if is_triangle:
            if dn <= 0 or dn >= 1:
                raise ValueError(f"三角波 duty_P={dp} 导致 duty_N={dn} 不合法")
        else:
            if dn <= 0 or dn >= 1:
                raise ValueError(f"duty_N={dn} 不合法，应在 0~1 之间")
            if dp + dn > 1.0:
                raise ValueError(f"duty_P + duty_N = {dp + dn:.3f} > 1")
        return dn

    def build_scope_scan_points(self, cfg: dict):
        values = self.build_linear_scan_values(cfg["scan_start"], cfg["scan_stop"], cfg["scan_step"])
        points = []
        scan_item = cfg.get("scan_item", "frequency")
        for value in values:
            point = {
                "waveform": cfg.get("waveform", "trapezoid"),
                "waveform_label": cfg.get("waveform_label", "梯形波"),
                "scan_item": scan_item,
                "scan_value": value,
                "freq_khz": float(cfg.get("fixed_freq_khz", 50.0)),
                "voltage": float(cfg.get("fixed_voltage", 10.0)),
                "duty_p": float(cfg.get("fixed_dp", 0.2)),
                "duty_n": float(cfg.get("fixed_dn", 0.2)),
                # 非直流偏置扫描时，Hdc 强制为 0，避免扫描过程中误开启电流源。
                "hdc": 0.0 if scan_item != "hdc" else float(cfg.get("fixed_hdc", 0.0)),
                "deadtime_ns": float(cfg.get("deadtime_ns", 50.0)),
            }
            if scan_item == "frequency":
                point["freq_khz"] = value
            elif scan_item == "voltage":
                point["voltage"] = value
            elif scan_item == "duty_p":
                point["duty_p"] = value
            elif scan_item == "duty_n":
                if point["waveform"] == "triangle":
                    raise ValueError("三角波只需要扫描 duty_P，不需要额外扫描 duty_N")
                point["duty_n"] = value
            elif scan_item == "hdc":
                point["hdc"] = value

            if point["voltage"] < 0:
                raise ValueError("电压不能小于 0")
            if point["hdc"] < 0:
                raise ValueError("直流偏置 Hdc 不能小于 0")
            if point["deadtime_ns"] < 0:
                raise ValueError("死区时间不能小于 0")
            point["duty_n_actual"] = self.validate_pwm_point(point)
            points.append(point)
        return points

    def build_pwm_params_from_point(self, point: dict):
        freq_hz = float(point["freq_khz"]) * 1000.0
        dp = float(point["duty_p"])
        is_triangle = point.get("waveform") == "triangle"
        dn_actual = (1.0 - dp) if is_triangle else float(point["duty_n"])
        dt_ns = float(point.get("deadtime_ns", 50.0))
        mode = MODE_TRIANGULAR if is_triangle else MODE_TRAPEZOIDAL

        carrier = int(FREQ2CARRIER / freq_hz + 0.5)
        if carrier < 1 or carrier > 65535:
            raise RuntimeError(f"频率 {point['freq_khz']:.3f} kHz 计算出的 CARRIER={carrier} 超出 16 位范围")

        if is_triangle:
            cmp_tri = int(carrier * dp + 0.5)
            cmp_l = cmp_tri
            cmp_h = cmp_tri
        else:
            cmp_l = int(carrier * dp + 0.5)
            cmp_h = int(carrier * (1.0 - dn_actual) + 0.5)

        deadtime_tbclk = int(dt_ns / 10.0 + 0.5)
        return {
            "mode": mode,
            "carrier": carrier,
            "cmp_l": cmp_l,
            "cmp_h": cmp_h,
            "deadtime": deadtime_tbclk,
            "dp": dp,
            "dn": dn_actual,
            "is_triangle": is_triangle,
            "freq_hz": freq_hz,
        }

    def set_dsp_pwm_for_auto_point(self, point: dict):
        if self.main_window is None or not hasattr(self.main_window, "tnpc_page"):
            raise RuntimeError("找不到 TNPC 通信控制页")
        ser = getattr(self.main_window.tnpc_page, "ser", None)
        if ser is None or not getattr(ser, "is_open", False):
            raise RuntimeError("请先在 TNPC 通信控制页连接 DSP 串口")

        params = self.build_pwm_params_from_point(point)
        send_command(ser, CMD_STOP_PWM, 0)
        send_command(ser, CMD_SET_MODE, params["mode"])
        send_command(ser, CMD_SET_CARRIER, params["carrier"])
        send_command(ser, CMD_SET_CMP_L, params["cmp_l"])
        send_command(ser, CMD_SET_CMP_H, params["cmp_h"])
        send_command(ser, CMD_SET_DEADTIME, params["deadtime"])
        send_command(ser, CMD_APPLY, 0)
        send_command(ser, CMD_START_PWM, 0)
        return params

    def set_dsp_pwm_for_auto_point_optional(self, point: dict, required: bool):
        if required:
            return self.set_dsp_pwm_for_auto_point(point)
        try:
            return self.set_dsp_pwm_for_auto_point(point)
        except Exception:
            return None

    def set_voltage_for_auto_point(self, voltage_v: float, required: bool):
        panel = None
        if self.main_window is not None and hasattr(self.main_window, "tnpc_page"):
            panel = getattr(self.main_window.tnpc_page, "power_panel", None)
        if panel is None or not hasattr(panel, "both_connected") or not panel.both_connected():
            if required:
                raise RuntimeError("扫描电压需要先在第一页连接两台 Chroma 电压源")
            return False
        errors = panel.set_voltage_both(voltage_v, voltage_v)
        if errors:
            raise RuntimeError("设置电压源失败：" + "；".join(errors))
        panel.output_on_both()
        return True

    def set_hdc_for_auto_point(self, hdc_value: float, required: bool):
        page = getattr(self.main_window, "current_source_page", None) if self.main_window is not None else None
        if page is None or getattr(page, "inst", None) is None:
            if required:
                raise RuntimeError("扫描直流偏置需要先在第二页连接电流源，并读取磁芯参数")
            return False
        try:
            if hasattr(page, "refresh_core_params"):
                page.refresh_core_params(show_message=False)
            current = page.hdc_to_current(hdc_value)
            if current < 0 or current > 76.0:
                raise RuntimeError(f"Hdc={hdc_value} A/m 对应电流 {current:.6f} A，超出 0~76A")
            voltage_limit = page.parse_voltage_limit_input() if hasattr(page, "parse_voltage_limit_input") else 5.0
            page.send_cmd(f"SOUR:VOLT {voltage_limit}")
            page.send_cmd(f"SOUR:CURR {current}")
            page.send_cmd("OUTP ON")
            return True
        except Exception:
            if required:
                raise
            return False

    def ensure_current_source_off_for_non_hdc_scan(self):
        """非直流偏置扫描开始前确保电流源输出关闭。"""
        page = getattr(self.main_window, "current_source_page", None) if self.main_window is not None else None
        if page is None or getattr(page, "inst", None) is None:
            return
        try:
            if hasattr(page, "stop_bias_scan"):
                page.stop_bias_scan(send_off=False)
            page.send_cmd("OUTP OFF")
            if hasattr(page, "status"):
                page.status.setText("状态：非直流偏置扫描，电流源输出已关闭")
        except Exception as e:
            self.message_signal.emit(f"非直流偏置扫描：关闭电流源输出失败，可检查电流源连接：{e}")

    def shutdown_scan_outputs_safely(self):
        """自动扫描结束/停止/报错后，静默关闭电流源和两台电压源输出。"""
        # 关闭电流源输出
        try:
            page = getattr(self.main_window, "current_source_page", None) if self.main_window is not None else None
            if page is not None and getattr(page, "inst", None) is not None:
                try:
                    if hasattr(page, "stop_bias_scan"):
                        page.stop_bias_scan(send_off=False)
                    page.send_cmd("OUTP OFF")
                    if hasattr(page, "status"):
                        page.status.setText("状态：自动扫描结束，输出已关闭")
                    self.message_signal.emit("自动扫描结束：已关闭电流源输出")
                except Exception as e:
                    self.message_signal.emit(f"自动扫描结束：关闭电流源输出失败：{e}")
        except Exception:
            pass

        # 关闭两台 Chroma 电压源输出
        try:
            panel = None
            if self.main_window is not None and hasattr(self.main_window, "tnpc_page"):
                panel = getattr(self.main_window.tnpc_page, "power_panel", None)
            if panel is not None:
                try:
                    if hasattr(panel, "emergency_off"):
                        panel.emergency_off()
                    elif hasattr(panel, "output_off_both"):
                        panel.output_off_both()
                    self.message_signal.emit("自动扫描结束：已关闭两台电压源输出")
                except Exception as e:
                    self.message_signal.emit(f"自动扫描结束：关闭电压源输出失败：{e}")
        except Exception:
            pass

    def scan_point_description(self, point: dict):
        item = point.get("scan_item", "frequency")
        label = ScopeScanSettingsDialog.ITEM_LABELS.get(item, item)
        unit = ScopeScanSettingsDialog.ITEM_UNITS.get(item, "")
        value = point.get("scan_value")
        unit_text = unit if unit else ""
        return f"{label}={value:g}{unit_text}"

    def get_manual_pwm_params_for_freq(self, freq_hz: float):
        """
        读取第一页 Manual Control 当前的占空比/死区/波形模式，
        并根据目标频率计算 CARRIER/CMP_L/CMP_H。
        """
        manual = None
        if self.main_window is not None:
            manual = getattr(getattr(self.main_window, "tnpc_page", None), "manual_page", None)

        # 默认值与 tnpc_core.py 中 ManualPage 初始值保持一致
        dp = 0.20
        dn = 0.20
        dt_ns = 50
        is_triangle = False

        try:
            if manual is not None and hasattr(manual, "dp_spin"):
                dp = float(manual.dp_spin.value())
            if manual is not None and hasattr(manual, "dn_spin"):
                dn = float(manual.dn_spin.value())
            if manual is not None and hasattr(manual, "dt_spin"):
                dt_ns = int(manual.dt_spin.value())
            if manual is not None and hasattr(manual, "mode_tri"):
                is_triangle = bool(manual.mode_tri.isChecked())
        except Exception:
            pass

        mode = MODE_TRIANGULAR if is_triangle else MODE_TRAPEZOIDAL

        if is_triangle:
            dn_actual = 1.0 - dp
        else:
            dn_actual = dn

        if dp <= 0:
            raise RuntimeError("duty_P 必须大于 0")
        if not is_triangle and dn_actual <= 0:
            raise RuntimeError("duty_N 必须大于 0")
        if dp + dn_actual > 1.0:
            raise RuntimeError("duty_P + duty_N 不能大于 1.0")

        carrier = int(FREQ2CARRIER / float(freq_hz) + 0.5)
        if carrier < 1 or carrier > 65535:
            raise RuntimeError(f"频率 {freq_hz/1000:.1f} kHz 计算出的 CARRIER={carrier} 超出 16 位范围")

        if is_triangle:
            cmp_tri = int(carrier * dp + 0.5)
            cmp_l = cmp_tri
            cmp_h = cmp_tri
        else:
            cmp_l = int(carrier * dp + 0.5)
            cmp_h = int(carrier * (1.0 - dn_actual) + 0.5)

        deadtime_tbclk = int(dt_ns / 10.0 + 0.5)

        return {
            "mode": mode,
            "carrier": carrier,
            "cmp_l": cmp_l,
            "cmp_h": cmp_h,
            "deadtime": deadtime_tbclk,
            "dp": dp,
            "dn": dn_actual,
            "is_triangle": is_triangle,
        }

    def set_dsp_frequency_for_auto_measure(self, freq_hz: float):
        """
        通过第一页 TNPC 串口给 DSP 下发目标频率。
        使用第一页 Manual Control 当前的 duty_P、duty_N、deadtime 和波形模式。
        """
        if self.main_window is None or not hasattr(self.main_window, "tnpc_page"):
            raise RuntimeError("找不到 TNPC 通信控制页")

        ser = getattr(self.main_window.tnpc_page, "ser", None)
        if ser is None or not getattr(ser, "is_open", False):
            raise RuntimeError("请先在 TNPC 通信控制页连接 DSP 串口")

        params = self.get_manual_pwm_params_for_freq(freq_hz)

        # 与 ManualPage.apply_params/start_pwm 一致：逐条等待 ACK。
        send_command(ser, CMD_STOP_PWM, 0)
        send_command(ser, CMD_SET_MODE, params["mode"])
        send_command(ser, CMD_SET_CARRIER, params["carrier"])
        send_command(ser, CMD_SET_CMP_L, params["cmp_l"])
        send_command(ser, CMD_SET_CMP_H, params["cmp_h"])
        send_command(ser, CMD_SET_DEADTIME, params["deadtime"])
        send_command(ser, CMD_APPLY, 0)
        send_command(ser, CMD_START_PWM, 0)

        return params

    def start_auto_sweep_measure(self):
        if self.auto_sweep_running:
            self.message_signal.emit("自动测量已经在运行")
            return

        try:
            self.require_connected()
        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))
            return

        if self.main_window is None or not hasattr(self.main_window, "tnpc_page"):
            QMessageBox.critical(self, "错误", "找不到 TNPC 通信控制页")
            return

        try:
            cfg = dict(self.scope_scan_config)
            scan_points = self.build_scope_scan_points(cfg)
            group_target_s = float(cfg.get("group_wait_s", 0.0))
            first_group_wait_s = float(cfg.get("first_group_wait_s", 0.0))
            points = int(float(self.log_points_edit.text().strip()))
            root_dir = Path(self.auto_root_dir_edit.text().strip())
            scope_addr = self.resource_combo.currentText().strip()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"自动扫描参数格式错误：{e}")
            return

        if not scan_points:
            QMessageBox.critical(self, "错误", "扫描点为空，请检查扫描范围和步长")
            return

        conn_ok, conn_error, conn_warning = self.check_scope_scan_device_connections(cfg)
        if not conn_ok:
            QMessageBox.critical(self, "连接错误", conn_error)
            return
        if conn_warning:
            ret = QMessageBox.question(
                self,
                "连接提示",
                conn_warning + "\n\n这些未连接项可忽略，仍然开始自动测量并保存结果吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if ret != QMessageBox.Yes:
                return

        if points <= 0:
            points = self.DEFAULT_WAVE_POINTS
        if group_target_s < 0:
            group_target_s = 0
        if first_group_wait_s < 0:
            first_group_wait_s = 0

        params = {
            "scan_config": cfg,
            "scan_points": scan_points,
            "group_target_s": group_target_s,
            "first_group_wait_s": first_group_wait_s,
            "points": points,
            "root_dir": root_dir,
            "scope_addr": scope_addr,
            "save_ch1": self.auto_save_ch1_check.isChecked(),
            "save_ch2": self.auto_save_ch2_check.isChecked(),
        }

        if not params["save_ch1"] and not params["save_ch2"]:
            QMessageBox.critical(self, "错误", "自动测量请至少勾选 CH1 或 CH2")
            return

        self.auto_sweep_running = True
        self.auto_start_btn.setEnabled(False)
        self.auto_stop_btn.setEnabled(True)
        self.auto_status_label.setText("自动测量运行中...")
        self.message_signal.emit(f"自动扫描测量开始，共 {len(scan_points)} 组")

        threading.Thread(
            target=self.auto_sweep_measure_worker,
            args=(params,),
            daemon=True
        ).start()

    def stop_auto_sweep_measure(self):
        self.auto_sweep_running = False
        self.message_signal.emit("正在请求停止自动测量，当前组完成后停止...")

    def on_auto_sweep_finished(self):
        self.auto_sweep_running = False
        self.auto_start_btn.setEnabled(True)
        self.auto_stop_btn.setEnabled(False)
        self.auto_status_label.setText("自动测量已停止 / 已完成")

    def scope_auto_setup_for_sweep(self):
        """
        自动扫描每组保存结果前调用示波器 Auto Setup，并等待自动设置完成。

        之前只发送 C1:ASET 后立即进入保存，后面几组可能出现示波器尚未完成
        自动调整就开始读图/读 CSV 的情况。这里固定执行：
        TRMD AUTO -> C1:ASET -> 等待 4 s -> TRMD AUTO -> 等待 1 s。
        """
        self.require_connected()
        try:
            self.scope.write("TRMD AUTO")
            time.sleep(0.3)
        except Exception:
            # 部分固件可能不接受 TRMD AUTO，但不影响继续发送 Auto Setup。
            pass
        self.scope.write("C1:ASET")
        time.sleep(4.0)
        try:
            self.scope.write("TRMD AUTO")
        except Exception:
            pass
        time.sleep(1.0)

    def wait_until_group_target_time(self, group_start_time: float, target_seconds: float):
        """
        让当前组从开始设置频率到开始保存前大约保持 target_seconds。
        如果 Auto Setup 本身耗时超过 target_seconds，则不再额外等待。
        """
        if target_seconds <= 0:
            return
        while self.auto_sweep_running:
            elapsed = time.time() - group_start_time
            remain = target_seconds - elapsed
            if remain <= 0:
                break
            time.sleep(min(0.05, remain))

    def auto_sweep_measure_worker(self, params: dict):
        try:
            root_dir = Path(params["root_dir"])
            ensure_dir(root_dir)

            scan_points = list(params.get("scan_points", []))
            scan_config = dict(params.get("scan_config", {}))
            scan_item = scan_config.get("scan_item", "frequency")
            voltage_required = scan_item == "voltage"
            hdc_required = scan_item == "hdc"
            dsp_required = scan_item in ("frequency", "duty_p", "duty_n")

            if not hdc_required:
                # 非直流偏置扫描：直流偏置为 0，电流源不参与扫描，并确保输出关闭。
                self.ensure_current_source_off_for_non_hdc_scan()

            # 自动测量开始前，在线程内部重新打开示波器 VISA 会话。
            self.auto_status_signal.emit("正在重新连接示波器 VISA 会话...")
            self.reopen_scope_session_for_auto_worker(params.get("scope_addr", ""))

            for idx, point in enumerate(scan_points, start=1):
                if not self.auto_sweep_running:
                    break

                group_name = chinese_group_name(idx)
                group_dir = root_dir / group_name
                group_start_time = time.time()
                freq_hz = float(point["freq_khz"]) * 1000.0
                desc = self.scan_point_description(point)

                self.message_signal.emit(f"{group_name}：设置扫描点 {desc}")
                self.auto_status_signal.emit(f"{group_name}：{desc}")

                # 1) 设置 TNPC PWM：扫描频率/duty 时必须连接；其他扫描项若未连接则跳过。
                pwm_params = self.set_dsp_pwm_for_auto_point_optional(point, required=dsp_required)

                # 2) 设置电压源：扫描电压时必须连接；其他扫描项若未连接则跳过。
                voltage_applied = self.set_voltage_for_auto_point(
                    float(point.get("voltage", 0.0)),
                    required=voltage_required
                )

                # 3) 设置直流偏置：只有扫描项为“直流偏置”时才调用电流源。
                #    其他扫描项中直流偏置固定为 0，扫描过程中电流源不开启。
                hdc_value = float(point.get("hdc", 0.0))
                if hdc_required:
                    hdc_applied = self.set_hdc_for_auto_point(
                        hdc_value,
                        required=True
                    )
                else:
                    hdc_value = 0.0
                    hdc_applied = False

                if idx == 1:
                    first_wait = float(params.get("first_group_wait_s", 0.0))
                    if first_wait > 0:
                        self.message_signal.emit(
                            f"{group_name}：第一组已设置 {desc}，先等待 {first_wait:.2f}s 再开始测量"
                        )
                        self.auto_status_signal.emit(f"{group_name}：第一组预等待 {first_wait:.2f}s")
                        wait_start = time.time()
                        while time.time() - wait_start < first_wait:
                            if not self.auto_sweep_running:
                                break
                            time.sleep(0.05)

                if not self.auto_sweep_running:
                    break

                self.message_signal.emit(f"{group_name}：示波器 Auto Setup")
                self.auto_status_signal.emit(f"{group_name}：示波器 Auto Setup")
                self.run_scope_operation_with_retry(
                    params.get("scope_addr", ""),
                    "示波器 Auto Setup",
                    self.scope_auto_setup_for_sweep
                )

                self.wait_until_group_target_time(group_start_time, params["group_target_s"])

                if not self.auto_sweep_running:
                    break

                ensure_dir(group_dir)

                self.message_signal.emit(f"{group_name}：保存屏幕图")
                self.auto_status_signal.emit(f"{group_name}：保存屏幕图和 CSV")
                screen_path = Path(
                    self.run_scope_operation_with_retry(
                        params.get("scope_addr", ""),
                        "保存屏幕图",
                        lambda: self.scope.save_screen_image(group_dir)
                    )
                )
                target_screen = group_dir / f"{group_name}_屏幕图{screen_path.suffix}"
                try:
                    if target_screen.exists():
                        target_screen.unlink()
                    screen_path.rename(target_screen)
                except Exception:
                    target_screen = screen_path

                if not self.auto_sweep_running:
                    break

                self.message_signal.emit(f"{group_name}：保存 CSV 数据")
                saved_files = self.run_scope_operation_with_retry(
                    params.get("scope_addr", ""),
                    "保存 CSV 数据",
                    lambda: self.save_one_realtime_record(
                        save_dir=group_dir,
                        prefix=group_name,
                        save_ch1=params["save_ch1"],
                        save_ch2=params["save_ch2"],
                        points=params["points"],
                        forced_base_freq=freq_hz
                    )
                )

                info_file = group_dir / f"{group_name}_扫描信息.txt"
                with open(info_file, "w", encoding="utf-8") as f:
                    f.write(f"组别: {group_name}\n")
                    f.write(f"波形类型: {point.get('waveform_label')}\n")
                    f.write(f"扫描项: {ScopeScanSettingsDialog.ITEM_LABELS.get(scan_item, scan_item)}\n")
                    f.write(f"扫描值: {point.get('scan_value')}\n")
                    f.write(f"频率_Hz: {freq_hz:.6f}\n")
                    f.write(f"频率_kHz: {point.get('freq_khz'):.6f}\n")
                    f.write(f"电压_V: {point.get('voltage'):.6f}\n")
                    f.write(f"直流偏置_Hdc_A_per_m: {point.get('hdc'):.6f}\n")
                    f.write(f"电压源已设置: {voltage_applied}\n")
                    f.write(f"电流源直流偏置已设置: {hdc_applied}\n")
                    f.write(f"每组等待时间_s: {params['group_target_s']:.6f}\n")
                    f.write(f"第一组预等待_s: {params.get('first_group_wait_s', 0.0):.6f}\n")
                    f.write(f"实际到开始保存耗时_s: {time.time() - group_start_time:.6f}\n")
                    f.write("示波器AutoSetup: TRMD AUTO -> C1:ASET -> 等待4s -> TRMD AUTO -> 等待1s\n")
                    f.write(f"TNPC_PWM已设置: {pwm_params is not None}\n")
                    if pwm_params is not None:
                        f.write(f"CARRIER: {pwm_params['carrier']}\n")
                        f.write(f"CMP_L: {pwm_params['cmp_l']}\n")
                        f.write(f"CMP_H: {pwm_params['cmp_h']}\n")
                        f.write(f"Deadtime_TBCLK: {pwm_params['deadtime']}\n")
                        f.write(f"duty_P: {pwm_params['dp']}\n")
                        f.write(f"duty_N: {pwm_params['dn']}\n")
                    else:
                        f.write("CARRIER: 未设置\n")
                        f.write("CMP_L: 未设置\n")
                        f.write("CMP_H: 未设置\n")
                        f.write("Deadtime_TBCLK: 未设置\n")
                        f.write("duty_P: 未设置\n")
                        f.write("duty_N: 未设置\n")
                    f.write(f"屏幕图: {target_screen}\n")
                    for file_path in saved_files:
                        f.write(f"CSV: {file_path}\n")

                self.message_signal.emit(f"{group_name} 完成：{desc}，耗时 {time.time() - group_start_time:.2f}s")

            if self.auto_sweep_running:
                self.message_signal.emit("自动扫描测量全部完成")
            else:
                self.message_signal.emit("自动扫描测量已停止")

        except Exception as e:
            if self.is_invalid_scope_session_error(e):
                self.message_signal.emit(
                    "自动扫描测量错误：示波器 VISA 会话失效。"
                    "请确认示波器 USB 未断开、未被 NI MAX/其他程序占用，然后重新连接示波器再开始。"
                )
            else:
                self.message_signal.emit(f"自动扫描测量错误：{e}")
        finally:
            # 每次自动扫描结束后，无论正常完成、停止还是报错，都关闭电流源和电压源输出。
            self.shutdown_scan_outputs_safely()
            self.auto_finished_signal.emit()

    def start_realtime_logging(self):
        # 当前窗口只保留“保存一次”，实时循环保存功能已停用。
        self.message_signal.emit("当前版本只支持保存一次 CSV")

    def stop_realtime_logging(self):
        self.is_logging = False

    def read_status(self):
        self.run_task(self.read_status_no_thread)

    def read_status_no_thread(self):
        self.require_connected()

        tdiv = self.scope.query("TDIV?")
        trdl = self.scope.query("TRDL?")

        try:
            ch1_deskew = self.scope.query("VBS? 'return=app.Acquisition.C1.Deskew'")
        except Exception:
            ch1_deskew = "0"

        ch1_ofst = self.scope.query("C1:OFST?")
        ch1_vdiv = self.scope.query("C1:VDIV?")
        ch2_ofst = self.scope.query("C2:OFST?")
        ch2_vdiv = self.scope.query("C2:VDIV?")

        try:
            ch1_attn = self.scope.get_channel_attenuation("C1")
        except Exception:
            ch1_attn = self.value("ch1_attn") if "ch1_attn" in self.fields else ""

        try:
            ch2_attn = self.scope.get_channel_attenuation("C2")
        except Exception:
            ch2_attn = self.value("ch2_attn") if "ch2_attn" in self.fields else ""

        mode = self.scope.query("TRMD?")

        self.field_signal.emit("tdiv", tdiv)
        self.field_signal.emit("trdl", trdl)
        self.field_signal.emit("ch1_deskew", ch1_deskew)
        self.field_signal.emit("ch1_ofst", ch1_ofst)
        self.field_signal.emit("ch1_vdiv", ch1_vdiv)
        self.field_signal.emit("ch1_attn", ch1_attn)
        self.field_signal.emit("ch2_ofst", ch2_ofst)
        self.field_signal.emit("ch2_vdiv", ch2_vdiv)
        self.field_signal.emit("ch2_attn", ch2_attn)

        self.message_signal.emit(
            f"当前状态：TRMD={mode}, TDIV={tdiv}, TRDL={trdl}, "
            f"C1:DESKEW={ch1_deskew}, C1:OFST={ch1_ofst}, C1:VDIV={ch1_vdiv}, C1:ATTN={ch1_attn}, "
            f"C2:OFST={ch2_ofst}, C2:VDIV={ch2_vdiv}, C2:ATTN={ch2_attn}"
        )

    def set_tdiv(self):
        value = self.value("tdiv")

        def task():
            self.require_connected()
            self.scope.write(f"TDIV {value}")
            result = self.scope.query("TDIV?")
            self.field_signal.emit("tdiv", result)
            self.message_signal.emit(f"TDIV 设置为：{result}")

        self.run_task(task)

    def tdiv_faster(self):
        factor = float(self.value("tdiv_step"))

        def task():
            self.require_connected()
            current = extract_float(self.scope.query("TDIV?"))
            new_value = current / factor
            self.scope.write(f"TDIV {fmt(new_value)}")
            result = self.scope.query("TDIV?")
            self.field_signal.emit("tdiv", result)
            self.message_signal.emit(f"时基变快：TDIV = {result}")

        self.run_task(task)

    def tdiv_slower(self):
        factor = float(self.value("tdiv_step"))

        def task():
            self.require_connected()
            current = extract_float(self.scope.query("TDIV?"))
            new_value = current * factor
            self.scope.write(f"TDIV {fmt(new_value)}")
            result = self.scope.query("TDIV?")
            self.field_signal.emit("tdiv", result)
            self.message_signal.emit(f"时基变慢：TDIV = {result}")

        self.run_task(task)

    def set_trdl(self):
        value = self.value("trdl")

        def task():
            self.require_connected()
            self.scope.write(f"TRDL {value}")
            result = self.scope.query("TRDL?")
            self.field_signal.emit("trdl", result)
            self.message_signal.emit(f"水平 Delay 设置为：{result}")

        self.run_task(task)

    def move_trdl(self, direction: int):
        step = float(self.value("trdl_step"))

        def task():
            self.require_connected()
            current = extract_float(self.scope.query("TRDL?"))
            new_value = current + direction * step
            self.scope.write(f"TRDL {fmt(new_value)}")
            result = self.scope.query("TRDL?")
            self.field_signal.emit("trdl", result)
            self.message_signal.emit(f"水平移动：TRDL = {result}")

        self.run_task(task)

    def zero_trdl(self):
        def task():
            self.require_connected()
            self.scope.write("TRDL 0")
            result = self.scope.query("TRDL?")
            self.field_signal.emit("trdl", result)
            self.message_signal.emit(f"水平 Delay 归零：{result}")

        self.run_task(task)

    def set_ch1_deskew(self):
        value = self.value("ch1_deskew")

        def task():
            self.require_connected()
            self.scope.write(f"VBS 'app.Acquisition.C1.Deskew = {value}'")
            result = self.scope.query("VBS? 'return=app.Acquisition.C1.Deskew'")
            self.field_signal.emit("ch1_deskew", result)
            self.message_signal.emit(f"CH1 Deskew 设置为：{result} s")

        self.run_task(task)

    def move_ch1_deskew(self, direction: int):
        step = float(self.value("ch1_deskew_step"))

        def task():
            self.require_connected()
            current_text = self.scope.query("VBS? 'return=app.Acquisition.C1.Deskew'")
            current = extract_float(current_text)
            new_value = current + direction * step
            self.scope.write(f"VBS 'app.Acquisition.C1.Deskew = {fmt(new_value)}'")
            result = self.scope.query("VBS? 'return=app.Acquisition.C1.Deskew'")
            self.field_signal.emit("ch1_deskew", result)
            self.message_signal.emit(f"CH1 Deskew 调整为：{result} s")

        self.run_task(task)

    def zero_ch1_deskew(self):
        def task():
            self.require_connected()
            self.scope.write("VBS 'app.Acquisition.C1.Deskew = 0'")
            result = self.scope.query("VBS? 'return=app.Acquisition.C1.Deskew'")
            self.field_signal.emit("ch1_deskew", result)
            self.message_signal.emit(f"CH1 Deskew 已归零：{result} s")

        self.run_task(task)

    def set_ch1_offset(self):
        value = self.value("ch1_ofst")

        def task():
            self.require_connected()
            self.scope.write(f"C1:OFST {value}")
            result = self.scope.query("C1:OFST?")
            self.field_signal.emit("ch1_ofst", result)
            self.message_signal.emit(f"CH1 Offset 设置为：{result}")

        self.run_task(task)

    def move_ch1_offset(self, direction: int):
        step = float(self.value("ch1_ofst_step"))

        def task():
            self.require_connected()
            current = extract_float(self.scope.query("C1:OFST?"))
            new_value = current + direction * step
            self.scope.write(f"C1:OFST {fmt(new_value)}")
            result = self.scope.query("C1:OFST?")
            self.field_signal.emit("ch1_ofst", result)
            self.message_signal.emit(f"CH1 垂直移动：Offset = {result}")

        self.run_task(task)

    def zero_ch1_offset(self):
        def task():
            self.require_connected()
            self.scope.write("C1:OFST 0")
            result = self.scope.query("C1:OFST?")
            self.field_signal.emit("ch1_ofst", result)
            self.message_signal.emit(f"CH1 Offset 归零：{result}")

        self.run_task(task)

    def set_ch1_vdiv(self):
        value = self.value("ch1_vdiv")

        def task():
            self.require_connected()
            result = self.scope.set_channel_vdiv("C1", value)
            self.field_signal.emit("ch1_vdiv", result)
            self.message_signal.emit(f"CH1 V/Div 手动设置为：{result}")

        self.run_task(task)

    def ch1_vdiv_smaller(self):
        factor = float(self.value("ch1_vdiv_step"))

        def task():
            self.require_connected()
            current = extract_float(self.scope.query("C1:VDIV?"))
            new_value = current / factor
            result = self.scope.set_channel_vdiv("C1", new_value)
            self.field_signal.emit("ch1_vdiv", result)
            self.message_signal.emit(f"CH1 放大：VDIV = {result}")

        self.run_task(task)

    def ch1_vdiv_larger(self):
        factor = float(self.value("ch1_vdiv_step"))

        def task():
            self.require_connected()
            current = extract_float(self.scope.query("C1:VDIV?"))
            new_value = current * factor
            result = self.scope.set_channel_vdiv("C1", new_value)
            self.field_signal.emit("ch1_vdiv", result)
            self.message_signal.emit(f"CH1 缩小：VDIV = {result}")

        self.run_task(task)

    def set_channel_attenuation_from_field(self, field_key: str, channel: str):
        value = self.value(field_key)

        def task():
            self.require_connected()
            result = self.scope.set_channel_attenuation(channel, value)
            self.field_signal.emit(field_key, result)
            self.message_signal.emit(f"{channel} 探头比例设置为：{result}")

        self.run_task(task)

    def quick_set_attenuation(self, field_key: str, channel: str, value):
        if field_key in self.fields:
            self.fields[field_key].setText(str(value))
        self.set_channel_attenuation_from_field(field_key, channel)

    def set_ch1_attenuation(self):
        self.set_channel_attenuation_from_field("ch1_attn", "C1")

    def set_ch2_attenuation(self):
        self.set_channel_attenuation_from_field("ch2_attn", "C2")

    def set_ch2_offset(self):
        value = self.value("ch2_ofst")

        def task():
            self.require_connected()
            self.scope.write(f"C2:OFST {value}")
            result = self.scope.query("C2:OFST?")
            self.field_signal.emit("ch2_ofst", result)
            self.message_signal.emit(f"CH2 Offset 设置为：{result}")

        self.run_task(task)

    def move_ch2_offset(self, direction: int):
        step = float(self.value("ch2_ofst_step"))

        def task():
            self.require_connected()
            current = extract_float(self.scope.query("C2:OFST?"))
            new_value = current + direction * step
            self.scope.write(f"C2:OFST {fmt(new_value)}")
            result = self.scope.query("C2:OFST?")
            self.field_signal.emit("ch2_ofst", result)
            self.message_signal.emit(f"CH2 垂直移动：Offset = {result}")

        self.run_task(task)

    def zero_ch2_offset(self):
        def task():
            self.require_connected()
            self.scope.write("C2:OFST 0")
            result = self.scope.query("C2:OFST?")
            self.field_signal.emit("ch2_ofst", result)
            self.message_signal.emit(f"CH2 Offset 归零：{result}")

        self.run_task(task)

    def set_ch2_vdiv(self):
        value = self.value("ch2_vdiv")

        def task():
            self.require_connected()
            result = self.scope.set_channel_vdiv("C2", value)
            self.field_signal.emit("ch2_vdiv", result)
            self.message_signal.emit(f"CH2 V/Div 手动设置为：{result}")

        self.run_task(task)

    def ch2_vdiv_smaller(self):
        factor = float(self.value("ch2_vdiv_step"))

        def task():
            self.require_connected()
            current = extract_float(self.scope.query("C2:VDIV?"))
            new_value = current / factor
            result = self.scope.set_channel_vdiv("C2", new_value)
            self.field_signal.emit("ch2_vdiv", result)
            self.message_signal.emit(f"CH2 放大：VDIV = {result}")

        self.run_task(task)

    def ch2_vdiv_larger(self):
        factor = float(self.value("ch2_vdiv_step"))

        def task():
            self.require_connected()
            current = extract_float(self.scope.query("C2:VDIV?"))
            new_value = current * factor
            result = self.scope.set_channel_vdiv("C2", new_value)
            self.field_signal.emit("ch2_vdiv", result)
            self.message_signal.emit(f"CH2 缩小：VDIV = {result}")

        self.run_task(task)

    def close_page(self):
        self.is_logging = False
        self.scope.disconnect()


# ============================================================
# Main window
# ============================================================

class IntegratedCommunicationPanel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TNPC + 电流源 + 示波器集成上位机")
        self.setMinimumWidth(1000)
        self.setMinimumHeight(760)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tnpc_page = TNPCPage(self)
        self.current_source_page = PSU2076CurrentSource()
        self.scope_page = ScopePage(self)

        # 第二页电流源控制读取第一页磁芯参数，用于 Idc 与 Hdc 的换算。
        if hasattr(self.current_source_page, "set_core_params_provider"):
            self.current_source_page.set_core_params_provider(lambda: dict(self.tnpc_page.core_params))
        if hasattr(self.current_source_page, "set_core_params"):
            self.current_source_page.set_core_params(dict(self.tnpc_page.core_params))

        self.tabs.addTab(self.tnpc_page, "TNPC 通信控制")
        self.tabs.addTab(self.current_source_page, "电流源通信控制")
        self.tabs.addTab(self.scope_page, "示波器通信控制")

        self.install_shortcuts()
        self.statusBar().showMessage("Ready")

    def install_shortcuts(self):
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc.setContext(Qt.ApplicationShortcut)
        esc.activated.connect(self.tnpc_page.emergency_stop)

    def closeEvent(self, event):
        try:
            self.tnpc_page.close_page()
        except Exception:
            pass

        try:
            if hasattr(self.current_source_page, "close_page"):
                self.current_source_page.close_page()
        except Exception:
            pass

        try:
            self.scope_page.close_page()
        except Exception:
            pass

        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IntegratedCommunicationPanel()
    window.show()
    sys.exit(app.exec_())

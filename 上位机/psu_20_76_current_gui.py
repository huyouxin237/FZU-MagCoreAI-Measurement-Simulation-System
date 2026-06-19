import os
import sys
import time
import pyvisa

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QGroupBox, QComboBox
)


# GW INSTEK PSU 20-76 参数
MAX_VOLTAGE = 20.0
MAX_CURRENT = 76.0


class PSU2076CurrentSource(QWidget):
    def __init__(self):
        super().__init__()

        self.rm = None
        self.inst = None

        # 从第一页 TNPC 通信控制页面读取/同步过来的磁芯参数
        # primary_turns: 原边匝数 Np
        # secondary_turns: 副边匝数 Ns
        # ae: 磁芯截面积 Ae，单位 mm²
        # le: 有效磁路长度 Le，单位 mm
        self.core_params = {}
        self.core_params_provider = None

        self.scan_values = []
        self.scan_index = 0
        self.scan_running = False
        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.apply_next_scan_point)

        self.setWindowTitle("GW INSTEK PSU 20-76 电流源控制")
        self.resize(620, 680)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # =====================================================
        # 连接区域
        # =====================================================
        conn_group = QGroupBox("电流源连接")
        conn_layout = QVBoxLayout(conn_group)

        self.addr_input = QLineEdit(os.environ.get("TNPC_CURRENT_SOURCE_VISA", ""))
        self.btn_connect = QPushButton("连接电流源")
        self.btn_disconnect = QPushButton("断开连接")

        conn_layout.addWidget(QLabel("VISA 地址，例如 ASRL::INSTR 或 USB/LAN VISA 资源："))
        conn_layout.addWidget(self.addr_input)

        conn_btn_layout = QHBoxLayout()
        conn_btn_layout.addWidget(self.btn_connect)
        conn_btn_layout.addWidget(self.btn_disconnect)
        conn_layout.addLayout(conn_btn_layout)

        main_layout.addWidget(conn_group)

        # =====================================================
        # 磁芯参数区域
        # =====================================================
        core_group = QGroupBox("磁芯参数与 Hdc 换算")
        core_layout = QGridLayout(core_group)

        self.core_info_label = QLabel("磁芯参数：未读取，请先在第一页输入磁芯参数")
        self.core_info_label.setWordWrap(True)

        self.btn_refresh_core = QPushButton("读取第一页磁芯参数")
        self.winding_combo = QComboBox()
        self.winding_combo.addItems(["原边 Np", "副边 Ns"])

        self.hdc_label = QLabel("当前 Hdc：-- A/m")
        self.hdc_label.setStyleSheet("font-weight: bold;")

        self.hdc_input = QLineEdit("0")
        self.btn_hdc_to_current = QPushButton("由 Hdc 计算电流")

        core_layout.addWidget(self.core_info_label, 0, 0, 1, 3)
        core_layout.addWidget(self.btn_refresh_core, 1, 0)
        core_layout.addWidget(QLabel("直流注入绕组："), 1, 1)
        core_layout.addWidget(self.winding_combo, 1, 2)
        core_layout.addWidget(self.hdc_label, 2, 0, 1, 3)
        core_layout.addWidget(QLabel("目标 Hdc，单位 A/m："), 3, 0)
        core_layout.addWidget(self.hdc_input, 3, 1)
        core_layout.addWidget(self.btn_hdc_to_current, 3, 2)

        main_layout.addWidget(core_group)

        # =====================================================
        # 单一值控制区域
        # =====================================================
        single_group = QGroupBox("单一值控制")
        single_layout = QGridLayout(single_group)

        self.current_input = QLineEdit("1.0")
        self.voltage_limit_input = QLineEdit("5.0")

        self.btn_set_current = QPushButton("设置电流")
        self.btn_set_voltage_limit = QPushButton("设置电压限值")
        self.btn_output_on = QPushButton("输出 ON")
        self.btn_output_off = QPushButton("输出 OFF")
        self.btn_safe_off = QPushButton("一键关闭输出")

        single_layout.addWidget(QLabel("设置电流 A，范围 0 ~ 76A："), 0, 0)
        single_layout.addWidget(self.current_input, 0, 1)
        single_layout.addWidget(self.btn_set_current, 0, 2)

        single_layout.addWidget(QLabel("电压限值 V，范围 0 ~ 20V："), 1, 0)
        single_layout.addWidget(self.voltage_limit_input, 1, 1)
        single_layout.addWidget(self.btn_set_voltage_limit, 1, 2)

        output_layout = QHBoxLayout()
        output_layout.addWidget(self.btn_output_on)
        output_layout.addWidget(self.btn_output_off)
        output_layout.addWidget(self.btn_safe_off)
        single_layout.addLayout(output_layout, 2, 0, 1, 3)

        main_layout.addWidget(single_group)

        # =====================================================
        # 直流偏置扫描区域
        # =====================================================
        scan_group = QGroupBox("直流偏置扫描控制")
        scan_layout = QGridLayout(scan_group)

        self.scan_start_hdc_input = QLineEdit("0")
        self.scan_stop_hdc_input = QLineEdit("1000")
        self.scan_step_hdc_input = QLineEdit("100")
        self.scan_dwell_input = QLineEdit("1.0")

        self.btn_start_scan = QPushButton("开始直流偏置扫描")
        self.btn_stop_scan = QPushButton("停止扫描并关闭输出")

        scan_layout.addWidget(QLabel("起始 Hdc A/m："), 0, 0)
        scan_layout.addWidget(self.scan_start_hdc_input, 0, 1)
        scan_layout.addWidget(QLabel("终止 Hdc A/m："), 0, 2)
        scan_layout.addWidget(self.scan_stop_hdc_input, 0, 3)

        scan_layout.addWidget(QLabel("步进 Hdc A/m："), 1, 0)
        scan_layout.addWidget(self.scan_step_hdc_input, 1, 1)
        scan_layout.addWidget(QLabel("每点停留 s："), 1, 2)
        scan_layout.addWidget(self.scan_dwell_input, 1, 3)

        scan_layout.addWidget(self.btn_start_scan, 2, 0, 1, 2)
        scan_layout.addWidget(self.btn_stop_scan, 2, 2, 1, 2)

        note = QLabel(
            "说明：Hdc = N × Idc / Le。Le 按第一页输入的 mm 自动换算为 m。"
            "扫描时会按照 Hdc 自动换算为直流注入电流。"
        )
        note.setWordWrap(True)
        scan_layout.addWidget(note, 3, 0, 1, 4)

        main_layout.addWidget(scan_group)

        # =====================================================
        # 状态栏
        # =====================================================
        self.status = QLabel("状态：未连接")
        self.status.setFrameStyle(QLabel.Panel | QLabel.Sunken)
        self.status.setMinimumHeight(26)
        main_layout.addWidget(self.status)

        # 信号绑定
        self.btn_connect.clicked.connect(self.connect_current_source)
        self.btn_disconnect.clicked.connect(self.disconnect_current_source)
        self.btn_refresh_core.clicked.connect(self.refresh_core_params)
        self.btn_hdc_to_current.clicked.connect(self.apply_hdc_to_current_input)

        self.btn_set_current.clicked.connect(self.set_current)
        self.btn_set_voltage_limit.clicked.connect(self.set_voltage_limit)
        self.btn_output_on.clicked.connect(self.output_on)
        self.btn_output_off.clicked.connect(self.output_off)
        self.btn_safe_off.clicked.connect(self.safe_output_off)

        self.btn_start_scan.clicked.connect(self.start_bias_scan)
        self.btn_stop_scan.clicked.connect(self.stop_bias_scan)

        self.current_input.textChanged.connect(self.update_hdc_display)
        self.winding_combo.currentIndexChanged.connect(self.update_hdc_display)

        self.update_core_info_label()
        self.update_hdc_display()
        self.update_connection_buttons()

    def update_connection_buttons(self):
        connected = self.inst is not None
        self.btn_connect.setEnabled(not connected)
        self.btn_disconnect.setEnabled(connected)

    # =========================================================
    # 磁芯参数同步与 Hdc 换算
    # =========================================================
    def set_core_params_provider(self, provider):
        """集成上位机调用：传入一个函数，用于从第一页实时读取磁芯参数。"""
        self.core_params_provider = provider
        self.refresh_core_params(show_message=False)

    def set_core_params(self, params):
        """集成上位机调用：第一页磁芯参数变化后同步到本页面。"""
        self.core_params = dict(params or {})
        self.update_core_info_label()
        self.update_hdc_display()

    def refresh_core_params(self, show_message=True):
        if self.core_params_provider is not None:
            try:
                self.set_core_params(self.core_params_provider())
                if show_message:
                    QMessageBox.information(self, "读取成功", "已读取第一页磁芯参数")
                return
            except Exception as e:
                if show_message:
                    QMessageBox.warning(self, "读取失败", str(e))
                return

        self.update_core_info_label()
        if show_message:
            QMessageBox.information(self, "提示", "当前没有绑定第一页参数读取函数，请先在第一页输入磁芯参数")

    def update_core_info_label(self):
        if not self.has_valid_core_params(show_message=False):
            self.core_info_label.setText("磁芯参数：未读取，请先在第一页输入磁芯参数")
            return

        self.core_info_label.setText(
            "磁芯参数："
            f"Np={self.core_params['primary_turns']}, "
            f"Ns={self.core_params['secondary_turns']}, "
            f"Ae={self.core_params['ae']} mm², "
            f"Le={self.core_params['le']} mm"
        )

    def has_valid_core_params(self, show_message=True):
        try:
            np_turns = int(self.core_params.get("primary_turns", 0))
            ns_turns = int(self.core_params.get("secondary_turns", 0))
            ae = float(self.core_params.get("ae", 0))
            le_mm = float(self.core_params.get("le", 0))
            ok = np_turns > 0 and ns_turns > 0 and ae > 0 and le_mm > 0
        except Exception:
            ok = False

        if not ok and show_message:
            QMessageBox.warning(self, "缺少磁芯参数", "请先在第一页点击“输入磁芯参数”，填写 Np、Ns、Ae、Le")

        return ok

    def selected_turns(self):
        if not self.has_valid_core_params(show_message=True):
            raise RuntimeError("缺少有效磁芯参数")

        if self.winding_combo.currentIndex() == 0:
            return int(self.core_params["primary_turns"]), "原边 Np"
        else:
            return int(self.core_params["secondary_turns"]), "副边 Ns"

    def current_to_hdc(self, current_a):
        """
        Hdc = N * Idc / Le
        Le 输入单位为 mm，这里换算为 m。
        输出单位：A/m。
        """
        turns, _ = self.selected_turns()
        le_m = float(self.core_params["le"]) / 1000.0
        return turns * float(current_a) / le_m

    def hdc_to_current(self, hdc_a_per_m):
        """
        Idc = Hdc * Le / N
        Le 输入单位为 mm，这里换算为 m。
        输出单位：A。
        """
        turns, _ = self.selected_turns()
        le_m = float(self.core_params["le"]) / 1000.0
        return float(hdc_a_per_m) * le_m / turns

    def format_hdc(self, hdc):
        return f"{hdc:.3f} A/m（{hdc / 1000.0:.6f} kA/m）"

    def update_hdc_display(self):
        if not self.has_valid_core_params(show_message=False):
            self.hdc_label.setText("当前 Hdc：-- A/m，请先在第一页输入磁芯参数")
            return

        try:
            current = float(self.current_input.text())
            hdc = self.current_to_hdc(current)
            _, winding_name = self.selected_turns()
            self.hdc_label.setText(f"当前 Hdc：{self.format_hdc(hdc)}，注入绕组：{winding_name}")
        except Exception:
            self.hdc_label.setText("当前 Hdc：-- A/m")

    def apply_hdc_to_current_input(self):
        try:
            hdc = float(self.hdc_input.text())
            current = self.hdc_to_current(hdc)

            if current < 0 or current > MAX_CURRENT:
                QMessageBox.warning(
                    self,
                    "换算超限",
                    f"Hdc={hdc} A/m 对应电流 {current:.6f} A，超出 0 ~ {MAX_CURRENT} A"
                )
                return

            self.current_input.setText(f"{current:.6f}")
            self.update_hdc_display()
            self.status.setText(f"状态：Hdc={self.format_hdc(hdc)} 已换算为电流 {current:.6f} A")

        except Exception as e:
            QMessageBox.warning(self, "换算失败", str(e))

    # =========================================================
    # 电流源通讯控制
    # =========================================================
    def connect_current_source(self):
        try:
            # 如果之前已经连接过，先释放旧会话，避免 ASRL 资源被自己占用
            if self.inst is not None or self.rm is not None:
                self.release_connection(send_off=True)

            addr = self.addr_input.text().strip()

            if not addr:
                QMessageBox.warning(self, "错误", "请输入 VISA 地址")
                self.update_connection_buttons()
                return

            # 优先使用 NI-VISA / IVI 后端
            try:
                self.rm = pyvisa.ResourceManager("@ivi")
            except Exception:
                self.rm = pyvisa.ResourceManager()

            self.inst = self.rm.open_resource(addr)
            self.inst.timeout = 10000

            # 如果是串口 ASRL 资源
            if addr.upper().startswith("ASRL"):
                self.inst.baud_rate = 9600
                self.inst.data_bits = 8
                self.inst.stop_bits = pyvisa.constants.StopBits.one
                self.inst.parity = pyvisa.constants.Parity.none
                self.inst.flow_control = pyvisa.constants.VI_ASRL_FLOW_NONE

            # PSU 系列一般用换行作为结束符
            self.inst.write_termination = "\n"
            self.inst.read_termination = "\n"

            self.status.setText("状态：电流源已连接")
            self.update_connection_buttons()
            QMessageBox.information(self, "连接成功", "电流源已连接")

        except Exception as e:
            self.inst = None
            try:
                if self.rm:
                    self.rm.close()
            except Exception:
                pass
            self.rm = None
            self.update_connection_buttons()
            QMessageBox.critical(self, "连接失败", str(e))

    def release_connection(self, send_off=True):
        """释放电流源 VISA 会话。send_off=True 时先尝试关闭输出。"""
        try:
            self.scan_timer.stop()
            self.scan_running = False
        except Exception:
            pass

        if self.inst is not None:
            if send_off:
                try:
                    self.inst.write_raw(b"OUTP OFF\n")
                    time.sleep(0.2)
                except Exception:
                    pass
            try:
                self.inst.close()
            except Exception:
                pass
            self.inst = None

        if self.rm is not None:
            try:
                self.rm.close()
            except Exception:
                pass
            self.rm = None

        self.update_connection_buttons()

    def disconnect_current_source(self):
        """手动断开电流源，断开前会先关闭输出。"""
        try:
            if self.inst is None and self.rm is None:
                self.status.setText("状态：电流源未连接")
                self.update_connection_buttons()
                return

            self.release_connection(send_off=True)
            self.status.setText("状态：电流源已断开，输出已关闭")
            QMessageBox.information(self, "断开成功", "电流源已断开，输出已关闭")

        except Exception as e:
            self.update_connection_buttons()
            QMessageBox.warning(self, "断开失败", str(e))

    def check_connected(self):
        if self.inst is None:
            raise RuntimeError("请先连接电流源")

    def send_cmd(self, cmd):
        self.check_connected()
        self.inst.write_raw((cmd + "\n").encode("ascii"))
        time.sleep(0.2)

    def parse_current_input(self):
        current = float(self.current_input.text())
        if current < 0 or current > MAX_CURRENT:
            raise ValueError(f"PSU 20-76 电流范围应为 0 ~ {MAX_CURRENT} A")
        return current

    def parse_voltage_limit_input(self):
        voltage = float(self.voltage_limit_input.text())
        if voltage < 0 or voltage > MAX_VOLTAGE:
            raise ValueError(f"PSU 20-76 电压限值范围应为 0 ~ {MAX_VOLTAGE} V")
        return voltage

    def set_current(self):
        try:
            self.check_connected()
            current = self.parse_current_input()

            self.send_cmd(f"SOUR:CURR {current}")
            self.update_hdc_display()

            if self.has_valid_core_params(show_message=False):
                hdc = self.current_to_hdc(current)
                self.status.setText(f"状态：已设置电流 {current} A，对应 Hdc={self.format_hdc(hdc)}")
            else:
                self.status.setText(f"状态：已设置电流 {current} A，Hdc 未计算")

        except Exception as e:
            QMessageBox.critical(self, "设置电流失败", str(e))

    def set_voltage_limit(self):
        try:
            self.check_connected()
            voltage = self.parse_voltage_limit_input()

            self.send_cmd(f"SOUR:VOLT {voltage}")
            self.status.setText(f"状态：已设置电压限值 {voltage} V")

        except Exception as e:
            QMessageBox.critical(self, "设置电压限值失败", str(e))

    def output_on(self):
        try:
            self.check_connected()
            voltage = self.parse_voltage_limit_input()
            current = self.parse_current_input()

            self.send_cmd(f"SOUR:VOLT {voltage}")
            self.send_cmd(f"SOUR:CURR {current}")
            self.send_cmd("OUTP ON")
            self.update_hdc_display()

            if self.has_valid_core_params(show_message=False):
                hdc = self.current_to_hdc(current)
                self.status.setText(
                    f"状态：输出已开启，电流 {current} A，电压限值 {voltage} V，Hdc={self.format_hdc(hdc)}"
                )
            else:
                self.status.setText(f"状态：输出已开启，电流 {current} A，电压限值 {voltage} V")

        except Exception as e:
            QMessageBox.critical(self, "输出开启失败", str(e))

    def output_off(self):
        try:
            self.check_connected()
            self.send_cmd("OUTP OFF")
            self.status.setText("状态：输出已关闭")

        except Exception as e:
            QMessageBox.critical(self, "输出关闭失败", str(e))

    def safe_output_off(self):
        """一键关闭输出：只做关闭输出，不修改电流和电压设置。"""
        try:
            self.check_connected()
            self.stop_bias_scan(send_off=False)
            self.send_cmd("OUTP OFF")
            self.status.setText("状态：已执行一键关闭输出")
            QMessageBox.information(self, "安全关闭", "电流源输出已关闭")

        except Exception as e:
            QMessageBox.critical(self, "一键关闭输出失败", str(e))

    # =========================================================
    # 直流偏置扫描控制
    # =========================================================
    def build_scan_values(self):
        start = float(self.scan_start_hdc_input.text())
        stop = float(self.scan_stop_hdc_input.text())
        step_abs = abs(float(self.scan_step_hdc_input.text()))

        if step_abs <= 0:
            raise ValueError("步进 Hdc 必须大于 0")

        if start == stop:
            return [start]

        direction = 1 if stop > start else -1
        step = direction * step_abs
        values = []
        value = start
        eps = step_abs * 1e-9

        if direction > 0:
            while value <= stop + eps:
                values.append(value)
                value += step
        else:
            while value >= stop - eps:
                values.append(value)
                value += step

        if values and values[-1] != stop:
            if (direction > 0 and values[-1] < stop) or (direction < 0 and values[-1] > stop):
                values.append(stop)

        return values

    def start_bias_scan(self):
        try:
            self.check_connected()
            if not self.has_valid_core_params(show_message=True):
                return

            voltage = self.parse_voltage_limit_input()
            dwell = float(self.scan_dwell_input.text())
            if dwell <= 0:
                raise ValueError("每点停留时间必须大于 0")

            values = self.build_scan_values()
            currents = [self.hdc_to_current(hdc) for hdc in values]

            for hdc, current in zip(values, currents):
                if current < 0 or current > MAX_CURRENT:
                    raise ValueError(
                        f"Hdc={hdc} A/m 对应电流 {current:.6f} A，超出 0 ~ {MAX_CURRENT} A"
                    )

            self.scan_values = values
            self.scan_index = 0
            self.scan_running = True
            self.scan_dwell_ms = int(dwell * 1000)

            self.send_cmd(f"SOUR:VOLT {voltage}")
            self.send_cmd("OUTP ON")

            self.status.setText(
                f"状态：开始直流偏置扫描，共 {len(values)} 点，电压限值 {voltage} V"
            )
            self.apply_next_scan_point()

        except Exception as e:
            self.scan_running = False
            self.scan_timer.stop()
            QMessageBox.critical(self, "直流偏置扫描启动失败", str(e))

    def apply_next_scan_point(self):
        try:
            if not self.scan_running:
                return

            if self.scan_index >= len(self.scan_values):
                self.scan_timer.stop()
                self.scan_running = False
                try:
                    self.send_cmd("OUTP OFF")
                except Exception:
                    pass
                self.status.setText("状态：直流偏置扫描完成，输出已关闭")
                return

            hdc = self.scan_values[self.scan_index]
            current = self.hdc_to_current(hdc)

            self.send_cmd(f"SOUR:CURR {current}")
            self.current_input.setText(f"{current:.6f}")
            self.hdc_input.setText(f"{hdc:.6f}")
            self.update_hdc_display()

            self.status.setText(
                f"状态：扫描第 {self.scan_index + 1}/{len(self.scan_values)} 点，"
                f"Hdc={self.format_hdc(hdc)}，Idc={current:.6f} A"
            )

            self.scan_index += 1
            self.scan_timer.start(self.scan_dwell_ms)

        except Exception as e:
            self.scan_timer.stop()
            self.scan_running = False
            QMessageBox.critical(self, "直流偏置扫描失败", str(e))

    def stop_bias_scan(self, send_off=True):
        self.scan_timer.stop()
        was_running = self.scan_running
        self.scan_running = False

        if send_off and self.inst is not None:
            try:
                self.send_cmd("OUTP OFF")
            except Exception:
                pass

        if was_running:
            self.status.setText("状态：直流偏置扫描已停止，输出已关闭")
        elif send_off:
            self.status.setText("状态：当前没有正在运行的直流偏置扫描")

    def close_page(self):
        """供集成上位机主窗口关闭时调用。"""
        try:
            self.release_connection(send_off=True)
        except Exception:
            pass

    def closeEvent(self, event):
        self.close_page()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = PSU2076CurrentSource()
    win.show()
    sys.exit(app.exec_())

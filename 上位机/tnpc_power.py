"""
TNPC v4 power supply module: Chroma 62012P-600-8 control + UI panel.
Two units: Power1 -> positive bus, Power2 -> negative bus.

Safety defaults:
  - OVP 70V, OCP 3A (programmed into hardware on connect)
  - Symmetric mode: both units output same voltage, both default to +V
  - IDN verified on connect (must contain "62012" or "62000")
"""
import time
import pyvisa

from PyQt5.QtWidgets import (
    QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QDoubleSpinBox, QCheckBox,
    QComboBox, QMessageBox
)


MAX_VOLTAGE = 600.0
MAX_CURRENT = 8.0
OVP_DEFAULT = 70.0    # over-voltage protection (hardware)
OCP_DEFAULT = 3.0     # over-current protection (hardware)
CMD_DELAY   = 0.05    # seconds between SCPI writes


class ChromaPower:
    """Chroma 62012P-600-8 电源的 pyvisa 薄封装。

    - connect(): 打开 VISA 资源 → 校验 *IDN? → 下发硬件级 OVP/OCP 保护
    - set_voltage/set_current: SCPI 命令写入（SOUR:VOLT, SOUR:CURR）
    - output_on/off: 切换输出继电器（CONF:OUTP ON/OFF）
    - close(): 断开前先强制输出 OFF
    OVP/OCP 在电源硬件层面，即使上位机崩溃仍会生效。
    """

    def __init__(self):
        self.inst = None
        self.addr = None

    def connect(self, addr, rm):
        """打开 VISA 资源、校验 IDN、设置硬件 OVP/OCP。

        IDN 必须包含 "62012" 或 "62000"，否则视为连错仪器并关闭资源。
        """
        inst = rm.open_resource(addr)
        inst.timeout = 5000
        try:
            # Verify IDN — reject wrong device before any other command
            idn = inst.query("*IDN?").strip()
            if ("62012" not in idn) and ("62000" not in idn):
                inst.close()
                raise ValueError(f"Unexpected IDN: {idn}")
        except Exception:
            try:
                inst.close()
            except Exception:
                pass
            raise

        self.inst = inst
        self.addr = addr

        # Hardware OVP/OCP — persistent protection independent of host software
        # Chroma 62000-P SCPI: CONF:OVP / CONF:OCP
        self._write(f"CONF:OVP {OVP_DEFAULT}")
        self._write(f"CONF:OCP {OCP_DEFAULT}")
        return idn

    def _write(self, cmd):
        if self.inst is None:
            raise RuntimeError("not connected")
        self.inst.write_raw((cmd + "\r\n").encode("ascii"))
        time.sleep(CMD_DELAY)

    def set_voltage(self, v):
        self._write(f"SOUR:VOLT {v}")

    def set_current(self, i):
        self._write(f"SOUR:CURR {i}")

    def output_on(self):
        self._write("CONF:OUTP ON")

    def output_off(self):
        self._write("CONF:OUTP OFF")

    def is_connected(self):
        return self.inst is not None

    def close(self):
        if self.inst is None:
            return
        try:
            self.output_off()
        except Exception:
            pass
        try:
            self.inst.close()
        except Exception:
            pass
        self.inst = None
        self.addr = None


def list_visa_resources():
    """枚举当前系统的所有 VISA 资源（USB / GPIB / LAN）。

    优先用 NI-VISA (@ivi)；失败则退回 pyvisa-py 默认后端。
    两者都失败时返回空列表。
    """
    try:
        rm = pyvisa.ResourceManager("@ivi")
        return list(rm.list_resources())
    except Exception:
        try:
            rm = pyvisa.ResourceManager()
            return list(rm.list_resources())
        except Exception:
            return []


# ============================================================
# UI: Power control panel (placed at top of main window)
# ============================================================
class PowerPanel(QGroupBox):
    """两台 Chroma 62012P-600-8 的统一控制面板（+母线 / -母线）。

    支持：
      - 对称模式（默认）：V1=V2，只需设一个值
      - 独立模式：V1/V2 分别设定
    扫描线程通过 set_voltage_both / output_on_both / output_off_both
    等 API 联动控制，不直接访问 UI 控件。
    emergency_off() 被主窗口的紧急停止按钮调用，绝不抛异常。
    """

    # Default VISA addresses (pre-filled, user can override via dropdown)
    DEFAULT_ADDR_P1 = "USB0::0x1698::0x0837::004000001534::INSTR"
    DEFAULT_ADDR_P2 = "USB0::0x1698::0x0837::004000000589::INSTR"

    def __init__(self, parent_window):
        super().__init__("Power Supplies (+bus / -bus)")
        self.pw = parent_window
        self.rm = None
        self.p1 = ChromaPower()
        self.p2 = ChromaPower()
        self.init_ui()

    def init_ui(self):
        # ================================================
        # 电源面板 UI：两行 VISA 地址（P1/P2 分行）
        # 右侧为 Scan USB / Connect 按钮（跨两行）
        # 下方依次为：对称模式、V1/V2/I 限值、操作按钮、状态
        # ================================================
        layout = QGridLayout(self)
        layout.setVerticalSpacing(4)
        layout.setHorizontalSpacing(8)

        # --- Row 0: P1 VISA 地址 ---
        layout.addWidget(QLabel("P1 VISA (+bus):"), 0, 0)
        self.addr1 = QComboBox()
        self.addr1.setEditable(True)
        self.addr1.addItem(self.DEFAULT_ADDR_P1)
        layout.addWidget(self.addr1, 0, 1, 1, 5)

        # --- Row 1: P2 VISA 地址 ---
        layout.addWidget(QLabel("P2 VISA (-bus):"), 1, 0)
        self.addr2 = QComboBox()
        self.addr2.setEditable(True)
        self.addr2.addItem(self.DEFAULT_ADDR_P2)
        layout.addWidget(self.addr2, 1, 1, 1, 5)

        # 右侧按钮：Scan USB 和 Connect 分别占两行的右上、右下
        self.scan_btn = QPushButton("Scan USB")
        self.scan_btn.clicked.connect(self.scan_visa)
        layout.addWidget(self.scan_btn, 0, 6)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        layout.addWidget(self.connect_btn, 1, 6)

        # --- Row 2: 对称模式 + 电压/电流设定 ---
        self.symmetric_chk = QCheckBox("Symmetric (P1=P2)")
        self.symmetric_chk.setChecked(True)
        self.symmetric_chk.toggled.connect(self.on_symmetric_toggled)
        layout.addWidget(self.symmetric_chk, 2, 0, 1, 2)

        layout.addWidget(QLabel("V1 (V):"), 2, 2)
        self.v1_spin = QDoubleSpinBox()
        self.v1_spin.setRange(0.0, MAX_VOLTAGE)
        self.v1_spin.setDecimals(2)
        self.v1_spin.setSingleStep(1.0)
        self.v1_spin.setValue(10.0)
        self.v1_spin.valueChanged.connect(self.on_v1_changed)
        layout.addWidget(self.v1_spin, 2, 3)

        layout.addWidget(QLabel("V2 (V):"), 2, 4)
        self.v2_spin = QDoubleSpinBox()
        self.v2_spin.setRange(0.0, MAX_VOLTAGE)
        self.v2_spin.setDecimals(2)
        self.v2_spin.setSingleStep(1.0)
        self.v2_spin.setValue(10.0)
        self.v2_spin.setEnabled(False)  # 对称模式下禁用 V2
        layout.addWidget(self.v2_spin, 2, 5)

        layout.addWidget(QLabel("I_lim (A):"), 2, 6)
        self.i_spin = QDoubleSpinBox()
        self.i_spin.setRange(0.0, MAX_CURRENT)
        self.i_spin.setDecimals(3)
        self.i_spin.setSingleStep(0.1)
        self.i_spin.setValue(0.5)
        layout.addWidget(self.i_spin, 2, 7)

        # --- Row 3: 操作按钮（Apply / ON / OFF） ---
        self.apply_btn = QPushButton("Apply V/I")
        self.apply_btn.clicked.connect(self.apply_setpoints)
        self.apply_btn.setEnabled(False)
        layout.addWidget(self.apply_btn, 3, 0, 1, 2)

        self.on_btn = QPushButton("Output ON (both)")
        self.on_btn.clicked.connect(self.output_on)
        self.on_btn.setEnabled(False)
        layout.addWidget(self.on_btn, 3, 2, 1, 3)

        self.off_btn = QPushButton("Output OFF (both)")
        self.off_btn.clicked.connect(self.output_off)
        self.off_btn.setEnabled(False)
        layout.addWidget(self.off_btn, 3, 5, 1, 3)

        # --- Row 4: 状态栏 ---
        self.status = QLabel("Disconnected")
        layout.addWidget(self.status, 4, 0, 1, 8)

    # -------------- slots --------------
    def scan_visa(self):
        resources = list_visa_resources()
        if not resources:
            QMessageBox.information(self, "Scan", "No VISA resources found.")
            return
        # Preserve currently typed text, repopulate dropdown
        for combo in (self.addr1, self.addr2):
            current = combo.currentText()
            combo.clear()
            for r in resources:
                combo.addItem(r)
            if current and current not in resources:
                combo.insertItem(0, current)
                combo.setCurrentIndex(0)

    def on_symmetric_toggled(self, checked):
        self.v2_spin.setEnabled(not checked)
        if checked:
            self.v2_spin.setValue(self.v1_spin.value())

    def on_v1_changed(self, value):
        if self.symmetric_chk.isChecked():
            self.v2_spin.blockSignals(True)
            self.v2_spin.setValue(value)
            self.v2_spin.blockSignals(False)

    def toggle_connection(self):
        if self.p1.is_connected() or self.p2.is_connected():
            self.disconnect_all()
            return
        self.connect_all()

    def connect_all(self):
        try:
            self.rm = pyvisa.ResourceManager("@ivi")
        except Exception:
            try:
                self.rm = pyvisa.ResourceManager()
            except Exception as e:
                QMessageBox.critical(self, "VISA Error", f"ResourceManager failed: {e}")
                return

        errors = []
        for ps, combo, name in ((self.p1, self.addr1, "P1"),
                                (self.p2, self.addr2, "P2")):
            addr = combo.currentText().strip()
            if not addr:
                errors.append(f"{name}: empty address")
                continue
            try:
                idn = ps.connect(addr, self.rm)
                self.status.setText(f"{name} connected: {idn[:40]}...")
            except Exception as e:
                errors.append(f"{name}: {e}")

        if errors:
            QMessageBox.warning(self, "Connection", "\n".join(errors))

        any_connected = self.p1.is_connected() or self.p2.is_connected()
        if any_connected:
            self.connect_btn.setText("Disconnect")
            self.apply_btn.setEnabled(True)
            self.on_btn.setEnabled(True)
            self.off_btn.setEnabled(True)
            self.status.setText(
                f"Connected  (OVP={OVP_DEFAULT}V, OCP={OCP_DEFAULT}A)"
            )

    def disconnect_all(self):
        self.p1.close()
        self.p2.close()
        if self.rm:
            try:
                self.rm.close()
            except Exception:
                pass
            self.rm = None
        self.connect_btn.setText("Connect")
        self.apply_btn.setEnabled(False)
        self.on_btn.setEnabled(False)
        self.off_btn.setEnabled(False)
        self.status.setText("Disconnected")

    def apply_setpoints(self):
        v1 = self.v1_spin.value()
        v2 = self.v2_spin.value() if not self.symmetric_chk.isChecked() else v1
        i  = self.i_spin.value()
        errors = []
        # Current limit first, then voltage (safer when ramping up)
        for ps, v, name in ((self.p1, v1, "P1"), (self.p2, v2, "P2")):
            if not ps.is_connected():
                continue
            try:
                ps.set_current(i)
                ps.set_voltage(v)
            except Exception as e:
                errors.append(f"{name}: {e}")
        if errors:
            QMessageBox.warning(self, "Apply", "\n".join(errors))
        else:
            self.status.setText(f"Applied: V1={v1:.2f}V V2={v2:.2f}V I_lim={i:.2f}A")

    def output_on(self):
        errors = []
        for ps, name in ((self.p1, "P1"), (self.p2, "P2")):
            if not ps.is_connected():
                continue
            try:
                ps.output_on()
            except Exception as e:
                errors.append(f"{name}: {e}")
        if errors:
            QMessageBox.warning(self, "Output ON", "\n".join(errors))
        else:
            self.status.setText("Output ON")

    def output_off(self):
        errors = []
        for ps, name in ((self.p1, "P1"), (self.p2, "P2")):
            if not ps.is_connected():
                continue
            try:
                ps.output_off()
            except Exception as e:
                errors.append(f"{name}: {e}")
        if errors:
            QMessageBox.warning(self, "Output OFF", "\n".join(errors))
        else:
            self.status.setText("Output OFF")

    # -------------- API used by scan / emergency stop --------------
    def emergency_off(self):
        """静默关闭两路输出，永不抛异常。

        用于紧急停止按钮 / Esc 快捷键 / closeEvent 等场景，
        不能因为一台电源通信失败影响另一台的关断。
        """
        for ps in (self.p1, self.p2):
            try:
                if ps.is_connected():
                    ps.output_off()
            except Exception:
                pass

    def set_voltage_both(self, v1, v2):
        """供扫描线程调用：同时给两台电源下发电压设定值。

        返回错误消息列表，空列表表示全部成功。
        """
        errors = []
        for ps, v, name in ((self.p1, v1, "P1"), (self.p2, v2, "P2")):
            if not ps.is_connected():
                errors.append(f"{name} not connected")
                continue
            try:
                ps.set_voltage(v)
            except Exception as e:
                errors.append(f"{name}: {e}")
        return errors

    def output_on_both(self):
        for ps in (self.p1, self.p2):
            if ps.is_connected():
                ps.output_on()

    def output_off_both(self):
        for ps in (self.p1, self.p2):
            if ps.is_connected():
                ps.output_off()

    def both_connected(self):
        return self.p1.is_connected() and self.p2.is_connected()

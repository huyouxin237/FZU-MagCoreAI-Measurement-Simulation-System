"""
TNPC v4 core module: UART protocol + scan thread + UI pages.
Merged from tnpc_protocol.py, tnpc_manual.py, tnpc_scan.py.
"""
import time
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QDoubleSpinBox, QSpinBox, QRadioButton,
    QButtonGroup, QGridLayout, QMessageBox, QProgressBar, QCheckBox,
    QComboBox
)
from PyQt5.QtGui import QFont


# ============================================================
# Protocol constants (must match DSP)
# ============================================================
FRAME_HEADER     = 0xAA
CMD_SET_CARRIER  = 0x01
CMD_SET_CMP_L    = 0x02
CMD_SET_CMP_H    = 0x03
CMD_SET_DEADTIME = 0x04
CMD_SET_MODE     = 0x05
CMD_APPLY        = 0x10
CMD_STOP_PWM     = 0x20
CMD_START_PWM    = 0x21
ACK = 0x06
NAK = 0x15

MODE_TRAPEZOIDAL = 0
MODE_TRIANGULAR  = 1

FREQ2CARRIER = 50e6   # 50MHz (EPWMCLK=100MHz, Up-Down mode)
BAUDRATE     = 4800   # v5: rolled back from 115200 to avoid host-side read/write
                      # jitter causing ACK misalignment (phantom NAK errors)

# Safety timing (seconds)
DISCHARGE_DELAY = 0.5   # wait after power OFF before touching PWM / params
POWER_SETTLE    = 0.2   # wait after OUTP ON for voltage to settle


def voltage_for_flux(B_pp, N, Ae_mm2, freq, duty_p):
    """根据目标峰峰磁密反算直流母线电压。

    由法拉第定律 V·t_on = N·Ae·ΔB 得出：
        V = ΔB · N · Ae · f / duty_p
    其中 t_on = duty_p / f 为正电压作用时间。
    Ae 输入单位为 mm²，内部转成 m²。
    """
    Ae = Ae_mm2 * 1e-6       # mm^2 -> m^2
    return B_pp * N * Ae * freq / duty_p


def send_command(ser, cmd, value):
    """向 DSP 发送一条 5 字节协议帧并同步等待 ACK/NAK。

    帧格式: [0xAA][CMD][VAL_H][VAL_L][CHK]
    校验:   CHK = CMD ^ VAL_H ^ VAL_L
    DSP 应答 0x06 = ACK（成功），0x15 = NAK（参数非法或校验失败）。
    任何非 ACK 都抛异常，由调用方处理。
    """
    val_h = (value >> 8) & 0xFF
    val_l = value & 0xFF
    chk = (cmd ^ val_h ^ val_l) & 0xFF
    frame = bytes([FRAME_HEADER, cmd, val_h, val_l, chk])
    ser.write(frame)
    resp = ser.read(1)
    if len(resp) == 0:
        raise TimeoutError("DSP no response")
    if resp[0] == NAK:
        raise ValueError(f"DSP NAK for cmd 0x{cmd:02X} val={value}")
    if resp[0] != ACK:
        raise ValueError(f"Unknown response: 0x{resp[0]:02X}")


def build_freq_list(freq_min, freq_max, pts_per_decade):
    """构造对数等距的频率列表，用于 Auto Scan 扫频。

    以 10³~10⁷ Hz 为范围上下界，按每 decade 指定点数取样，
    再用 [freq_min, freq_max] 做二次过滤。
    """
    freq_list = []
    for idx in range(int(3 * pts_per_decade), int(7 * pts_per_decade) + 1):
        logf = idx / pts_per_decade
        f = 10 ** logf
        if freq_min <= f <= freq_max:
            freq_list.append(f)
    return freq_list


def build_range_list(vmin, vmax, step):
    """构造线性等距的数值列表（duty/电压/磁密通用）。

    末端加 step * 0.01 容差，避免浮点误差漏掉右端点。
    """
    result = []
    v = vmin
    while v <= vmax + step * 0.01:
        result.append(round(v, 4))
        v += step
    return result


# ============================================================
# Background scan thread
# ============================================================

# Soft maximum bus voltage (used as default limit for flux-mode scan)
MAX_SAFE_VOLTAGE = 200.0


class ScanThread(QThread):
    """后台扫描线程：遍历 freq × dp × dn × 电压/磁密 四维网格。

    每个工作点的执行时序（带电源时）：
        1) 电源 OUTP OFF
        2) 等 DISCHARGE_DELAY 秒（母线电容通过绕组放电）
        3) 发送 PWM 参数 + APPLY + START_PWM
        4) 设定两台电源电压（对称）
        5) OUTP ON，等 POWER_SETTLE 秒稳定
        6) 发射 point_info 信号通知上层（供后续采集使用）

    任何异常发生时通过 finally 块强制关电源，保证安全。
    """
    progress = pyqtSignal(int, int)
    point_info = pyqtSignal(str)
    finished_signal = pyqtSignal()
    error = pyqtSignal(str)

    # Parameters (dict keys):
    #   is_triangle, deadtime
    #   freq_locked/fixed/min/max/pts_per_decade
    #   dp_locked/fixed/min/max/step
    #   dn_locked/fixed/min/max/step
    #   use_power (bool): if False, runs v3-style scan without power control
    #   power_mode: 'voltage' | 'flux'
    #   v_locked/fixed/min/max/step               (when power_mode == 'voltage')
    #   B_locked/fixed/min/max/step, N, Ae_mm2    (when power_mode == 'flux')
    #   i_limit                                   (current limit for both PSUs)
    #   power_panel: PowerPanel instance (for set_voltage_both / output_on_both / off)

    def __init__(self, ser, params):
        super().__init__()
        self.ser = ser
        self.params = params
        self._stop_flag = False

    def stop(self):
        """请求线程尽快停止。仅置标志位，不抢占当前工作点。"""
        self._stop_flag = True

    def _safe_stop_pwm_and_power(self, panel):
        """安全停机序列：先关电源 → 等放电 → 再停 PWM。

        发生扫描异常或电压越限时调用，保证不会在 PWM 停止瞬间
        电源仍带电导致母线无控制。
        """
        if panel is not None:
            try:
                panel.output_off_both()
            except Exception:
                pass
            time.sleep(DISCHARGE_DELAY)
        try:
            send_command(self.ser, CMD_STOP_PWM, 0)
        except Exception:
            pass

    def run(self):
        """线程主循环：构造扫描网格，按安全时序逐点下发参数。"""
        p = self.params
        deadtime = p['deadtime']
        is_triangle = p.get('is_triangle', False)
        mode = MODE_TRIANGULAR if is_triangle else MODE_TRAPEZOIDAL
        use_power = p.get('use_power', False)
        panel = p.get('power_panel', None) if use_power else None
        i_limit = p.get('i_limit', 0.5)

        # Build freq / dp / dn lists (same as before)
        if p.get('freq_locked', False):
            freq_list = [p['freq_fixed']]
        else:
            freq_list = build_freq_list(p['freq_min'], p['freq_max'], p['pts_per_decade'])

        if p.get('dp_locked', False):
            dp_list = [p['dp_fixed']]
        else:
            dp_list = build_range_list(p['dp_min'], p['dp_max'], p['dp_step'])

        if is_triangle:
            dn_list = [None]
        elif p.get('dn_locked', False):
            dn_list = [p['dn_fixed']]
        else:
            dn_list = build_range_list(p['dn_min'], p['dn_max'], p['dn_step'])

        # Build power setpoint list
        power_mode = p.get('power_mode', 'voltage')
        if not use_power:
            power_list = [None]
        elif power_mode == 'voltage':
            if p.get('v_locked', False):
                power_list = [p['v_fixed']]
            else:
                power_list = build_range_list(p['v_min'], p['v_max'], p['v_step'])
        else:  # flux
            if p.get('B_locked', False):
                power_list = [p['B_fixed']]
            else:
                power_list = build_range_list(p['B_min'], p['B_max'], p['B_step'])

        # Set current limit once before loop
        if use_power:
            try:
                if panel.p1.is_connected():
                    panel.p1.set_current(i_limit)
                if panel.p2.is_connected():
                    panel.p2.set_current(i_limit)
            except Exception as e:
                self.error.emit(f"Current limit failed: {e}")
                return

        # --- Count valid points ---
        total = 0
        for dp_val in dp_list:
            for dn_val in dn_list:
                dn_actual = (1.0 - dp_val) if is_triangle else dn_val
                if dp_val + dn_actual > 1.0:
                    continue
                for _freq in freq_list:
                    for _pw in power_list:
                        total += 1

        count = 0
        try:
            for dp_val in dp_list:
                if self._stop_flag: break
                for dn_val in dn_list:
                    if self._stop_flag: break
                    dn_actual = (1.0 - dp_val) if is_triangle else dn_val
                    if dp_val + dn_actual > 1.0:
                        continue
                    d0 = (1.0 - dp_val - dn_actual) / 2.0

                    for freq in freq_list:
                        if self._stop_flag: break

                        carrier = int(FREQ2CARRIER / freq + 0.5)
                        if is_triangle:
                            cmp_tri = int(carrier * dp_val + 0.5)
                            cmp_l = cmp_tri
                            cmp_h = cmp_tri
                        else:
                            cmp_l = int(carrier * dp_val + 0.5)
                            cmp_h = int(carrier * (1.0 - dn_actual) + 0.5)

                        for pw_val in power_list:
                            if self._stop_flag: break

                            # Compute target bus voltage
                            if not use_power:
                                v_target = None
                                info_tail = ""
                            elif power_mode == 'voltage':
                                v_target = pw_val
                                info_tail = f" V={v_target:.1f}V"
                            else:
                                N = p['N']
                                Ae = p['Ae_mm2']
                                v_target = voltage_for_flux(pw_val, N, Ae, freq, dp_val)
                                info_tail = f" B={pw_val*1000:.1f}mT V={v_target:.1f}V"
                                if v_target > p.get('v_max_soft', MAX_SAFE_VOLTAGE):
                                    self.error.emit(
                                        f"Computed V={v_target:.1f}V exceeds soft limit "
                                        f"({p.get('v_max_soft', MAX_SAFE_VOLTAGE):.1f}V) at "
                                        f"f={freq/1000:.1f}kHz dP={dp_val:.2f} B={pw_val*1000:.1f}mT"
                                    )
                                    self._safe_stop_pwm_and_power(panel)
                                    return

                            # --- Safe sequence: power OFF -> discharge -> set PWM -> PWM ON -> power ON ---
                            if use_power:
                                panel.output_off_both()
                                time.sleep(DISCHARGE_DELAY)

                            try:
                                send_command(self.ser, CMD_STOP_PWM, 0)
                                send_command(self.ser, CMD_SET_MODE, mode)
                                send_command(self.ser, CMD_SET_CARRIER, carrier)
                                send_command(self.ser, CMD_SET_CMP_L, cmp_l)
                                send_command(self.ser, CMD_SET_CMP_H, cmp_h)
                                send_command(self.ser, CMD_SET_DEADTIME, deadtime)
                                send_command(self.ser, CMD_APPLY, 0)
                                send_command(self.ser, CMD_START_PWM, 0)
                            except Exception as e:
                                self.error.emit(f"UART: {e}")
                                self._safe_stop_pwm_and_power(panel)
                                return

                            if use_power and v_target is not None:
                                errs = panel.set_voltage_both(v_target, v_target)
                                if errs:
                                    self.error.emit("; ".join(errs))
                                    self._safe_stop_pwm_and_power(panel)
                                    return
                                panel.output_on_both()
                                time.sleep(POWER_SETTLE)

                            count += 1
                            self.progress.emit(count, total)
                            info = (f"dP={dp_val:.2f} dN={dn_actual:.2f} d0={d0:.2f} "
                                    f"f={freq/1000:.1f}kHz carrier={carrier}{info_tail}")
                            self.point_info.emit(info)
                            time.sleep(0.05)
        finally:
            # Always leave in a safe state at thread exit
            if use_power:
                try:
                    panel.output_off_both()
                except Exception:
                    pass

        self.finished_signal.emit()


# ============================================================
# Manual control page
# ============================================================
class ManualPage(QWidget):
    """手动控制页：单点设置频率/占空比/死区后 Apply，再 Start/Stop PWM。

    左侧输入参数，右侧实时显示派生的 CARRIER/CMP_L/CMP_H/DT_TBCLK。
    触发 valueChanged 自动做本地校验，参数非法时禁用 Apply 按钮。
    """
    def __init__(self, parent_window):
        super().__init__()
        self.pw = parent_window
        self.init_ui()

    def init_ui(self):
        # ================================================
        # 初始化手动控制页面的 UI 布局
        # 左侧：输入参数（频率/duty/死区），右侧：只读派生值，下方：按钮
        # ================================================
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        manual_group = QGroupBox("Manual Control")
        g = QGridLayout()
        g.setVerticalSpacing(6)        # 压缩行间距
        g.setHorizontalSpacing(12)
        g.setContentsMargins(10, 10, 10, 10)

        g.addWidget(QLabel("Waveform:"), 0, 0)
        self.mode_trap = QRadioButton("梯形波")
        self.mode_tri = QRadioButton("三角波")
        self.mode_trap.setChecked(True)
        self.mode_group = QButtonGroup()
        self.mode_group.addButton(self.mode_trap)
        self.mode_group.addButton(self.mode_tri)
        self.mode_trap.toggled.connect(self.on_mode_changed)
        ml = QHBoxLayout()
        ml.addWidget(self.mode_trap)
        ml.addWidget(self.mode_tri)
        mw = QWidget()
        mw.setLayout(ml)
        g.addWidget(mw, 0, 1, 1, 2)

        g.addWidget(QLabel("Freq (kHz):"), 1, 0)
        self.freq_spin = QDoubleSpinBox()
        self.freq_spin.setRange(10.0, 500.0)
        self.freq_spin.setValue(50.0)
        self.freq_spin.setSingleStep(10.0)
        self.freq_spin.setDecimals(1)
        self.freq_spin.valueChanged.connect(self.on_param_changed)
        g.addWidget(self.freq_spin, 1, 1)

        g.addWidget(QLabel("duty_P (GA):"), 2, 0)
        self.dp_spin = QDoubleSpinBox()
        self.dp_spin.setRange(0.01, 0.99)
        self.dp_spin.setValue(0.20)
        self.dp_spin.setSingleStep(0.05)
        self.dp_spin.setDecimals(3)
        self.dp_spin.valueChanged.connect(self.on_param_changed)
        g.addWidget(self.dp_spin, 2, 1)

        g.addWidget(QLabel("duty_N (GB):"), 3, 0)
        self.dn_spin = QDoubleSpinBox()
        self.dn_spin.setRange(0.01, 0.99)
        self.dn_spin.setValue(0.20)
        self.dn_spin.setSingleStep(0.05)
        self.dn_spin.setDecimals(3)
        self.dn_spin.valueChanged.connect(self.on_param_changed)
        g.addWidget(self.dn_spin, 3, 1)

        g.addWidget(QLabel("duty_0 (G0):"), 4, 0)
        self.d0_label = QLabel("0.300")
        self.d0_label.setFont(QFont("Consolas", 10))
        g.addWidget(self.d0_label, 4, 1)

        g.addWidget(QLabel("Deadtime (ns):"), 5, 0)
        self.dt_spin = QSpinBox()
        self.dt_spin.setRange(10, 100)  # 1~10 TBCLK cycles @100MHz
        self.dt_spin.setValue(50)
        self.dt_spin.setSingleStep(10)
        g.addWidget(self.dt_spin, 5, 1)

        g.addWidget(QLabel("CARRIER:"), 1, 2)
        self.carrier_label = QLabel("1000")
        self.carrier_label.setFont(QFont("Consolas", 10))
        g.addWidget(self.carrier_label, 1, 3)

        g.addWidget(QLabel("CMP_L:"), 2, 2)
        self.cmpl_label = QLabel("200")
        self.cmpl_label.setFont(QFont("Consolas", 10))
        g.addWidget(self.cmpl_label, 2, 3)

        g.addWidget(QLabel("CMP_H:"), 3, 2)
        self.cmph_label = QLabel("800")
        self.cmph_label.setFont(QFont("Consolas", 10))
        g.addWidget(self.cmph_label, 3, 3)

        g.addWidget(QLabel("DT (TBCLK):"), 5, 2)
        self.dt_tbclk_label = QLabel("10")
        self.dt_tbclk_label.setFont(QFont("Consolas", 10))
        g.addWidget(self.dt_tbclk_label, 5, 3)

        self.valid_label = QLabel("")
        self.valid_label.setStyleSheet("color: red;")
        g.addWidget(self.valid_label, 6, 0, 1, 4)

        btn = QHBoxLayout()
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self.apply_params)
        self.apply_btn.setEnabled(False)
        btn.addWidget(self.apply_btn)

        self.start_btn = QPushButton("Start PWM")
        self.start_btn.clicked.connect(self.start_pwm)
        self.start_btn.setEnabled(False)
        btn.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop PWM")
        self.stop_btn.clicked.connect(self.stop_pwm)
        self.stop_btn.setEnabled(False)
        btn.addWidget(self.stop_btn)

        g.addLayout(btn, 7, 0, 1, 4)
        manual_group.setLayout(g)
        layout.addWidget(manual_group)
        layout.addStretch()            # 让 manual_group 停靠顶部，不再被拉伸

        self.on_param_changed()

    def set_connected(self, connected):
        self.start_btn.setEnabled(connected)
        self.stop_btn.setEnabled(connected)
        if connected:
            self.on_param_changed()
        else:
            self.apply_btn.setEnabled(False)

    def on_mode_changed(self):
        if self.mode_tri.isChecked():
            self.dn_spin.setEnabled(False)
            self.dn_spin.setValue(0)
        else:
            self.dn_spin.setEnabled(True)
        self.on_param_changed()

    def is_triangle(self):
        return self.mode_tri.isChecked()

    def on_param_changed(self):
        """参数输入变化时调用：重算派生值 + 做本地合法性校验。

        梯形波: duty_P + duty_N ≤ 1, CMP_L < CMP_H (三角波时两者相等)
        CARRIER 范围 100~5000 (对应频率 100kHz ~ 5MHz 上下限)
        校验不通过则禁用 Apply 按钮，错误信息在底部标红显示。
        """
        freq = self.freq_spin.value() * 1000
        dp = self.dp_spin.value()
        dt_ns = self.dt_spin.value()

        if self.mode_tri.isChecked():
            dn = 1.0 - dp
            self.dn_spin.blockSignals(True)
            self.dn_spin.setValue(dn)
            self.dn_spin.blockSignals(False)
            d0 = 0.0
        else:
            dn = self.dn_spin.value()
            d0 = (1.0 - dp - dn) / 2.0

        carrier = int(FREQ2CARRIER / freq + 0.5)
        if self.mode_tri.isChecked():
            cmp_tri = int(carrier * dp + 0.5)
            cmp_l = cmp_tri
            cmp_h = cmp_tri
        else:
            cmp_l = int(carrier * dp + 0.5)
            cmp_h = int(carrier * (1.0 - dn) + 0.5)
        dt_tbclk = int(dt_ns / 10.0 + 0.5)

        self.d0_label.setText(f"{d0:.3f}")
        self.carrier_label.setText(str(carrier))
        self.cmpl_label.setText(str(cmp_l))
        self.cmph_label.setText(str(cmp_h))
        self.dt_tbclk_label.setText(str(dt_tbclk))

        errors = []
        if dp <= 0:
            errors.append("duty_P must be > 0")
        if not self.mode_tri.isChecked():
            if dn <= 0:
                errors.append("duty_N must be > 0")
            if dp + dn > 1.0:
                errors.append("duty_P + duty_N > 1.0")
            if d0 < 0:
                errors.append("duty_0 < 0")
            if cmp_l >= cmp_h:
                errors.append("CMP_L >= CMP_H (unsafe)")
        if carrier < 100:
            errors.append("CARRIER < 100")
        if carrier > 5000:
            errors.append("CARRIER > 5000")

        if errors:
            self.valid_label.setText(" | ".join(errors))
            self.valid_label.setStyleSheet("color: red;")
            self.apply_btn.setEnabled(False)
        else:
            self.valid_label.setText("Parameters OK")
            self.valid_label.setStyleSheet("color: green;")
            ser = self.pw.ser
            self.apply_btn.setEnabled(ser is not None and ser.is_open)

    def apply_params(self):
        """下发当前 UI 参数到 DSP：依次设 MODE/CARRIER/CMP_L/CMP_H/DEADTIME 再 APPLY。

        注意：每条命令都是同步的（等 ACK 再发下一条），任何 NAK 都会抛异常。
        DSP 端的 APPLY 做完整性校验（mode 对称性、cmp 关系），若失败仍会 NAK。
        """
        ser = self.pw.ser
        if not ser or not ser.is_open:
            return
        freq = self.freq_spin.value() * 1000
        dp = self.dp_spin.value()
        dn = self.dn_spin.value()
        dt_ns = self.dt_spin.value()
        mode = MODE_TRIANGULAR if self.mode_tri.isChecked() else MODE_TRAPEZOIDAL

        carrier = int(FREQ2CARRIER / freq + 0.5)
        if self.mode_tri.isChecked():
            cmp_tri = int(carrier * dp + 0.5)
            cmp_l = cmp_tri
            cmp_h = cmp_tri
        else:
            cmp_l = int(carrier * dp + 0.5)
            cmp_h = int(carrier * (1.0 - dn) + 0.5)
        dt_tbclk = int(dt_ns / 10.0 + 0.5)

        try:
            send_command(ser, CMD_SET_MODE, mode)
            send_command(ser, CMD_SET_CARRIER, carrier)
            send_command(ser, CMD_SET_CMP_L, cmp_l)
            send_command(ser, CMD_SET_CMP_H, cmp_h)
            send_command(ser, CMD_SET_DEADTIME, dt_tbclk)
            send_command(ser, CMD_APPLY, 0)
            self.pw.statusBar().showMessage(
                f"Applied: f={freq/1000:.1f}kHz dP={dp:.3f} dN={dn:.3f} "
                f"CARRIER={carrier} CMP_L={cmp_l} CMP_H={cmp_h}")
        except Exception as e:
            QMessageBox.warning(self, "Communication Error", str(e))

    def start_pwm(self):
        ser = self.pw.ser
        if not ser:
            return
        try:
            send_command(ser, CMD_START_PWM, 0)
            self.pw.statusBar().showMessage("PWM Started")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def stop_pwm(self):
        ser = self.pw.ser
        if not ser:
            return
        try:
            send_command(ser, CMD_STOP_PWM, 0)
            self.pw.statusBar().showMessage("PWM Stopped")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))


# ============================================================
# Auto scan page
# ============================================================
class ScanPage(QWidget):
    """自动扫描页：支持频率/duty_P/duty_N/电压/磁密 五维扫描。

    每一维都可通过 Lock 复选框固定为单点，其余维度展开为等距网格。
    "DC Bus" 分组框可选勾，勾选后扫描过程自动控制两台电源输出。
    """
    def __init__(self, parent_window):
        super().__init__()
        self.pw = parent_window
        self.scan_thread = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        mode_group = QGroupBox("Scan Waveform")
        mode_layout = QHBoxLayout()
        self.mode_trap = QRadioButton("梯形波")
        self.mode_tri = QRadioButton("三角波")
        self.mode_trap.setChecked(True)
        self.mode_btn_group = QButtonGroup()
        self.mode_btn_group.addButton(self.mode_trap)
        self.mode_btn_group.addButton(self.mode_tri)
        self.mode_trap.toggled.connect(self.on_mode_changed)
        mode_layout.addWidget(self.mode_trap)
        mode_layout.addWidget(self.mode_tri)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        freq_group = QGroupBox("Frequency")
        fg = QGridLayout()

        self.freq_lock = QCheckBox("Lock")
        self.freq_lock.toggled.connect(self.on_freq_lock)
        fg.addWidget(self.freq_lock, 0, 0)

        fg.addWidget(QLabel("Fixed (kHz):"), 0, 1)
        self.freq_fixed = QDoubleSpinBox()
        self.freq_fixed.setRange(10, 500)
        self.freq_fixed.setValue(100)
        self.freq_fixed.setDecimals(1)
        self.freq_fixed.setEnabled(False)
        fg.addWidget(self.freq_fixed, 0, 2)

        fg.addWidget(QLabel("Min (kHz):"), 1, 0)
        self.freq_min = QDoubleSpinBox()
        self.freq_min.setRange(10, 500)
        self.freq_min.setValue(50)
        self.freq_min.setDecimals(0)
        fg.addWidget(self.freq_min, 1, 1)

        fg.addWidget(QLabel("Max (kHz):"), 1, 2)
        self.freq_max = QDoubleSpinBox()
        self.freq_max.setRange(10, 500)
        self.freq_max.setValue(500)
        self.freq_max.setDecimals(0)
        fg.addWidget(self.freq_max, 1, 3)

        fg.addWidget(QLabel("Pts/decade:"), 1, 4)
        self.freq_pts = QSpinBox()
        self.freq_pts.setRange(1, 50)
        self.freq_pts.setValue(10)
        fg.addWidget(self.freq_pts, 1, 5)

        freq_group.setLayout(fg)
        layout.addWidget(freq_group)

        dp_group = QGroupBox("duty_P (GA)")
        dpg = QGridLayout()

        self.dp_lock = QCheckBox("Lock")
        self.dp_lock.toggled.connect(self.on_dp_lock)
        dpg.addWidget(self.dp_lock, 0, 0)

        dpg.addWidget(QLabel("Fixed:"), 0, 1)
        self.dp_fixed = QDoubleSpinBox()
        self.dp_fixed.setRange(0.01, 0.99)
        self.dp_fixed.setValue(0.3)
        self.dp_fixed.setSingleStep(0.05)
        self.dp_fixed.setDecimals(2)
        self.dp_fixed.setEnabled(False)
        dpg.addWidget(self.dp_fixed, 0, 2)

        dpg.addWidget(QLabel("Min:"), 1, 0)
        self.dp_min = QDoubleSpinBox()
        self.dp_min.setRange(0.01, 0.99)
        self.dp_min.setValue(0.1)
        self.dp_min.setSingleStep(0.05)
        self.dp_min.setDecimals(2)
        dpg.addWidget(self.dp_min, 1, 1)

        dpg.addWidget(QLabel("Max:"), 1, 2)
        self.dp_max = QDoubleSpinBox()
        self.dp_max.setRange(0.01, 0.99)
        self.dp_max.setValue(0.5)
        self.dp_max.setSingleStep(0.05)
        self.dp_max.setDecimals(2)
        dpg.addWidget(self.dp_max, 1, 3)

        dpg.addWidget(QLabel("Step:"), 1, 4)
        self.dp_step = QDoubleSpinBox()
        self.dp_step.setRange(0.01, 0.5)
        self.dp_step.setValue(0.1)
        self.dp_step.setSingleStep(0.05)
        self.dp_step.setDecimals(2)
        dpg.addWidget(self.dp_step, 1, 5)

        dp_group.setLayout(dpg)
        layout.addWidget(dp_group)

        self.dn_group = QGroupBox("duty_N (GB)")
        dng = QGridLayout()

        self.dn_lock = QCheckBox("Lock")
        self.dn_lock.toggled.connect(self.on_dn_lock)
        dng.addWidget(self.dn_lock, 0, 0)

        dng.addWidget(QLabel("Fixed:"), 0, 1)
        self.dn_fixed = QDoubleSpinBox()
        self.dn_fixed.setRange(0.01, 0.99)
        self.dn_fixed.setValue(0.3)
        self.dn_fixed.setSingleStep(0.05)
        self.dn_fixed.setDecimals(2)
        self.dn_fixed.setEnabled(False)
        dng.addWidget(self.dn_fixed, 0, 2)

        dng.addWidget(QLabel("Min:"), 1, 0)
        self.dn_min = QDoubleSpinBox()
        self.dn_min.setRange(0.01, 0.99)
        self.dn_min.setValue(0.1)
        self.dn_min.setSingleStep(0.05)
        self.dn_min.setDecimals(2)
        dng.addWidget(self.dn_min, 1, 1)

        dng.addWidget(QLabel("Max:"), 1, 2)
        self.dn_max = QDoubleSpinBox()
        self.dn_max.setRange(0.01, 0.99)
        self.dn_max.setValue(0.5)
        self.dn_max.setSingleStep(0.05)
        self.dn_max.setDecimals(2)
        dng.addWidget(self.dn_max, 1, 3)

        dng.addWidget(QLabel("Step:"), 1, 4)
        self.dn_step = QDoubleSpinBox()
        self.dn_step.setRange(0.01, 0.5)
        self.dn_step.setValue(0.1)
        self.dn_step.setSingleStep(0.05)
        self.dn_step.setDecimals(2)
        dng.addWidget(self.dn_step, 1, 5)

        self.dn_group.setLayout(dng)
        layout.addWidget(self.dn_group)

        dt_layout = QHBoxLayout()
        dt_layout.addWidget(QLabel("Deadtime (ns):"))
        self.dt_spin = QSpinBox()
        self.dt_spin.setRange(10, 100)  # 1~10 TBCLK cycles @100MHz
        self.dt_spin.setValue(50)
        self.dt_spin.setSingleStep(10)
        dt_layout.addWidget(self.dt_spin)
        dt_layout.addStretch()
        layout.addLayout(dt_layout)

        # ---------------- Power / Flux scan ----------------
        self.power_group = QGroupBox("DC Bus (disabled if power not connected)")
        self.power_group.setCheckable(True)
        self.power_group.setChecked(False)
        pg = QGridLayout()

        pg.addWidget(QLabel("Source:"), 0, 0)
        self.psrc_volt = QRadioButton("Voltage")
        self.psrc_flux = QRadioButton("磁密")
        self.psrc_volt.setChecked(True)
        self.psrc_group = QButtonGroup()
        self.psrc_group.addButton(self.psrc_volt)
        self.psrc_group.addButton(self.psrc_flux)
        self.psrc_volt.toggled.connect(self.on_psrc_changed)
        pg.addWidget(self.psrc_volt, 0, 1)
        pg.addWidget(self.psrc_flux, 0, 2)

        pg.addWidget(QLabel("I_lim (A):"), 0, 3)
        self.p_ilim = QDoubleSpinBox()
        self.p_ilim.setRange(0.01, 8.0)
        self.p_ilim.setDecimals(2)
        self.p_ilim.setSingleStep(0.1)
        self.p_ilim.setValue(0.5)
        pg.addWidget(self.p_ilim, 0, 4)

        pg.addWidget(QLabel("V_max_soft (V):"), 0, 5)
        self.p_vmax = QDoubleSpinBox()
        self.p_vmax.setRange(1.0, 600.0)
        self.p_vmax.setDecimals(1)
        self.p_vmax.setValue(70.0)
        pg.addWidget(self.p_vmax, 0, 6)

        # Voltage sweep row
        self.v_lock = QCheckBox("Lock")
        self.v_lock.toggled.connect(self.on_v_lock)
        pg.addWidget(self.v_lock, 1, 0)
        pg.addWidget(QLabel("V Fixed:"), 1, 1)
        self.v_fixed = QDoubleSpinBox()
        self.v_fixed.setRange(0, 600); self.v_fixed.setDecimals(1); self.v_fixed.setValue(10)
        self.v_fixed.setEnabled(False)
        pg.addWidget(self.v_fixed, 1, 2)
        pg.addWidget(QLabel("Min:"), 1, 3)
        self.v_min = QDoubleSpinBox(); self.v_min.setRange(0,600); self.v_min.setDecimals(1); self.v_min.setValue(10)
        pg.addWidget(self.v_min, 1, 4)
        pg.addWidget(QLabel("Max:"), 1, 5)
        self.v_max = QDoubleSpinBox(); self.v_max.setRange(0,600); self.v_max.setDecimals(1); self.v_max.setValue(50)
        pg.addWidget(self.v_max, 1, 6)
        pg.addWidget(QLabel("Step:"), 1, 7)
        self.v_step = QDoubleSpinBox(); self.v_step.setRange(0.1,100); self.v_step.setDecimals(1); self.v_step.setValue(10)
        pg.addWidget(self.v_step, 1, 8)

        # Flux sweep row (units in mT; converted to T internally)
        self.b_lock = QCheckBox("Lock")
        self.b_lock.toggled.connect(self.on_b_lock)
        pg.addWidget(self.b_lock, 2, 0)
        pg.addWidget(QLabel("磁密 Fixed (mT):"), 2, 1)
        self.b_fixed = QDoubleSpinBox()
        self.b_fixed.setRange(0.1, 2000); self.b_fixed.setDecimals(1); self.b_fixed.setValue(50)
        self.b_fixed.setEnabled(False)
        pg.addWidget(self.b_fixed, 2, 2)
        pg.addWidget(QLabel("Min (mT):"), 2, 3)
        self.b_min = QDoubleSpinBox(); self.b_min.setRange(0.1, 2000); self.b_min.setDecimals(1); self.b_min.setValue(20)
        pg.addWidget(self.b_min, 2, 4)
        pg.addWidget(QLabel("Max (mT):"), 2, 5)
        self.b_max = QDoubleSpinBox(); self.b_max.setRange(0.1, 2000); self.b_max.setDecimals(1); self.b_max.setValue(100)
        pg.addWidget(self.b_max, 2, 6)
        pg.addWidget(QLabel("Step (mT):"), 2, 7)
        self.b_step = QDoubleSpinBox(); self.b_step.setRange(0.1, 500); self.b_step.setDecimals(1); self.b_step.setValue(20)
        pg.addWidget(self.b_step, 2, 8)

        # Core parameters (only needed in flux mode)
        pg.addWidget(QLabel("N (turns):"), 3, 0)
        self.b_N = QSpinBox(); self.b_N.setRange(1, 999); self.b_N.setValue(10)
        pg.addWidget(self.b_N, 3, 1)
        pg.addWidget(QLabel("Ae (mm²):"), 3, 2)
        self.b_Ae = QDoubleSpinBox(); self.b_Ae.setRange(0.1, 10000); self.b_Ae.setDecimals(2); self.b_Ae.setValue(100)
        pg.addWidget(self.b_Ae, 3, 3)

        self.power_group.setLayout(pg)
        layout.addWidget(self.power_group)
        self.on_psrc_changed()  # set initial enable state

        # ---------------- Control buttons ----------------
        btn_layout = QHBoxLayout()
        self.scan_start_btn = QPushButton("Start Scan")
        self.scan_start_btn.clicked.connect(self.start_scan)
        self.scan_start_btn.setEnabled(False)
        btn_layout.addWidget(self.scan_start_btn)

        self.scan_stop_btn = QPushButton("Stop Scan")
        self.scan_stop_btn.clicked.connect(self.stop_scan)
        self.scan_stop_btn.setEnabled(False)
        btn_layout.addWidget(self.scan_stop_btn)
        layout.addLayout(btn_layout)

        self.scan_progress = QProgressBar()
        layout.addWidget(self.scan_progress)

        self.scan_info = QLabel("")
        self.scan_info.setFont(QFont("Consolas", 9))
        layout.addWidget(self.scan_info)

        layout.addStretch()

    def set_connected(self, connected):
        self.scan_start_btn.setEnabled(connected)

    def on_mode_changed(self):
        is_tri = self.mode_tri.isChecked()
        self.dn_group.setEnabled(not is_tri)

    def on_freq_lock(self, checked):
        self.freq_fixed.setEnabled(checked)
        self.freq_min.setEnabled(not checked)
        self.freq_max.setEnabled(not checked)
        self.freq_pts.setEnabled(not checked)

    def on_dp_lock(self, checked):
        self.dp_fixed.setEnabled(checked)
        self.dp_min.setEnabled(not checked)
        self.dp_max.setEnabled(not checked)
        self.dp_step.setEnabled(not checked)

    def on_dn_lock(self, checked):
        self.dn_fixed.setEnabled(checked)
        self.dn_min.setEnabled(not checked)
        self.dn_max.setEnabled(not checked)
        self.dn_step.setEnabled(not checked)

    def on_psrc_changed(self):
        is_volt = self.psrc_volt.isChecked()
        # Voltage row
        self.v_lock.setEnabled(is_volt)
        self.v_fixed.setEnabled(is_volt and self.v_lock.isChecked())
        for w in (self.v_min, self.v_max, self.v_step):
            w.setEnabled(is_volt and not self.v_lock.isChecked())
        # Flux row
        self.b_lock.setEnabled(not is_volt)
        self.b_fixed.setEnabled((not is_volt) and self.b_lock.isChecked())
        for w in (self.b_min, self.b_max, self.b_step):
            w.setEnabled((not is_volt) and not self.b_lock.isChecked())
        self.b_N.setEnabled(not is_volt)
        self.b_Ae.setEnabled(not is_volt)

    def on_v_lock(self, checked):
        if self.psrc_volt.isChecked():
            self.v_fixed.setEnabled(checked)
            self.v_min.setEnabled(not checked)
            self.v_max.setEnabled(not checked)
            self.v_step.setEnabled(not checked)

    def on_b_lock(self, checked):
        if self.psrc_flux.isChecked():
            self.b_fixed.setEnabled(checked)
            self.b_min.setEnabled(not checked)
            self.b_max.setEnabled(not checked)
            self.b_step.setEnabled(not checked)

    def start_scan(self):
        """点击 Start Scan 时触发：收集 UI 参数、创建后台线程、连接信号。

        若勾选 DC Bus 但电源未连接，直接拒绝启动并弹窗提示。
        磁密输入 mT 在此处统一转成 T 传给线程。
        """
        ser = self.pw.ser
        if not ser or not ser.is_open:
            return

        is_tri = self.mode_tri.isChecked()
        use_power = self.power_group.isChecked()
        power_panel = getattr(self.pw, 'power_panel', None)

        if use_power:
            if power_panel is None or not power_panel.both_connected():
                QMessageBox.warning(self, "Scan",
                    "DC Bus sweep requires both power supplies to be connected.")
                return

        params = {
            'is_triangle': is_tri,
            'deadtime': int(self.dt_spin.value() / 10.0 + 0.5),
            'freq_locked': self.freq_lock.isChecked(),
            'freq_fixed': self.freq_fixed.value() * 1000,
            'freq_min': self.freq_min.value() * 1000,
            'freq_max': self.freq_max.value() * 1000,
            'pts_per_decade': self.freq_pts.value(),
            'dp_locked': self.dp_lock.isChecked(),
            'dp_fixed': self.dp_fixed.value(),
            'dp_min': self.dp_min.value(),
            'dp_max': self.dp_max.value(),
            'dp_step': self.dp_step.value(),
            'dn_locked': self.dn_lock.isChecked() if not is_tri else True,
            'dn_fixed': self.dn_fixed.value() if not is_tri else 0,
            'dn_min': self.dn_min.value() if not is_tri else 0,
            'dn_max': self.dn_max.value() if not is_tri else 0,
            'dn_step': self.dn_step.value() if not is_tri else 0.1,
            'use_power': use_power,
            'power_panel': power_panel,
            'power_mode': 'voltage' if self.psrc_volt.isChecked() else 'flux',
            'i_limit': self.p_ilim.value(),
            'v_max_soft': self.p_vmax.value(),
            'v_locked': self.v_lock.isChecked(),
            'v_fixed': self.v_fixed.value(),
            'v_min': self.v_min.value(),
            'v_max': self.v_max.value(),
            'v_step': self.v_step.value(),
            'B_locked': self.b_lock.isChecked(),
            'B_fixed': self.b_fixed.value() / 1000.0,  # mT -> T
            'B_min': self.b_min.value() / 1000.0,
            'B_max': self.b_max.value() / 1000.0,
            'B_step': self.b_step.value() / 1000.0,
            'N': self.b_N.value(),
            'Ae_mm2': self.b_Ae.value(),
        }

        self.scan_thread = ScanThread(ser, params)
        self.scan_thread.progress.connect(self.on_progress)
        self.scan_thread.point_info.connect(self.on_info)
        self.scan_thread.finished_signal.connect(self.on_finished)
        self.scan_thread.error.connect(self.on_error)

        self.scan_start_btn.setEnabled(False)
        self.scan_stop_btn.setEnabled(True)
        self.scan_thread.start()

    def stop_scan(self):
        if self.scan_thread:
            self.scan_thread.stop()

    def on_progress(self, current, total):
        self.scan_progress.setMaximum(total)
        self.scan_progress.setValue(current)

    def on_info(self, info):
        self.scan_info.setText(info)
        self.pw.statusBar().showMessage(f"Scanning: {info}")

    def on_finished(self):
        self.scan_start_btn.setEnabled(True)
        self.scan_stop_btn.setEnabled(False)
        self.scan_progress.setValue(0)
        self.pw.statusBar().showMessage("Scan completed")

    def on_error(self, msg):
        self.scan_start_btn.setEnabled(True)
        self.scan_stop_btn.setEnabled(False)
        QMessageBox.warning(self, "Scan Error", msg)

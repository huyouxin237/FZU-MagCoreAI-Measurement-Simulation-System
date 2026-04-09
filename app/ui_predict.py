import re
import numpy as np
import streamlit as st
import pandas as pd

from magnet import config as c
from magnet.constants import material_list, material_manufacturers, material_extra
from magnet.io import load_dataframe
from magnet.plots import waveform_visualization, waveform_visualization_2axes, plot_core_loss, \
    cycle_points_sinusoidal, cycle_points_trapezoidal
from magnet.core import core_loss_default, core_loss_arbitrary
from magnet.constants import core_loss_range


# 将 DataFrame 转换为 CSV 格式，用于下载
def convert_df(df):
    return df.to_csv().encode('utf-8')


def ui_core_loss_predict(m):
    """
    MagNet 智能表单 - 核心损耗预测（中文化版本）
    此函数生成交互式界面，用于不同材料与波形下的磁芯损耗计算。
    """

    # 页面标题与介绍
    st.title('用于交互式设计的 MagNet 智能表单')
    st.markdown("""---""")

    # 输入部分
    st.header(f'输入：案例 {m}')
    col1, col2 = st.columns(2)

    with col2:
        excitation = st.selectbox(
            f'激励波形类型：', ('正弦波', '三角波', '梯形波', '任意波形'),
            key=f'excitation {m}')

    with col1:
        material = st.selectbox(
            f'磁性材料：',
            material_list,
            index=9,
            key=f'material {m}')

    mu_relative = material_extra[material][0]
    df = load_dataframe(material)  # 加载数据以确定参数范围

    with col1:
        freq = st.slider(
            "频率 (kHz)",
            10,
            1000,
            200,
            step=1,
            key=f'freq {m}') * 1e3  # 前端显示单位为 kHz，内部计算使用 Hz
        if freq < min(df['Frequency']):
            st.warning(f"模型尚未在 {round(min(df['Frequency']) * 1e-3)} kHz 以下训练，MagNet AI 将进行外推计算。")
        if freq > max(df['Frequency']):
            st.warning(f"模型尚未在 {round(max(df['Frequency']) * 1e-3)} kHz 以上训练，MagNet AI 将进行外推计算。")

        # 任意波形输入模式
        if excitation == "任意波形":
            flux_string_militesla = st.text_input(
                f'波形模式 - 交流磁通密度 (mT)',
                [0, 150, 0, -20, -27, -20, 0],
                key=f'flux {m}')
            duty_string_percentage = st.text_input(
                f'波形模式 - 占空比 (%)',
                [0, 50, 60, 65, 70, 75, 80],
                key=f'duty {m}')
            duty_read = [float(i) / 100 for i in re.findall(r"[-+]?\d*\.?\d+|[-+]?\d+", duty_string_percentage)]
            flux_read = [float(i) * 1e-3 for i in re.findall(r"[-+]?\d*\.?\d+|[-+]?\d+", flux_string_militesla)]
            duty_read.append(1)
            flux_read.append(flux_read[0])
            flux_vector = np.array(flux_read)
            duty_vector = np.array(duty_read)

            flag_inputs_ok = 1  # 用于检查输入是否有效
            if len(duty_vector) != len(flux_vector):
                flag_inputs_ok = 0
                st.error('磁通与占空比数组长度不一致，请修改后再试。')
            if max(duty_vector) > 1:
                flag_inputs_ok = 0
                st.error('占空比应小于 100%，请修正输入。')
            if min(duty_vector) < 0:
                flag_inputs_ok = 0
                st.error('占空比应为正值，请修正输入。')
            flag_duty_wrong = 0
            for i in range(0, len(duty_vector) - 1):
                if duty_vector[i] >= duty_vector[i + 1]:
                    flag_duty_wrong = 1
            if flag_duty_wrong == 1:
                flag_inputs_ok = 0
                st.error('占空比必须递增，请移除 100% 占空比对应项。')
            if flag_inputs_ok == 0:
                st.subheader('波形设为 0，请修正上方错误后继续。')
                duty_vector = [0, 1]
                flux_vector = [0, 0]

            # 检查是否存在次级磁滞回路
            flag_minor_loop = 0
            if np.argmin(flux_vector) < np.argmax(flux_vector):
                for i in range(np.argmin(flux_vector), np.argmax(flux_vector)):
                    if flux_vector[i + 1] < flux_vector[i]:
                        flag_minor_loop = 1
                for i in range(np.argmax(flux_vector), len(flux_vector) - 1):
                    if flux_vector[i + 1] > flux_vector[i]:
                        flag_minor_loop = 1
                for i in range(0, np.argmin(flux_vector)):
                    if flux_vector[i + 1] > flux_vector[i]:
                        flag_minor_loop = 1
            else:
                for i in range(0, np.argmax(flux_vector)):
                    if flux_vector[i + 1] < flux_vector[i]:
                        flag_minor_loop = 1
                for i in range(np.argmin(flux_vector), len(flux_vector) - 1):
                    if flux_vector[i + 1] < flux_vector[i]:
                        flag_minor_loop = 1
                for i in range(np.argmax(flux_vector), np.argmin(flux_vector)):
                    if flux_vector[i + 1] > flux_vector[i]:
                        flag_minor_loop = 1
            if flag_minor_loop == 1:
                st.warning('检测到次级磁滞回路，神经网络未对此波形进行训练。')

            flux_bias = np.average(np.interp(np.linspace(0, 1, c.streamlit.n_nn), np.array(duty_vector), np.array(flux_vector)))
            bias = flux_bias / (mu_relative * c.streamlit.mu_0)
            st.write(f'Hdc={round(bias, 2)} A/m，'
                     f'根据平均磁通 {round(flux_bias * 1e3)} mT 与 μr={round(mu_relative)} 近似估算')

            flux_vector = flux_vector - flux_bias  # 去除直流分量
            flux = (max(flux_vector)-min(flux_vector))/2

        # 非任意波形（正弦、三角、梯形）
        if excitation != "任意波形":
            flux = st.slider(
                f'交流磁通密度 (mT)',
                1,
                500,
                50,
                step=1,
                key=f'flux {m}',
                help=f'幅值（非峰峰值）') / 1e3

        if flux < min(df['Flux_Density']):
            st.warning(f"模型未在 {round(min(df['Flux_Density']) * 1e3)} mT 以下训练，MagNet AI 正在外推。")
        if flux > max(df['Flux_Density']):
            st.warning(f"模型未在 {round(max(df['Flux_Density']) * 1e3)} mT 以上训练，MagNet AI 正在外推。")

        # 三角波与梯形波占空比设置
        if excitation != "任意波形":
            duty_step = 0.01
            if excitation == "正弦波":
                duty = None
            if excitation == "三角波":
                duty_p = st.slider('占空比', duty_step, 1 - duty_step, 0.5, step=duty_step, key=f'duty {m}')
                duty_n = 1 - duty_p
                duty_0 = 0
                duty = duty_p
            if excitation == "梯形波":
                duty_p = st.slider('占空比 D1', duty_step, 1 - duty_step, 0.5, step=duty_step, key=f'dutyP {m}',
                                   help='上升部分最大斜率段')
                duty_n = st.slider('占空比 D3', duty_step, 1 - duty_p,
                                   max(round((1 - duty_p) / 2, 2), duty_step), step=duty_step,
                                   key=f'dutyN {m}', help='下降部分最大斜率段')
                duty_0 = round((1 - duty_p - duty_n) / 2, 2)
                st.write(f'中间占空比 D2=D4=(1-D1-D3)/2={duty_0}')
                duty = [duty_p, duty_n, duty_0]

        # DC 偏置设置
        if excitation != "任意波形":
            bias_b_max = 0.3
            max_bias = (bias_b_max - flux) / (mu_relative * c.streamlit.mu_0)
            bias = st.slider('直流偏置 (A/m)', 0, round(max_bias), 0, step=5, key=f'bias {m}',
                             help=f'由于无 Bdc 数据，Hdc 用于近似计算。Bdc≈μH，μr={mu_relative}')
            flux_bias = bias * mu_relative * c.streamlit.mu_0

        temp = st.slider('温度 (°C)', 0, 120, 25, step=5, key=f'temp {m}')
        if temp < min(df['Temperature']):
            st.warning(f"模型未在 {round(min(df['Temperature']))} °C 以下训练，AI 正在外推。")
        if temp > max(df['Temperature']):
            st.warning(f"模型未在 {round(max(df['Temperature']))} °C 以上训练，AI 正在外推。")

    # 损耗计算
    if excitation == '任意波形':
        loss, not_extrapolated = core_loss_arbitrary(material, freq, flux_vector, temp, bias, duty_vector)
    else:
        loss, not_extrapolated = core_loss_default(material, freq, flux, temp, bias, duty, batched=False)

    # 波形可视化
    with col2:
        if excitation == "任意波形":
            waveform_visualization(st, x=duty_vector, y=np.multiply(flux_vector + flux_bias, 1e3))
        else:
            if excitation == '正弦波':
                [cycle_list, flux_list, volt_list] = cycle_points_sinusoidal(c.streamlit.n_points_plot)
            if excitation in ['三角波', '梯形波']:
                [cycle_list, flux_list, volt_list] = cycle_points_trapezoidal(duty_p, duty_n, duty_0)
            flux_vector = np.add(np.multiply(flux_list, flux), flux_bias)
            waveform_visualization_2axes(st,
                x1=np.multiply(cycle_list, 1e6 / freq),
                x2=cycle_list,
                y1=np.multiply(flux_vector, 1e3),
                y2=volt_list,
                x1_aux=cycle_list,
                y1_aux=flux_list,
                title=f"<b>波形可视化</b>")

    # 输出部分
    st.header(f'输出：案例 {m}：{round(loss / 1e3 ,2)} kW/m³')
    if not not_extrapolated:
        st.warning("注意：该数据可能为外推结果，AI 未在此条件下训练。")

    info_string = f'{material_manufacturers[material]} - {material}, {excitation} 激励, f={round(freq / 1e3)} kHz, Bac={round(flux * 1e3)} mT, 偏置={round(bias)} A/m'
    st.write(f'{info_string}, T={round(temp)} °C')

    st.warning('''实线：插值预测，MagNet AI 重现训练数据。
虚线：外推预测，MagNet AI 在训练范围外进行估算。''')

    st.markdown("""---""")

import os.path
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from magnet.constants import material_list, material_extra, material_core_params
from magnet.io import load_dataframe, load_hull
import numpy as np
from magnet.core import BH_Transformer, loss_BH, bdata_generation, point_in_hull
from magnet import config as c

STREAMLIT_ROOT = os.path.dirname(__file__)


def convert_df(df):
    return df.to_csv().encode('utf-8')


def ui_intro(m):
    # ---------------- 页面标题与简介 ----------------
    st.title('MagNet AI助力科研、教育与设计')  # MagNet AI for Research, Education and Design
    st.markdown("""---""")

    # ---------------- 输入区块 ----------------
    col1, col2 = st.columns(2)
    with col1:
        st.header('MagNet AI 输入')  # MagNet AI Input
        material = st.selectbox(
            f'材料选择：',  # Material:
            material_list,
            index=9,
            key=f'material {m}',
            help='从可用的材料列表中选择')  # select from a list of available materials

        mu_relative = material_extra[material][0]
        st.caption(
            f'{material} 的初始相对磁导率 μ 设为 {mu_relative}，用于确定预测 B-H 回线的中心。')  # Initial Relative Permeability info

        dataset = load_dataframe(material)  # 加载数据以确定参数范围

        temp = st.slider(
            "温度 [°C]",  # Temperature [C]
            0.0,
            120.0,
            25.0,
            1.0,
            format='%f',
            key=f'temp {m}',
            help='器件表面温度')  # Device surface temperature

        if temp < min(dataset['Temperature']):
            st.warning(f"温度低于 {round(min(dataset['Temperature']))} °C，结果可能为外推值。")  # extrapolated warning
        if temp > max(dataset['Temperature']):
            st.warning(f"温度高于 {round(max(dataset['Temperature']))} °C，结果可能为外推值。")

        freq = st.slider(
            "频率 [kHz]",  # Frequency [kHz]
            10.0,
            1000.0,
            200.0,
            1.0,
            format='%f',
            key=f'freq {m}',
            help='激励的基波频率') * 1e3  # Fundamental frequency

        if freq < min(dataset['Frequency']):
            st.warning(f"频率低于 {round(min(dataset['Frequency']) * 1e-3)} kHz，结果可能为外推值。")
        if freq > max(dataset['Frequency']):
            st.warning(f"频率高于 {round(max(dataset['Frequency']) * 1e-3)} kHz，结果可能为外推值。")

    # ---------------- 磁通输入选项 ----------------
    with col2:
        st.subheader('选项 1：自定义 B 输入')  # Option 1: Arbitrary B Input
        bdata0 = 100 * np.sin(np.linspace(0, 2 * np.pi, c.streamlit.n_nn))
        output = {'B [mT]': bdata0}
        csv = convert_df(pd.DataFrame(output))
        st.write(
            f"训练输入的一个周期内Bac波形（单位mT）数据是包含 {c.streamlit.n_nn} 个点的数组。用户上传B波形文件后自动检测直流偏置，若B数组长度不匹配，将进行上采样和下采样处理。以下为模板示例：")
        st.download_button(
            f"下载示例 {c.streamlit.n_nn}-步每周期的 100 mT 正弦 B 波形 CSV 文件",  # Download example
            data=csv,
            file_name='B-Input.csv',
            mime='text/csv',
        )

        inputB = st.file_uploader(
            "上传用户定义的 CSV 文件：",  # Upload CSV File
            type='csv',
            key=f'bfile {m}'
        )

        st.markdown("""---""")

        st.subheader('选项 2：标准 B 输入')  # Option 2: Standard B Input
        if inputB is None:
            default = st.radio(
                "选择激励波形",  # Select default waveform
                ["正弦波", "三角波", "梯形波"])  # Sinusoidal / Triangular / Trapezoidal
            flux = st.slider(
                "Bac 幅值 [mT]",  # Bac Amplitude [mT]
                10.0,
                350.0,
                50.0,
                1.0,
                format='%f',
                key=f'flux_sine {m}',
                help='峰-峰值磁通密度的一半') / 1e3

            if default == "正弦波":
                duty = None
                dd = 0.5
            if default == "三角波":
                duty = st.slider(
                    "占空比",  # Duty Cycle
                    0.0,
                    1.0,
                    0.5,
                    0.01,
                    format='%f',
                    key=f'duty_tri {m}',
                    help='上升段的占空比')
                dd = duty
            if default == "梯形波":
                duty_p = st.slider(
                    "上升段占空比",  # Duty Cycle (Rising)
                    0.01,
                    1 - 0.01,
                    0.2,
                    0.01,
                    format='%f',
                    key=f'duty_trap_p1 {m}',
                    help='上升段的占空比')
                duty_n = st.slider(
                    "下降段占空比",  # Duty Cycle (Falling)
                    0.01,
                    round((1 - duty_p) / 0.01) * 0.01,
                    duty_p if duty_p <= 0.5 else round((1 - duty_p) / 2 / 0.01 - 1) * 0.01,
                    0.01,
                    format='%f',
                    key=f'duty_trap_p2 {m}',
                    help='下降段的占空比')
                duty = [duty_p, duty_n, (1 - duty_p - duty_n) / 2]
                dd = duty[0]
            phase = st.slider(
                "起始相位 [°]",  # Starting Phase
                0.0,
                360.0,
                0.0,
                1.0,
                format='%f',
                key=f'phase_trap {m}',
                help='水平平移波形。理论上不影响 B-H 回线或损耗。') / 360.0

            bdata_start0 = bdata_generation(flux, duty)
            bdata = np.roll(bdata_start0, np.int_(phase * c.streamlit.n_nn))

        # ---------------- 用户自定义波形 ----------------
        if inputB is not None:
            df = pd.read_csv(inputB)
            st.write("已上传用户自定义波形，默认波形功能已禁用：")
            st.write(df.T)
            st.write("若要移除上传文件并重新启用默认输入，请点击右上角的叉号。")
            bdata_read = df["B [mT]"].to_numpy()
            bdata = np.interp(np.linspace(0, 1, c.streamlit.n_nn), np.linspace(0, 1, len(bdata_read)),
                              bdata_read * 1e-3)

            # 检测是否存在次级回线 (Minor loop)
            flag_minor_loop = 0
            if np.argmin(bdata) < np.argmax(bdata):
                for i in range(np.argmin(bdata), np.argmax(bdata)):
                    if bdata[i + 1] < bdata[i]:
                        flag_minor_loop = 1
            else:
                for i in range(np.argmax(bdata)):
                    if bdata[i + 1] < bdata[i]:
                        flag_minor_loop = 1
            if flag_minor_loop == 1:
                st.warning("模型未在包含次级回线的波形上训练，结果可能为外推。")

        # ---------------- 偏置设置 ----------------
        with col1:
            if inputB is not None:
                bias = np.average(bdata) / (mu_relative * c.streamlit.mu_0)
                bdata = bdata - bias * mu_relative * c.streamlit.mu_0
                st.write(f'根据输入 B 波形与 μ={mu_relative}，直流偏置为 {round(bias)} A/m')
            else:
                bias = st.slider(
                    "Hdc 偏置 [A/m]",  # Hdc Bias
                    -20.0,
                    40.0,
                    0.0,
                    1.0,
                    format='%f',
                    key=f'bias {m}',
                    help='由直流偏置电流决定')

            st.write('下一步：选择或上传 B 波形。')

            if bias < 0:
                st.warning("偏置低于 0 A/m，结果可能为外推。")
            if bias > max(dataset['DC_Bias']):
                st.warning(f"偏置高于 {round(max(dataset['DC_Bias']))} A/m，结果可能为外推。")

        with col2:
            if max(abs(bdata)) + bias * mu_relative * c.streamlit.mu_0 > max(dataset['Flux_Density']):
                st.warning(f"峰值磁通密度超过 {round(max(dataset['Flux_Density']) * 1e3)} mT，结果可能为外推。"
                           f"(Bac={round((max(bdata) - min(bdata)) / 2 * 1e3)} mT, Bdc={round(bias * mu_relative * c.streamlit.mu_0 * 1e3)} mT)")

            # 检查 dB/dt 是否超出范围
            flag_dbdt_high = 0
            dbdt_max = c.streamlit.vpkpk_max / (material_core_params[material][2] * material_core_params[material][1])
            for i in range(0, len(bdata) - 1):
                if abs(bdata[i + 1] - bdata[i]) * freq * c.streamlit.n_nn > dbdt_max:
                    flag_dbdt_high = 1
            if flag_dbdt_high == 1:
                st.warning(f"dB/dt 超过 {round(dbdt_max * 1e-3)} mT/ns，结果可能为外推。")

    # ---------------- 模型计算与结果 ----------------
    hdata = BH_Transformer(material, freq, temp, bias, bdata)
    loss = loss_BH(bdata, hdata, freq)

    Eq = load_hull(material)
    if inputB is None:
        point = np.array([freq, flux, bias, temp, dd])
        not_extrapolated = point_in_hull(point, Eq)
    else:
        point = np.array([freq, (max(bdata) - min(bdata)) / 2, bias, temp, 0.5])
        not_extrapolated = point_in_hull(point, Eq)

    st.markdown("""---""")
    st.header('MagNet AI 输出')  # MagNet AI Output
    st.caption('材料特性、寄生参数及测量误差都会影响结果。')

    if not not_extrapolated:
        st.warning("所选条件超出训练数据范围。")

    # ---------------- 输出图表 ----------------
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader('有效 B-H 波形')  # Effective B-H Waveform
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Scatter(
                x=np.linspace(1, c.streamlit.n_nn, num=c.streamlit.n_nn) / c.streamlit.n_nn,
                y=(bdata + bias * mu_relative * c.streamlit.mu_0 * np.ones(c.streamlit.n_nn)) * 1e3,
                line=dict(color='mediumslateblue', width=4),
                name="B [mT]"),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=np.linspace(1, c.streamlit.n_nn, num=c.streamlit.n_nn) / c.streamlit.n_nn,
                y=(bias * mu_relative * c.streamlit.mu_0 * np.ones(c.streamlit.n_nn)) * 1e3,
                line=dict(color='mediumslateblue', dash='longdash', width=2),
                name="Bdc [mT]"),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=np.linspace(1, c.streamlit.n_nn, num=c.streamlit.n_nn) / c.streamlit.n_nn,
                y=hdata + bias * np.ones(c.streamlit.n_nn),
                line=dict(color='firebrick', width=4),
                name="H [A/m]"),
            secondary_y=True,
        )
        fig.update_xaxes(title_text="周期比例")
        fig.update_yaxes(title_text="B - 磁通密度 [mT]", color='mediumslateblue', secondary_y=False)
        fig.update_yaxes(title_text="H - 磁场强度 [A/m]", color='firebrick', secondary_y=True)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader('有效 B-H 回线')  # Effective B-H Loop
        fig = make_subplots(specs=[[{"secondary_y": False}]])
        fig.add_trace(
            go.Scatter(
                x=np.tile(hdata + bias * np.ones(c.streamlit.n_nn), 2),
                y=np.tile((bdata + bias * mu_relative * c.streamlit.mu_0 * np.ones(c.streamlit.n_nn)) * 1e3, 2),
                line=dict(color='mediumslateblue', width=4),
                name="预测 B-H 回线"),  # Predicted B-H Loop
            secondary_y=False,
        )
        fig.update_yaxes(title_text="B - 磁通密度 [mT]")
        fig.update_xaxes(title_text="H - 磁场强度 [A/m]")
        st.plotly_chart(fig, use_container_width=True)

    with col1:
        output = {'B [mT]': (bdata + bias * mu_relative * c.streamlit.mu_0) * 1e3,
                  'H [A/m]': hdata + bias}
        csv = convert_df(pd.DataFrame(output))
        st.download_button(
            "下载 B-H 回线 CSV 文件",  # Download BH Loop
            data=csv,
            file_name='BH-Loop.csv',
            mime='text/csv',
        )

    with col3:
        st.subheader(f'体积损耗：{np.round(loss / 1e3, 2)} kW/m³')  # Volumetric Loss
        st.subheader('不同材料损耗排名：')  # Ranking among materials

        loss_test_list = pd.DataFrame(columns=['材料', '损耗 [kW/m³]', '当前选择'])
        for material_test in material_list:
            hdata_test = BH_Transformer(material_test, freq, temp, bias, bdata)
            loss_test = loss_BH(bdata, hdata_test, freq)
            this_one = '✓' if (material_test == material) else ''
            loss_test_list = loss_test_list.append({
                '材料': material_test,
                '损耗 [kW/m³]': np.round(loss_test / 1e3, 2),
                '当前选择': this_one}, ignore_index=True)

        loss_test_list = loss_test_list.sort_values(by='损耗 [kW/m³]')
        loss_test_list.index = range(1, len(loss_test_list) + 1)
        st.dataframe(data=loss_test_list)

    st.markdown("""---""")

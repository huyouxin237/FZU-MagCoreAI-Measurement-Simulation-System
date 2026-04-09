import streamlit as st
import numpy as np
from magnet import config as c
import os

from magnet.simplecs.classes import CircuitModel, MagModel, CoreMaterial
from magnet.core import core_loss_arbitrary, BH_Transformer, loss_BH
from magnet.constants import material_list, material_extra, material_steinmetz_param


def SimulationPLECS(m):
    path = os.path.dirname(os.path.realpath(__file__))

    col1, col2 = st.columns(2)
    with col1:
        # 选择拓扑结构
        topology_list = ("Buck", "Boost", "Flyback", "DAB")
        topology_type = st.selectbox(
            "拓扑结构:",
            topology_list,
            key='Topology'
        )

    # 电路模型实例
    circuit = CircuitModel(topology_type)

    # 电路参数
    Param = {
        'Vi': 0,
        'Vo': 0,
        'Ro': 0,
        'Lk': 0,
        'fsw': 0,
        'duty': 0,
        'ph': 0
    }

    st.header("电路参数")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        # 显示电路图
        circuit.displaySch(path)
    with col3:
        Param['Vi'] = st.number_input("输入电压 [V]", min_value=0.01, max_value=1000., value=24., step=2.,
                                      key='Vi')
        Param['Ro'] = st.number_input("负载电阻 [Ω]", min_value=0.01, max_value=1e6, value=10., step=5.,
                                      key='R')
        if topology_type == "DAB":
            Param['Lk'] = st.number_input("串联电感 [μH]", min_value=0.001, max_value=1000., value=10., step=1.,
                                          key='Lk') * 1e-6
    with col4:
        Param['fsw'] = st.number_input("开关频率 [kHz]", min_value=50., max_value=500., value=200., step=10.,
                                       key='fsw') * 1e3
        if topology_type == "DAB":
            Param['ph'] = st.number_input("相位偏移 [度]", min_value=0., max_value=360., value=90., step=1.,
                                          key='ph') / 360.
            Param['duty'] = 0.5
        else:
            Param['duty'] = st.number_input("占空比 [标幺值]", min_value=0.01, max_value=0.99, value=0.5, step=0.01,
                                            key='duty')
    # 将输入参数赋值给仿真参数结构
    circuit.setParam(Param)

    # 磁芯参数
    Param_mag = {
        'lc': 0,
        'Ac': 0,
        'lg': 0,
        'Np': 0,
        'Ns': 0
    }

    if topology_type == "Flyback" or topology_type == "DAB":
        mag = MagModel("Toroid_2W")
    else:
        mag = MagModel("Toroid")

    st.header("磁芯几何参数")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        # 显示几何结构
        mag.displaySch(path)
    with col3:
        Param_mag['lc'] = st.number_input("磁芯长度 [mm]", min_value=0.01, max_value=1000., value=103., step=1.,
                                          key='Lc') * 1e-3
        Param_mag['Ac'] = st.number_input("横截面积 [mm²]", min_value=0.01, max_value=1000., value=96., step=1.,
                                          key='Ac') * 1e-6
    with col4:
        Param_mag['lg'] = st.number_input("气隙长度 [mm]", min_value=0.0001, max_value=1000., value=0.5, step=0.01,
                                          key='lg') * 1e-3

        Param_mag['Np'] = st.number_input("初级匝数", min_value=0., max_value=100., value=8., step=1.,
                                          key='Np')
        if topology_type == "Flyback" or topology_type == "DAB":
            Param_mag['Ns'] = st.number_input("次级匝数", min_value=0., max_value=100., value=8.,
                                              step=1., key='Ns')

    # 将输入参数赋值给仿真参数结构
    mag.setParam(Param_mag)

    Vc = (Param_mag['lc'] + Param_mag['lg']) * Param_mag['Ac']

    # Steinmetz 参数
    st.header("磁性材料参数")

    col1, col2 = st.columns(2)
    with col1:
        Material_type = st.selectbox(
            "材料类型:",
            material_list,
            index=9,
            key='Material'
        )

        k_i, alpha, beta = material_steinmetz_param[Material_type]
        mu_r_0 = material_extra[Material_type][0]

        Param_material = {
            'mu_r': mu_r_0,
            'iGSE_ki': k_i,
            'iGSE_alpha': alpha,
            'iGSE_beta': beta
        }
        material = CoreMaterial(Material_type)
        material.setParam(Param_material)
        st.write(f"初始相对磁导率: {material.mu_r} (参考值)")

    with col2:
        Temperature = st.number_input(
            f'温度 (°C)',
            0,
            120,
            25,
            step=5,
            key=f'temp {m}')

    # 选择后端仿真引擎
    col1, col2 = st.columns(2)

    with col1:
        # 选择后端仿真引擎
        backend_list = ("Plecs", "Python")
        backend_type = st.selectbox(
            "仿真引擎:",
            backend_list,
            key='Backend'
        )

    # 仿真并获取数据
    result = st.button("开始仿真", key='Simulate')
    st.markdown("""---""")

    circuit.setMagModel(mag, material)

    if result:

        st.header("仿真结果")

        if backend_type == "Plecs":
            flux, field, time = circuit.steadyRun(path)
        elif backend_type == "Python":
            flux, field, time = circuit.steadyRun_py(path)

        flux = np.array(flux)
        time = np.array(time)
        time_vector = np.multiply(time, Param['fsw'])

        temp = (time_vector <= 1)
        flux = flux[temp]

        field = np.array(field)
        field = field[temp]

        bias = (np.max(field) + np.min(field)) / 2
        time_vector = time_vector[temp]

        flux_amp = (np.max(flux) - np.min(flux)) / 2

        duty = time_vector
        bdata_pre = np.interp(np.linspace(0, 1, c.streamlit.n_nn + 1), np.array(duty), np.array(flux))
        bdata_pre = bdata_pre[:-1]

        bdata = bdata_pre - np.average(bdata_pre)

        hdata = BH_Transformer(material=Material_type,
                               freq=Param['fsw'],
                               temp=Temperature,
                               bias=bias,
                               bdata=bdata)
        loss = loss_BH(bdata, hdata, freq=Param['fsw'])
        circuit.Binterp = bdata
        circuit.Hinterp = hdata
        circuit.bias = bias

        st.header("基于仿真波形的磁芯损耗 (25°C)")
        st.subheader(f'{round(loss * Vc, 2)} W ({round(loss / 1e3, 2)} kW/m³)')

        if flux_amp < 0.01:
            st.warning("""
                     在当前参数配置下，模拟的磁通密度幅值**过小**。
                     预测的磁芯损耗结果可能不准确！
                     """)
        elif flux_amp > 0.3:
            st.warning("""
                     在当前参数配置下，模拟的磁通密度幅值**过大**。
                     预测的磁芯损耗结果可能不准确！
                     """)
        elif topology_type == "DAB":
            st.write(f"""
                     **注意**: 此磁芯损耗结果是**变压器**磁芯中的损耗，
                     而串联辅助电感被假定为无损耗。""")

        col1, col2 = st.columns(2)
        with col1:
            circuit.displayWfm()
        with col2:
            circuit.displayBH()
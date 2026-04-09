import streamlit as st
import numpy as np

from magnet import config as c
from magnet.constants import material_list, material_manufacturers, material_extra
from magnet.io import load_dataframe, load_metadata
from magnet.plots import scatter_plot, waveform_visualization_2axes, cycle_points_sinusoidal, cycle_points_trapezoidal


def ui_core_loss_dbs(n=1):

    for i in range(int(n)):
        ui_core_loss_db(chr(ord('A') + i))


def ui_core_loss_db(m):

    st.title('MagNet共享与可视化数据库')
    st.markdown("""---""")
    st.header(f'输入参数：案例 {m}')

    col1, col2 = st.columns(2)
    with col2:
        excitation = st.selectbox(
             f'激励波形：',
            ('正弦波', '三角波', '梯形波'),
            key=f'excitation {m}',
            index=1)
    with col1:
        material = st.selectbox(
            f'材料类型：',
            material_list,
            index=9,
            key=f'material {m}')
    with col1:
        # temperature = st.sidebar.radio(
        #     f'Temperature (C)',
        #     [25, 50, 70, 90],
        #     key=f'temp {m}',
        #     horizontal=False)  # TODO Switch to radio buttons once we update the Streamlit version
        temperature = st.selectbox(
              f'温度 (℃)：',
            [25, 50, 70, 90],
            key=f'temp {m}')

    df = load_dataframe(material)  # To find the range of the variables

    with col1:
        [freq_min_aux, freq_max_aux] = st.slider(
           f'频率范围 (kHz)：',
          round(min(df['Frequency'])*1e-3),
          round(max(df['Frequency'])*1e-3),
          (round(min(df['Frequency'])*1e-3), round(max(df['Frequency'])*1e-3)),
          step=1,
          key=f'freq {m}')
        freq_min = freq_min_aux * 1e3
        freq_max = freq_max_aux * 1e3
        freq_avg = (freq_max + freq_min) / 2

        [flux_min_aux, flux_max_aux] = st.slider(
            f'交流磁通密度范围 (mT)：',
            round(min(df['Flux_Density'])*1e3),
            round(max(df['Flux_Density'])*1e3),
            (round(min(df['Flux_Density'])*1e3), round(max(df['Flux_Density'])*1e3)),
            step=5,
            key=f'flux {m}',
            help=f'指交流信号的幅值，而非峰峰值')
        flux_min = flux_min_aux / 1e3
        flux_max = flux_max_aux / 1e3
        flux_avg = (flux_max + flux_min) / 2

        if round(round(max(df['DC_Bias']) / 15) * 15) == 0:
            dc_bias = 0
            flux_bias = 0
            st.write(f'仅有无直流偏置数据可用')
        else:
            mu_relative = material_extra[material][0]
            dc_bias = st.slider(
                f'直流偏置 (A/m)：',
                0,
                round(round(max(df['DC_Bias']) / 15) * 15),
                0,
                step=15,
                key=f'bias {m}',
                help=f'Hdc provided as Bdc is not measured. '
                     f'Bdc approximated with B=mu*H for mur={mu_relative} for the plots')
            flux_bias = dc_bias * mu_relative * c.streamlit.mu_0

        if excitation == '三角波':
            duty_p = st.slider(
                f'占空比：',
                0.1,
                0.9,
                0.5,
                step=0.1,
                key=f'duty {m}')
            duty_n = 1.0 - duty_p  # For triangular excitation, there are no flat parts
            duty_0 = 0.0
        if excitation == '梯形波':
            duty_p = st.slider(
                 f'占空比 (D1)：',
                0.1,
                0.9 - 2 * 0.1,
                0.5 - 0.1,
                step=0.1,
                key=f'dutyP {m}',
                help=f'上升段（最大斜率部分）')
            duty_n_max = 1.0 - duty_p - 0.2
            if duty_p in [0.1, 0.3, 0.5, 0.7]:  # TODO: probably there is a more elegant way to implement this
                duty_n_min = 0.1
            elif duty_p in [0.2, 0.4, 0.6]:
                duty_n_min = 0.2
            if duty_n_max <= duty_n_min+0.01:  # In case they are equal but implemented for floats
                duty_n = st.slider(
                     f'占空比 (D3)（固定）',
                    duty_n_max - 0.01,
                    duty_n_max + 0.01,
                    duty_n_max,
                    step=1.0,
                    key=f'dutyN {m}',
                    help=f'下降段（最大斜率部分）由D1决定')  # Step outside the range to fix the variable
            else:
                duty_n = st.slider(
                     f'占空比 (D3)：',
                    duty_n_min,
                    duty_n_max,
                    duty_n_max,
                    step=2 * 0.1,
                    key=f'dutyN {m}',
                    help=f'下降段（最大斜率部分），最大值受D1限制')
            duty_0 = (1-duty_p-duty_n)/2
            st.write(f'占空比 D2=D4=(1-D1-D3)/2)={round(duty_0, 1)}'),

    with col2:
        if excitation == '正弦波':
            [cycle_list, flux_list, volt_list] = cycle_points_sinusoidal(c.streamlit.n_points_plot)
        if excitation in ['三角波', '梯形波']:
            [cycle_list, flux_list, volt_list] = cycle_points_trapezoidal(duty_p, duty_n, duty_0)
        flux_vector = np.multiply(flux_list, flux_avg)

        waveform_visualization_2axes(
            st,
            x1=np.multiply(cycle_list, 1e6 / freq_avg),  # In us
            x2=cycle_list,  # Percentage
            y1=np.multiply(np.add(flux_vector, flux_bias), 1e3),  # In mT
            y2=volt_list,  # Per unit
            x1_aux=cycle_list,  # Percentage
            y1_aux=flux_list,
            title=f"<b>波形可视化</b>"
                  f"<br>f={format(freq_avg / 1e3, '.0f')} kHz, Bac={format(flux_avg * 1e3, '.0f')} mT")

    if excitation == '正弦波':
        df = load_dataframe(material, freq_min, freq_max, flux_min, flux_max, dc_bias, -1.0, -1.0, temperature)
    if excitation in ['三角波', '梯形波']:
        df = load_dataframe(material, freq_min, freq_max, flux_min, flux_max, dc_bias, duty_p, duty_n, temperature)

    col1, col2 = st.columns([1, 2])
    with col1:
        st.header(f'输出结果: 案例 {m}')
        st.write(f'{material_manufacturers[material]} - {material}, '
                 f'{excitation} 激励')
        st.write(f'频率范围=[{round(freq_min / 1e3)}-{round(freq_max / 1e3)}] kHz, '
                 f'交流磁通密度=[{round(flux_min * 1e3)}-{round(flux_max * 1e3)}] mT, '
                 f'直流偏置={round(dc_bias)} A/m')
        if excitation == "正弦波":
            st.write(f'温度={round(temperature)} C')
        if excitation == "三角波":
            st.write(f'占空比={round(duty_p, 2)}, '
                     f'温度={round(temperature)} C')
        if excitation == "梯形波":
            st.write(f'D1={round(duty_p, 2)}, '
                     f'D2={round(duty_0, 2)}, '
                     f'D3={round(duty_n, 2)}, '
                     f'D4={round(duty_0, 2)}, '
                     f'温度={round(temperature)} C')

    if df.empty:
        st.subheader("⚠️ 警告：当前范围内无数据，请调整参数范围。")
    else:
        # with st.expander('Measurement details'):
        #     metadata = load_metadata(material)
        #     st.write('Core information: ', metadata['info_core'])
        #     st.write('Setup information: ', metadata['info_setup'])
        #     st.write('Data-processing information: ', metadata['info_processing'])
        #     st.write(
        #         'Note: the dc bias, duty cycles and temperature have small variations with respect to the data '
        #         'reported here, this data has been rounded for visualization purposes. '
        #         'The measurements can be obtain from the download section.')
        with col1:
            with st.expander('磁芯信息：'):
                metadata = load_metadata(material)
                st.write(metadata['info_core'])

            st.subheader(f'下载数据:')
            df_csv = df[['Frequency', 'Flux_Density', 'Power_Loss']]
            file = df_csv.to_csv(index=False).encode('utf-8')
            if excitation == "正弦波":
                csv_name = material + '-' + excitation + '_' + str(dc_bias) + 'Am-1(bias)_'\
                           + str(temperature) + 'C(temp).csv'
            if excitation == "三角波":
                csv_name = material + '-' + excitation + '_' + str(dc_bias) + 'Am-1(bias)_'\
                           + str(duty_p) + '(duty)_' + str(temperature) + 'C(temp).csv'
            if excitation == "梯形波":
                csv_name = material + '-' + excitation + '_' + str(dc_bias) + 'Am-1(bias)_'\
                           + str(duty_p) + '(D1)_' + str(duty_n) + '(D3)_' + str(temperature) + 'C(temp).csv'
            st.download_button(
                '下载 CSV 数据',
                file,
                csv_name,
                'text/csv',
                key=m,
                help='下载包含频率、磁通密度和损耗的数据文件 (.csv)')
            st.write('单位说明：f [Hz], B [T], Pv [W/m³]')
            c_axis = st.selectbox(
                f'选择图表颜色轴：',
                ['磁通密度', '频率', '功率损耗'],
                key=f'c_axis {m}')

        with col2:
            st.plotly_chart(scatter_plot(
                df,
                x='Frequency_kHz' if c_axis == '磁通密度' else
                'Flux_Density_mT',
                y='Frequency_kHz' if c_axis == '功率损耗' else
                'Power_Loss_kW/m3',
                c='Flux_Density_mT' if c_axis == '磁通密度' else
                'Frequency_kHz' if c_axis == '频率' else
                'Power_Loss_kW/m3'),
                use_container_width=True, )

    st.markdown("""---""")

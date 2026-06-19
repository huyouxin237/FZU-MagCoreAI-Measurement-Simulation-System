import streamlit as st
import os
import tempfile
import zipfile
import shutil
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time

# 导入你原本定义好的材料列表
from magnet.constants import material_list


def ui_fem_analysis(m):
    st.markdown("""---""")

    # 后台预置 zip 目录路径
    PRESET_FLD_DIR = r"D:\ANSYS"

    # 初始化预置文件路径默认值
    PRESET_FLD_ZIP_PATH = None

    # ================= 1. 网格数据解析参数设置 =================
    st.header(f'1. 设置仿真工况参数')
    col1, col2, col3 = st.columns(3)

    with col1:
        frequency = st.number_input('设置频率 (Hz)', min_value=1.0, value=100000.0, step=1000.0, key=f'freq_{m}')
    with col2:
        hdc_value = st.number_input('直流偏置 Hdc (A/m)', value=17.3, step=1.0, key=f'hdc_{m}')
    with col3:
        temperature = st.number_input('设置温度 (℃)', min_value=-50.0, value=25.0, step=5.0, key=f'temp_{m}')

    # ================= 2. AI 模型预测参数设置 =================
    st.header(f'2. 激励类型与材料设置')
    col4, col5 = st.columns(2)

    with col4:
        waveform_type = st.selectbox('激励类型', ["正弦波", "三角波", "梯形波"], key=f'wave_{m}')

        if waveform_type in ["三角波", "梯形波"]:
            duty_cycle = st.number_input(
                '占空比 (%)',
                min_value=0.0,
                max_value=100.0,
                value=50.0,
                step=1.0,
                key=f'duty_{m}'
            )
        else:
            duty_cycle = None

        use_manual_waveform = st.checkbox("手动指定波形 (跳过 CNN AI 识别)", value=False, key=f'manual_wave_{m}')

    with col5:
        extra_materials = ['N87', '3C90', '3C92', '3C94', '3C95', '3E6', '3F4', '77', '78', '79', 'ML95S', 'N27', 'N30',
                           'N49', 'T37']
        material = st.selectbox('选择磁芯材料', extra_materials, index=0, key=f'mat_{m}')
        design_name = st.text_input('设计名称 (可选)', value='Design_1', key=f'design_{m}')

    # ================= 3. 文件上传区 =================
    st.header(f'3. 上传网格数据 (.fld)')

    data_source = st.radio(
        "选择数据来源",
        ["上传本地 zip", "使用服务器预置 fld.zip"],
        horizontal=True,
        key=f"data_source_{m}"
    )

    uploaded_fld_zip = None
    if data_source == "上传本地 zip":
        st.info("请在本地将 Ansys Maxwell 导出的多个时间步的 .fld 文件打包为一个 .zip 压缩包并上传。")
        uploaded_fld_zip = st.file_uploader("上传 fld 数据的 .zip 压缩包", type=["zip"], key=f'zip_{m}')
    else:
        # 扫描服务器预置目录，列出所有 zip 文件供选择
        if os.path.exists(PRESET_FLD_DIR):
            zip_files = sorted([f for f in os.listdir(PRESET_FLD_DIR) if f.endswith('.zip')])
            if zip_files:
                selected_zip_name = st.selectbox(
                    "选择服务器预置 fld.zip 文件",
                    options=zip_files,
                    key=f"preset_zip_{m}"
                )
                PRESET_FLD_ZIP_PATH = os.path.join(PRESET_FLD_DIR, selected_zip_name)
                st.success(f"已选择：{selected_zip_name}（完整路径：{PRESET_FLD_ZIP_PATH}）")
            else:
                st.error(f"未在服务器目录 {PRESET_FLD_DIR} 中找到任何 .zip 文件")
        else:
            st.error(f"服务器预置目录不存在：{PRESET_FLD_DIR}")

    uploaded_hdc_fld = st.file_uploader("上传 Hdc.fld 文件 (可选)", type=["fld", "txt"], key=f'hdc_fld_{m}')

    # ================= 4. 运行预测按钮 =================
    st.markdown("""---""")
    if st.button('运行有限元网格解析与损耗预测', type='primary', use_container_width=True):
        if data_source == "上传本地 zip" and not uploaded_fld_zip:
            st.error("请先上传包含 .fld 文件的 zip 压缩包！")
            return

        if data_source == "使用服务器预置 fld.zip":
            if not PRESET_FLD_ZIP_PATH:
                st.error(f"未选择任何预置文件，请检查服务器目录：{PRESET_FLD_DIR}")
                return
            if not os.path.exists(PRESET_FLD_ZIP_PATH):
                st.error(f"服务器预置文件不存在：{PRESET_FLD_ZIP_PATH}")
                return

        progress_bar = st.progress(0, text="初始化处理流程...")

        def update_progress(percent, text):
            progress_bar.progress(percent, text=text)

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                update_progress(10, "阶段 1/4: 正在准备 .zip 文件...")

                zip_path = os.path.join(temp_dir, "data.zip")
                if data_source == "上传本地 zip":
                    with open(zip_path, "wb") as f:
                        f.write(uploaded_fld_zip.getbuffer())
                else:
                    shutil.copyfile(PRESET_FLD_ZIP_PATH, zip_path)

                update_progress(15, "阶段 1/4: 正在解压 .zip 文件...")
                fld_extract_path = os.path.join(temp_dir, "fld_files")
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(fld_extract_path)

                update_progress(20, "阶段 2/4: 正在校验文件与准备 AI 预测环境...")

                actual_fld_path = fld_extract_path
                for root, dirs, files in os.walk(fld_extract_path):
                    if any(f.endswith('.fld') for f in files):
                        actual_fld_path = root
                        break

                fld_files = [f for f in os.listdir(actual_fld_path) if f.endswith('.fld')] if os.path.exists(actual_fld_path) else []
                if not fld_files:
                    st.error("未找到任何 .fld 文件，请检查 zip 内容！")
                    return

                hdc_fld_path = None
                if uploaded_hdc_fld:
                    hdc_fld_path = os.path.join(temp_dir, "Hdc.fld")
                    with open(hdc_fld_path, "wb") as f:
                        f.write(uploaded_hdc_fld.getbuffer())

                user_params = {
                    'frequency': frequency,
                    'temperature': temperature,
                    'hdc': hdc_value,
                    'waveform_type': waveform_type,
                    'duty_cycle': duty_cycle,
                    'material': material,
                    'design_name': design_name,
                    'use_manual_waveform': use_manual_waveform
                }

                from magnet.core_fem import run_fem_pipeline

                total_loss, total_volume_mm3, detail_csv_path, mesh_npz_path = run_fem_pipeline(
                    fld_extract_path=actual_fld_path,
                    hdc_fld_path=hdc_fld_path,
                    user_params=user_params,
                    temp_dir=temp_dir,
                    progress_callback=update_progress
                )

                update_progress(100, "所有处理已完成！正在渲染图表...")
                time.sleep(0.5)
                progress_bar.empty()

                st.success("有限元网格解析与神经网络预测成功完成！")

                # ================= 渲染结果区域 =================
                results_df = pd.read_csv(detail_csv_path)
                max_bm = results_df['Bm_T'].max() if 'Bm_T' in results_df.columns else 0.0

                summary_df = pd.DataFrame([{
                    "设计名称": user_params.get('design_name', 'Unnamed'),
                    "磁芯型号": "-",
                    "材料": material,
                    "体积(mm³)": f"{total_volume_mm3:.0f}",
                    "波形": waveform_type,
                    "占空比": f"{duty_cycle}%" if duty_cycle else "-",
                    "频率(Hz)": f"{frequency:.0f}",
                    "Bm(T)": f"{max_bm:.3f}",
                    "磁芯损耗(W)": f"{total_loss:.3f}"
                }])

                st.write("**计算结果汇总:**")
                st.dataframe(summary_df, hide_index=True, use_container_width=True)

                st.write("**精确网格空间分布图 (可鼠标拖拽旋转、缩放):**")
                tab1, tab2 = st.tabs(["磁密分布 (Bm_T)", "损耗密度分布 (W/m³)"])

                noaxis = dict(
                    showbackground=False,
                    showgrid=False,
                    zeroline=False,
                    showticklabels=False,
                    title=''
                )

                # 读取并解析后端构建的真实几何拓扑网格
                with np.load(str(mesh_npz_path)) as mesh_data:
                    mx, my, mz = mesh_data['x'], mesh_data['y'], mesh_data['z']
                    mi, mj, mk = mesh_data['i'], mesh_data['j'], mesh_data['k']
                    mbm, mpcv = mesh_data['bm'], mesh_data['pcv']
                    ex, ey, ez = mesh_data['ex'], mesh_data['ey'], mesh_data['ez']

                # 定义通用的网格连线图层
                wireframe_trace = go.Scatter3d(
                    x=ex, y=ey, z=ez, mode='lines',
                    line=dict(color='rgba(0,0,0,0.3)', width=1.5),
                    showlegend=False, hoverinfo='skip'
                )

                with tab1:
                    fig_bm = go.Figure()
                    fig_bm.add_trace(go.Mesh3d(
                        x=mx, y=my, z=mz, i=mi, j=mj, k=mk,
                        intensity=mbm, colorscale='Jet', intensitymode='vertex',
                        flatshading=False, showscale=True, colorbar_title="Bm (T)"
                    ))
                    fig_bm.add_trace(wireframe_trace)
                    fig_bm.update_layout(
                        scene=dict(xaxis=noaxis, yaxis=noaxis, zaxis=noaxis, aspectmode='data'),
                        margin=dict(l=0, r=0, b=0, t=0)
                    )
                    st.plotly_chart(fig_bm, use_container_width=True)

                with tab2:
                    fig_loss = go.Figure()
                    fig_loss.add_trace(go.Mesh3d(
                        x=mx, y=my, z=mz, i=mi, j=mj, k=mk,
                        intensity=mpcv, colorscale='Jet', intensitymode='vertex',
                        flatshading=False, showscale=True, colorbar_title="Pcv (W/m³)"
                    ))
                    fig_loss.add_trace(wireframe_trace)
                    fig_loss.update_layout(
                        scene=dict(xaxis=noaxis, yaxis=noaxis, zaxis=noaxis, aspectmode='data'),
                        margin=dict(l=0, r=0, b=0, t=0)
                    )
                    st.plotly_chart(fig_loss, use_container_width=True)

                st.markdown("<br>", unsafe_allow_html=True)
                with open(detail_csv_path, "rb") as f:
                    csv_bytes = f.read()

                st.download_button(
                    label="下载网格损耗明细数据(CSV)",
                    data=csv_bytes,
                    file_name=f"per_cell_summary_{material}.csv",
                    mime="text/csv",
                    type="primary"
                )

        except Exception as e:
            progress_bar.empty()
            st.error(f"处理出错，请检查数据格式或模型文件路径: {e}")
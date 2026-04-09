import os
import sys
import os.path
from PIL import Image
import streamlit as st

# 先设置 Python 模块搜索路径，让它能找到 src/magnet
APP_ROOT = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(APP_ROOT, ".."))
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")

if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

st.set_page_config(page_title='MagNet 磁芯损耗预测平台', page_icon="⚡", layout='wide')

from magnet import __version__
from ui_db import ui_core_loss_db
from ui_predict import ui_core_loss_predict
from ui_intro import ui_intro

# 1. 同时保留原本的电路仿真和新写的电磁仿真
from magnet.simplecs.simfunctions import SimulationPLECS
from ui_fem import ui_fem_analysis

from magnet.constants import material_list
from magnet.io import load_dataframe

STREAMLIT_ROOT = os.path.dirname(__file__)


def ui_multiple_materials(fn, n=1, *args, **kwargs):
    """
    显示多个材料的输入界面，每个界面对应一个材料（A、B、C...）
    """
    for i in range(int(n)):
        fn(chr(ord('A') + i), *args, **kwargs)


def contributor(name, email):
    st.sidebar.markdown(f'<h5>{name} ({email})</h5>', unsafe_allow_html=True)


if __name__ == '__main__':

    st.sidebar.header('MagNet 平台')

    # 2. 在侧边栏增加第五个独立选项：电磁仿真预测
    function_select = st.sidebar.radio(
        '请选择功能：',
        ('MagNet AI', 'MagNet 数据库', 'MagNet 智能表格',
         'MagNet 电路仿真', '电磁仿真预测'),
    )

    if 'n_material' not in st.session_state:
        st.session_state.n_material = 1

    if function_select in ['MagNet 数据库', 'MagNet 智能表格']:
        clicked = st.sidebar.button("添加另一个案例")
        if clicked:
            st.session_state.n_material += 1

    if function_select == 'MagNet AI':
        ui_multiple_materials(ui_intro)
        st.session_state.n_material = 1

    if function_select == 'MagNet 数据库':
        ui_multiple_materials(ui_core_loss_db, st.session_state.n_material)

    if function_select == 'MagNet 智能表格':
        ui_multiple_materials(ui_core_loss_predict, st.session_state.n_material)

    # 3. 恢复原装的电路仿真页面
    if function_select == 'MagNet 电路仿真':
        st.title('MagNet 电路仿真分析')
        ui_multiple_materials(SimulationPLECS)
        st.session_state.n_material = 1

    # 4. 新增的电磁仿真预测页面
    if function_select == '电磁仿真预测':
        st.title('MagNet 电磁仿真有限元预测')
        ui_fem_analysis(m='A')
        st.session_state.n_material = 1

    st.write('本网站数据和代码部分源自普利斯顿MagNet计划，由以下单位维护补充：(排名不分先后)')
    st.image(Image.open(os.path.join(STREAMLIT_ROOT, 'img', 'school_logo.png')), width=500)

    st.markdown('---')
    st.markdown(f"<h6>MAGNet v{__version__}</h6>", unsafe_allow_html=True)

    st.sidebar.header('MagNet 数据统计')
    n_tot = 0
    for material in material_list:
        n_tot = n_tot + len(load_dataframe(material))
    st.sidebar.write(f'- 数据总量: {n_tot}')
    st.sidebar.write(f'- 材料数量: {len(material_list)}')
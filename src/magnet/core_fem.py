import os
import re
import csv
from pathlib import Path
from typing import Tuple, Optional, Callable

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from pykrige.ok import OrdinaryKriging
from scipy.spatial import cKDTree
import pytorch_lightning as pl
from concurrent.futures import ThreadPoolExecutor, as_completed

# 文件名保持不变，内容已经是新的了
from .MagNet_Data126 import MagNetDataModule
from .MagNet_Model_Flash3_126 import Transformer, Lit_model

# ================== 全局常量 ==================
TARGET_LEN = 1024
GROUP_SIZE = 10
VERT_PICK = (0, 4, 7, 9)


# ================== 1. 基础数学与几何运算模块 ==================
def read_grid_data(file_path):
    data = []
    with open(file_path, 'r', errors='ignore') as file:
        for line in file:
            if line.startswith('-') or line[0].isdigit():
                try:
                    row_data = list(map(float, line.split()))
                    if len(row_data) == 4:
                        data.append(row_data)
                except ValueError:
                    continue
    return np.array(data)


def get_time_from_filename(file_name: str) -> float:
    try:
        m = re.search(r'Time\s*=\s*([0-9]*\.?[0-9]+)\s*[a-zA-Z]+', file_name)
        return float(m.group(1)) if m else float('inf')
    except Exception:
        return float('inf')


def compute_tetrahedron_volume(coords):
    A, B, C, D = np.array(coords[0]), np.array(coords[4]), np.array(coords[7]), np.array(coords[9])
    volume_m3 = np.abs(np.dot(B - A, np.cross(C - A, D - A))) / 6.0
    return volume_m3, volume_m3 * 1e9


def process_one_fld(file_path):
    grid_data = read_grid_data(file_path)
    temp_B, temp_V = [], []
    for i in range(0, len(grid_data), 10):
        group = grid_data[i:i + 10]
        if len(group) < 10:
            continue
        vol_m3, _ = compute_tetrahedron_volume(group[:, :3])
        temp_V.append(vol_m3)

        B_vertices = group[[0, 4, 7, 9], 3].sum()
        B_midpoints = group[[j for j in range(10) if j not in (0, 4, 7, 9)], 3].sum()
        B_cell = (-B_vertices / 20.0) + (B_midpoints / 5.0)
        temp_B.append(B_cell)
    return temp_B, temp_V


# ================== 2. 真实 3D 拓扑提取模块 ==================
def extract_smooth_mesh_data(grid_data, Pcv_array, Bm_array):
    """提取精确的外表面三角形、顶点以及网格边框用于前端平滑渲染"""
    num_elements = len(grid_data) // 10
    verts = np.zeros((num_elements, 4, 3))

    # 1. 提取所有四面体的 4 个核心顶点
    for i in range(num_elements):
        base = i * 10
        verts[i, 0] = grid_data[base + 0, :3]
        verts[i, 1] = grid_data[base + 4, :3]
        verts[i, 2] = grid_data[base + 7, :3]
        verts[i, 3] = grid_data[base + 9, :3]

    verts_flat = verts.reshape(-1, 3)
    # 舍入处理避免浮点误差导致的节点无法合并
    verts_rounded = np.round(verts_flat, decimals=5)
    unique_verts, inverse_indices = np.unique(verts_rounded, axis=0, return_inverse=True)
    elem_nodes = inverse_indices.reshape(num_elements, 4)

    # 2. 生成所有四面体的四个面
    faces = np.empty((num_elements * 4, 3), dtype=int)
    faces[0::4] = elem_nodes[:, [0, 1, 2]]
    faces[1::4] = elem_nodes[:, [0, 1, 3]]
    faces[2::4] = elem_nodes[:, [0, 2, 3]]
    faces[3::4] = elem_nodes[:, [1, 2, 3]]

    # 3. 寻找外表面（只出现过一次的面即为边界表面）
    faces_sorted = np.sort(faces, axis=1)
    unique_faces, unique_indices, unique_counts = np.unique(faces_sorted, axis=0, return_index=True, return_counts=True)
    boundary_mask = unique_counts == 1
    boundary_faces = unique_faces[boundary_mask]

    # 将网格单元的损耗值平滑映射到顶点上 (Gouraud 阴影需要)
    original_indices = unique_indices[boundary_mask]
    elem_ids = original_indices // 4

    vert_Pcv = np.zeros(len(unique_verts))
    vert_Bm = np.zeros(len(unique_verts))
    vert_count = np.zeros(len(unique_verts))

    for face, eid in zip(boundary_faces, elem_ids):
        vert_Pcv[face] += Pcv_array[eid]
        vert_Bm[face] += Bm_array[eid]
        vert_count[face] += 1

    valid = vert_count > 0
    vert_Pcv[valid] /= vert_count[valid]
    vert_Bm[valid] /= vert_count[valid]

    # 4. 提取真实的表面线框 (Edges) 用于前端勾勒
    edges = np.empty((len(boundary_faces) * 3, 2), dtype=int)
    edges[0::3] = boundary_faces[:, [0, 1]]
    edges[1::3] = boundary_faces[:, [1, 2]]
    edges[2::3] = boundary_faces[:, [2, 0]]
    edges.sort(axis=1)
    unique_edges = np.unique(edges, axis=0)

    ex = np.empty((len(unique_edges), 3))
    ey = np.empty((len(unique_edges), 3))
    ez = np.empty((len(unique_edges), 3))

    ex[:, 0] = unique_verts[unique_edges[:, 0], 0]
    ex[:, 1] = unique_verts[unique_edges[:, 1], 0]
    ex[:, 2] = np.nan
    ey[:, 0] = unique_verts[unique_edges[:, 0], 1]
    ey[:, 1] = unique_verts[unique_edges[:, 1], 1]
    ey[:, 2] = np.nan
    ez[:, 0] = unique_verts[unique_edges[:, 0], 2]
    ez[:, 1] = unique_verts[unique_edges[:, 1], 2]
    ez[:, 2] = np.nan

    return unique_verts, boundary_faces, vert_Pcv, vert_Bm, ex.flatten(), ey.flatten(), ez.flatten()


# ================== 3. 波形与对齐模块 ==================
def keep_two_and_flip_second(y: np.ndarray, target_len: int = TARGET_LEN) -> np.ndarray:
    vals = np.asarray(y, dtype=float)
    N = len(vals)
    if N < 5: return vals.copy()

    d = np.diff(vals)
    peaks = [k for k in range(1, N - 1) if d[k - 1] > 0 and d[k] <= 0]
    if len(peaks) < 2:
        x_old, x_new = np.linspace(0, 1, N), np.linspace(0, 1, target_len)
        return np.interp(x_new, x_old, vals - vals.mean())

    p1, p2 = peaks[0], peaks[1]
    valleys = [k for k in range(1, N - 1) if d[k - 1] < 0 and d[k] >= 0]

    v0_candidates = [v for v in valleys if v < p1]
    v0 = v0_candidates[-1] if v0_candidates else 0
    v1_candidates = [v for v in valleys if p1 < v < p2]
    v1 = v1_candidates[-1] if v1_candidates else (p1 + p2) // 2
    v2_candidates = [v for v in valleys if v > p2]
    v2 = v2_candidates[0] if v2_candidates else (N - 1)

    v0, v1, v2 = int(max(0, min(v0, N - 2))), int(max(v0 + 1, min(v1, N - 2))), int(max(v1 + 1, min(v2, N - 1)))

    seg = vals[v0:v2 + 1].copy()
    seg[(v1 - v0):] *= -1.0
    seg -= seg.mean()

    return np.interp(np.linspace(0, 1, target_len), np.linspace(0, 1, len(seg)), seg)


def triangle_min_up_down(y: np.ndarray, target_len: int = TARGET_LEN) -> np.ndarray:
    vals = np.asarray(y, dtype=float)
    if vals.size < 5: return vals.copy()
    v0 = int(np.argmin(vals))
    rot = np.concatenate([vals[v0:], vals[:v0]])
    d = np.diff(rot)
    v2 = next((k for k in range(2, len(rot) - 1) if d[k - 1] < 0 and d[k] >= 0), None)
    seg = rot if v2 is None else rot[:v2 + 1]
    seg -= seg.mean()
    return np.interp(np.linspace(0, 1, target_len), np.linspace(0, 1, len(seg)), seg)


def _group_centers_from_coords_csv(coords_csv_path: str, group_size: int = GROUP_SIZE,
                                   pick_idx=VERT_PICK) -> np.ndarray:
    df = pd.read_csv(coords_csv_path)
    coords = df[['x', 'y', 'z']].values.astype(np.float64)
    centers = [coords[[g * group_size + i for i in pick_idx], :].mean(axis=0)
               for g in range(len(coords) // group_size)
               if (g * group_size + max(pick_idx)) < len(coords)]
    return np.vstack(centers) if centers else np.empty((0, 3), dtype=np.float64)


def _group_centers_from_fld(file_path: str, group_size: int = GROUP_SIZE, pick_idx=VERT_PICK):
    arr = read_grid_data(file_path)
    centers, hmean = [], []
    for g in range(len(arr) // group_size):
        base = g * group_size
        if base + max(pick_idx) >= len(arr): break
        centers.append(arr[[base + i for i in pick_idx], :3].astype(np.float64).mean(axis=0))
        hmean.append(arr[base:base + group_size, 3].astype(np.float64).mean())
    return (np.vstack(centers), np.asarray(hmean, dtype=np.float64)) if centers else (np.empty((0, 3)), np.empty(0))


def compute_hdc_from_same_grid_base_to_hdc(hdc_fld_path, coords_csv_path, fill_val):
    base_centers = _group_centers_from_coords_csv(coords_csv_path)
    n_cells = len(base_centers)
    hdc_centers, hdc_means = _group_centers_from_fld(hdc_fld_path)

    tree_hdc = cKDTree(hdc_centers)
    dist_m, nn_idx = tree_hdc.query(base_centers, k=1)

    radius_used = float(np.percentile(dist_m, 90) * 1.5) if len(base_centers) >= 2 else np.inf
    matched = dist_m <= radius_used

    Hdc_aligned = np.full(n_cells, float(fill_val), dtype=np.float64)
    Hdc_aligned[matched] = hdc_means[nn_idx[matched]]
    return Hdc_aligned


# ================== 4. 核心调度：网格处理 Pipeline ==================
def process_fld_data_backend(fld_path, hdc_path, user_params, output_dir, progress_callback=None):
    out_dir = Path(output_dir) / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    file_names = sorted([f for f in os.listdir(fld_path) if f.endswith('.fld')], key=get_time_from_filename)
    file_paths = [os.path.join(fld_path, f) for f in file_names]

    if not file_paths:
        raise ValueError("未找到任何 .fld 文件")

    if progress_callback:
        progress_callback(30, "阶段 3/4: 正在提取坐标与处理底层网格...")

    first_grid = read_grid_data(file_paths[0])
    coord_path = out_dir / "coordinates.csv"
    pd.DataFrame(first_grid[:, :3], columns=['x', 'y', 'z']).to_csv(coord_path, index=False)

    n_workers = 4
    results_B, volume_list = [], None

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        future_map = {pool.submit(process_one_fld, p): idx for idx, p in enumerate(file_paths)}
        for future in as_completed(future_map):
            idx = future_map[future]
            B_list, V_list = future.result()
            results_B.append((idx, B_list))
            if volume_list is None: volume_list = V_list

    results_B.sort(key=lambda x: x[0])
    df_B = pd.DataFrame([b for _, b in results_B]).T

    if progress_callback:
        progress_callback(50, "阶段 3/4: 正在对齐波形并处理几何属性...")

    processed_rows = [keep_two_and_flip_second(row, TARGET_LEN) for row in df_B.to_numpy()]
    df_B = pd.DataFrame(processed_rows)

    df_Bm = pd.DataFrame(df_B.max(axis=1))
    df_Bm.to_csv(out_dir / "Bm.csv", index=False, header=False)
    df_B.to_csv(out_dir / "B.csv", index=False, header=False)

    row_count = len(df_B)
    pd.DataFrame([user_params['frequency']] * row_count).to_csv(out_dir / "F.csv", index=False, header=False)
    pd.DataFrame([user_params['temperature']] * row_count).to_csv(out_dir / "T.csv", index=False, header=False)
    pd.DataFrame(volume_list).to_csv(out_dir / "volume.csv", index=False, header=False)

    if hdc_path and os.path.exists(hdc_path):
        Hdc_arr = compute_hdc_from_same_grid_base_to_hdc(hdc_path, str(coord_path), fill_val=user_params['hdc'])
        pd.DataFrame(Hdc_arr).to_csv(out_dir / "Hdc.csv", index=False, header=False)
    else:
        Hdc_scaled = np.full(row_count, fill_value=user_params['hdc'], dtype=float)
        pd.DataFrame(Hdc_scaled).to_csv(out_dir / "Hdc.csv", index=False, header=False)

    N = len(df_B)
    onehot = np.zeros((N, 3), dtype=int)

    if user_params.get('use_manual_waveform', False):
        text2idx = {"正弦波": 0, "三角波": 1, "梯形波": 2}
        idx = text2idx.get(user_params['waveform_type'], 0)
        onehot[:, idx] = 1
        if idx == 1:
            new_rows = [triangle_min_up_down(row.values, TARGET_LEN) for _, row in df_B.iterrows()]
            pd.DataFrame(new_rows).to_csv(out_dir / "B.csv", index=False, header=False)
            pd.DataFrame(np.max(new_rows, axis=1)).to_csv(out_dir / "Bm.csv", index=False, header=False)
    else:
        text2idx = {"正弦波": 0, "三角波": 1, "梯形波": 2}
        idx = text2idx.get(user_params['waveform_type'], 0)
        onehot[:, idx] = 1

    pd.DataFrame(onehot).to_csv(out_dir / "Waveform.csv", index=False, header=False)
    return out_dir


# ================== 5. 核心调度：AI 模型预测 Pipeline ==================
def predict_core_loss_backend(data_dir, first_fld, user_params, output_root, progress_callback=None):
    material = user_params['material']

    if progress_callback:
        progress_callback(70, f"阶段 4/4: 正在加载 {material} AI 模型进行损耗预测...")

    current_dir = os.path.dirname(os.path.abspath(__file__))
    MODEL_ROOT = os.path.join(current_dir, "magnet_result")
    CKPT_PATH = os.path.join(MODEL_ROOT, f'{material}_model.ckpt')
    NORM_INFO_PATH = os.path.join(MODEL_ROOT, f'{material}_train_norm_dic.json')

    if not os.path.exists(CKPT_PATH) or not os.path.exists(NORM_INFO_PATH):
        raise FileNotFoundError(f"找不到材料 {material} 的模型文件或归一化配置！\n请检查路径：\n{CKPT_PATH}")

    data_B = pd.read_csv(os.path.join(data_dir, 'B.csv'), header=None)
    data_Bm = pd.read_csv(os.path.join(data_dir, 'Bm.csv'), header=None)
    data_F = pd.read_csv(os.path.join(data_dir, 'F.csv'), header=None)
    data_Hdc = pd.read_csv(os.path.join(data_dir, 'Hdc.csv'), header=None)
    data_T = pd.read_csv(os.path.join(data_dir, 'T.csv'), header=None)
    data_W = pd.read_csv(os.path.join(data_dir, 'Waveform.csv'), header=None)
    data_Vol = pd.read_csv(os.path.join(data_dir, 'volume.csv'), header=None)

    pl.seed_everything(666)

    dm = MagNetDataModule(
        data_B=data_B, data_T=data_T, data_F=data_F, data_H_dc=data_Hdc,
        data_P=None, data_W=data_W, data_Bm=data_Bm,
        batch_size=256, num_workers=0,
        norm_info_path=NORM_INFO_PATH
    )
    dm.prepare_data()
    dm.setup('inference')

    net = Transformer()

    model = Lit_model.load_from_checkpoint(
        checkpoint_path=CKPT_PATH,
        net=net,
        normB=dm.normB, normF=dm.normF, normP=dm.normP, sample_num=1024,
        strict=True
    )

    trainer = pl.Trainer(accelerator="cpu", deterministic=True, logger=False)
    trainer.test(model=model, dataloaders=dm.test_dataloader())

    # 👇 核心修复：取出模型预测值与真实Bm，进行物理边界拦截
    Pcv = model.results.reshape(-1).astype(float)
    volume = data_Vol.values.reshape(-1)
    raw_Bm = data_Bm.values.reshape(-1)

    # 1. 物理死区拦截：如果网格的峰值磁密 Bm < 15mT (0.015 T)，物理上损耗几乎为0，强制清零，防止 AI 模型对未知死区胡乱放大
    dead_zone_mask = raw_Bm < 0.015
    Pcv[dead_zone_mask] = 0.0

    # 2. 暴力防爆拦截：如果模型依然对某些特殊网格输出大于 1e7 W/m^3 的离谱体密度损耗，强制清零
    explosion_mask = Pcv > 1e7
    Pcv[explosion_mask] = 0.0
    # 👆 修复结束

    Ptotal = Pcv * volume
    total_core_loss = np.sum(Ptotal)
    total_volume_mm3 = np.sum(volume) * 1e9

    if progress_callback:
        progress_callback(90, "预测完成，正在重构 3D 拓扑网格与平滑渲染数据...")

    result_dir = Path(output_root) / "result"
    result_dir.mkdir(parents=True, exist_ok=True)
    csv_path = result_dir / f"per_cell_summary_{material}.csv"

    # 生成明细 CSV
    wave_map = {0: "正弦波", 1: "三角波", 2: "梯形波"}
    wave_idx = np.argmax(data_W.values, axis=1)
    coord_path = os.path.join(str(data_dir), "coordinates.csv")
    centers = _group_centers_from_coords_csv(coord_path)

    per_cell = pd.DataFrame({
        "cell_id": np.arange(Pcv.size) + 1, "x": centers[:, 0], "y": centers[:, 1], "z": centers[:, 2],
        "design": user_params.get('design_name', 'Unnamed'), "material": material,
        "waveform": np.vectorize(wave_map.get)(wave_idx), "Bm_T": data_Bm.values.reshape(-1),
        "F_Hz": data_F.values.reshape(-1), "Hdc_Am": data_Hdc.values.reshape(-1),
        "T_C": data_T.values.reshape(-1), "Volume_m3": volume, "Volume_mm3": volume * 1e9,
        "Pcv_W_per_m3": Pcv, "P_cell_W": Ptotal,
    })
    per_cell.to_csv(csv_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_NONNUMERIC)

    # 提取并保存平滑网格拓扑数据 (强制将路径转为字符串避免 Windows 错误)
    first_grid = read_grid_data(first_fld)
    mesh_data = extract_smooth_mesh_data(first_grid, Pcv, data_Bm.values.reshape(-1))

    mesh_npz_path = result_dir / f"surface_mesh_{material}.npz"
    np.savez_compressed(
        str(mesh_npz_path),
        x=mesh_data[0][:, 0], y=mesh_data[0][:, 1], z=mesh_data[0][:, 2],
        i=mesh_data[1][:, 0], j=mesh_data[1][:, 1], k=mesh_data[1][:, 2],
        pcv=mesh_data[2], bm=mesh_data[3],
        ex=mesh_data[4], ey=mesh_data[5], ez=mesh_data[6]
    )

    return total_core_loss, total_volume_mm3, str(csv_path), str(mesh_npz_path)


# ================== 6. 供前端调用的顶层 API ==================
def run_fem_pipeline(fld_extract_path: str, hdc_fld_path: Optional[str], user_params: dict, temp_dir: str,
                     progress_callback: Optional[Callable] = None):
    # 找到首个 fld 用于提取拓扑结构
    file_names = sorted([f for f in os.listdir(fld_extract_path) if f.endswith('.fld')], key=get_time_from_filename)
    first_fld = os.path.join(fld_extract_path, file_names[0])

    data_dir = process_fld_data_backend(fld_extract_path, hdc_fld_path, user_params, temp_dir, progress_callback)
    total_loss, total_volume_mm3, detail_csv_path, mesh_npz_path = predict_core_loss_backend(data_dir, first_fld,
                                                                                             user_params, temp_dir,
                                                                                             progress_callback)

    return total_loss, total_volume_mm3, detail_csv_path, mesh_npz_path
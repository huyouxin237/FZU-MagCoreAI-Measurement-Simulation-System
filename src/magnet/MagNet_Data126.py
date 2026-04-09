from typing import Any
import torch
from torch.utils.data import Dataset, DataLoader, TensorDataset
import pytorch_lightning as pl
import json
import os
import numpy as np


class EmptyDataset(Dataset):
    def __init__(self):
        super(EmptyDataset, self).__init__()

    def __len__(self):
        return 0

    def __getitem__(self, index):
        raise IndexError("Empty dataset, no items to get")


class MagNetDataModule(pl.LightningDataModule):
    def __init__(self, data_B, data_T, data_F, data_H_dc,
                 data_P, data_W, data_Bm,
                 norm_info_path=None, batch_size=1, num_workers=20, sample_num=1024):
        super().__init__()
        self.data_B = data_B
        self.data_F = data_F
        self.data_T = data_T
        self.data_H_dc = data_H_dc
        self.data_P = data_P
        self.data_W = data_W  # one-hot [N, 3]
        self.data_Bm = data_Bm  # [N, 1]
        self.norm_info_path = norm_info_path
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.sample_num = sample_num
        self.norm_info = None
        self.is_infer = data_P is None

        if norm_info_path is not None and os.path.exists(norm_info_path):
            with open(norm_info_path, 'r') as file:
                info = json.load(file)
            self.norm_info = {
                'normB': [torch.tensor(info['normB'][0]), torch.tensor(info['normB'][1])],
                'normF': [torch.tensor(info['normF'][0]), torch.tensor(info['normF'][1])],
                'normT': [torch.tensor(info['normT'][0]), torch.tensor(info['normT'][1])],
                'normH_dc': [torch.tensor(info['normH_dc'][0]), torch.tensor(info['normH_dc'][1])],
                'normP': [torch.tensor(info['normP'][0]), torch.tensor(info['normP'][1])],
                'normBm': [torch.tensor(info['normBm'][0]), torch.tensor(info['normBm'][1])]
            }

    def prepare_data(self):
        self.data_B = self.data_B.astype(np.float32)
        in_B = torch.from_numpy(self.data_B.values).float().unsqueeze(2)
        N, D, C = in_B.size()
        in_B = torch.nn.functional.interpolate(in_B.view(N, C, D), size=self.sample_num, mode='linear').view(N, -1, C)

        in_Bm = torch.from_numpy(self.data_Bm.values).float().view(-1, 1)
        in_T = torch.from_numpy(self.data_T.values).float().view(-1, 1)
        in_H_dc = torch.from_numpy(self.data_H_dc.values).float().view(-1, 1)
        in_F = torch.from_numpy(self.data_F.values).float().view(-1, 1)
        in_F = torch.log(in_F)
        in_W = torch.from_numpy(self.data_W.values).float()  # one-hot [N, 3]
        # === 这里插入统计代码 =========================
        counts = in_W.sum(dim=0)  # Tensor([n_sine, n_tri, n_trap])
        print("正弦 / 三角 / 梯形 样本数:", counts.tolist())
        # =============================================
        # 归一化
        if self.norm_info is None:
            self.normB = [torch.mean(in_B), torch.std(in_B)]
            self.normBm = [torch.mean(in_Bm), torch.std(in_Bm)]
            self.normF = [torch.mean(in_F), torch.std(in_F)]
            self.normT = [torch.mean(in_T), torch.std(in_T)]
            self.normH_dc = [torch.mean(in_H_dc), torch.std(in_H_dc)]
        else:
            self.normB = self.norm_info['normB']
            self.normF = self.norm_info['normF']
            self.normT = self.norm_info['normT']
            self.normH_dc = self.norm_info['normH_dc']
            self.normBm = self.norm_info['normBm']

        in_B = (in_B - self.normB[0]) / self.normB[1]
        in_F = (in_F - self.normF[0]) / self.normF[1]
        in_T = (in_T - self.normT[0]) / self.normT[1]
        in_H_dc = (in_H_dc - self.normH_dc[0]) / self.normH_dc[1]
        in_Bm = (in_Bm - self.normBm[0]) / self.normBm[1]

        if self.data_P is not None:
            gt_P = torch.from_numpy(self.data_P.values).float().view(-1, 1)
            out_P = torch.log(gt_P)
            self.normP = [torch.mean(out_P), torch.std(out_P)]
            out_P = (out_P - self.normP[0]) / self.normP[1]
        else:
            gt_P = torch.zeros((N, 1))
            out_P = torch.zeros((N, 1))
            assert self.norm_info is not None, 'norm_info is necessary when groundtruth is not provided!'
            self.normP = self.norm_info['normP']

        self.dataset = TensorDataset(
            in_B,  # 0
            in_T,  # 1
            in_F,  # 2
            in_H_dc,  # 3
            in_W,  # 4  <<<<<<<<<<<<<<<<<<<<<<<<<<<
            in_Bm,  # 5
            out_P,  # 6
            gt_P  # 7
        )

        if self.norm_info is None and self.norm_info_path is not None:
            norm_info = {
                'normB': [self.normB[0].item(), self.normB[1].item()],
                'normF': [self.normF[0].item(), self.normF[1].item()],
                'normT': [self.normT[0].item(), self.normT[1].item()],
                'normH_dc': [self.normH_dc[0].item(), self.normH_dc[1].item()],
                'normP': [self.normP[0].item(), self.normP[1].item()],
                'normBm': [self.normBm[0].item(), self.normBm[1].item()]
            }
            with open(self.norm_info_path, 'w') as f:
                json.dump(norm_info, f, indent=4)
            # assert torch.all((in_W.sum(dim=1) == 1)), "每条样本的 one-hot 波形变量必须严格为 one-hot！"
            print("data_F describe:\n", self.data_F.describe())
            print("data_P describe:\n", self.data_P.describe())
            if (self.data_F <= 0).any().any():  # 针对DataFrame所有元素
                print("警告！频率中含有 <= 0 的值！")
            if (self.data_P <= 0).any().any():
                print("警告！损耗P中含有 <= 0 的值！")

    # setup, train_dataloader, val_dataloader, test_dataloader保持不变

    def setup(self, stage=None, train_ratio=0.8, val_ratio=0.2):
        # 判断是否进入推理模式（自动 + 手动双保险）
        is_infer = (stage == 'inference') or (self.data_P is None)

        if is_infer:
            print("当前为推理模式（inference mode），不划分训练集和验证集。")
            self.train_dataset = EmptyDataset()
            self.valid_dataset = EmptyDataset()
            self.test_dataset = self.dataset
        else:
            print("当前为训练模式（training mode），将数据划分为训练集、验证集、测试集。")
            train_size = int(train_ratio * len(self.dataset))
            valid_size = int(val_ratio * len(self.dataset))
            test_size = len(self.dataset) - train_size - valid_size
            self.train_dataset, self.valid_dataset, self.test_dataset = torch.utils.data.random_split(
                self.dataset, [train_size, valid_size, test_size])

        print(
            f"数据划分情况：Train({len(self.train_dataset)}) | Val({len(self.valid_dataset)}) | Test({len(self.test_dataset)})")

    def train_dataloader(self):
        return DataLoader(
            self.train_dataset,
            batch_size=self.batch_size,
            num_workers=self.num_workers,
            shuffle=True,
            pin_memory=True,
            persistent_workers=(self.num_workers > 0)
        )

    def val_dataloader(self):
        return DataLoader(
            self.valid_dataset,
            batch_size=self.batch_size,
            num_workers=self.num_workers,
            shuffle=False,
            pin_memory=True,
            persistent_workers=(self.num_workers > 0)
        )

    def test_dataloader(self):
        return DataLoader(
            self.test_dataset,
            batch_size=self.batch_size,
            num_workers=self.num_workers,
            shuffle=False,
            pin_memory=True,
            persistent_workers=(self.num_workers > 0)
        )

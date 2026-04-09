from typing import Any
import torch
import math
import matplotlib.pyplot as plt
from torch import optim, nn, Tensor
import pytorch_lightning as pl
import numpy as np


class Transformer(nn.Module):
    def __init__(self,
                 B_in_channel=1024,
                 dim_hidden=24,
                 dim_proj_fusion=40,
                 n_encoder_layers=1,
                 n_heads=4,
                 dropout_encoder=0.0,
                 dropout_pos_enc=0.0,
                 dim_feedforward_encoder=40,
                 num_waveform_types=3,  # 波形类型数量
                 fft_bins=16  # <--- 新增: 取多少个FFT谐波分量
                 ):
        super().__init__()

        self.fft_bins = fft_bins

        self.proj_B = nn.Sequential(
            nn.Linear(1, dim_hidden),
            nn.GELU(),
            nn.Linear(dim_hidden, dim_hidden)
        )

        # 保留PE不影响功能，也可注释
        self.positional_encoding_layer = PositionalEncoding(
            d_model=dim_hidden,
            dropout=dropout_pos_enc,
            max_len=B_in_channel
        )
        # 三分支encoder
        self.encoder_list = nn.ModuleList([
            nn.TransformerEncoder(
                nn.TransformerEncoderLayer(
                    d_model=dim_hidden,
                    nhead=n_heads,
                    dim_feedforward=dim_feedforward_encoder,
                    dropout=dropout_encoder,
                    activation="gelu",
                    batch_first=True
                ),
                num_layers=n_encoder_layers,
                norm=None
            ) for _ in range(num_waveform_types)
        ])

        self.proj_fusion = nn.Sequential(
            nn.Linear(dim_hidden + self.fft_bins + 4, dim_proj_fusion),
            nn.GELU(),
            nn.Linear(dim_proj_fusion, dim_proj_fusion),
            nn.GELU(),
            nn.Linear(dim_proj_fusion, 1)
        )

    def forward(
            self, B_curve: Tensor, Temp: Tensor, Freq: Tensor,
            H_dc: Tensor, W: Tensor, Bm: Tensor
    ) -> Tensor:
        # ---- Transformer branch: mean pooling ----
        B_embed = self.proj_B(B_curve)
        B_embed = self.positional_encoding_layer(B_embed)
        enc_out = torch.zeros_like(B_embed)
        for i, encoder in enumerate(self.encoder_list):
            idx = (W[:, i] == 1).nonzero(as_tuple=True)[0]
            if idx.numel() == 0:
                continue
            enc_res = encoder(B_embed[idx])
            enc_out[idx] = enc_res
        trans_feat = enc_out.mean(dim=1)  # [batch, dim_hidden]

        # ---- 原始波形 FFT pooling ----
        x = B_curve.squeeze(-1)  # [batch, seq]
        Xf = torch.fft.rfft(x, dim=1)
        fft_feats = torch.abs(Xf[:, :self.fft_bins])
        fft_feats = (fft_feats - fft_feats.mean(1, keepdim=True)) / (fft_feats.std(1, keepdim=True) + 1e-6)

        env_feat = torch.cat([Temp, Freq, H_dc, Bm], dim=1)  # (batch, 4)
        # 关键：三路拼接
        fusion_input = torch.cat([trans_feat, fft_feats, env_feat], dim=1)  # (batch, dim_hidden + fft_bins + 4)

        P_pred = self.proj_fusion(fusion_input)
        return P_pred


class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, dropout: float = 0.1, max_len: int = 5000):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        position = torch.arange(max_len).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2) * (-math.log(10000.0) / d_model))
        pe = torch.zeros(max_len, d_model)
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer('pe', pe)

    def forward(self, x: Tensor) -> Tensor:
        x = x + self.pe[:x.size(1)]
        return self.dropout(x)


class Lit_model(pl.LightningModule):
    def __init__(self, net, learning_rate=0.003, save_dir='./', CLR_step_size=None,
                 normB=None, normF=None, normP=None, sample_num=1024):
        super().__init__()
        self.net = net
        self.learning_rate = learning_rate
        self.CLR_step_size = CLR_step_size
        self.save_dir = save_dir
        self.normB = normB
        self.normF = normF
        self.normP = normP
        self.val_err = None
        self.val_err95 = None

        self.example_input_array = tuple((
            torch.randn(32, sample_num, 1),  # B
            torch.randn(32, 1),  # T
            torch.randn(32, 1),  # F
            torch.randn(32, 1),  # Hdc
            torch.nn.functional.one_hot(torch.randint(0, 3, (32,)), num_classes=3).float(),
            torch.randn(32, 1),
            torch.randn(32, 1)
        ))

        self.metric = torch.nn.MSELoss()
        self.val_step_err = []
        self.val_step_loss = []
        self.test_pred_P = []
        self.test_step_err = []
        self.results = torch.tensor([])

    def forward(self, in_B, in_T, in_F, in_H_dc, in_W, in_Bm, out_P=None):
        return self.net(in_B, in_T, in_F, in_H_dc, in_W, in_Bm)

    def training_step(self, batch, batch_idx):
        in_B, in_T, in_F, in_Hdc, in_W, in_Bm, out_P, gt_P = batch
        pred_P = self.net(in_B, in_T, in_F, in_Hdc, in_W, in_Bm)
        loss = self.metric(pred_P, out_P)
        lr = self.trainer.optimizers[0].param_groups[0]['lr']
        self.log("train_loss", loss, prog_bar=True)
        self.log('lr', lr, prog_bar=True, on_step=True, on_epoch=False)
        return loss

    def on_validation_epoch_start(self):
        self.val_step_err = []
        self.val_step_loss = []

    def validation_step(self, batch, batch_idx):
        in_B, in_T, in_F, in_Hdc, in_W, in_Bm, out_P, gt_P = batch
        pred_P = self.net(in_B, in_T, in_F, in_Hdc, in_W, in_Bm)
        val_loss = self.metric(pred_P, out_P)
        retrans_pred_P = torch.exp(pred_P * self.normP[1] + self.normP[0])
        # 新增调试输出
        if batch_idx == 0:
            print("gt_P前10:", gt_P.view(-1)[:10])
            print("pred_P前10:", pred_P.view(-1)[:10])
            print("retrans_pred_P前10:", retrans_pred_P.view(-1)[:10])
        error_re = torch.abs(retrans_pred_P - gt_P) / (torch.abs(gt_P) + 1e-8) * 100
        self.val_step_err.append(error_re.detach().cpu())
        self.val_step_loss.append(val_loss.detach().cpu())
        self.log("val_loss", val_loss, prog_bar=True)

    def on_validation_epoch_end(self):
        import numpy as np
        if not self.val_step_err:
            self.val_err = None
            self.val_err95 = None
            print("val_step_err为空")
            return
        all_errors = torch.cat([x.reshape(-1) for x in self.val_step_err], dim=0).numpy()
        print("all_errors前10:", all_errors[:10])
        print("all_errors是否含有nan:", np.isnan(all_errors).any())
        val_err = float(np.mean(all_errors))
        val_err95 = float(np.percentile(all_errors, 95))
        print("val_err:", val_err, "val_err95:", val_err95)
        self.log("val_err", val_err, prog_bar=True)
        self.log("val_err95", val_err95, prog_bar=True)
        self.val_err = val_err
        self.val_err95 = val_err95
        self.val_step_err.clear()
        self.val_step_loss.clear()

    def test_step(self, batch, batch_idx):
        in_B, in_T, in_F, in_Hdc, in_W, in_Bm, out_P, gt_P = batch
        pred_P = self.net(in_B, in_T, in_F, in_Hdc, in_W, in_Bm)
        retrans_pred_P = torch.exp(pred_P * self.normP[1] + self.normP[0])
        self.test_pred_P.append(retrans_pred_P)
        if not (gt_P == 0).all():
            Error_re = torch.abs(retrans_pred_P - gt_P) / torch.abs(gt_P) * 100
            self.test_step_err.append(Error_re)

    def on_test_epoch_end(self):
        if len(self.test_step_err) > 0:
            test_epoch_err = torch.vstack(self.test_step_err)
            test_err = test_epoch_err.mean()
            test_err_95 = torch.quantile(test_epoch_err, 0.95, interpolation='nearest')
            self.log("test_err", test_err)
            self.log('test_err95', test_err_95)
        data_P = torch.vstack(self.test_pred_P)
        self.results = data_P.squeeze(1).cpu().numpy()

    def configure_optimizers(self):
        optimizer = optim.Adam(self.parameters(), lr=self.learning_rate)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer,
            mode='min',
            factor=0.9,
            patience=8,
            min_lr=1e-7
            # verbose=True  ← ❌ 删掉！PyTorch 不需要它
        )
        scheduler_dict = {
            'scheduler': scheduler,
            'monitor': 'val_err',
            'interval': 'epoch',
            'frequency': 1
        }
        return {'optimizer': optimizer, 'lr_scheduler': scheduler_dict}



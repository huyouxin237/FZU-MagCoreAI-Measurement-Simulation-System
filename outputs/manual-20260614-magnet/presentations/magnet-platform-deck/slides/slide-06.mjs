import path from "node:path";
import { C, rect, text, pill, addTitle, addFooter, addImage, line } from "./common.mjs";

export async function slide06(presentation, ctx) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  addTitle(
    slide,
    "FEM SURROGATE",
    "FEM 模块对 FLD 场数据执行网格级 AI 损耗预测",
    "线上不实时求解 Maxwell：用户上传已导出的场数据，平台完成解析、波形对齐、代理预测与三维结果重建"
  );

  rect(slide, 48, 192, 260, 426, C.paper, { lineColor: "#D5DCE1" });
  text(slide, "1  数据输入", 68, 210, 190, 30, { fontSize: 21, bold: true, color: C.red });
  pill(slide, "上传 fld.zip", 72, 266, 210, 44, C.paleBlue, C.navy, 16);
  pill(slide, "可选 Hdc.fld", 72, 326, 210, 44, C.paleGreen, C.teal, 16);
  text(slide, "频率 / 温度 / Hdc\n波形类型 / 材料 / 设计名", 74, 398, 206, 82, {
    fontSize: 17, color: C.ink, align: "center",
  });
  text(slide, "支持本地上传或服务器预设数据包", 74, 522, 206, 50, {
    fontSize: 14, color: C.gray, align: "center",
  });

  rect(slide, 334, 192, 330, 426, "#EEF2F5", { line: false });
  text(slide, "2  网格处理", 356, 210, 220, 30, { fontSize: 21, bold: true, color: C.blue });
  const process = [
    "按时间步读取 .fld",
    "提取四面体单元 B(t)",
    "计算单元体积与 Bm",
    "统一插值为 1024 点",
    "对齐温度 / 频率 / Hdc",
  ];
  process.forEach((p, i) => {
    rect(slide, 368, 264 + i * 58, 262, 40, i === 4 ? C.paleYellow : C.paper, { lineColor: "#CCD4DA" });
    text(slide, p, 384, 269 + i * 58, 230, 30, { fontSize: 15, color: C.ink, align: "center" });
    if (i < process.length - 1) line(slide, 499, 304 + i * 58, 499, 322 + i * 58, C.blue, 2);
  });

  rect(slide, 690, 192, 248, 426, C.paper, { lineColor: "#D5DCE1" });
  text(slide, "3  Transformer–FFT", 708, 210, 212, 30, { fontSize: 20, bold: true, color: C.teal, align: "center" });
  addImage(
    slide,
    path.join(ctx.assetDir, "transformer_fft_hybrid_loss_model.png"),
    724, 258, 180, 328, "contain",
    "Transformer FFT hybrid loss model"
  );

  rect(slide, 966, 192, 262, 426, "#EAF0F5", { line: false });
  text(slide, "4  空间结果", 988, 210, 200, 30, { fontSize: 21, bold: true, color: C.navy });
  const colors = ["#D9ECF2","#9BC9D8","#4D9DB6","#F2C36B","#E66B4E"];
  for (let r = 0; r < 5; r += 1) {
    for (let c = 0; c < 5; c += 1) {
      const color = colors[Math.min(4, Math.floor((r + c) / 2))];
      rect(slide, 1000 + c * 36, 274 + r * 36, 30, 30, color, {
        geometry: "triangle", lineColor: "#FFFFFF", lineWidth: 1,
        rotation: (r + c) % 2 ? 180 : 0,
      });
    }
  }
  text(slide, "可交互三维网格", 1002, 470, 180, 26, { fontSize: 16, bold: true, color: C.ink, align: "center" });
  pill(slide, "Bm 分布", 990, 516, 104, 36, C.paleBlue, C.navy, 14);
  pill(slide, "Pcv 分布", 1102, 516, 104, 36, C.paleYellow, C.red, 14);
  text(slide, "汇总总损耗并下载逐单元 CSV", 990, 568, 218, 38, {
    fontSize: 14, color: C.gray, align: "center",
  });

  addFooter(slide, 6);
  return slide;
}

import path from "node:path";
import { C, rect, text, pill, addImage, addCircuitTrace } from "./common.mjs";

export async function slide01(presentation, ctx) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  addCircuitTrace(slide);

  text(slide, "MAGNET AI", 54, 42, 250, 34, {
    fontSize: 18, color: C.red, bold: true,
  });
  text(slide, "磁芯损耗在线预测\n与多物理场分析平台", 54, 98, 660, 150, {
    fontSize: 52, color: C.teal, bold: true, valign: "top",
  });
  text(slide, "实验数据库 × 轻量 Transformer × 电路仿真 × FEM 场后处理", 58, 250, 690, 45, {
    fontSize: 21, color: C.ink, bold: true,
  });
  text(slide, "面向磁性材料研究、磁性器件设计与教学验证的浏览器交互式工程平台", 58, 298, 680, 58, {
    fontSize: 20, color: C.gray,
  });

  const modules = [
    ["数据查询", C.paleGreen, C.teal],
    ["智能表格", C.paleBlue, C.teal],
    ["B-H预测", C.paleYellow, C.red],
    ["电路仿真", "#DDE6F5", C.blue],
    ["FEM预测", "#D9E1F0", C.navy],
  ];
  modules.forEach((m, i) => pill(slide, m[0], 58 + i * 132, 392, 118, 42, m[1], m[2], 16));

  rect(slide, 790, 56, 438, 530, C.paper, { lineColor: "#D8DEE3", lineWidth: 1 });
  addImage(
    slide,
    path.join(ctx.assetDir, "system-photo.png"),
    812, 78, 394, 282, "cover",
    "MagNet magnetic measurement experimental setup"
  );
  text(slide, "从真实实验数据出发", 816, 382, 360, 34, {
    fontSize: 25, color: C.navy, bold: true,
  });
  text(slide, "覆盖材料、频率、温度、磁通密度、波形与直流偏置等多维工况", 816, 421, 360, 70, {
    fontSize: 18, color: C.gray, valign: "top",
  });
  rect(slide, 816, 515, 340, 4, C.red, { line: false });
  text(slide, "在线查询 → AI预测 → 仿真耦合 → 空间损耗分布", 816, 524, 370, 44, {
    fontSize: 16, color: C.ink, bold: true,
  });

  text(slide, "Princeton MagNet 数据与模型体系的本地化集成与扩展", 58, 626, 690, 30, {
    fontSize: 14, color: C.gray,
  });
  text(slide, "01", 1180, 640, 48, 28, {
    fontSize: 13, color: C.gray, bold: true, align: "right",
  });
  return slide;
}

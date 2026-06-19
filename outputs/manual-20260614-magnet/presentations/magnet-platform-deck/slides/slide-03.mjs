import path from "node:path";
import { C, rect, text, pill, addTitle, addFooter, addImage, waveform, line } from "./common.mjs";

export async function slide03(presentation, ctx) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  addTitle(
    slide,
    "DATA EXPLORATION",
    "实验数据库让材料与工况筛选可视、可查、可下载",
    "数据库页面用于检索真实测量点；智能表格页面用于在给定工况下快速预测损耗"
  );

  rect(slide, 48, 188, 420, 420, C.paper, { lineColor: "#D5DCE1" });
  text(slide, "多维测量空间", 68, 206, 260, 34, {
    fontSize: 22, bold: true, color: C.navy,
  });
  addImage(
    slide,
    path.join(ctx.assetDir, "measurement-range.png"),
    70, 250, 376, 272, "contain",
    "MagNet measurement range"
  );
  text(slide, "频率 × 磁通密度 × Hdc × 温度 × 波形占空比", 70, 535, 360, 48, {
    fontSize: 16, color: C.gray, align: "center",
  });

  rect(slide, 500, 188, 330, 420, "#F0F3F6", { line: false });
  text(slide, "交互筛选面板", 522, 206, 250, 34, {
    fontSize: 22, bold: true, color: C.teal,
  });
  pill(slide, "材料：N87", 524, 260, 130, 38, C.paper, C.ink, 15);
  pill(slide, "波形：三角波", 668, 260, 138, 38, C.paper, C.ink, 15);
  text(slide, "频率范围  25–500 kHz", 524, 318, 264, 28, {
    fontSize: 15, color: C.ink,
  });
  rect(slide, 526, 352, 258, 5, "#C8D2D9", { line: false });
  rect(slide, 594, 349, 98, 11, C.teal, { line: false });
  text(slide, "磁通密度  10–350 mT", 524, 382, 264, 28, {
    fontSize: 15, color: C.ink,
  });
  rect(slide, 526, 416, 258, 5, "#C8D2D9", { line: false });
  rect(slide, 566, 413, 138, 11, C.red, { line: false });
  text(slide, "波形预览", 524, 446, 120, 26, {
    fontSize: 15, bold: true, color: C.gray,
  });
  waveform(slide, 534, 482, 240, 66, C.blue, "tri");
  pill(slide, "筛选并查询", 584, 556, 144, 36, C.red, "#FFFFFF", 15);

  rect(slide, 862, 188, 366, 420, C.paper, { lineColor: "#D5DCE1" });
  text(slide, "输出与下载", 884, 206, 220, 34, {
    fontSize: 22, bold: true, color: C.navy,
  });
  line(slide, 914, 514, 1192, 514, "#CDD5DB", 1);
  line(slide, 914, 278, 914, 514, "#CDD5DB", 1);
  const dots = [
    [950,468,C.teal],[980,440,C.blue],[1014,420,C.teal],[1050,382,C.red],
    [1090,350,C.blue],[1126,322,C.red],[1160,290,C.navy],[1180,336,C.teal],
  ];
  dots.forEach(([x,y,c]) => rect(slide, x, y, 12, 12, c, { geometry: "ellipse", line: false }));
  text(slide, "频率 / 磁通密度 / 损耗散点图", 896, 530, 308, 30, {
    fontSize: 15, color: C.gray, align: "center",
  });
  pill(slide, "下载 CSV", 950, 566, 188, 28, C.navy, "#FFFFFF", 14);

  addFooter(slide, 3);
  return slide;
}

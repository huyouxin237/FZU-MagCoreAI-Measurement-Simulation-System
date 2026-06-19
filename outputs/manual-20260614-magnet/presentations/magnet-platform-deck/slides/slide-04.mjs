import path from "node:path";
import { C, rect, text, pill, addTitle, addFooter, addImage, waveform, line } from "./common.mjs";

export async function slide04(presentation, ctx) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  addTitle(
    slide,
    "AI SURROGATE",
    "轻量 Transformer 由 B 波形重建 H 波形并计算 B-H 损耗",
    "模型不是直接输出一个静态系数，而是学习材料在频率、温度与偏置条件下的动态磁滞响应"
  );

  rect(slide, 52, 198, 244, 384, C.paper, { lineColor: "#D5DCE1" });
  text(slide, "输入", 72, 214, 130, 30, { fontSize: 22, bold: true, color: C.red });
  waveform(slide, 78, 268, 190, 92, C.teal, "sine");
  text(slide, "B(t) 单周期波形", 78, 362, 190, 28, {
    fontSize: 16, bold: true, align: "center",
  });
  pill(slide, "f", 76, 426, 46, 38, C.paleBlue, C.navy, 18);
  pill(slide, "T", 132, 426, 46, 38, C.paleGreen, C.teal, 18);
  pill(slide, "Hdc", 188, 426, 76, 38, C.paleYellow, C.red, 16);
  text(slide, "标准波形或用户上传 CSV", 72, 500, 204, 52, {
    fontSize: 15, color: C.gray, align: "center",
  });

  rect(slide, 330, 198, 480, 384, "#EEF2F5", { line: false });
  text(slide, "Encoder–Decoder Transformer", 356, 214, 420, 34, {
    fontSize: 23, bold: true, color: C.navy, align: "center",
  });
  addImage(
    slide,
    path.join(ctx.assetDir, "transformer.png"),
    362, 258, 416, 234, "contain",
    "Transformer architecture for B to H sequence prediction"
  );
  const specs = [
    ["d_model", "24"], ["Heads", "4"], ["Enc/Dec", "1 / 1"], ["序列", "128点"],
  ];
  specs.forEach((s, i) => {
    const x = 354 + i * 108;
    text(slide, s[1], x, 510, 96, 30, { fontSize: 20, bold: true, color: C.teal, align: "center" });
    text(slide, s[0], x, 540, 96, 24, { fontSize: 12, color: C.gray, align: "center" });
  });

  rect(slide, 844, 198, 384, 384, C.paper, { lineColor: "#D5DCE1" });
  text(slide, "输出", 866, 214, 130, 30, { fontSize: 22, bold: true, color: C.navy });
  waveform(slide, 878, 262, 302, 72, C.red, "sine");
  text(slide, "预测 H(t)", 878, 332, 302, 28, { fontSize: 15, bold: true, align: "center" });
  line(slide, 902, 502, 1145, 502, "#BFC8CE", 1);
  line(slide, 1022, 382, 1022, 536, "#BFC8CE", 1);
  const loopPts = [[930,470],[954,430],[990,404],[1022,420],[1054,470],[1082,516],[1114,526],[1140,492]];
  for (let i = 0; i < loopPts.length - 1; i += 1) {
    line(slide, ...loopPts[i], ...loopPts[i + 1], C.blue, 3);
  }
  const loopPts2 = [...loopPts].reverse().map(([x,y],i)=>[x, y - 18 + i*2]);
  for (let i = 0; i < loopPts2.length - 1; i += 1) {
    line(slide, ...loopPts2[i], ...loopPts2[i + 1], C.teal, 3);
  }
  text(slide, "B-H 回线积分 → 体积损耗 Pv", 884, 540, 292, 30, {
    fontSize: 16, bold: true, color: C.ink, align: "center",
  });

  addFooter(slide, 4);
  return slide;
}

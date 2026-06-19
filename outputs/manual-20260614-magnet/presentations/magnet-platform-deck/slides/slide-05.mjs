import { C, rect, text, pill, arrow, addTitle, addFooter, waveform, line } from "./common.mjs";

export async function slide05(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  addTitle(
    slide,
    "CIRCUIT CO-SIMULATION",
    "电路仿真先生成真实激励波形，再由代理模型估算磁芯损耗",
    "电路侧可选 PLECS 或 Python 简化模型；AI 负责把仿真波形映射为磁滞回线与损耗"
  );

  text(slide, "支持拓扑", 54, 194, 100, 28, { fontSize: 17, bold: true, color: C.gray });
  const tops = ["Buck", "Boost", "Flyback", "DAB"];
  tops.forEach((t, i) => pill(slide, t, 174 + i * 142, 187, 126, 42, i === 3 ? C.navy : C.paleBlue, i === 3 ? "#FFFFFF" : C.navy, 17));
  text(slide, "后端", 780, 194, 60, 28, { fontSize: 17, bold: true, color: C.gray });
  pill(slide, "PLECS", 852, 187, 112, 42, C.paleYellow, C.red, 16);
  pill(slide, "Python", 978, 187, 112, 42, C.paleGreen, C.teal, 16);

  const stageY = 288;
  arrow(slide, "输入电路参数\n与磁芯几何", 54, stageY, 228, 104, C.red, { fontSize: 19 });
  arrow(slide, "运行稳态仿真\n获得 B/H 波形", 296, stageY, 228, 104, "#7898D0", { fontSize: 19 });
  arrow(slide, "调用材料\nTransformer", 538, stageY, 228, 104, C.blue, { fontSize: 19 });
  arrow(slide, "回线积分\n计算磁芯损耗", 780, stageY, 228, 104, C.navy, { fontSize: 19 });
  rect(slide, 1024, stageY, 204, 104, C.paper, { lineColor: C.teal, lineWidth: 2 });
  text(slide, "输出", 1044, 298, 80, 24, { fontSize: 15, color: C.gray, bold: true });
  text(slide, "2.37 W", 1040, 324, 164, 34, { fontSize: 29, color: C.teal, bold: true, align: "center" });
  text(slide, "总磁芯损耗", 1040, 362, 164, 18, { fontSize: 12, color: C.gray, align: "center" });

  rect(slide, 54, 446, 1174, 164, "#EEF2F5", { line: false });
  text(slide, "仿真结果不仅给出一个数值，还保留工程可解释性", 78, 466, 580, 34, {
    fontSize: 22, bold: true, color: C.navy,
  });
  waveform(slide, 82, 518, 250, 66, C.blue, "tri");
  text(slide, "磁通波形", 136, 574, 140, 22, { fontSize: 13, color: C.gray, align: "center" });
  line(slide, 404, 576, 572, 576, "#AEB9C0", 1);
  line(slide, 488, 500, 488, 600, "#AEB9C0", 1);
  const p1=[[420,558],[444,522],[470,510],[496,528],[520,566],[548,590]];
  const p2=[[420,540],[444,512],[470,518],[496,546],[520,582],[548,574]];
  for (const pts of [p1,p2]) for(let i=0;i<pts.length-1;i++) line(slide,...pts[i],...pts[i+1],pts===p1?C.teal:C.red,2.5);
  text(slide, "B-H 回线", 430, 574, 120, 22, { fontSize: 13, color: C.gray, align: "center" });
  text(slide, "同时输出", 680, 492, 120, 28, { fontSize: 15, color: C.gray, bold: true });
  pill(slide, "偏置 Hdc", 678, 530, 132, 36, C.paper, C.ink, 14);
  pill(slide, "磁通幅值", 824, 530, 132, 36, C.paper, C.ink, 14);
  pill(slide, "体积损耗", 970, 530, 132, 36, C.paper, C.ink, 14);
  text(slide, "磁通幅值过小/过大时自动提示预测风险", 678, 568, 424, 26, {
    fontSize: 14, color: C.red, bold: true,
  });
  addFooter(slide, 5);
  return slide;
}

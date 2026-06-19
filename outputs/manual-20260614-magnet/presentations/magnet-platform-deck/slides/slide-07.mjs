import path from "node:path";
import { C, rect, text, pill, addFooter, addImage, line } from "./common.mjs";

export async function slide07(presentation, ctx) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  text(slide, "从数据到设计，形成可复用的磁芯损耗分析闭环", 58, 58, 1030, 66, {
    fontSize: 42, color: C.teal, bold: true,
  });
  text(slide, "同一套材料数据与代理模型，服务科研、教学和工程设计三个场景", 62, 128, 880, 34, {
    fontSize: 19, color: C.gray,
  });

  rect(slide, 488, 232, 304, 236, C.navy, { line: false });
  text(slide, "MagNet\n在线平台", 530, 270, 220, 90, {
    fontSize: 36, color: "#FFFFFF", bold: true, align: "center",
  });
  text(slide, "数据 · 模型 · 仿真 · 可视化", 514, 372, 252, 40, {
    fontSize: 16, color: "#DDE7F4", bold: true, align: "center",
  });

  const audiences = [
    ["科研", "查询实验数据\n验证新模型\n导出 B-H 曲线", 80, 232, C.red, C.paleYellow],
    ["教学", "调整波形与工况\n观察磁滞回线\n理解损耗机理", 80, 476, C.teal, C.paleGreen],
    ["设计", "比较材料\n耦合电路波形\n评估空间损耗", 900, 232, C.blue, C.paleBlue],
    ["扩展", "新增材料模型\n接入仿真数据\n形成团队工具链", 900, 476, C.navy, "#DDE5F1"],
  ];
  audiences.forEach(([titleValue, body, x, y, accent, fill]) => {
    rect(slide, x, y, 300, 156, fill, { lineColor: accent, lineWidth: 1.5 });
    rect(slide, x, y, 8, 156, accent, { line: false });
    text(slide, titleValue, x + 28, y + 18, 100, 36, {
      fontSize: 24, bold: true, color: accent,
    });
    text(slide, body, x + 28, y + 60, 240, 78, {
      fontSize: 17, color: C.ink, valign: "top",
    });
  });

  line(slide, 380, 310, 488, 310, C.red, 3);
  line(slide, 380, 554, 488, 410, C.teal, 3);
  line(slide, 792, 310, 900, 310, C.blue, 3);
  line(slide, 792, 410, 900, 554, C.navy, 3);

  rect(slide, 430, 505, 420, 100, C.paper, { lineColor: "#D4DCE1" });
  text(slide, "平台核心优势", 454, 518, 160, 26, { fontSize: 16, color: C.red, bold: true });
  text(slide, "浏览器交互 · 参数化输入 · 训练范围提示 · 图表输出 · CSV下载", 454, 548, 370, 42, {
    fontSize: 17, color: C.ink, bold: true, align: "center",
  });

  pill(slide, "真实数据驱动", 80, 655, 180, 36, C.paleGreen, C.teal, 14);
  pill(slide, "轻量代理模型", 278, 655, 180, 36, C.paleBlue, C.blue, 14);
  pill(slide, "电路/场协同", 476, 655, 180, 36, C.paleYellow, C.red, 14);
  pill(slide, "结果可解释", 674, 655, 180, 36, "#DDE5F1", C.navy, 14);
  pill(slide, "流程可扩展", 872, 655, 180, 36, C.paper, C.ink, 14);

  text(slide, "THANK YOU", 1080, 654, 144, 36, {
    fontSize: 15, color: C.gray, bold: true, align: "right",
  });
  return slide;
}

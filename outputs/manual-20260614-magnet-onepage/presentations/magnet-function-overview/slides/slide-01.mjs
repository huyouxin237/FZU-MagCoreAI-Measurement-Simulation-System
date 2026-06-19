import fs from "node:fs";
import path from "node:path";

const W = 1280;
const H = 720;
const FONT = "Microsoft YaHei";

function addRect(slide, x, y, w, h, fill, line = null, radius = false, name = undefined) {
  return slide.shapes.add({
    geometry: radius ? "roundRect" : "rect",
    name,
    position: { left: x, top: y, width: w, height: h },
    fill: fill ? { type: "solid", color: fill } : { type: "none" },
    line: line || { color: "#FFFFFF", transparency: 100, width: 0 },
  });
}

function addText(slide, text, x, y, w, h, opts = {}) {
  const box = addRect(slide, x, y, w, h, null, null, false, opts.name);
  box.text.style = {
    fontSize: opts.fontSize ?? 18,
    typeface: opts.font ?? FONT,
    color: opts.color ?? "#1C2B36",
    bold: opts.bold ?? false,
    alignment: opts.align ?? "left",
    verticalAlignment: opts.valign ?? "middle",
    autoFit: "shrinkText",
    insets: opts.insets ?? { left: 4, right: 4, top: 2, bottom: 2 },
  };
  box.text = text;
  return box;
}

function addStage(slide, text, x, y, w, color) {
  const shape = slide.shapes.add({
    geometry: "rect",
    position: { left: x, top: y, width: w, height: 64 },
    fill: { type: "solid", color },
    line: { color, width: 1 },
  });
  shape.text.style = {
    fontSize: 20,
    typeface: FONT,
    color: "#FFFFFF",
    bold: true,
    alignment: "center",
    verticalAlignment: "middle",
    autoFit: "shrinkText",
    insets: { left: 12, right: 12, top: 7, bottom: 7 },
  };
  shape.text = text;
  return shape;
}

function addPlaceholder(slide, label, hint, x, y, w, h) {
  const frame = addRect(
    slide, x, y, w, h, "#F8FBFC",
    { color: "#6F9EAA", width: 1.5, dash: "dash" },
    false
  );
  frame.opacity = 0.88;
  addText(slide, label, x + 12, y + 14, w - 24, 28, {
    fontSize: 16, color: "#287B91", bold: true, align: "center"
  });
  addText(slide, hint, x + 18, y + 48, w - 36, h - 64, {
    fontSize: 13, color: "#71838A", align: "center", valign: "middle"
  });
}

function addCapability(slide, title, lines, x, y, w, accent) {
  addRect(slide, x, y, w, 6, accent);
  addText(slide, title, x, y + 14, w, 30, {
    fontSize: 19, color: accent, bold: true, align: "center"
  });
  addText(slide, lines, x + 12, y + 50, w - 24, 100, {
    fontSize: 15, color: "#263A44", align: "center", valign: "top",
    insets: { left: 10, right: 8, top: 4, bottom: 4 }
  });
}

export async function slide01(presentation, ctx) {
  const slide = presentation.slides.add();
  slide.size = { width: W, height: H };

  const bgPath = path.resolve(ctx.workspaceDir, "assets", "PPT内页.png");
  const bgData = `data:image/png;base64,${fs.readFileSync(bgPath).toString("base64")}`;
  slide.images.add({
    dataUrl: bgData,
    alt: "中国研究生电子设计竞赛内页背景",
    position: { left: 0, top: 0, width: W, height: H },
    fit: "cover",
  });

  addText(slide, "平台能力", 58, 34, 120, 22, {
    name: "kicker-01-label",
    fontSize: 14, color: "#D71920", bold: true
  });
  addRect(slide, 42, 40, 8, 8, "#D71920", null, false, "kicker-01-marker");
  addText(slide, "一个平台贯通数据、AI预测、电路分析与FEM损耗映射", 42, 60, 1010, 50, {
    fontSize: 34, color: "#2587A1", bold: true
  });
  addText(slide, "材料与工况统一输入，按需求选择分析深度，在线获得可视化与可导出的磁芯损耗结果", 45, 111, 930, 28, {
    fontSize: 16, color: "#50636B"
  });

  addStage(slide, "材料与工况\n统一输入", 55, 161, 220, "#D71920");
  addText(slide, "→", 275, 168, 18, 48, { fontSize: 25, color: "#7B929B", bold: true, align: "center" });
  addStage(slide, "实测数据查询\n快速损耗预测", 293, 161, 220, "#78A2DB");
  addText(slide, "→", 513, 168, 18, 48, { fontSize: 25, color: "#7B929B", bold: true, align: "center" });
  addStage(slide, "电路级 / FEM级\n仿真分析", 531, 161, 220, "#315CAA");
  addText(slide, "→", 751, 168, 18, 48, { fontSize: 25, color: "#7B929B", bold: true, align: "center" });
  addStage(slide, "曲线、云图与\nCSV结果输出", 769, 161, 262, "#173B72");

  addPlaceholder(slide, "图片区 1", "建议放置：\n网站输入界面或功能首页截图", 55, 259, 260, 252);

  const panel = addRect(slide, 337, 259, 694, 252, "#FFFFFF", { color: "#D8E3E7", width: 1 });
  panel.opacity = 0.92;
  addCapability(
    slide,
    "实验数据与智能表格",
    "材料 / 温度 / 频率筛选\n标准与任意磁通波形\n查询、预测与CSV下载",
    355, 276, 202, "#2587A1"
  );
  addCapability(
    slide,
    "MagNet AI与电路仿真",
    "B(t) → H(t) 与 B-H 回线\n体积损耗与材料排名\n四类典型电路波形分析",
    575, 276, 220, "#315CAA"
  );
  addCapability(
    slide,
    "FEM网格损耗预测",
    "FLD / 偏置场文件解析\n逐单元Pcv与总损耗\n三维Bm / Pcv分布导出",
    813, 276, 200, "#173B72"
  );

  addPlaceholder(slide, "图片区 2", "建议放置：\nB-H回线 / 材料排名结果", 1052, 157, 178, 166);
  addPlaceholder(slide, "图片区 3", "建议放置：\nFEM三维损耗云图", 1052, 345, 178, 166);

  addRect(slide, 55, 538, 1175, 2, "#C9D7DC");
  addText(slide, "一个浏览器工作流完成“查数据 — 设工况 — 选分析层级 — 生成损耗结果”", 55, 553, 920, 35, {
    fontSize: 22, color: "#263A44", bold: true
  });
  addText(slide, "无需本地环境配置", 55, 602, 220, 28, {
    fontSize: 15, color: "#D71920", bold: true, align: "center"
  });
  addText(slide, "训练范围与外推提示", 280, 602, 220, 28, {
    fontSize: 15, color: "#2587A1", bold: true, align: "center"
  });
  addText(slide, "多维图表交互可视化", 505, 602, 220, 28, {
    fontSize: 15, color: "#315CAA", bold: true, align: "center"
  });
  addText(slide, "预测结果一键导出", 730, 602, 220, 28, {
    fontSize: 15, color: "#173B72", bold: true, align: "center"
  });
  addText(slide, "注：本页聚焦网站功能，核心模型架构另页展示。", 55, 657, 640, 20, {
    fontSize: 11, color: "#77868C"
  });

  return slide;
}

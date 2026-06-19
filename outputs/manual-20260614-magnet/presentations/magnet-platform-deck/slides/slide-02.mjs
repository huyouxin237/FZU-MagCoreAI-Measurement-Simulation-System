import { C, rect, text, arrow, addTitle, addFooter, addCircuitTrace, metric } from "./common.mjs";

export async function slide02(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  addCircuitTrace(slide);
  addTitle(
    slide,
    "PLATFORM WORKFLOW",
    "一套平台贯通数据查询、AI预测与两级仿真",
    "浏览器端统一输入工况，后端按任务调用实验数据库、波形模型或网格级代理模型"
  );

  const stages = [
    ["选择材料与波形", C.red],
    ["输入频率、温度\n磁通与偏置", "#7E9FD8"],
    ["加载材料模型", C.blue],
    ["生成 B-H 与损耗", C.navy],
    ["导出曲线/明细", C.teal],
  ];
  stages.forEach((s, i) => arrow(slide, s[0], 52 + i * 236, 238, 220, 108, s[1], { fontSize: 21 }));

  const labels = [
    ["数据基础", "HDF5 实验数据库\n材料参数与训练范围"],
    ["AI代理", "B(t)→H(t)\nB-H 回线积分"],
    ["电路耦合", "Buck / Boost\nFlyback / DAB"],
    ["空间分析", "FLD 网格解析\n逐单元 Pcv 预测"],
  ];
  labels.forEach((item, i) => {
    const x = 72 + i * 292;
    rect(slide, x, 394, 250, 112, C.paper, { lineColor: "#CBD3D9", lineWidth: 1 });
    text(slide, item[0], x + 18, 408, 210, 30, {
      fontSize: 18, bold: true, color: i === 0 ? C.red : C.navy,
    });
    text(slide, item[1], x + 18, 442, 210, 44, {
      fontSize: 15, color: C.gray, valign: "top",
    });
  });

  rect(slide, 52, 548, 1176, 98, "#EEF2F5", { line: false });
  metric(slide, "10", "主数据库材料", 100, 557, 150, C.teal);
  metric(slide, "4", "电路拓扑", 366, 557, 150, C.blue);
  metric(slide, "2", "代理模型链路", 632, 557, 150, C.red);
  metric(slide, "15", "FEM可选材料模型", 898, 557, 190, C.navy);
  text(slide, "预测结果支持图表展示\n与 CSV 下载", 1094, 566, 118, 60, {
    fontSize: 13, color: C.ink, bold: true, align: "center",
  });
  addFooter(slide, 2);
  return slide;
}

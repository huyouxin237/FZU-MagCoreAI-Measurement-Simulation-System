export const C = {
  bg: "#F7F8FA",
  paper: "#FFFFFF",
  teal: "#2A829A",
  navy: "#173B68",
  blue: "#3D64B1",
  red: "#D7262E",
  ink: "#18222B",
  gray: "#63717C",
  line: "#B9C2C9",
  paleBlue: "#DCEAF2",
  paleGreen: "#E7F0DA",
  paleYellow: "#F5E8C5",
  paleGray: "#E9EDF0",
};

export function rect(slide, x, y, w, h, fill, opts = {}) {
  const shape = slide.shapes.add({
    geometry: opts.geometry || (opts.radius ? "roundRect" : "rect"),
    position: { left: x, top: y, width: w, height: h },
    fill: fill ? { type: "solid", color: fill, transparency: opts.transparency || 0 } : { type: "none" },
    line: opts.line === false
      ? { fill: { type: "none" }, width: 0 }
      : { style: "solid", fill: opts.lineColor || C.line, width: opts.lineWidth || 1 },
  });
  if (opts.rotation) shape.rotation = opts.rotation;
  return shape;
}

export function text(slide, value, x, y, w, h, opts = {}) {
  const shape = rect(slide, x, y, w, h, null, { line: false });
  shape.text.style = {
    fontSize: opts.fontSize || 22,
    typeface: opts.typeface || "Microsoft YaHei",
    color: opts.color || C.ink,
    bold: opts.bold || false,
    alignment: opts.align || "left",
    verticalAlignment: opts.valign || "middle",
    autoFit: opts.autoFit || "shrinkText",
    insets: opts.insets || { top: 4, right: 4, bottom: 4, left: 4 },
  };
  shape.text = value;
  return shape;
}

export function pill(slide, value, x, y, w, h, fill, color = C.ink, fontSize = 16) {
  const s = rect(slide, x, y, w, h, fill, { radius: true, line: false });
  s.text.style = {
    fontSize,
    typeface: "Microsoft YaHei",
    color,
    bold: true,
    alignment: "center",
    verticalAlignment: "middle",
    autoFit: "shrinkText",
    insets: { top: 5, right: 8, bottom: 5, left: 8 },
  };
  s.text = value;
  return s;
}

export function arrow(slide, value, x, y, w, h, fill, opts = {}) {
  const s = rect(slide, x, y, w, h, fill, {
    geometry: "rightArrow",
    line: false,
  });
  s.text.style = {
    fontSize: opts.fontSize || 21,
    typeface: "Microsoft YaHei",
    color: opts.color || "#FFFFFF",
    bold: true,
    alignment: "center",
    verticalAlignment: "middle",
    autoFit: "shrinkText",
    insets: { top: 8, right: 26, bottom: 8, left: 16 },
  };
  s.text = value;
  return s;
}

export function line(slide, x1, y1, x2, y2, color = C.line, width = 2) {
  return slide.shapes.add({
    geometry: "line",
    position: {
      left: Math.min(x1, x2),
      top: Math.min(y1, y2),
      width: Math.max(1, Math.abs(x2 - x1)),
      height: Math.max(1, Math.abs(y2 - y1)),
    },
    fill: { type: "none" },
    line: { style: "solid", fill: color, width },
  });
}

export function connect(slide, from, to, opts = {}) {
  return slide.shapes.connect(from, to, {
    kind: opts.kind || "straight",
    fromSide: opts.fromSide || "right",
    toSide: opts.toSide || "left",
    line: {
      style: "solid",
      fill: opts.color || C.blue,
      width: opts.width || 2,
      endArrow: opts.endArrow || "triangle",
    },
  });
}

export function metric(slide, value, label, x, y, w, color = C.navy) {
  text(slide, value, x, y, w, 42, {
    fontSize: 34, color, bold: true, align: "center",
  });
  text(slide, label, x, y + 46, w, 26, {
    fontSize: 14, color: C.gray, align: "center",
  });
}

export function waveform(slide, x, y, w, h, color = C.teal, kind = "sine") {
  line(slide, x, y + h / 2, x + w, y + h / 2, "#AAB5BC", 1);
  const pts = [];
  const count = 18;
  for (let i = 0; i <= count; i += 1) {
    const px = x + (w * i) / count;
    let py;
    if (kind === "tri") {
      const t = (i / count) * 2;
      const v = t <= 1 ? -1 + 2 * t : 3 - 2 * t;
      py = y + h / 2 - v * h * 0.36;
    } else {
      py = y + h / 2 - Math.sin((i / count) * Math.PI * 2) * h * 0.36;
    }
    pts.push([px, py]);
  }
  for (let i = 0; i < pts.length - 1; i += 1) {
    line(slide, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], color, 2.5);
  }
}

export function addTitle(slide, kicker, titleValue, subtitle) {
  rect(slide, 44, 42, 7, 25, C.red, { line: false });
  text(slide, kicker.toUpperCase(), 61, 38, 320, 30, {
    fontSize: 14, color: C.red, bold: true,
  });
  text(slide, titleValue, 44, 72, 1160, 58, {
    fontSize: 39, color: C.teal, bold: true,
  });
  if (subtitle) {
    text(slide, subtitle, 48, 134, 1120, 38, {
      fontSize: 18, color: C.gray,
    });
  }
}

export function addFooter(slide, page) {
  line(slide, 44, 682, 1236, 682, "#D7DDE1", 1);
  text(slide, "MAGNET PLATFORM", 44, 687, 220, 21, {
    fontSize: 10, color: C.gray, bold: true,
  });
  text(slide, String(page).padStart(2, "0"), 1178, 687, 56, 21, {
    fontSize: 10, color: C.gray, bold: true, align: "right",
  });
}

export function addCircuitTrace(slide) {
  const segments = [
    [880, 52, 1215, 52], [1010, 52, 1010, 95], [1010, 95, 1165, 95],
    [1165, 95, 1165, 128], [930, 660, 1215, 660], [930, 620, 930, 660],
    [1030, 620, 1030, 660], [1130, 620, 1130, 660],
  ];
  for (const seg of segments) line(slide, ...seg, "#E4E9EC", 1);
  for (const [x, y] of [[1010,52],[1165,95],[930,660],[1030,660],[1130,660]]) {
    rect(slide, x - 3, y - 3, 6, 6, "#D9E1E5", { geometry: "ellipse", line: false });
  }
}

export function addImage(slide, imagePath, x, y, w, h, fit = "cover", alt = "") {
  const ext = path.extname(imagePath).toLowerCase();
  const mime = ext === ".jpg" || ext === ".jpeg" ? "image/jpeg" : "image/png";
  const dataUrl = `data:${mime};base64,${fs.readFileSync(imagePath).toString("base64")}`;
  return slide.images.add({
    dataUrl,
    alt,
    position: { left: x, top: y, width: w, height: h },
    fit,
  });
}

export function labelBox(slide, titleValue, body, x, y, w, h, fill, accent) {
  const box = rect(slide, x, y, w, h, fill, { lineColor: accent, lineWidth: 1.3 });
  rect(slide, x, y, 7, h, accent, { line: false });
  text(slide, titleValue, x + 18, y + 10, w - 28, 30, {
    fontSize: 18, bold: true, color: C.ink,
  });
  text(slide, body, x + 18, y + 42, w - 28, h - 50, {
    fontSize: 14, color: C.gray, valign: "top",
  });
  return box;
}
import fs from "node:fs";
import path from "node:path";

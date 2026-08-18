// 图片索引自动同步脚本
// 用法（在项目根目录运行）：
//   node sync-gallery.js              # 仅扫描 pic/ 并重写 images.js
//   node sync-gallery.js --convert     # 先把新图片自动转成 WebP，再扫描重写 images.js
// 效果：自动扫描 pic/ 下所有子文件夹里的图片，每个文件夹一个分类，重写 images.js。
// 之后你只需把新图片放进对应文件夹，运行本脚本即可，无需手动编辑 images.js。
const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

const PIC_DIR = path.join(__dirname, "pic");
const OUT_FILE = path.join(__dirname, "images.js");

// 支持展示的图片扩展名（按优先级，webp 优先）
const IMAGE_EXTS = [".webp", ".jpg", ".jpeg", ".jfif", ".png", ".gif", ".avif"];

// 文件夹名 -> 显示名称
const NAME_MAP = { other: "其他", deepsleep: "DeepSleep", default: null };

function collectGroups() {
  const groups = [];
  const entries = fs.readdirSync(PIC_DIR, { withFileTypes: true });
  for (const e of entries) {
    if (!e.isDirectory()) continue;
    const dir = e.name;
    const abs = path.join(PIC_DIR, dir);
    const fileNames = fs.readdirSync(abs);
    // 收集该文件夹所有图片，按 IMAGE_EXTS 优先级排序
    const byExt = {};
    for (const fn of fileNames) {
      const ext = path.extname(fn).toLowerCase();
      if (IMAGE_EXTS.includes(ext)) {
        (byExt[ext] = byExt[ext] || []).push(fn);
      }
    }
    // 组装：webp 优先，其余按后缀补充；同名已转 webp 的 jpg/jfif 会被跳过
    const images = [];
    const seenBase = new Set();
    for (const ext of IMAGE_EXTS) {
      const list = (byExt[ext] || []).sort();
      for (const fn of list) {
        const base = path.basename(fn, path.extname(fn));
        if (seenBase.has(base)) continue; // 已加入同名 webp，跳过原图
        seenBase.add(base);
        images.push("pic/" + dir + "/" + fn);
      }
    }
    if (images.length === 0) continue;
    const name = NAME_MAP[dir] || dir;
    groups.push({ id: dir, name, images });
  }
  // 稳定排序：保持子文件夹在磁盘上的顺序
  return groups;
}

// 可选步骤：调用 convert_webp.py 先把新图片转成 WebP
function runConvert(options) {
  console.log("[sync-gallery] 正在将新图片转换为 WebP ...");
  try {
    execSync("python convert_webp.py", { cwd: __dirname, stdio: "inherit", encoding: "utf8" });
  } catch (e) {
    console.error("[sync-gallery] 转换脚本执行失败：" + e.message);
    console.error("[sync-gallery] 请确认已安装 Python 和 Pillow（pip install pillow），或改用：node sync-gallery.js（跳过转换）");
    process.exitCode = 1;
  }
}

function main() {
  const args = process.argv.slice(2);
  if (args.includes("--convert")) {
    runConvert();
  }
  const groups = collectGroups();
  const lines = [];
  lines.push("// 由 sync-gallery.js 自动生成，请勿手动编辑。");
  lines.push("// 新图片放进 pic/ 对应文件夹后运行：node sync-gallery.js");
  lines.push("const GALLERY = {");
  lines.push("  groups: [");
  for (const g of groups) {
    lines.push("    {");
    lines.push("      id: " + JSON.stringify(g.id) + ",");
    lines.push("      name: " + JSON.stringify(g.name) + ",");
    lines.push("      images: [");
    for (const im of g.images) lines.push("        " + JSON.stringify(im) + ",");
    lines.push("      ]");
    lines.push("    },");
  }
  lines.push("  ]");
  lines.push("};");
  lines.push("");
  fs.writeFileSync(OUT_FILE, lines.join("\n"), "utf8");
  console.log("images.js 已更新：" + groups.length + " 个分组，共 " + groups.reduce((s, g) => s + g.images.length, 0) + " 张图片");
  for (const g of groups) console.log("  - " + g.name + " (" + g.id + "): " + g.images.length + " 张");
}

main();

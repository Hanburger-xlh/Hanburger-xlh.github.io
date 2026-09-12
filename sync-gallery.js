// 图片索引同步脚本（转发到 build-gallery.py）
// 用法（在项目根目录运行）：
//   node sync-gallery.js              # 生成缩略图 + 重写 images.js
//   node sync-gallery.js --convert    # 先把新图片转成 WebP，再执行上面的步骤
//   node sync-gallery.js --force      # 强制重建所有缩略图
//
// 说明：实际的扫描 / 缩略图 / 尺寸读取都由 build-gallery.py 完成。
// 缩略图与宽高必须用能解码 WebP 的库来做，Node 原生没有这种能力，
// 因此这里只保留一个熟悉的入口名，避免两套生成逻辑各自为政。
const { execFileSync } = require("child_process");
const path = require("path");

const ROOT = __dirname;
const args = process.argv.slice(2);

function run(cmd, argv, label) {
  console.log("[sync-gallery] " + label);
  execFileSync(cmd, argv, { cwd: ROOT, stdio: "inherit" });
}

if (args.includes("--convert")) {
  run("python", ["convert_webp.py"], "正在将新图片转换为 WebP ...");
}

const pyArgs = ["build-gallery.py"];
if (args.includes("--force")) pyArgs.push("--force");
if (args.includes("--no-thumb")) pyArgs.push("--no-thumb");

try {
  run("python", pyArgs, "生成缩略图并重写 images.js ...");
} catch (e) {
  console.error("[sync-gallery] 执行 build-gallery.py 失败：" + e.message);
  console.error("[sync-gallery] 请确认已安装 Python 和 Pillow（pip install pillow）。");
  process.exitCode = 1;
}

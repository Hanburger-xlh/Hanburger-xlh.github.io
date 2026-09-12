#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make-icons.py — 生成站点的图标与分享封面图

产出（都在仓库根目录，供 GitHub Pages 直接引用）：
    favicon.svg         浏览器标签图标（矢量，手写在下方 SVG 常量里）
    apple-touch-icon.png 180x180，iOS 添加到主屏用
    og-cover.png        1200x630，微信/QQ/飞书/Twitter 分享时的预览图

配色取自 index.html 的 CSS 变量：
    --bg #0d0f14   --accent #7c9cff   --accent-2 #b48cff

用法：python make-icons.py
"""
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("需要 Pillow：pip install pillow")
    sys.exit(1)

ROOT = os.path.dirname(os.path.abspath(__file__))
BG = (13, 15, 20)
ACCENT = (124, 156, 255)
ACCENT2 = (180, 140, 255)
TITLE = "hans窝"
SUBTITLE = "文章 · 网址 · 图片 · B站动态 · 游戏日常"

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",     # 微软雅黑 Bold
    r"C:\Windows\Fonts\msyh.ttc",       # 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf",     # 黑体
    r"C:\Windows\Fonts\arialbd.ttf",
]

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#7c9cff"/>
      <stop offset="100%" stop-color="#b48cff"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="14" fill="#0d0f14"/>
  <rect x="4" y="4" width="56" height="56" rx="12" fill="url(#g)"/>
  <text x="32" y="45" font-family="Segoe UI, Helvetica, Arial, sans-serif"
        font-size="38" font-weight="700" text-anchor="middle" fill="#0d0f14">h</text>
</svg>
"""


def load_font(size):
    for path in FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    print("[warn] 未找到中文字体，回退默认字体（中文可能显示为方块）")
    return ImageFont.load_default()


def gradient(size):
    """左上 --accent 到右下 --accent-2 的对角渐变。"""
    w, h = size
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(0, w, 1):
            t = (x / max(1, w - 1) + y / max(1, h - 1)) / 2
            px[x, y] = (
                int(ACCENT[0] + (ACCENT2[0] - ACCENT[0]) * t),
                int(ACCENT[1] + (ACCENT2[1] - ACCENT[1]) * t),
                int(ACCENT[2] + (ACCENT2[2] - ACCENT[2]) * t),
            )
    return img


def centered(draw, text, font, cy, fill, width):
    box = draw.textbbox((0, 0), text, font=font)
    w = box[2] - box[0]
    h = box[3] - box[1]
    draw.text(((width - w) / 2 - box[0], cy - h / 2 - box[1]), text, font=font, fill=fill)
    return h


def main():
    # 1) favicon.svg
    svg_path = os.path.join(ROOT, "favicon.svg")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(FAVICON_SVG)
    print(f"[ok] {os.path.basename(svg_path)}")

    # 2) apple-touch-icon.png 180x180
    S = 180
    icon = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(icon)
    r = 40
    # 圆角矩形渐变底
    grad = gradient((S - 24, S - 24))
    mask = Image.new("L", (S - 24, S - 24), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 25, S - 25], radius=r, fill=255)
    icon.paste(grad, (12, 12), mask)
    f = load_font(110)
    box = d.textbbox((0, 0), "h", font=f)
    d.text(((S - (box[2] - box[0])) / 2 - box[0], (S - (box[3] - box[1])) / 2 - box[1]),
           "h", font=f, fill=(10, 12, 18))
    icon.save(os.path.join(ROOT, "apple-touch-icon.png"), "PNG", optimize=True)
    print("[ok] apple-touch-icon.png  180x180")

    # 3) og-cover.png 1200x630
    W, H = 1200, 630
    cover = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(cover)
    band = gradient((W, 260))
    cover.paste(band, (0, 0))
    # 底部留深色，放副标题
    f_title = load_font(96)
    f_sub = load_font(34)
    centered(d, TITLE, f_title, 340, (232, 234, 240), W)
    centered(d, SUBTITLE, f_sub, 440, (139, 147, 167), W)
    centered(d, "hanburger-xlh.github.io", load_font(26), 540, (110, 118, 140), W)
    cover.save(os.path.join(ROOT, "og-cover.png"), "PNG", optimize=True)
    print("[ok] og-cover.png  1200x630")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build-gallery.py — 扫描 pic/，生成缩略图与 images.js（相册索引）。

做三件事：
    1. 扫描 pic/ 下每个子文件夹（一个文件夹 = 一个分类），按扩展名优先级排序并去重
       （同名已有 .webp 时跳过 .jpg/.png 等原图），与旧 sync-gallery.js 行为一致。
    2. 为每张图生成缩略图到 pic-thumb/<分类>/<同名>.webp（长边 ≤ THUMB_MAX，质量 THUMB_QUALITY）。
       原图平均 209 KB、中位宽 1254px（最大 4096px），而网格每格只显示约 400px，
       实测全库 49.1 MB → 10.0 MB（降 80%）。原图保留给灯箱看大图。
       已存在且比原图新的缩略图会跳过（幂等）。
    3. 重写 images.js，每条记录同时带上缩略图、原图与宽高：
           { t: 缩略图路径, f: 原图路径, w: 宽, h: 高 }
       宽高供 <img> 输出 width/height 属性，避免瀑布流逐张重排（CLS）。

用法：
    python build-gallery.py              # 生成缩略图 + 重写 images.js
    python build-gallery.py --no-thumb   # 只重写 images.js（不动缩略图）
    python build-gallery.py --force      # 强制重建所有缩略图
"""
import os
import sys
import argparse
import datetime

try:
    from PIL import Image
except ImportError:
    Image = None

ROOT = os.path.dirname(os.path.abspath(__file__))
PIC_DIR = os.path.join(ROOT, "pic")
THUMB_DIR = os.path.join(ROOT, "pic-thumb")
OUT_FILE = os.path.join(ROOT, "images.js")

# 支持展示的图片扩展名（按优先级，webp 优先）
IMAGE_EXTS = [".webp", ".jpg", ".jpeg", ".jfif", ".png", ".gif", ".avif"]
NAME_MAP = {"other": "其他", "deepsleep": "DeepSleep"}
THUMB_MAX = 640
THUMB_QUALITY = 80


def log(msg):
    print(f"[build-gallery] {msg}", flush=True)


def rel(path):
    """转成站点用的相对路径（正斜杠）。"""
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def collect_groups():
    """返回 [{"id","name","images":[(full_abs, ext, base)]}]，顺序保持磁盘顺序。"""
    groups = []
    for entry in sorted(os.listdir(PIC_DIR)):
        abs_dir = os.path.join(PIC_DIR, entry)
        if not os.path.isdir(abs_dir):
            continue
        files = os.listdir(abs_dir)
        by_ext = {}
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in IMAGE_EXTS:
                by_ext.setdefault(ext, []).append(fn)
        images = []
        seen_base = set()
        for ext in IMAGE_EXTS:
            for fn in sorted(by_ext.get(ext, [])):
                base = os.path.splitext(fn)[0]
                if base in seen_base:
                    continue                      # 已加入同名 webp，跳过原图
                seen_base.add(base)
                images.append((os.path.join(abs_dir, fn), ext, base))
        if not images:
            continue
        groups.append({"id": entry, "name": NAME_MAP.get(entry, entry), "images": images})
    return groups


def make_thumb(src_abs, group_id, base, force=False):
    """
    生成缩略图，返回 (相对路径, 宽, 高)。
    读不到尺寸或转换失败时返回 (原图相对路径, None, None)，由调用方回退。
    """
    if Image is None:
        return rel(src_abs), None, None
    try:
        with Image.open(src_abs) as im:
            w, h = im.size
    except Exception as e:
        log(f"[warn] 无法读取尺寸，跳过缩略图：{rel(src_abs)}（{e}）")
        return rel(src_abs), None, None

    dst_dir = os.path.join(THUMB_DIR, group_id)
    dst_abs = os.path.join(dst_dir, base + ".webp")
    if (not force and os.path.isfile(dst_abs)
            and os.path.getmtime(dst_abs) >= os.path.getmtime(src_abs)):
        return rel(dst_abs), w, h

    try:
        os.makedirs(dst_dir, exist_ok=True)
        with Image.open(src_abs) as im:
            if getattr(im, "is_animated", False) and getattr(im, "n_frames", 1) > 1:
                # 动图保持原样（thumbnail 不适用），网格仍加载原图
                return rel(src_abs), w, h
            if max(im.size) > THUMB_MAX:
                im.thumbnail((THUMB_MAX, THUMB_MAX), Image.LANCZOS)
            else:
                # 原图本来就小，缩略图不会更小，直接用原图，避免无谓文件
                return rel(src_abs), w, h
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA" if "A" in im.mode else "RGB")
            im.save(dst_abs, "WEBP", quality=THUMB_QUALITY, method=4)
        return rel(dst_abs), w, h
    except Exception as e:
        log(f"[warn] 缩略图生成失败，回退原图：{rel(src_abs)}（{e}）")
        return rel(src_abs), w, h


def main():
    ap = argparse.ArgumentParser(description="生成 pic/ 缩略图并重写 images.js")
    ap.add_argument("--no-thumb", action="store_true", help="只重写 images.js，不生成缩略图")
    ap.add_argument("--force", action="store_true", help="强制重建所有缩略图")
    args = ap.parse_args()

    if not os.path.isdir(PIC_DIR):
        log(f"[error] 找不到 {PIC_DIR}")
        return 1
    if Image is None and not args.no_thumb:
        log("[error] 需要 Pillow 才能生成缩略图：pip install pillow（或用 --no-thumb）")
        return 1

    made = reused = 0
    groups = collect_groups()
    out_groups = []
    total = 0
    for g in groups:
        items = []
        for src_abs, _ext, base in g["images"]:
            if args.no_thumb:
                try:
                    with Image.open(src_abs) as im:
                        w, h = im.size
                except Exception:
                    w, h = None, None
                t = rel(src_abs)
            else:
                before = os.path.isfile(os.path.join(THUMB_DIR, g["id"], base + ".webp"))
                t, w, h = make_thumb(src_abs, g["id"], base, args.force)
                if t != rel(src_abs) and not before:
                    made += 1
                elif t != rel(src_abs):
                    reused += 1
            items.append((t, rel(src_abs), w, h))
        if items:
            out_groups.append({"id": g["id"], "name": g["name"], "items": items})
            total += len(items)

    lines = []
    lines.append("// 由 build-gallery.py 自动生成，请勿手动编辑。")
    lines.append("// 新图片放进 pic/ 对应文件夹后运行：python build-gallery.py")
    lines.append("// 每条：t=缩略图(网格用) f=原图(灯箱用) w/h=原始像素尺寸(供 img 预留位置)")
    lines.append("const GALLERY = {")
    lines.append("  groups: [")
    for g in out_groups:
        lines.append("    {")
        lines.append("      id: " + repr(g["id"]).replace("'", '"') + ",")
        lines.append("      name: " + repr(g["name"]).replace("'", '"') + ",")
        lines.append("      images: [")
        for t, f, w, h in g["items"]:
            lines.append(
                '        { t: "%s", f: "%s", w: %s, h: %s },'
                % (t, f, w if w else 0, h if h else 0)
            )
        lines.append("      ]")
        lines.append("    },")
    lines.append("  ]")
    lines.append("};")
    lines.append("")
    with open(OUT_FILE, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines))

    thumb_files = 0
    thumb_bytes = 0
    if os.path.isdir(THUMB_DIR):
        for dirpath, _dn, fns in os.walk(THUMB_DIR):
            for fn in fns:
                thumb_files += 1
                thumb_bytes += os.path.getsize(os.path.join(dirpath, fn))

    log(f"已写 {rel(OUT_FILE)}：{len(out_groups)} 个分组，{total} 张")
    for g in out_groups:
        log(f"  - {g['name']} ({g['id']}): {len(g['items'])} 张")
    if not args.no_thumb:
        log(f"缩略图：本次新建 {made}，复用 {reused}；pic-thumb/ 共 {thumb_files} 个 "
            f"{thumb_bytes/1024/1024:.1f} MB")
    log(f"完成于 {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

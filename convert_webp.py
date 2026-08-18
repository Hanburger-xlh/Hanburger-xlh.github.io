#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convert_webp.py - 将 pic/ 下所有图片转为 WebP（保留原图）
用法：python convert_webp.py
支持：.jpg/.jpeg/.jfif/.png/.gif  -> 同名 .webp
行为：目标 .webp 已存在则跳过（幂等）；动图 .gif 转成动态 WebP 保留动画。
"""
import os
from PIL import Image

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pic")
SRC_EXTS = {".jpg", ".jpeg", ".jfif", ".png", ".gif"}
QUALITY = 85


def is_animated(im):
    try:
        return getattr(im, "is_animated", False) and im.n_frames > 1
    except Exception:
        return False


def convert(src):
    dst = os.path.splitext(src)[0] + ".webp"
    if os.path.exists(dst):
        return "skip"
    try:
        with Image.open(src) as im:
            opt = im.info.get("optimize", False)
            if is_animated(im):
                frames = []
                for i in range(im.n_frames):
                    im.seek(i)
                    fr = im.convert("RGBA" if "A" in im.getbands() else "RGB")
                    frames.append(fr)
                im.seek(0)
                duration = im.info.get("duration", 100)
                loop = im.info.get("loop", 0)
                frames[0].save(
                    dst, "WEBP", save_all=True, append_images=frames[1:],
                    duration=duration, loop=loop, quality=QUALITY,
                )
            else:
                mode = im.mode
                if mode not in ("RGB", "RGBA"):
                    im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
                im.save(dst, "WEBP", quality=QUALITY)
        return "ok"
    except Exception as e:
        return "FAIL:" + str(e)


def main():
    results = {"ok": 0, "skip": 0, "fail": 0}
    files = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in SRC_EXTS:
                continue
            files += 1
            src = os.path.join(dirpath, fn)
            r = convert(src)
            if r == "ok":
                results["ok"] += 1
                print("  OK:", src)
            elif r == "skip":
                results["skip"] += 1
            else:
                results["fail"] += 1
                print("  FAIL:", src, "-", r)
    print("TOTAL convertable:", files)
    print("CONVERTED:", results["ok"])
    print("SKIPPED (webp exists):", results["skip"])
    print("FAILED:", results["fail"])


if __name__ == "__main__":
    main()

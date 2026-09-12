#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch-bili-images.py — 把 bili.json 里的 B 站图片下载到本仓库，并改写为站内相对路径。

背景：
    crawl-bili.js 抓到的动态里，图片字段是 B 站图床的外链（i0/i1/i2.hdslb.com），
    网站只能靠 <img referrerpolicy="no-referrer"> 直连外链。外链依赖 B 站可用性、
    可能被风控/防盗链影响。本脚本把它们下载到本地，随仓库一起发布，网站自给自足。

处理范围（只处理这两个字段，均来自动态本身）：
    cover  —— 每条动态的首图（图文取第一张、图片动态取第一张、视频取封面、专栏无图）
    avatar —— UP 主头像
    注意：B 站动态抓取里**没有视频文件地址**，只有视频封面和动态页链接。

存放位置：
    bili-img/cover/<sha1(源URL)前16位>.webp
    bili-img/avatar/<sha1(源URL)前16位>.webp
    （刻意放在 pic/ 之外：sync-gallery.js 会把 pic/ 的每个子目录当成相册分类。）

行为：
    - 目标文件已存在 → 直接复用，不重复下载（幂等）。
    - 下载失败 / 不是允许的图床域名 → 保留原始外链，不影响网站其余部分。
    - 结束时清理 bili-img/ 下不再被 bili.json 引用的文件，避免仓库无限膨胀。

用法：
    python bili-daily/fetch-bili-images.py
"""

import io
import os
import sys
import json
import time
import hashlib
import argparse
from concurrent.futures import ThreadPoolExecutor

try:
    import requests
except ImportError:  # 极端情况下退回标准库
    requests = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根（bili-daily 的上一级）
IMG_ROOT = os.path.join(ROOT, "bili-img")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
REFERER = "https://www.bilibili.com/"
ALLOW_HOST_SUFFIX = (".hdslb.com", ".biliimg.com")   # 只允许 B 站图床
QUALITY = 82
# 按前端实际显示尺寸缩放（index.html：头像 44x44，封面 max-height:220px）：
#   不缩放的话单张平均约 230 KB，每天新增 1~3 MB 二进制进 git 历史且永久累积。
MAX_COVER_PX = 720      # 封面长边上限
MAX_AVATAR_PX = 128     # 头像长边上限（44px 的 2 倍余量，兼顾高分屏）
TIMEOUT = 30
WORKERS = 4
# 视频/音频地址不是图片，明确排除（B 站动态里本来也不提供文件地址）
BLOCK_EXTS = (".mp4", ".m4s", ".flv", ".m3u8", ".mp3", ".aac")

MAX_PX = {"cover": MAX_COVER_PX, "avatar": MAX_AVATAR_PX}


def log(msg):
    print(time.strftime("[%Y-%m-%d %H:%M:%S]") + " " + str(msg), flush=True)


def is_remote(u):
    return isinstance(u, str) and u.lower().startswith(("http://", "https://"))


def host_allowed(url):
    """只下载 B 站图床的图片，避免被 bili.json 里的任意地址牵着走。"""
    try:
        from urllib.parse import urlparse
        h = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not h:
        return False
    if any(h == s.lstrip(".") or h.endswith(s) for s in ALLOW_HOST_SUFFIX):
        return not h.endswith((".mp4", ".m4s", ".flv", ".m3u8"))
    return False


def guess_ext(url):
    from urllib.parse import urlparse
    path = urlparse(url).path or ""
    ext = os.path.splitext(path)[1].lower()
    return ext if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp") else ".jpg"


def target_rel(kind, url, ext=".webp"):
    """内容寻址命名：源 URL 变则文件名变，配合末尾清理天然去重。"""
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return f"bili-img/{kind}/{h}{ext}"


def fetch_bytes(url):
    headers = {"User-Agent": UA, "Referer": REFERER, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
    if requests is not None:
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        return r.content
    import urllib.request
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def write_webp(raw, dst_abs, max_px=None):
    """按需缩放并转成 WebP；失败则原样写出（返回实际使用的扩展名）。"""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as im:
            animated = getattr(im, "is_animated", False) and getattr(im, "n_frames", 1) > 1
            if animated:
                # 动图无法简单 thumbnail，保持原尺寸
                im.save(dst_abs, "WEBP", quality=QUALITY, save_all=True)
            else:
                if max_px and max(im.size) > max_px:
                    im.thumbnail((max_px, max_px), Image.LANCZOS)
                if im.mode not in ("RGB", "RGBA"):
                    im = im.convert("RGBA" if "A" in im.mode else "RGB")
                im.save(dst_abs, "WEBP", quality=QUALITY, method=4)
        return ".webp"
    except Exception as e:
        base, _ = os.path.splitext(dst_abs)
        fallback = base + ".bin"
        with open(fallback, "wb") as f:
            f.write(raw)
        log(f"[warn] WebP 转换失败，已原样保存：{os.path.basename(fallback)}（{e}）")
        return ".bin"


def handle_one(kind, url):
    """
    返回站内相对路径（正斜杠）；不该处理或失败时返回 None。
    """
    if not is_remote(url):
        return None                     # 已经是本地路径
    if not host_allowed(url):
        log(f"[skip] 非 B 站图床，保留外链：{url[:90]}")
        return None
    if os.path.splitext(url.lower())[1] in BLOCK_EXTS:
        return None

    rel = target_rel(kind, url)
    dst_abs = os.path.join(ROOT, rel.replace("/", os.sep))
    if os.path.isfile(dst_abs):
        return rel                      # 已有缓存

    os.makedirs(os.path.dirname(dst_abs), exist_ok=True)
    try:
        raw = fetch_bytes(url)
    except Exception as e:
        log(f"[warn] 下载失败，保留外链：{url[:90]}（{e}）")
        return None

    ext = write_webp(raw, dst_abs, MAX_PX.get(kind))
    if ext != ".webp":
        rel = os.path.splitext(rel)[0] + ext
    return rel


def collect_tasks(items):
    tasks = []
    for it in items:
        for kind in ("cover", "avatar"):
            u = it.get(kind)
            if is_remote(u):
                tasks.append((it, kind, u))
    return tasks


def main():
    ap = argparse.ArgumentParser(description="把 bili.json 的 B 站图片下载到本仓库")
    ap.add_argument("--repo", default=ROOT, help="仓库根目录（默认取本脚本的上一级）")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    bili_json = os.path.join(repo, "bili.json")
    img_root = os.path.join(repo, "bili-img")

    if not os.path.isfile(bili_json):
        log(f"[error] 找不到 {bili_json}")
        return 0
    try:
        with open(bili_json, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log(f"[error] 解析 bili.json 失败：{e}")
        return 0

    items = data.get("items") or []
    if not items:
        log("[skip] bili.json 没有条目")
        return 0

    tasks = collect_tasks(items)
    log(f"待处理图片 {len(tasks)} 个（cover/avatar 外链）")

    # 同一 URL 只下一次
    url_cache = {}
    def work(task):
        it, kind, url = task
        if url in url_cache:
            return it, kind, url, url_cache[url]
        rel = handle_one(kind, url)
        url_cache[url] = rel
        return it, kind, url, rel

    changed = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for it, kind, url, rel in pool.map(work, tasks):
            if rel and it.get(kind) != rel:
                it[kind] = rel
                changed += 1

    # 清理不再被引用的本地图片
    referenced = set()
    for it in items:
        for kind in ("cover", "avatar"):
            v = it.get(kind)
            if isinstance(v, str) and v.startswith("bili-img/"):
                referenced.add(os.path.normcase(os.path.join(repo, v.replace("/", os.sep))))
    removed = 0
    if os.path.isdir(img_root):
        for dirpath, _dirnames, filenames in os.walk(img_root):
            for fn in filenames:
                abs_p = os.path.join(dirpath, fn)
                if os.path.normcase(abs_p) not in referenced:
                    try:
                        os.remove(abs_p)
                        removed += 1
                    except OSError:
                        pass
        # 清掉空目录
        for dirpath, dirnames, filenames in os.walk(img_root, topdown=False):
            if not dirnames and not filenames:
                try:
                    os.rmdir(dirpath)
                except OSError:
                    pass

    if changed or removed:
        with open(bili_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log(f"已更新 bili.json：改写 {changed} 个字段，清理 {removed} 个旧文件")
    else:
        log("本地图片均为最新，bili.json 无需改动")

    n_local = sum(1 for it in items for k in ("cover", "avatar")
                  if isinstance(it.get(k), str) and it[k].startswith("bili-img/"))
    log(f"当前条目 {len(items)} 条，其中站内图片字段 {n_local} 个")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"[error] 未捕获异常：{e}")
        sys.exit(0)      # 不阻断后续发布流程

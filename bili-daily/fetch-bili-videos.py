#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch-bili-videos.py — 下载动态里的 B 站视频（仅 360P、且时长 ≤5 分钟），保留最近一周。

为什么限制这么严：
    * 480P 单条长视频实测可达 80+ MB（48 分钟 avc 轨 83.7 MB），
      加上音频合并后超过 GitHub 单文件 100 MB 硬上限，会被直接拒收；
    * git 历史不可回收，删除工作区文件不会释放仓库体积，
      因此必须把"每周新增体积"压在可接受范围。
    360P + ≤5 分钟的单条约 5~18 MB，可长期维持。

取流策略（匿名即可，360P 是匿名可得的清晰度）：
    1. x/web-interface/view          -> cid / 真实时长
    2. x/player/playurl qn=16 fnval=1 -> durl(mp4，音视频合一)，直接保存
    3. 上一步拿不到 durl 时退回 fnval=4048(dash) -> 分别下视频轨(360P)与音频轨，ffmpeg 合并

保留策略：
    仅保留下载文件对应的动态发布时间在 KEEP_DAYS=7 天内的视频；
    超期或不再被 bili.json 引用的文件会被删除，并清掉条目的 video 字段
    （条目本身仍留在 bili.json 里，只是不再带本地视频）。

用法：
    python bili-daily/fetch-bili-videos.py
    python bili-daily/fetch-bili-videos.py --max-duration 300 --days 7
"""

import io
import os
import sys
import json
import time
import shutil
import argparse
import subprocess

try:
    import requests
except ImportError:
    requests = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
REFERER = "https://www.bilibili.com/"
VIDEO_ROOT_REL = "bili-video"

MAX_DURATION = 300       # 只下载 5 分钟以内的视频（秒）
KEEP_DAYS = 7            # 本地视频保留天数
QN = 16                  # 16=360P（匿名可得），32=480P，64=720P
TIMEOUT = 60             # 普通 API 超时
DL_TIMEOUT = 600         # 下载超时


def log(msg):
    print(time.strftime("[%Y-%m-%d %H:%M:%S]") + " " + str(msg), flush=True)


def http_get(url, cookie="", timeout=TIMEOUT):
    headers = {"User-Agent": UA, "Referer": REFERER}
    if cookie:
        headers["Cookie"] = cookie
    if requests is not None:
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r
    import urllib.request
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout)


def get_json(url, cookie=""):
    return json.loads(http_get(url, cookie).content.decode("utf-8"))


def get_cookie():
    """匿名身份：只要 buvid3/buvid4 即可；360P 不需要 SESSDATA。"""
    env_sess = os.environ.get("BILI_SESSDATA", "").strip()
    parts = []
    try:
        spi = get_json("https://api.bilibili.com/x/frontend/finger/spi")
        d = spi.get("data") or {}
        if d.get("b_3"):
            parts.append("buvid3=" + d["b_3"])
        if d.get("b_4"):
            parts.append("buvid4=" + d["b_4"])
    except Exception as e:
        log(f"[warn] 取 buvid 失败：{e}")
    if env_sess:
        parts.append("SESSDATA=" + env_sess)
    return "; ".join(parts), bool(env_sess)


def resolve_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    for p in (r"C:\Users\hanburger\miniconda3\Library\bin\ffmpeg.exe",
              r"C:\ffmpeg\bin\ffmpeg.exe"):
        if os.path.isfile(p):
            return p
    return ""


def download_to(url, dst_abs, cookie=""):
    tmp = dst_abs + ".part"
    headers = {"User-Agent": UA, "Referer": REFERER}
    if cookie:
        headers["Cookie"] = cookie
    with open(tmp, "wb") as f:
        if requests is not None:
            with requests.get(url, headers=headers, timeout=DL_TIMEOUT, stream=True) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if chunk:
                        f.write(chunk)
        else:
            import urllib.request
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=DL_TIMEOUT) as resp:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
    os.replace(tmp, dst_abs)


def pick_dash(dash):
    """360P 优先 avc（兼容性最好），音频取最低码率以省体积。"""
    vids = [v for v in (dash.get("video") or []) if v.get("id") == QN]
    if not vids:
        vids = sorted(dash.get("video") or [], key=lambda v: v.get("id", 0))
    if not vids:
        return None, None
    avc = [v for v in vids if str(v.get("codecs", "")).startswith("avc")]
    v = (avc or vids)[0]
    auds = sorted(dash.get("audio") or [], key=lambda a: a.get("id", 0))
    return v, (auds[0] if auds else None)


def fetch_one(bvid, dst_abs, cookie):
    """下载单个视频；返回 (成功, 说明)。已存在则视为成功。"""
    if os.path.isfile(dst_abs):
        return True, "已存在"

    try:
        view = get_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", cookie)
    except Exception as e:
        return False, f"view 接口异常 {e}"
    if view.get("code") != 0:
        return False, f"view code={view.get('code')} {view.get('message')}"
    data = view["data"]
    cid = data["cid"]
    duration = int(data.get("duration") or 0)
    if duration and duration > MAX_DURATION:
        return False, f"时长 {duration}s 超过 {MAX_DURATION}s，跳过"

    base = (f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}"
            f"&qn={QN}&fnver=0&fourk=0&fnval=")
    os.makedirs(os.path.dirname(dst_abs), exist_ok=True)

    # 1) durl：音视频合一的 mp4，最省事
    try:
        j = get_json(base + "1", cookie)
        if j.get("code") == 0:
            durl = j["data"].get("durl") or []
            if durl:
                download_to(durl[0]["url"], dst_abs, cookie)
                size = os.path.getsize(dst_abs)
                return True, f"durl/mp4 {size/1024/1024:.1f} MB（{duration}s）"
            note = "durl 为空"
        else:
            note = f"durl code={j.get('code')}"
    except Exception as e:
        note = f"durl 异常 {e}"

    # 2) dash：分别下视频/音频轨再合并
    try:
        j = get_json(base + "4048", cookie)
        if j.get("code") != 0:
            return False, f"{note}；dash code={j.get('code')} {j.get('message')}"
        v, a = pick_dash(j["data"].get("dash") or {})
        if not v:
            return False, f"{note}；dash 无可选轨"
        ff = resolve_ffmpeg()
        if not ff:
            return False, f"{note}；需要 ffmpeg 合并但未找到"
        vt, at = dst_abs + ".v.m4s", dst_abs + ".a.m4s"
        try:
            download_to(v["baseUrl"], vt, cookie)
            if a:
                download_to(a["baseUrl"], at, cookie)
                cmd = [ff, "-y", "-loglevel", "error", "-i", vt, "-i", at, "-c", "copy", dst_abs]
            else:
                cmd = [ff, "-y", "-loglevel", "error", "-i", vt, "-c", "copy", dst_abs]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=DL_TIMEOUT)
            if r.returncode != 0 or not os.path.isfile(dst_abs):
                return False, f"ffmpeg 合并失败：{(r.stderr or '')[-200:]}"
        finally:
            for t in (vt, at):
                if os.path.isfile(t):
                    try:
                        os.remove(t)
                    except OSError:
                        pass
        size = os.path.getsize(dst_abs)
        return True, f"dash/{v.get('width')}x{v.get('height')} {size/1024/1024:.1f} MB（{duration}s）"
    except Exception as e:
        return False, f"{note}；dash 异常 {e}"


def main():
    global MAX_DURATION, KEEP_DAYS

    ap = argparse.ArgumentParser(description="下载 B 站动态里的短视频（360P，≤5 分钟）")
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--max-duration", type=int, default=MAX_DURATION, help="最长时长（秒）")
    ap.add_argument("--days", type=int, default=KEEP_DAYS, help="本地保留天数")
    ap.add_argument("--max-downloads", type=int, default=6, help="单次运行最多下载几个（防突发批量）")
    ap.add_argument("--dry-run", action="store_true", help="只列出会做什么，不下载")
    args = ap.parse_args()

    MAX_DURATION, KEEP_DAYS = args.max_duration, args.days

    repo = os.path.abspath(args.repo)
    bili_json = os.path.join(repo, "bili.json")
    video_root = os.path.join(repo, VIDEO_ROOT_REL)
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
    now = time.time()
    cutoff = now - KEEP_DAYS * 86400
    cookie, has_sess = get_cookie()
    log(f"保留 {KEEP_DAYS} 天内、时长 ≤{MAX_DURATION}s 的视频；360P；登录态={'有' if has_sess else '无（匿名）'}")

    changed = 0
    downloaded = 0
    skipped = 0
    for it in items:
        bvid = it.get("bvid")
        if not bvid:
            continue
        try:
            ts = int(it.get("ts") or 0)
        except (TypeError, ValueError):
            ts = 0
        rel = f"{VIDEO_ROOT_REL}/{bvid}.mp4"
        abs_p = os.path.join(repo, rel.replace("/", os.sep))

        # 超期：删文件 + 去掉字段（条目保留在 bili.json 中）
        if ts and ts < cutoff:
            if os.path.isfile(abs_p):
                try:
                    os.remove(abs_p)
                    log(f"[过期] 删除 {rel}（发布于 {time.strftime('%Y-%m-%d', time.localtime(ts))}）")
                except OSError:
                    pass
            if it.get("video"):
                it.pop("video", None)
                changed += 1
            skipped += 1
            continue

        if args.dry_run:
            if not os.path.isfile(abs_p):
                log(f"[dry-run] 将下载 {bvid}（时长字段 {it.get('durSec')}）")
            continue

        if downloaded >= args.max_downloads:
            log(f"[限额] 本次已下载 {downloaded} 个，其余留到下次")
            break

        if os.path.isfile(abs_p):
            if it.get("video") != rel:
                it["video"] = rel
                changed += 1
            continue

        ok, note = fetch_one(bvid, abs_p, cookie)
        if ok:
            downloaded += 1
            it["video"] = rel
            changed += 1
            log(f"[ok] {bvid} {note}")
        else:
            skipped += 1
            log(f"[skip] {bvid} {note}")
            # 文件可能残留半成品
            for p in (abs_p, abs_p + ".part"):
                if os.path.isfile(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

    # 清理不再被引用的本地视频
    referenced = set()
    for it in items:
        v = it.get("video")
        if isinstance(v, str) and v.startswith(VIDEO_ROOT_REL + "/"):
            referenced.add(os.path.normcase(os.path.join(repo, v.replace("/", os.sep))))
    removed = 0
    if os.path.isdir(video_root):
        for fn in os.listdir(video_root):
            abs_p = os.path.join(video_root, fn)
            if os.path.isfile(abs_p) and os.path.normcase(abs_p) not in referenced:
                try:
                    os.remove(abs_p)
                    removed += 1
                except OSError:
                    pass

    if changed:
        with open(bili_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log(f"已更新 bili.json（{changed} 处改动），清理 {removed} 个文件")
    else:
        log(f"bili.json 无需改动，清理 {removed} 个文件")

    n = sum(1 for it in items if it.get("video"))
    files = [f for f in os.listdir(video_root)] if os.path.isdir(video_root) else []
    total = sum(os.path.getsize(os.path.join(video_root, f)) for f in files) / 1024 / 1024
    log(f"本地视频 {len(files)} 个 / {total:.1f} MB；带 video 字段的条目 {n}；本次下载 {downloaded}，跳过 {skipped}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"[error] 未捕获异常：{e}")
        sys.exit(0)      # 不阻断后续发布流程

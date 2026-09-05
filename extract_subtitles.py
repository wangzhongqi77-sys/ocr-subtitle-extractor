#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_subtitles.py — 视频 OCR 字幕提取器

流程：抽帧(ffmpeg 优先 / OpenCV 保底) → PaddleOCR → 连续去重 → 输出两份结果
  - <out>.txt      精修字幕（连续相同内容只保留一条）
  - _raw_<out>.txt 原始 OCR（每一帧都写，不过滤不去重，供人工核实对照）

用法：
  python extract_subtitles.py --video clip.mp4 --out subs.txt
  python extract_subtitles.py --video clip.mp4 --out subs.txt --mode full
  python extract_subtitles.py --video clip.mp4 --out subs.txt --typo-map typoMap.json

依赖：
  pip install paddleocr opencv-python
  并自行安装 ffmpeg（可选，未安装时自动退回 OpenCV 抽帧）
"""
import argparse
import cv2
import difflib
import json
import os
import subprocess
from paddleocr import PaddleOCR


def get_texts(r):
    # 兼容 PaddleOCR v5（返回对象，rec_texts 是属性）与旧版（返回 dict）
    if isinstance(r, dict):
        return r.get("rec_texts", []) or []
    return getattr(r, "rec_texts", []) or []


def similarity(a, b):
    # 字符级相似度（0~1），用于把“同一句字幕的近似读”合并成一条
    return difflib.SequenceMatcher(None, a, b).ratio()


def build_crop(mode, custom):
    """返回 ffmpeg 的 crop 前缀（含结尾逗号），full 模式为空。"""
    if custom:
        return custom
    if mode == "full":
        return ""
    # bottom：只取画面底部 30%，排除顶部品牌 logo / 贴纸干扰
    return "crop=iw:ih*0.3:0:ih*0.7,"


def extract_frames(video, tmp, crop_vf, fps):
    """抽帧：ffmpeg 优先，OpenCV 保底。返回 (文件列表, 方法名)。"""
    os.makedirs(tmp, exist_ok=True)
    # 清空旧帧，避免上一轮残留污染本轮回填
    for f in os.listdir(tmp):
        if f.endswith(".jpg"):
            try:
                os.remove(os.path.join(tmp, f))
            except OSError:
                pass

    vf = crop_vf + f"fps={fps}"
    try:
        r = subprocess.run(
            ["ffmpeg", "-i", video, "-vf", vf, "-q:v", "2", "-y",
             os.path.join(tmp, "f_%03d.jpg")],
            capture_output=True, text=True, timeout=300,
        )
        files = sorted(f for f in os.listdir(tmp) if f.endswith(".jpg"))
        if r.returncode == 0 and files:
            print(f"[extract] ffmpeg OK, {len(files)} frames", flush=True)
            return files, "ffmpeg"
        print(f"[extract] ffmpeg rc={r.returncode}, jpgs={len(files)}", flush=True)
    except Exception as e:
        print(f"[extract] ffmpeg error: {e}", flush=True)

    # 保底：OpenCV 抽帧
    print("[extract] fallback -> OpenCV", flush=True)
    cap = cv2.VideoCapture(video)
    video_fps = cap.get(cv2.CAP_PROP_FPS) or 1
    step = max(int(video_fps) // max(fps, 1), 1)
    idx, saved = 0, 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % step == 0:
            if crop_vf:  # bottom 模式裁剪底部 30%
                h = frame.shape[0]
                frame = frame[int(h * 0.7):h, :]
            cv2.imwrite(os.path.join(tmp, f"f_{saved:03d}.jpg"), frame)
            saved += 1
        idx += 1
    cap.release()
    files = sorted(f for f in os.listdir(tmp) if f.endswith(".jpg"))
    print(f"[extract] OpenCV OK, {len(files)} frames", flush=True)
    return files, "opencv"


def main():
    ap = argparse.ArgumentParser(description="视频 OCR 字幕提取")
    ap.add_argument("--video", required=True, help="输入视频路径")
    ap.add_argument("--out", required=True, help="输出字幕文件路径（如 subs.txt）")
    ap.add_argument("--frames-dir", default=None,
                    help="抽帧临时目录（默认：<out 同目录>/_frames）")
    ap.add_argument("--mode", choices=["bottom", "full"], default="bottom",
                    help="bottom=只取底部30%（默认，适合顶部有 logo 的视频）；"
                         "full=整帧（适合双层字幕/顶部也有字幕的视频）")
    ap.add_argument("--fps", type=int, default=1, help="每秒抽帧数（默认 1）")
    ap.add_argument("--crop", default=None,
                    help="自定义 ffmpeg crop 表达式，覆盖 --mode（高级用法）")
    ap.add_argument("--typo-map", default=None,
                    help="可选：错字修正 JSON（{\"错字\":\"正字\"}），逐条 replace")
    ap.add_argument("--merge-threshold", type=float, default=0.8,
                    help="相似度合并阈值（0~1）：>=此值视为同一句字幕的近似读，不重复输出。"
                         "设 1.0 等于「仅完全相同才合并」")
    ap.add_argument("--no-merge", action="store_true",
                    help="关闭相似度合并，退回「相邻完全相同才去重」的旧逻辑")
    args = ap.parse_args()

    out_abs = os.path.abspath(args.out)
    tmp = args.frames_dir or os.path.join(os.path.dirname(out_abs), "_frames")
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)

    typo_map = {}
    if args.typo_map:
        typo_map = json.load(open(args.typo_map, encoding="utf-8"))

    crop_vf = build_crop(args.mode, args.crop)
    files, method = extract_frames(args.video, tmp, crop_vf, args.fps)
    print(f"Frames: {len(files)} via {method}")

    ocr = PaddleOCR(lang="ch", use_doc_orientation_classify=False,
                    use_doc_unwarping=False)

    raw_path = os.path.join(os.path.dirname(out_abs),
                            "_raw_" + os.path.basename(out_abs))
    results, prev = [], None
    with open(raw_path, "w", encoding="utf-8") as fraw:
        for i, f in enumerate(files):
            r = ocr.predict(os.path.join(tmp, f))[0]
            txt = " ".join(get_texts(r))
            for wrong, right in typo_map.items():
                txt = txt.replace(wrong, right)
            txt = " ".join(txt.split())  # 去首尾/折叠多余空白，消灭“ 多空格”类噪声
            sec = int(i / max(args.fps, 1))
            m, s = divmod(sec, 60)
            stamp = f"[{m:02d}:{s:02d}]"
            fraw.write(f"{stamp} {txt}\n")  # 所有帧都写（不过滤不去重），供核对
            if not txt:
                prev = None
                continue
            if prev is None:
                results.append(f"{stamp} {txt}")
                prev = txt
            elif args.no_merge or similarity(prev, txt) < args.merge_threshold:
                # 明显不同（或关了合并）→ 新一句字幕，输出
                results.append(f"{stamp} {txt}")
                prev = txt
            # 否则：相似度够高 = 同一句字幕的近似读（多空格/多O等），跳过不重复输出
            if i % 10 == 0:
                print(f"{i}/{len(files)}", flush=True)

    with open(out_abs, "w", encoding="utf-8") as f:
        f.write("\n".join(results))
    print(f"\n{len(results)} lines -> {out_abs}")
    print(f"{len(files)} raw lines -> {raw_path}")


if __name__ == "__main__":
    main()

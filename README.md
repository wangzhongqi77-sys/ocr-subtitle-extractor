# ocr-subtitle-extractor

从视频里用 OCR 把字幕文字抠出来的小工具 + 工作流。

专治「抖音/短视频里有一段口播字幕想转成文本」这类需求：抽帧 → PaddleOCR 识别 → 去重 → 输出精修字幕，并保留**原始逐帧 OCR** 供人工核实。

## 为什么不直接用现成字幕提取软件

- 很多短视频字幕是**烧录在画面里的**（不是软字幕），通用工具提取不到。
- VideoSubFinder / VSE 这类软件封装太厚、精度不可控，且不做「识别 → 核实」闭环。
- 本工具保留原始逐帧 OCR，让你能**逐帧核对有没有漏读**——这是 OCR 最容易翻车的地方。

## 安装

```bash
pip install paddleocr opencv-python
```

ffmpeg 可选：装了就用 ffmpeg 抽帧（更快），没装自动退回 OpenCV。

- Windows 下载：https://ffmpeg.org/download.html
- macOS：`brew install ffmpeg`
- Linux：`apt install ffmpeg`

## 用法

```bash
# 基础：底部 30% 字幕（默认，适合顶部有 logo 的视频）
python extract_subtitles.py --video clip.mp4 --out subs.txt

# 双层字幕（顶部也有花字卖点）：抽整帧
python extract_subtitles.py --video clip.mp4 --out subs.txt --mode full

# 带错字自动修正
python extract_subtitles.py --video clip.mp4 --out subs.txt --typo-map typoMap.example.json
```

| 参数 | 说明 | 默认 |
|---|---|---|
| `--video` | 输入视频路径（必填） | — |
| `--out` | 输出字幕文件路径（必填） | — |
| `--mode` | `bottom`（底部30%）/ `full`（整帧） | `bottom` |
| `--fps` | 每秒抽帧数 | `1` |
| `--frames-dir` | 抽帧临时目录 | `<out 同目录>/_frames` |
| `--typo-map` | 错字修正 JSON（见下） | 无 |
| `--crop` | 自定义 ffmpeg 裁剪表达式，覆盖 `--mode` | 无 |

运行后生成两份文件（以 `--out subs.txt` 为例）：

- `subs.txt` — 精修字幕（连续相同去重）
- `_raw_subs.txt` — 原始逐帧 OCR（**核实依据，不要删**）

## 错字修正表

OCR 对数字、形近字容易读错。维护一份 `typoMap.json` 即可自动修：

```json
{
  "碟杀": "碟刹",
  "弯彩": "弯梁",
  "汽车纤": "汽车级"
}
```

参考 `typoMap.example.json`，按你自己的视频往里加。

## 核实流程（重要）

OCR **会漏读**——低对比度、特殊字体、画面叠加文字都可能识别不到。所以：

1. 打开 `_raw_subs.txt`（原始逐帧）和 `subs.txt`（精修）对比。
2. 出逐条对照表：每条精修对应哪些原始帧。
3. **原始里连续空帧超过 2 秒，必须翻对应截图确认**（抽帧目录里的 `f_NNN.jpg`，`f_001` = 第 0 秒）。空白 ≠ 没字。

> 核实 = 读已有数据 + 出对照表 + 空白帧翻截图。**不要为了核实重跑 OCR**，原始数据已经在 `_raw_` 里了。

## 踩过的坑（已实测）

- ❌ 多帧投票不能解决漏读（漏读时 3 帧全空，投了个寂寞）。
- ❌ SSIM 跳帧会导致漏内容，坚决不用。
- ❌ 同一轮并行跑多个 PaddleOCR 会挤崩（各自加载模型 → raw 0 字节），必须串行。
- ❌ 核实 ≠ 重跑 OCR。

## License

MIT

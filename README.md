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
| `--merge-threshold` | 相似度合并阈值（0~1）：>=此值视为同一句字幕的近似读，不重复输出 | `0.8` |
| `--no-merge` | 关闭相似度合并，退回「相邻完全相同才去重」的旧逻辑 | 关 |

默认开启**相似度合并**（阈值 `0.8`）：同一句字幕在不同帧上被读成「多空格 / 多 O」之类的近似读，只保留一条，避免清单出现重复噪声。想退回「相邻完全相同才去重」的旧逻辑，加 `--no-merge`；想调灵敏度改 `--merge-threshold`（设 `1.0` 等于只合并完全相同的）。注意：合并只去"近义重复"噪声，救不了"真·认错字"，错字仍要靠 `_raw_` 翻截图核对。

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

## 和同类工具的区别

市面上有 VSE（video-subtitle-extractor，9000+⭐）、VideOCR（GUI + GPU + 200 语言 + Docker）、HardSubExtract 等，底层基本都是 PaddleOCR。本工具不跟它们在「功能多」上卷，差异化在三点：

1. **提取即可核对，不怕漏读**。同时输出 `_raw_字幕.txt`（每一帧原始 OCR，不过滤不去重）和精修版。OCR 会漏读低对比度 / 特殊字体的字——本工具强制你翻空白帧截图核对漏句。大工具只管「吐字幕」，不管你漏没漏。
2. **踩坑经验写进文档**。多帧投票救不了漏读、SSIM 跳帧会漏内容、双层字幕（抖音类「顶部花字卖点 + 底部口播」）要用 `full` 模式——这些是用真视频一帧帧试出来的，全写在 `SKILL.md` 里，不让你踩第二遍。
3. **单文件、零花活**。一个 `extract_subtitles.py`，参数化，ffmpeg 抽帧 + OpenCV 保底，MIT 随便改。没有 GUI、没有 GPU 依赖、没有 Docker，适合想看懂原理、自己改的人。
4. **对新版 PaddleOCR 开箱即用，且能跑在没屏幕的环境**。本工具按 PaddleOCR v5 的 `predict()` + `rec_texts` 写法实现，且没有 GUI 依赖，能在服务器 / 云 / 自动化脚本里跑。注意：头部竞品 VSE、VideOCR 其实也在活跃维护、且已升级到 PaddleOCR v5，它们「打不开」只是因为带窗口的桌面软件需要屏幕；而底层库 videocr_paddle 等会滞后于 PaddleOCR 最新小版本（我们装的 3.4.1 已移除旧 kwarg，旧库直接报错）。所以相对竞品，本工具的实在优势是「无头可跑 + 开箱即用 + 提取完能翻原文核对」，而不是「比它们新」。详见 `BENCHMARK_对比报告.md`。

> 要「拖个视频一键出 srt」→ VideOCR / VSE 这类 GUI 工具更省事，但它们本质是 Windows 桌面软件、大多还要 GPU/Docker，在无头/云环境里跑不了；CLI 形态的竞品（videocr_paddle、HardSubExtract）在本机实测需改代码适配新 PaddleOCR。
> 要「可审计、可核对、能学明白原理、换新版本不崩」的提取流程 → 用这个。

## License

MIT

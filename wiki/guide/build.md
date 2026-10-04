# 重新构建

## 一代

```powershell
uv run python pipeline/build.py
```

依次执行：

1. 用 FFDec 导出脚本 / 文本 / symbolClass（到 `work/scripts`）；
2. 从 ParaTranz 导出生成内嵌字幕的 `patch/DTSound.as`；
3. 生成汉化后的玩法 ActionScript；
4. 生成汉化 UI 文本 + 两个中文字体子集（展示体 `RoadOfTheDeadCN` + 正文思源宋体）；
5. 合并回 SWF 并编译。

产物：`dist/rotd-zh.swf`

可选参数：

```powershell
# 指定原版 SWF
uv run python pipeline/build.py --orig dist/Road-Of-The-Dead.swf

# 跳过 FFDec 导出（复用 work/scripts，调样式时可省时间）
uv run python pipeline/build.py --skip-export
```

## 二代

二代没有单一入口，UI 汉化由 `pipeline/ui/build_rotd2_ui.py` 完成（默认输出
`dist/rotd2-zh-ui.swf`，正式产物用 `--out` 指定）：

```powershell
# 标准二代
uv run python pipeline/ui/build_rotd2_ui.py `
  --orig dist/Road-Of-The-Dead2.swf `
  --out  dist/rotd2-zh.swf

# True Hell 体验版
uv run python pipeline/ui/build_rotd2_ui.py `
  --orig "dist/Road-Of-The-Dead2.TRUE HELL MOD体验版 .swf" `
  --scripts work2/truehell_scripts/scripts `
  --texts   work2/truehell_scripts/texts `
  --workdir work2/truehell `
  --out    dist/rotd2-true-hell-zh.swf
```

二代构建依赖 `work2/` 下的反编译脚本与 ASR 数据：

| 路径 | 用途 |
|---|---|
| `work2/scripts/scripts` | 反编译脚本（字面量替换 + 字幕注入的输入） |
| `work2/scripts/texts` | 导出的烘焙文本 |
| `work2/asr_gpu.json` | 语音时长 / 分段 |
| `work2/stream_timing.json` | 开场流式音轨逐段起止时间 |

这些可由 FFDec 导出与 ASR 流程重新生成；仓库不包含游戏本体，需先准备原版 SWF。

## 构建前的翻译同步

构建**直接读取** `data/paratranz`（一代）与 `data/paratranz2`（二代）。
要使用平台最新翻译，先执行：

```powershell
$env:PARATRANZ_TOKEN = "<token>"
uv run python pipeline/paratranz/pull_translations.py
```

详见[翻译平台工作流](/guide/translations)。

## 体积说明

中间步骤输出未压缩 SWF（FWS），最后一步 `compress_swf()` 会重新 zlib 压缩成
游戏原版的 CWS。一代约 30.19 MB → 27.43 MB，二代约 57.6 MB → 49.1 MB。

# 环境准备

## 必需

| 组件 | 用途 | 获取方式 |
|---|---|---|
| Python 3.12+ / [uv](https://docs.astral.sh/uv/) | 主环境：FFDec 调用 / 导出分析 / 构建 | `uv sync` |
| Java 17+ | 运行 FFDec CLI | 系统安装 |
| FFDec CLI | 导出 / 替换 SWF 资源 | `pipeline/tools/fetch-tools.ps1` |
| 原版游戏 SWF | 构建输入 | 自行获取，默认放 `dist/` |

```powershell
uv sync
# 下载 FFDec（走国内镜像可加 -Proxy）
pwsh -File pipeline/tools/fetch-tools.ps1 -Proxy http://127.0.0.1:7897
```

默认原版路径为 `dist/Road-Of-The-Dead.swf`，可用 `--orig` 覆盖。

## 字体（构建时自动裁剪）

| 字体 | 说明 |
|---|---|
| `data/fonts/RoadOfTheDeadCN.ttf` | Dirty Ego 风格中文游戏字体（展示体） |
| `data/fonts/NotoSerifSC-SemiBold.ttf` | 思源宋体，SIL OFL 1.1 |
| `data/fonts/NotoSansSC-VF.ttf` | Noto Sans SC 可变字体，SIL OFL 1.1 |

重新拉取 Noto Sans SC：

```powershell
pwsh -File pipeline/tools/fetch-fonts.ps1 -Proxy http://127.0.0.1:7897
```

## ASR（可选，仅在重新转写时用）

ASR 产物（`data/asr_all.json`、`stream_segments.json` 等）已随仓库提供，
**重新构建不需要 GPU**，只有需要重新转录语音时才需要。

AMD GPU 走 whisper.cpp + Vulkan：

```powershell
pwsh -File pipeline/tools/fetch-whisper.ps1
uv run python pipeline/asr/asr_vulkan.py --voice-only --concurrency 4
uv run python pipeline/asr/asr.py --no-vad --voice-only --concurrency 4
uv run python pipeline/asr/clean_asr.py --asr work/asr_gpu.json
```

所有转写流程共用一个常驻 whisper-server：模型只加载一次，请求并发执行。

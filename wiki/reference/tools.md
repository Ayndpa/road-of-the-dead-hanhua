# 分析与调试工具

## 一代构建 / 生成

| 脚本 | 用途 |
|---|---|
| `pipeline/build.py` | 一代完整构建入口 |
| `pipeline/subtitles/make_dtsound.py` | 生成内嵌字幕的 `DTSound.as` |
| `pipeline/runtime/patch_as3.py` | 运行时字符串替换 |
| `pipeline/ui/build_ui.py` | 准备 UI 文本 + 字体子集 |
| `pipeline/ui/build_all.py` | 一代拼接 + 编译 |
| `pipeline/ui/menu_labels.py` | 主菜单矢量标签 → 中文矢量 SVG 并替换 shape |
| `pipeline/lib/align_controls.py` | 按原版墨迹轴重排静态标签 |

## 二代构建

| 脚本 | 用途 |
|---|---|
| `pipeline/ui/build_rotd2_ui.py` | 二代 UI 汉化（12 字体槽适配） |
| `pipeline/ui/align_rotd2.py` | 二代静态标签对齐 |
| `pipeline/ui/fit_menu_rotd2.py` | 二代主菜单标签按英文墨迹缩放 |
| `pipeline/ui/book_labels_rotd2.py` | 二代生存手册书脊矢量文字 |

## SWF 只读分析

| 脚本 | 用途 |
|---|---|
| `pipeline/swf/swf_labels.py` | 主时间轴帧标签 / 场景 / 流式音轨覆盖范围 |
| `pipeline/swf/stream_timing.py` | 帧 → 真实音频时间的精确换算 |
| `pipeline/swf/swf_text_fonts.py` | 每个 `DefineText` 用的字体 |
| `pipeline/swf/frame_chars.py` | 某一帧上放置了哪些 character |
| `pipeline/swf/walk_sprite.py` | 递归展开 sprite 结构 |
| `pipeline/swf/scan_strings.py` | 扫描反编译 AS3 里疑似用户可见的字符串 |
| `pipeline/swf/dump_as3_strings.py` | 词法扫描 AS3 字符串字面量 |
| `pipeline/swf/collect_menu_shapes.py` | 导出菜单 Shape 供重绘 |

## 共享库

| 脚本 | 用途 |
|---|---|
| `pipeline/lib/remap_font.py` | 改文本指向的字体 id（支持一次改多个旧 id → 一个槽） |
| `pipeline/lib/translations.py` | 读取平台 CSV（`ROT_TRANSLATIONS` 可覆盖） |

## 第三方工具拉取

```powershell
pwsh -File pipeline/tools/fetch-tools.ps1  -Proxy http://127.0.0.1:7897   # FFDec
pwsh -File pipeline/tools/fetch-whisper.ps1 -Proxy http://127.0.0.1:7897  # whisper.cpp (Vulkan)
pwsh -File pipeline/tools/fetch-fonts.ps1  -Proxy http://127.0.0.1:7897   # Noto Sans SC
```

## ASR（可选）

```powershell
uv run python pipeline/asr/asr_vulkan.py --voice-only --concurrency 4
uv run python pipeline/asr/asr.py --no-vad --voice-only --concurrency 4
uv run python pipeline/asr/clean_asr.py --asr work/asr_gpu.json
```

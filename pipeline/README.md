# pipeline 目录索引

Road of the Dead 汉化工具链的脚本集合。所有脚本都按功能放在子包里，统一使用
`pipeline.<包>.<模块>` 的绝对导入，并在启动时把**仓库根目录**加入 `sys.path`，
因此既可以用文件路径运行（`uv run python pipeline/...`），也可以被导入。

## 目录

```
pipeline/
  build.py            一代完整构建入口（导出 → 字幕 → 运行时文本 → UI → 合并回 SWF）
  lib/                共享库
  asr/                语音转写
  swf/                SWF 只读分析 / 一次性工具
  ui/                 UI 汉化构建
  runtime/            运行时 AS3 文本
  subtitles/          游戏内字幕
  paratranz/          ParaTranz 导入 / 回传
  tools/              第三方工具拉取脚本（fetch-*.ps1）
```

## 常用入口

```powershell
uv run python pipeline/build.py                     # 一代完整构建
uv run python pipeline/ui/build_rotd2_ui.py         # 二代 UI 汉化
uv run python pipeline/tools/...                    # 见 tools/（pwsh -File ...）

# ASR（可选，仅在重新转写时用；下面是常驻 whisper-server，模型只加载一次）
uv run python pipeline/asr/asr_vulkan.py --voice-only --concurrency 4
uv run python pipeline/asr/asr.py --no-vad --voice-only --concurrency 4
uv run python pipeline/asr/clean_asr.py --asr work/asr_gpu.json
```

## 分包说明

### lib/ — 共享库
| 模块 | 用途 |
|---|---|
| `translations.py` | 读取 `data/paratranz/*.csv`（`ROT_TRANSLATIONS` 可覆盖） |
| `remap_font.py` | SWF 字节级字体重映射 / layout 克隆 / FontName 改写 |
| `align_controls.py` | 按原版墨迹轴重排静态 `DefineText`（居中 / 右对齐 / 裁剪框） |

### asr/ — 语音转写
| 模块 | 用途 |
|---|---|
| `whisper_server.py` | 常驻 whisper-server 客户端（模型只加载一次，供下面各流程共用） |
| `asr.py` | 全文件转写（Silero VAD 可选，走 server） |
| `asr_vulkan.py` | 批量 GPU 转写（走 server，`--concurrency` 并发、`--shards/--shard` 分片） |
| `asr_segments.py` | VAD 分段 + 逐段增益归一化转写（走 server） |
| `asr_filter.py` | ASR 文本侧清理规则（供 `clean_asr` 复用） |
| `clean_asr.py` | 丢弃幻觉 / 非对白片段 |
| `merge_asr.py` | 合并 CPU / GPU 分片结果 |
| `pick_voice.py` | 从 ASR 结果里挑出对白片段 |

### swf/ — 只读分析
| 模块 | 用途 |
|---|---|
| `swf_labels.py` | 主时间轴帧标签 / 场景 / 流式音轨范围 |
| `stream_timing.py` | 帧 → 真实音频时间换算 |
| `swf_text_fonts.py` | 每个 `DefineText`/`DefineEditText` 用的字体 |
| `frame_chars.py` | 某帧范围内放置了哪些 character |
| `frame_labels.py` | FrameLabel → 帧号 |
| `walk_sprite.py` | 递归展开 sprite 的叶子 character |
| `collect_menu_shapes.py` | 导出菜单 Shape 供重绘 |
| `dump_as3_strings.py` | 词法扫描 AS3 字符串字面量 |
| `dump_ui.py` | 导出 FFDec 文本标签为 charId + 记录段 JSON |
| `scan_strings.py` | 扫描反编译 AS3 里疑似用户可见的字符串 |

### ui/ — UI 汉化构建
| 模块 | 用途 |
|---|---|
| `menu_labels.py` | 主菜单矢量按钮 → 中文矢量 SVG 替换 shape |
| `build_ui.py` | 准备翻译后的 UI 文本 + CJK 字体子集 |
| `build_all.py` | 一代拼接 + 编译（UI 文本 + 字幕并入 SWF） |
| `build_rotd2_ui.py` | 二代 UI 汉化（12 字体槽适配） |
| `align_rotd2.py` | 二代静态标签对齐 |
| `book_labels_rotd2.py` | 二代生存手册书脊矢量文字 |
| `fit_menu_rotd2.py` | 二代主菜单标签按英文墨迹缩放 |

### runtime/ — 运行时文本
| 模块 | 用途 |
|---|---|
| `patch_as3.py` | 按字面量精确替换玩法脚本里的用户可见字符串 |

### subtitles/ — 游戏内字幕
| 模块 | 用途 |
|---|---|
| `make_dtsound.py` | 字幕补丁入口 / CLI（`--out patch/DTSound.as`） |
| `dtsound/` | 实现包：AS3 模板、AS3 字面量编码、中英句对齐、ASR 时间对齐、装配 |

### paratranz/ — 翻译平台
| 模块 | 用途 |
|---|---|
| `extract_rotd2.py` | 提取二代用户可见文本为平台源 CSV |
| `push_translations.py` | 把本地 CSV 回传覆盖平台数据 |
| `multiget.py` | 多线程分段下载（模型 / 大文件） |

## 约定

- 本地导入一律写成 `from pipeline.lib.translations import ...` 这种绝对形式；
  脚本只负责把仓库根目录放进 `sys.path`，不需要自己所在目录。
- 子进程调用统一用 `ROOT / "pipeline" / "<包>" / "<脚本>.py"`；`build.py` 用
  `pipeline/<包>/<脚本>.py` 相对仓库根的路径。
- `dtsound/` 是普通子包，可用 `uv run python -m pipeline.subtitles.dtsound --help`
  运行；也可以直接用 `pipeline/subtitles/make_dtsound.py`。

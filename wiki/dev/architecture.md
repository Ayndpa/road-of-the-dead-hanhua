# 总体架构

## 设计目标

对原始 SWF 做**无损结构修改**：不改源码逻辑（除少量字符串），不替换美术资源，
随时可以从原版重新构建。

## 数据流

```
             data/paratranz{,2}/*.csv        data/fonts/*.ttf
                     │                              │
                     ▼                              ▼
  ┌──────────────────────────────────────────────────────────┐
  │                      pipeline                            │
  │                                                          │
  │  FFDec 导出 ──► 字幕生成 ──► AS3 字面量替换 ──► UI 文本   │
  │       │             │              │             │        │
  │       └─────────────┴──────────────┴─────────────┘        │
  │                          │                                │
  │                  字体子集 + 重映射                        │
  │                          │                                │
  │                          ▼                                │
  │                  FFDec -replace 回填 SWF                  │
  │                          │                                │
  │                    zlib 压缩 (CWS)                        │
  └──────────────────────────┬───────────────────────────────┘
                             ▼
                     dist/rotd{,2}-zh.swf
```

## 改动介入点

| 层面 | 介入方式 | 模块 |
|---|---|---|
| 语音字幕 | 钩 `DTSound.Play()` | `pipeline/subtitles/` |
| 开场流式音轨 | `ENTER_FRAME` 帧号换算 | `pipeline/subtitles/dtsound/` |
| 运行时文本 | AS3 字面量精确替换 | `pipeline/runtime/patch_as3.py` |
| 烘焙 UI 文本 | `DefineText` 逐记录重写 | `pipeline/ui/build_ui.py` |
| 字体 | `DefineFont` 换字形 + 子集 | `pipeline/ui/build_all.py` |
| 主菜单矢量字 | `DefineShape` 矢量重绘 | `pipeline/ui/menu_labels.py` |
| 静态文本对齐 | 按原版墨迹轴改 `translatex` | `pipeline/lib/align_controls.py` |
| 字体重映射 | 字节级改 `DefineText` 字体 id | `pipeline/lib/remap_font.py` |

## 三大难点

1. **FFDec 的坑**
   - `-importText` 是静默空操作，必须用 `-replace <charId> <txt>`。
   - 换字体时按字符重映射已有 `DefineText` 的字形索引，遇到无 Unicode 映射的字形会越界崩溃。
   - 中文更短时残留尾部旧字形。

2. **字体 layout**
   - `DefineEditText` 靠 `DefineFont` 的 advance 表排版；槽缺 layout 会让动态文本宽度塌成 0 而消失。
   - 运行时文本框按**字体名字符串**查找嵌入字体，名字撞车会导致中文命中拉丁字体而空白。

3. **对齐**
   - 英文换中文后变短，FFDec 在标签左原点重新左对齐，原本居中 / 右对齐的行会偏移。
   - 需按原版**墨迹轴**（而非存储框）重新对齐，并放宽裁剪框避免中文被切。

各难点的完整处理见后续章节。

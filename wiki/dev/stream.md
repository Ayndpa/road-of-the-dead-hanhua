# 开场流式音轨

开场旁白在主时间轴的**流式音轨**（`-1.mp3`）里，不经过 `DTSound`。

## 帧 → 时间换算

用 `Event.ENTER_FRAME` 把主时间轴帧号换算成音轨时间：

```
t = (currentFrame - 1) / frameRate - 1.58
```

`1.58s` 是实测偏移：`pipeline/swf/stream_timing.py` 解析全部 `SoundStreamBlock`
的 MP3 帧头，算出每帧的真实音频时间，整条时间轴偏移恒定。

## 二代偏移

二代根音频流从第 75 帧开始、30 fps，且流声音相对时间轴滞后约 3.1s
（对照解码后的 MP3 包时间测得），因此：

```
t = (frame - 1) / 30 - (74 + 93) / 30
```

对应 `build_rotd2_ui.py` 里的 `stream_offset=(74.0 + 93.0) / 30.0`。

## 非对白片段过滤

Whisper 会把纯音乐段识别成 `*Dramatic Music*` 这类舞台提示。这类片段**没有台词、
不应有字幕**，因此：

- 同步层：`pull_translations.py` 拉取 `stream.csv` 时会丢弃整行都是括注
  （如 `*Dramatic Music*`）的条目，`push_translations.py` 上传时同样过滤并
  因此把这类 key 从平台移除，避免暴露给汉化组；
- 构建层：`generate.py` 在生成流式字幕前再用 `asr_filter.is_stage_direction()`
  兜底过滤，即使 CSV 里混入也不会显示。

判定规则只看**整行**是否为括注音效标签（`is_stage_direction`），不会误伤
`[unit] to base.` 这类包含占位符的真实台词。

## 数据结构

| 文件 | 内容 |
|---|---|
| `data/stream_timing.json` | 逐段起止时间（结构数据，非翻译） |
| `data/stream_segments.json` | 逐段 ASR（含时间戳） |
| `data/paratranz/stream.csv` | `stream_NN → 中文` |

## 分析工具

`pipeline/swf/stream_timing.py` 解析帧头；`pipeline/swf/swf_labels.py`
可列出主时间轴帧标签 / 场景 / 流式音轨覆盖范围，用于定位偏移。

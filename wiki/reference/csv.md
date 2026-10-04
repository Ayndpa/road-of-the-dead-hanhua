# 翻译文件格式

平台 CSV 格式：`key,original,translation,context`（无表头），与上传 / 下载的文件完全一致。
一代放 `data/paratranz/`，二代放 `data/paratranz2/`。

| 文件 | 对应内容 | key | 原文列 |
|---|---|---|---|
| `voice.csv` | 语音字幕（`DTSound.Play` 查表） | `SND_*` 声音类名 | 英文台词 |
| `stream.csv` | 开场流式音轨字幕 | `stream_NN` | 英文原文（时间来自 `stream_timing.json`） |
| `ui.csv` | 烘焙 `DefineText`（多段用换行分隔，段数须与原版一致） | `ui_<DefineText id>` | 原英文 |
| `as3.csv` | 成就 / 提示 / 关卡等运行时文本 | `as3_<文件>_<序号>` | FFDec 反编译出的字面量 |
| `menu.csv` | 主菜单手绘按钮标签 | 标签名（如 `StoryMode`） | 按钮英文 |

## 加载规则

`pipeline/lib/translations.py`：

- 跳过空行、以 `#` 开头的注释行与表头行；
- 只把 `translation` 非空的词条纳入构建（未译条目回退原文）；
- `ui.csv`：key 去掉 `ui_` 前缀，译文按 `\n` 拆成记录列表 `{DefineText id: [record, ...]}`；
- `as3.csv`：按 `context` 聚合成 `{文件名: {英文字面量: 中文}}`。

## 重要约定

::: warning ui.csv 段数必须一致
`ui.csv` 里一条词条就是整段 UI 文本，多段用换行分隔，翻译时**段数必须与原版一致**
（对应 `--- RECORDSEPARATOR ---`）。段数错位会让标签导入错行。
:::

::: tip stream.csv 会过滤非对白片段
整行是括注音效标签（如 Whisper 在纯音乐段产生的 `*Dramatic Music*`）的词条没有台词，
不应有字幕。`pull_translations.py` / `push_translations.py` 会丢弃这些行，
构建也会兜底过滤；`push_translations.py` 的非增量上传还会把它们从平台移除。
:::

- 字幕表以 `\uXXXX` 纯 ASCII 形式编译进 ABC，避免编译器编码问题；
- 双语字幕同时使用 `original` 与 `translation` 两列，因此原文列也要尽量准确。

## 导出 / 回传

```powershell
$env:PARATRANZ_TOKEN = "<token>"
uv run python pipeline/paratranz/pull_translations.py    # 平台 → 本地
uv run python pipeline/paratranz/push_translations.py    # 本地 → 平台
```

# 翻译平台工作流

所有中文翻译都放在 **ParaTranz** 项目里，仓库只保留平台导出的 CSV
（`data/paratranz/*.csv` 与 `data/paratranz2/*.csv`），构建**直接读取**这些文件 ——
源码里不再内嵌任何翻译。

- 一代项目：<https://paratranz.cn/projects/20958>
- 二代项目：<https://paratranz.cn/projects/20962>

平台 CSV 格式：`key,original,translation,context`（无表头），与上传 / 下载的文件完全一致。

## 从平台下拉最新翻译

```powershell
$env:PARATRANZ_TOKEN = "<ParaTranz API Token>"
uv run python pipeline/paratranz/pull_translations.py
```

脚本按项目逐文件调用：

```
GET /projects/{id}/files/{fileId}/translation
```

并以平台自身的 `key,original,translation,context` 布局（CRLF、无 BOM）写回本地，
因此构建读到的就是平台上的内容。

常用参数：

```powershell
# 只拉某个项目
uv run python pipeline/paratranz/pull_translations.py --project 20962

# 只拉某个文件
uv run python pipeline/paratranz/pull_translations.py --file voice.csv

# 只预览不写入
uv run python pipeline/paratranz/pull_translations.py --dry-run
```

Token 可放在仓库根目录 `.env`（已被 `.gitignore` 忽略）：

```
PARATRANZ_TOKEN=xxxxxxxx
```

## 标准工作流

1. 在 ParaTranz 上翻译 / 校对；
2. 从平台下拉最新 CSV 到本地（上节命令），或设置 `ROT_TRANSLATIONS` 指向导出目录，
   不动仓库里的文件；
3. `uv run python pipeline/build.py`（一代）或 `build_rotd2_ui.py`（二代）重新构建。

## 反向同步（本地 → 平台）

本地改了原文 / 译文后回传平台覆盖旧数据：

```powershell
$env:PARATRANZ_TOKEN = "<ParaTranz API Token>"
uv run python pipeline/paratranz/push_translations.py                 # 一代 20958 + 二代 20962 全部文件
uv run python pipeline/paratranz/push_translations.py --project 20962 --file as3.csv
```

脚本会先把仓库 CSV 作为**源文件**重新上传（补上平台缺失的词条），再按 key
通过词条 API 覆盖译文；`--dry-run` 只打印不提交。

## `ROT_TRANSLATIONS`

`pipeline/lib/translations.py` 通过环境变量 `ROT_TRANSLATIONS` 选择翻译目录：

- 一代构建默认 `data/paratranz`；
- `build_rotd2_ui.py` 会 `setdefault` 到 `data/paratranz2`。

指向临时导出目录即可在不改动仓库文件的情况下试译：

```powershell
$env:ROT_TRANSLATIONS = "D:\exports\paratranz2"
uv run python pipeline/ui/build_rotd2_ui.py --out dist/rotd2-zh.swf
```

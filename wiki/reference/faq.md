# 常见问题

## 构建

### 找不到 FFDec

```
FFDec not found at .../tools/ffdec/ffdec-cli.jar
```

运行：

```powershell
pwsh -File pipeline/tools/fetch-tools.ps1 -Proxy http://127.0.0.1:7897
```

### 字体子集失败 / 缺少字体

`build_rotd2_ui.py` 报 `missing ...NotoSansSC-VF.ttf`，运行：

```powershell
pwsh -File pipeline/tools/fetch-fonts.ps1 -Proxy http://127.0.0.1:7897
```

### 二代构建报缺少 `work2` 数据

二代依赖 `work2/scripts/scripts`、`work2/scripts/texts`、`work2/asr_gpu.json`、
`work2/stream_timing.json`。用 FFDec 重新导出脚本 / 文本，并按需重跑 ASR 流程。

### 拉取翻译报 401 / 无 token

设置 `PARATRANZ_TOKEN`（或 `PT_TOKEN`）、或写入仓库根目录 `.env`（已被忽略）。
干跑验证：`uv run python pipeline/paratranz/pull_translations.py --dry-run`。

## 运行表现

### 选项 / 成就页空白

字体槽缺 layout（advance）表，动态 `DefineEditText` 宽度塌成 0。
见[二代多字体适配 · layout 表克隆](/dev/rotd2#_1-layout-表克隆)。

### 中文不显示但拉丁字母正常

运行时文本框按字体**名字**命中拉丁字体。见
[二代多字体适配 · 字体名不能撞车](/dev/rotd2#_2-字体名不能撞车)。

### 字幕与语音不同步

确认使用了 `data/asr_all.json` 的真实分段；开场音轨偏移见
[开场流式音轨](/dev/stream)。一代偏移 `1.58s`，二代为 `(74+93)/30`。

### 居中 / 右对齐文本偏移或被切

见[文本对齐](/dev/alignment)，裁剪框需放宽到新墨迹范围 + 20 twips。

## 版本与版权

- 仓库不包含游戏本体与第三方工具；游戏版权归 Evil-Dog / SickDeathFiend 所有。
- 中文字体为 `RoadOfTheDeadCN.ttf`、`NotoSerifSC-SemiBold.ttf`（SIL OFL 1.1）
  与 `NotoSansSC-VF.ttf`（SIL OFL 1.1）；公开发布前请自行确认授权。

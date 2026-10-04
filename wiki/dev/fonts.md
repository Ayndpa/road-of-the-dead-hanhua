# 一代字体适配

## 原版字形不止两种

原版 UI 有 15 个 `DefineFont` 标签、约 10 种字形名，其中**有译文**的就有
Dirty Ego、Modern No. 20、Arial（26/32/1758）、Arial Black（46/558）、
Verdana（87/88/94）、Arial Narrow（4013）、FFF Calypso（1103）、FFF Business Bold（1106）。

汉化按每个字形的**视觉角色**各配一套中文字形（`pipeline/ui/build_all.py` 的 `G1_FONT_MAP`）：

| 原版字形 | 用在哪 | 中文槽 | 汉化字体 |
|---|---|---|---|
| Dirty Ego（20，手绘做旧） | 菜单 / HUD / 标题 / 提示 | 92 | `RoadOfTheDeadCN.ttf` |
| Modern No. 20（22，Didone 衬线） | 升级说明 / 操作·选项列表 / 成就等正文 | 22 | `NotoSerifSC-SemiBold.ttf` |
| Arial（26/32/1758）/ Verdana（87/88/94）/ Arial Narrow（4013） | NG 提示、勋章弹窗、更多游戏等 | 94 | Noto Sans SC |
| FFF Calypso（1103）/ FFF Business Bold（1106） | 排行榜标题 / 高分榜标签 | 1106 | Noto Sans SC Bold |
| Arial Black（46/558） | 制作名单标题 | 1758 | Noto Sans SC Black |

## 子集裁剪

每个字体只包含**它自己那些标签会画到的字**（再加 ASCII 与 AS3 运行时可能赋给
任意文本框的中文），用 `pyftsubset` 逐字体裁剪并丢弃 `GSUB/GPOS/GDEF` 等
SWF 用不到的表。

## layout（advance）表

**槽必须自带 layout 表**：FFDec 换字形时会保留原 `DefineFont` 的 `HasLayout` 标志，
而 `DefineEditText` 靠它排版；无 layout 的槽会让运行时动态文本（车库的 "Drive To …"、
提示框、HUD 计数）宽度塌成 0 而消失。

展示 / 正文 / 无衬线 / 粗体四个槽都带 layout；Arial Black 槽只承载静态文本。

## 保留原样

**font 20（"Dirty Ego"）本身不动**：标题 logo、制作名单、HUD 数字等未被翻译的
text 保持字节一致。

## 两个通用坑

与二代相同：

1. FFDec 换字体时会按字符重映射已有 `DefineText` 的字形索引（原字体有无 Unicode
   映射的字形时会越界崩溃）；
2. 新中文更短时会残留尾部空格。

所以构建同样**先把静态标签截成空记录、再用 `text:formatted` 逐记录写回**。

## 压缩

成品最后 `compress_swf()` 重新 zlib 压缩成 CWS（中间步骤输出的是未压缩 FWS）：
30.19 MB → 27.43 MB。

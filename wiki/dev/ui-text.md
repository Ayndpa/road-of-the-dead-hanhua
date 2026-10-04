# UI 烘焙文本

## 问题

UI 文字是**烘焙的 `DefineText`**（没有运行时字符串），所以不能靠替换字符串来汉化。

> 注意：FFDec 的 `-importText` 是**静默空操作**（不报错但什么都不改），
> 必须用 `-replace <charId> <txt>`。

## 记录分隔符

文本里 `--- RECORDSEPARATOR ---` 是记录分隔符，翻译时**段数必须一致**。

一条 `ui.csv` 词条就是整段 UI 文本，多段用换行分隔：

```
key,original,translation,context
ui_3953,OPTIONS,选项,
```

`pipeline/lib/translations.py` 的 `_ui_translations()` 会把平台 key 的 `ui_` 前缀剥掉，
重建为 `{DefineText id: [record, ...]}`。

## 逐记录重写

因为以下两个原因，构建先把静态标签**截成空记录（保留每条记录的样式与条数）**，
再用 `-format text:formatted` 逐记录写回译文：

1. FFDec 换字体时按字符重映射已有 `DefineText` 的字形索引，遇到无 Unicode 映射的字形会越界崩溃；
2. 新中文比英文短时会在标签里留下多余的旧字形（显示为尾部空格）。

多行文本的分行原样保留。

## 保留原样的部分

- 标题 logo（`Road of the Dead` / `Road of the Dead 2`）保持原始字体设计；
- 制作名单、HUD 数字、品牌字样逐字节未改动。

`build_rotd2_ui.py` 会扫描 `ui.csv` 的 `original`，把扁平化后等于
`roadofthedead` / `roadofthedead2` 的标签加入 `title_ids`，完全不重定向、不重导入。

## 相关脚本

| 脚本 | 用途 |
|---|---|
| `pipeline/ui/build_ui.py` | 准备翻译后的 UI 文本 + 字体子集（一代） |
| `pipeline/ui/build_all.py` | 一代拼接 + 编译 |
| `pipeline/swf/dump_ui.py` | 导出 FFDec 文本标签为 charId + 记录段 JSON |

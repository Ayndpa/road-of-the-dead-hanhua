# 运行时文本

成就、提示框、关卡介绍、地点名等在 AS3 字符串里，用 `pipeline/runtime/patch_as3.py`
按**字面量精确替换**。

## 做法

- 用**词法扫描**提取用户可见字符串（`pipeline/swf/dump_as3_strings.py`），
  避免正则把代码当成字符串；
- 中英对照表来自 `data/paratranz/as3.csv`（`context` 列即文件名）；
- 只替换在反编译源码里实际存在的字面量，对不上的条目会打印告警而不是改坏代码。

一代共 233 处；二代在 `build_rotd2_ui.py` 的 `as3_script_patches()` 里复用同一思路，
逐文件替换并把命中数打印出来（如 `as3 RDHelp.as: 80/80`）。

## as3.csv 格式

```
as3_<文件>_<序号>,<FFDec 反编译出的字面量>,<中文>,<文件名>
```

加载后重建为 `{文件名: {英文字面量: 中文}}`。

**不要把引擎枚举值当文案翻译。** `MainTimeline.as` 里给 Newgrounds 组件设置的两个值是
`APIConnector` 内部按英文字面量 `switch` 的枚举，不是界面文本：

- `debugMode = "Simulate Logged-in User"` → `_apiConnect` 匹配后设为
  `DEBUG_MODE_LOGGED_IN`，伪造登录会话，`API.hasUserSession` 为真，
  `TestSession()` 不显示护照/登录框；
- `connectorType = "Flash Ad Only"` → `initAd` 用来切换广告帧。

一旦译成中文就匹配不到：`debugMode` 掉进 `default`（`Off` → `RELEASE_MODE`），
本地没有真实 Newgrounds 会话时 `hasUserSession` 为假，每次启动都会弹出登录提示。
`pipeline/lib/translations.py` 用 `_NON_TRANSLATABLE_AS3` 强制跳过这两条，
`data/paratranz2/as3.csv` 里也保持英文。

## 二代附带的运行时修复

在替换字面量的同时，`build_rotd2_ui.py` 还对 `RDGame` 与 `MainTimeline` 打了几个
结构性补丁：

| 补丁 | 作用 |
|---|---|
| `apply_start_guard_patch` | 用 `m_bDidStart` 阻止 `DoStartGame` 二次执行，修复开场跳过仍重播 |
| `apply_layout_patch` | 隐藏失效的 Newgrounds 广告位并把加载面板居中 |

`apply_start_guard_patch` 的成因：`Start` 同时武装一个 5s 定时器并监听
`API_CONNECTED`；Newgrounds shim 即使连接失败也会派发 `API_CONNECTED`，
于是事件与定时器都会调用 `DoStartGame`，第二次会重跑 `StartCinematic("NGIntro", true)`。

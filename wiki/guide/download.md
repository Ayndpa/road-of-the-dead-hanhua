# 下载与安装

::: warning 版权说明
仓库**不包含**游戏本体与第三方工具，也不分发游戏文件。请自行获取原始 SWF。
游戏版权归 Evil-Dog / SickDeathFiend 所有，本汉化仅用于个人学习与汉化交流。
:::

## 玩家

1. 获取对应作品的原始 SWF。
2. 下载对应构建产物，替换或并列放置：
   - 一代：`rotd-zh.swf`
   - 二代：`rotd2-zh.swf`
   - 二代 True Hell：`rotd2-true-hell-zh.swf`
3. 用 Flash Player 打开（仓库内 `dist/FlashPlayer.exe` 可用于本地测试）。

### 操作提示

| 按键 | 功能 |
|---|---|
| `F2` | 字幕总开关 |
| `F3` | 打开 / 关闭字幕设置面板 |
| `↑ ↓` | 面板中选择设置行 |
| `← →` / `回车` | 修改当前设置 |

## 开发者

从仓库克隆后，按[环境准备](/guide/environment)装好依赖，再按[重新构建](/guide/build)生成产物。

```powershell
git clone <repo>
cd road-of-the-dead-hanhua
uv sync
pwsh -File pipeline/tools/fetch-tools.ps1 -Proxy http://127.0.0.1:7897
```

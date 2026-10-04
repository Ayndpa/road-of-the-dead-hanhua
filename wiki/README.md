# Road of the Dead中文Wiki

基于 **VitePress** 的中文 Wiki：一方面整理《Road of the Dead》（Road of the Dead）一代与二代的
**游戏资料**（剧情、玩法、武器、敌人、车辆、地点、成就），另一方面记录本项目的
**汉化工程文档**。

## 本地开发

```powershell
cd wiki
bun install
bun run docs:dev        # http://localhost:5173
```

## 构建静态站点

```powershell
bun run docs:build      # 输出到 wiki/.vitepress/dist
bun run docs:preview    # 本地预览构建产物
```

> 本 Wiki 使用 [bun](https://bun.sh/) 作为包管理器；若已安装 Node.js，
> `npm install && npm run docs:build` 亦可。

## 目录结构

```
wiki/
  index.md                 首页
  game/                    游戏资料（主板块）
    index.md               系列概览
    rotd1.md               Road of the Dead
    rotd2.md               Road of the Dead 2
    gameplay.md            玩法与操作
    modes.md               游戏模式
    weapons.md             武器
    enemies.md             敌人
    vehicles.md            车辆与升级
    world.md               角色与地点
    achievements.md        成就
  fandom/                  Saga of the Dead 资料库（Fandom 中文翻译）
    index.md               资料库首页（分组索引）
    *.md                   111 篇翻译页
    en/                    英文原文（构建时排除）
  fandom-img/              资料库图片（本地化，构建时打包）
  tools/                   抓取 / 生成脚本
    scrape_fandom.py       抓取 Fandom 全站为 Markdown
    build_glossary.py      从游戏内汉化生成术语表
    build_fandom_index.py  生成资料库首页与侧边栏
    localize_fandom_images.py  下载图片并改写链接
    fix_cjk_emphasis.py    修复 CJK 旁无法闭合的 Markdown 强调
  guide/                   汉化项目
    introduction.md        汉化项目介绍
    features.md            成果一览
    download.md            下载与安装
    environment.md         环境准备
    build.md               重新构建
    translations.md        翻译平台工作流
  dev/                     汉化实现原理
    architecture.md        总体架构
    subtitles.md           语音字幕
    stream.md              开场流式音轨
    ui-text.md             UI 烘焙文本
    fonts.md               一代字体适配
    menu-labels.md         主菜单矢量重绘
    runtime.md             运行时文本
    alignment.md           文本对齐
    rotd2.md               二代多字体适配
  reference/               汉化参考
    pipeline.md            pipeline 目录
    csv.md                 翻译文件格式
    tools.md               分析调试工具
    faq.md                 常见问题
  public/logo.jpeg         站点横幅 Logo
  .vitepress/              配置与主题
```

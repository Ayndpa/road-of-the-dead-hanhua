import { defineConfig } from 'vitepress'
import fandomSidebar from './fandom-sidebar.mts'

const gameSidebar = [
  {
    text: '游戏资料',
    items: [
      { text: '系列概览', link: '/game/' },
      { text: 'Road of the Dead', link: '/game/rotd1' },
      { text: 'Road of the Dead 2', link: '/game/rotd2' },
      { text: '玩法与操作', link: '/game/gameplay' },
      { text: '游戏模式', link: '/game/modes' },
      { text: '武器', link: '/game/weapons' },
      { text: '敌人', link: '/game/enemies' },
      { text: '车辆与升级', link: '/game/vehicles' },
      { text: '角色与地点', link: '/game/world' },
      { text: '成就', link: '/game/achievements' }
    ]
  }
]

const hanhuaSidebar = [
  {
    text: '汉化项目',
    items: [
      { text: '项目介绍', link: '/guide/introduction' },
      { text: '成果一览', link: '/guide/features' },
      { text: '下载与安装', link: '/guide/download' },
      { text: '环境准备', link: '/guide/environment' },
      { text: '重新构建', link: '/guide/build' },
      { text: '翻译平台工作流', link: '/guide/translations' }
    ]
  },
  {
    text: '实现原理',
    items: [
      { text: '总体架构', link: '/dev/architecture' },
      { text: '语音字幕', link: '/dev/subtitles' },
      { text: '开场流式音轨', link: '/dev/stream' },
      { text: 'UI 烘焙文本', link: '/dev/ui-text' },
      { text: '一代字体适配', link: '/dev/fonts' },
      { text: '主菜单矢量重绘', link: '/dev/menu-labels' },
      { text: '运行时文本', link: '/dev/runtime' },
      { text: '文本对齐', link: '/dev/alignment' },
      { text: '二代多字体适配', link: '/dev/rotd2' }
    ]
  },
  {
    text: '参考',
    items: [
      { text: 'pipeline 目录', link: '/reference/pipeline' },
      { text: '翻译文件格式', link: '/reference/csv' },
      { text: '分析调试工具', link: '/reference/tools' },
      { text: '常见问题', link: '/reference/faq' }
    ]
  }
]

export default defineConfig({
  lang: 'zh-CN',
  title: 'Road of the Dead中文Wiki',
  description:
    '中文版的 Road of the Dead（死亡之路）系列百科：剧情、玩法、武器、敌人、车辆与成就，以及 Fandom 资料库中文翻译与项目汉化文档。',
  base: '/',
  cleanUrls: true,
  lastUpdated: true,
  srcExclude: ['README.md', 'fandom/en/**', 'fandom/_*.md'],
  markdown: {
    lineNumbers: true,
    theme: { light: 'github-light', dark: 'github-dark' }
  },
  head: [
    ['meta', { name: 'theme-color', content: '#cb0000' }],
    ['meta', { name: 'og:title', content: 'Road of the Dead中文Wiki' }],
    [
      'meta',
      {
        name: 'og:description',
        content: '中文版的Road of the Dead系列百科与汉化文档'
      }
    ]
  ],
  themeConfig: {
    logo: '/logo.jpeg',
    outline: { level: [2, 3], label: '本页目录' },
    nav: [
      { text: '首页', link: '/' },
      {
        text: '游戏',
        activeMatch: '^/game/',
        items: [
          { text: '系列概览', link: '/game/' },
          { text: 'Road of the Dead', link: '/game/rotd1' },
          { text: 'Road of the Dead 2', link: '/game/rotd2' },
          { text: '玩法与操作', link: '/game/gameplay' },
          { text: '游戏模式', link: '/game/modes' },
          { text: '武器', link: '/game/weapons' },
          { text: '敌人', link: '/game/enemies' },
          { text: '车辆与升级', link: '/game/vehicles' },
          { text: '角色与地点', link: '/game/world' },
          { text: '成就', link: '/game/achievements' }
        ]
      },
      {
        text: '资料库',
        activeMatch: '^/fandom/',
        items: [
          { text: '资料库首页', link: '/fandom/' },
          { text: '游戏作品', link: '/fandom/saga-of-the-dead-wiki' },
          { text: '角色', link: '/fandom/characters' },
          { text: '敌人', link: '/fandom/common-undead' },
          { text: '武器', link: '/fandom/weapons' },
          { text: '载具', link: '/fandom/humvee' },
          { text: '地点', link: '/fandom/evans-city' }
        ]
      },
      {
        text: '汉化',
        activeMatch: '^/(guide|dev|reference)/',
        items: [
          { text: '汉化项目', link: '/guide/introduction' },
          { text: '重新构建', link: '/guide/build' },
          { text: '翻译平台', link: '/guide/translations' },
          { text: '实现原理', link: '/dev/architecture' },
          { text: 'pipeline 参考', link: '/reference/pipeline' }
        ]
      }
    ],
    sidebar: {
      '/game/': gameSidebar,
      '/fandom/': fandomSidebar,
      '/guide/': hanhuaSidebar,
      '/dev/': hanhuaSidebar,
      '/reference/': hanhuaSidebar
    },
    search: { provider: 'local' },
    docFooter: { prev: '上一篇', next: '下一篇' },
    darkModeSwitchLabel: '外观',
    lightModeSwitchTitle: '切换到浅色模式',
    darkModeSwitchTitle: '切换到深色模式',
    sidebarMenuLabel: '目录',
    returnToTopLabel: '回到顶部',
    lastUpdated: {
      text: '最后更新',
      formatOptions: { dateStyle: 'short', timeStyle: 'short' }
    },
    footer: {
      message: '本站为玩家整理的中文资料站；游戏版权归 Evil-Dog / SickDeathFiend 所有，资料库译自 Saga of The Dead Wiki（CC BY-SA）。',
      copyright: 'Road of the Dead中文Wiki'
    }
  }
})

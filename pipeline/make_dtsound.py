"""Generate a patched DTSound.as that adds an in-game subtitle overlay.

The overlay is driven from DTSound.Play(): every sound played by the game's
sound system is looked up by its embedded class name (e.g. ``SND_CheckPoint1Post``)
in a subtitle table, and the Chinese line is shown at the bottom of the stage
for the duration of the clip.

Subtitles are injected as a pure-ASCII AS3 string literal (``\\uXXXX`` escapes)
so the source never depends on the compiler's text encoding.

The Chinese lines come from the ParaTranz export (``data/paratranz/voice.csv`` and
``stream.csv``); clip durations / speech segments still come from the ASR cache
(``data/asr_all.json``) and the streamed-audio timing from
``data/stream_timing.json``.

Usage:
    python pipeline/make_dtsound.py --out patch/DTSound.as
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = ROOT / "work" / "scripts" / "scripts" / "DTSound.as"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from translations import pairs  # noqa: E402

REC_SEP = "\x02"   # between entries
FLD_SEP = "\x01"   # between class name and text
SUB_SEP = "\x03"   # between timed sub-lines


def swf_stage_size(path: Path) -> tuple[float, float]:
    """Native (design) stage size of a SWF, in pixels.

    This is the coordinate space the movie is authored in (e.g. 600x400 for
    Road of the Dead). It is *not* the player window size: after the player
    window is resized/maximised, ``Stage.stageWidth/Height`` can report the
    scaled window instead, which is why overlays anchored to those values end
    up off-screen. Layout uses this fixed design size instead.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return 0.0, 0.0
    if len(data) < 9:
        return 0.0, 0.0
    sig = data[:3]
    body = data[8:]
    if sig == b"CWS":
        import zlib
        try:
            body = zlib.decompress(body)
        except zlib.error:
            return 0.0, 0.0
    elif sig == b"ZWS":
        import lzma
        try:
            body = lzma.decompress(body)
        except lzma.LZMAError:
            return 0.0, 0.0
    elif sig != b"FWS":
        return 0.0, 0.0

    bit = 0

    def read_bits(n: int) -> int:
        nonlocal bit
        v = 0
        for _ in range(n):
            byte = body[bit >> 3]
            v = (v << 1) | ((byte >> (7 - (bit & 7))) & 1)
            bit += 1
        return v

    def read_sbits(n: int) -> int:
        v = read_bits(n)
        if v & (1 << (n - 1)):
            v -= 1 << n
        return v

    nbits = read_bits(5)
    if nbits == 0:
        return 0.0, 0.0
    xmin = read_sbits(nbits)
    xmax = read_sbits(nbits)
    ymin = read_sbits(nbits)
    ymax = read_sbits(nbits)
    return (xmax - xmin) / 20.0, (ymax - ymin) / 20.0

IMPORT_BLOCK = """package
{
   import flash.display.MovieClip;
   import flash.display.Shape;
   import flash.display.Sprite;
   import flash.display.Stage;
   import flash.events.Event;
   import flash.events.KeyboardEvent;
   import flash.events.MouseEvent;
   import flash.events.SampleDataEvent;
   import flash.events.TimerEvent;
   import flash.filters.GlowFilter;
   import flash.media.Sound;
   import flash.media.SoundChannel;
   import flash.media.SoundTransform;
   import flash.net.SharedObject;
   import flash.text.Font;
   import flash.text.TextField;
   import flash.text.TextFormat;
   import flash.text.TextFormatAlign;
   import flash.utils.ByteArray;
   import flash.utils.Timer;
   import flash.utils.getQualifiedClassName;
   import flash.utils.getTimer;
   
   internal class DTSound extends BasicObject
   {
"""

STATIC_VARS = """
      internal static var m_SubTable:Object = null;
      
      internal static var m_SubContainer:Sprite = null;
      
      internal static var m_SubBg:Shape = null;
      
      internal static var m_SubText:TextField = null;
      
      internal static var m_SubFormat:TextFormat = null;
      
      internal static var m_SubTimer:Timer = null;
      
      internal static var m_SubStage:Stage = null;
      
      internal static var m_bSubReady:Boolean = false;
      
      internal static var m_bSubOn:Boolean = true;
      
      internal static var m_ToastText:TextField = null;
      
      internal static var m_ToastBox:Sprite = null;
      
      internal static var m_bToastReady:Boolean = false;
      
      internal static var m_ToastTimer:Timer = null;
      
      internal static var m_iTick:int = 0;
      
      internal static var m_DbgTimer:Timer = null;
      
      internal static var m_bDbgMode:Boolean = __DBG_MODE__;
      
      internal static var m_StreamSegs:Array = null;
      
      internal static var m_SubRoot:MovieClip = null;
      
      internal static var m_fFps:Number = 30;
      
      internal static var m_fStreamOffset:Number = __STREAM_OFFSET__;
      
      internal static var m_iStreamSeg:int = -2;
      
      internal static var m_TimedTable:Object = null;
      
      internal static var m_TimedClips:Object = null;
      
      internal static var m_Subs:Array = null;
      
      internal static var m_iSubCount:int = 0;
      
      internal static var m_fStageW:Number = -1;
      
      internal static var m_fStageH:Number = -1;
      
      internal static var m_fDesignW:Number = __DESIGN_W__;
      
      internal static var m_fDesignH:Number = __DESIGN_H__;
      
      internal static var m_iSubLang:int = 1;
      
      internal static var m_iSubSize:int = 1;
      
      internal static var m_bSubBg:Boolean = true;
      
      internal static var m_SubSO:SharedObject = null;
      
      internal static var m_SettingsRoot:Sprite = null;
      
      internal static var m_bSettingsOpen:Boolean = false;
      
      internal static var m_iSetSel:int = 0;
      
      internal static var m_SetRows:Array = null;
      
      internal static var m_SetFormat:TextFormat = null;
      
      internal static var m_SubSizes:Array = null;
"""

METHODS = r"""
      internal static function SubtitleDataExpr() : String
      {
         return __SUBTITLE_CHUNKS__;
      }
      
      internal static function StreamDataExpr() : String
      {
         return __STREAM_CHUNKS__;
      }
      
      internal static function TimedDataExpr() : String
      {
         return __TIMED_CHUNKS__;
      }
      
      internal static function GetTimedTable() : Object
      {
         var szData:String = null;
         var recs:Array = null;
         var i:int = 0;
         var j:int = 0;
         var rec:String = null;
         var subs:Array = null;
         var ln:String = null;
         var p1:int = 0;
         var p2:int = 0;
         var p3:int = 0;
         var cls:String = null;
         var f:Array = null;
         var arr:Array = null;
         if(m_TimedTable != null)
         {
            return m_TimedTable;
         }
         m_TimedTable = new Object();
         szData = TimedDataExpr();
         if(szData != null && szData.length > 0)
         {
            recs = szData.split(String.fromCharCode(2));
            for(i = 0; i < recs.length; i++)
            {
               rec = String(recs[i]);
               p1 = rec.indexOf(String.fromCharCode(1));
               if(p1 <= 0)
               {
                  continue;
               }
               cls = rec.substring(0,p1);
               subs = rec.substring(p1 + 1).split(String.fromCharCode(3));
               arr = new Array();
               for(j = 0; j < subs.length; j++)
               {
                  ln = String(subs[j]);
                  p1 = ln.indexOf(String.fromCharCode(1));
                  p2 = p1 >= 0 ? ln.indexOf(String.fromCharCode(1),p1 + 1) : -1;
                  p3 = p2 >= 0 ? ln.indexOf(String.fromCharCode(1),p2 + 1) : -1;
                  if(p3 > p2)
                  {
                     f = new Array();
                     f.push(Number(ln.substring(0,p1)));
                     f.push(Number(ln.substring(p1 + 1,p2)));
                     f.push(ln.substring(p2 + 1,p3));
                     f.push(ln.substring(p3 + 1));
                     arr.push(f);
                  }
               }
               if(arr.length > 0)
               {
                  m_TimedTable[cls] = arr;
               }
            }
         }
         return m_TimedTable;
      }
      
      internal static function HasTimedClips() : Boolean
      {
         var key:String = null;
         if(m_TimedClips == null)
         {
            return false;
         }
         for(key in m_TimedClips)
         {
            return true;
         }
         return false;
      }
      
      internal static function UpdateTimedClips() : *
      {
         var keys:Array = null;
         var i:int = 0;
         var key:String = null;
         var rec:Array = null;
         var data:Array = null;
         var el:Number = 0;
         var j:int = -1;
         var k:int = 0;
         var seg:Array = null;
         if(m_TimedClips == null)
         {
            return;
         }
         keys = new Array();
         for(key in m_TimedClips)
         {
            keys.push(key);
         }
         for(i = 0; i < keys.length; i++)
         {
            key = String(keys[i]);
            rec = m_TimedClips[key] as Array;
            if(rec == null)
            {
               continue;
            }
            data = rec[0] as Array;
            el = (getTimer() - int(rec[1])) / 1000;
            if(el > Number(data[data.length - 1][1]) + 0.8)
            {
               delete m_TimedClips[key];
               continue;
            }
            j = -1;
            for(k = 0; k < data.length; k++)
            {
               if(el >= Number(data[k][0]) - 0.15 && el <= Number(data[k][1]) + 0.25)
               {
                  j = k;
                  break;
               }
            }
            if(j == int(rec[2]))
            {
               continue;
            }
            rec[2] = j;
            if(j < 0)
            {
               continue;
            }
            seg = data[j] as Array;
            ShowSubtitleOn(key,String(seg[2]),String(seg[3]),(Number(seg[1]) - Number(seg[0]) + 0.45) * 1000);
         }
      }
      
      internal static function GetStreamSegments() : Array
      {
         var szData:String = null;
         var lines:Array = null;
         var segs:Array = null;
         var f:Array = null;
         var i:int = 0;
         var ln:String = null;
         var p1:int = 0;
         var p2:int = 0;
         var p3:int = 0;
         if(m_StreamSegs != null)
         {
            return m_StreamSegs;
         }
         m_StreamSegs = new Array();
         szData = StreamDataExpr();
         if(szData != null && szData.length > 0)
         {
            lines = szData.split(String.fromCharCode(2));
            for(i = 0; i < lines.length; i++)
            {
               ln = String(lines[i]);
               p1 = ln.indexOf(String.fromCharCode(1));
               if(p1 > 0)
               {
                  p2 = ln.indexOf(String.fromCharCode(1),p1 + 1);
                  p3 = p2 >= 0 ? ln.indexOf(String.fromCharCode(1),p2 + 1) : -1;
                  if(p3 > p2)
                  {
                     f = new Array();
                     f.push(Number(ln.substring(0,p1)));
                     f.push(Number(ln.substring(p1 + 1,p2)));
                     f.push(ln.substring(p2 + 1,p3));
                     f.push(ln.substring(p3 + 1));
                     m_StreamSegs.push(f);
                  }
               }
            }
         }
         return m_StreamSegs;
      }
      
      internal static function FindStreamSegment(t:Number) : int
      {
         var i:int = 0;
         var segs:Array = null;
         segs = GetStreamSegments();
         for(i = 0; i < segs.length; i++)
         {
            if(t >= Number(segs[i][0]) - 0.2 && t <= Number(segs[i][1]) + 0.35)
            {
               return i;
            }
         }
         return -1;
      }
      
      internal static function OnStreamFrame(e:Event) : *
      {
         var t:Number = 0;
         var i:int = 0;
         m_iTick++;
         TickSubtitles();
         CheckStageResize();
         if(m_SubRoot == null)
         {
            return;
         }
         if(!m_bSubOn)
         {
            return;
         }
         UpdateTimedClips();
         if(HasTimedClips())
         {
            return;
         }
         t = (m_SubRoot.currentFrame - 1) / m_fFps - m_fStreamOffset;
         if(t < 0)
         {
            t = 0;
         }
         i = FindStreamSegment(t);
         if(i == m_iStreamSeg)
         {
            return;
         }
         m_iStreamSeg = i;
         if(i < 0)
         {
            return;
         }
         ShowSubtitleOn("_stream",String(GetStreamSegments()[i][2]),String(GetStreamSegments()[i][3]),(Number(GetStreamSegments()[i][1]) - Number(GetStreamSegments()[i][0]) + 0.5) * 1000);
      }
      
      internal static function GetSubtitleTable() : Object
      {
         var szData:String = null;
         var lines:Array = null;
         var i:int = 0;
         var ln:String = null;
         var p:int = 0;
         var p2:int = 0;
         var zh:String = null;
         var en:String = null;
         if(m_SubTable != null)
         {
            return m_SubTable;
         }
         m_SubTable = new Object();
         szData = SubtitleDataExpr();
         if(szData != null && szData.length > 0)
         {
            lines = szData.split(String.fromCharCode(2));
            for(i = 0; i < lines.length; i++)
            {
               ln = String(lines[i]);
               p = ln.indexOf(String.fromCharCode(1));
               if(p > 0)
               {
                  p2 = ln.indexOf(String.fromCharCode(1),p + 1);
                  if(p2 > p)
                  {
                     zh = ln.substring(p + 1,p2);
                     en = ln.substring(p2 + 1);
                  }
                  else
                  {
                     zh = ln.substring(p + 1);
                     en = "";
                  }
                  m_SubTable[ln.substring(0,p)] = [zh,en];
               }
            }
         }
         return m_SubTable;
      }
      
      internal static function PickSubtitleFont() : String
      {
         var wanted:Array = ["Microsoft YaHei","\u5fae\u8f6f\u96c5\u9ed1","Microsoft YaHei UI","SimHei","\u9ed1\u4f53","SimSun","\u5b8b\u4f53","Noto Sans SC","Source Han Sans SC","\u601d\u6e90\u9ed1\u4f53","PingFang SC","Droid Sans Fallback"];
         var avail:Object = new Object();
         var list:Array = null;
         var i:int = 0;
         var szName:String = null;
         list = Font.enumerateFonts(false);
         for(i = 0; i < list.length; i++)
         {
            szName = String(Font(list[i]).fontName);
            avail[szName] = true;
         }
         list = Font.enumerateFonts(true);
         for(i = 0; i < list.length; i++)
         {
            szName = String(Font(list[i]).fontName);
            avail[szName] = true;
         }
         for(i = 0; i < wanted.length; i++)
         {
            if(avail[String(wanted[i])] == true)
            {
               return String(wanted[i]);
            }
         }
         return "Microsoft YaHei";
      }
      
      internal static function InitSubtitles() : Boolean
      {
         var rootMC:MovieClip = null;
         var st:Stage = null;
         if(m_bSubReady)
         {
            return true;
         }
         if(BasicGame.Instance == null)
         {
            return false;
         }
         rootMC = BasicGame.Instance.m_RootMC;
         if(rootMC == null || rootMC.stage == null)
         {
            return false;
         }
         st = rootMC.stage;
         m_SubStage = st;
         m_fStageW = st.stageWidth;
         m_fStageH = st.stageHeight;
         m_SubRoot = rootMC;
         if(m_fDesignW <= 0 || m_fDesignH <= 0)
         {
            m_fDesignW = rootMC.loaderInfo.width;
            m_fDesignH = rootMC.loaderInfo.height;
         }
         if(m_fDesignW <= 0)
         {
            m_fDesignW = st.stageWidth;
         }
         if(m_fDesignH <= 0)
         {
            m_fDesignH = st.stageHeight;
         }
         m_fFps = st.frameRate;
         if(m_fFps < 1)
         {
            m_fFps = 30;
         }
         LoadSubSettings();
         m_SubContainer = new Sprite();
         m_SubContainer.mouseEnabled = false;
         m_SubBg = new Shape();
         m_SubContainer.addChild(m_SubBg);
         m_SubText = new TextField();
         m_SubText.mouseEnabled = false;
         m_SubText.selectable = false;
         m_SubText.multiline = true;
         m_SubText.wordWrap = true;
         m_SubText.embedFonts = false;
         m_SubText.antiAliasType = "advanced";
         m_SubText.width = m_fDesignW - 56;
         m_SubText.height = 150;
         m_SubContainer.addChild(m_SubText);
         m_SubFormat = new TextFormat();
         m_SubFormat.font = PickSubtitleFont();
         m_SubFormat.size = SubSizePx();
         m_SubFormat.bold = true;
         m_SubFormat.color = 16777215;
         m_SubFormat.align = TextFormatAlign.CENTER;
         m_SubFormat.leading = 2;
         m_SubText.defaultTextFormat = m_SubFormat;
         m_SubText.filters = [new GlowFilter(0,1,4,4,8,3,false,false)];
         m_SubTimer = new Timer(2000,1);
         m_SubTimer.addEventListener(TimerEvent.TIMER,OnSubtitleTimer);
         st.addChild(m_SubContainer);
         st.addEventListener(KeyboardEvent.KEY_DOWN,OnSubtitleKeyDown);
         st.addEventListener(Event.ENTER_FRAME,OnStreamFrame);
         st.addEventListener(Event.RESIZE,OnSubtitleResize);
         if(m_bDbgMode)
         {
            m_DbgTimer = new Timer(1000,0);
            m_DbgTimer.addEventListener(TimerEvent.TIMER,DbgTick);
            m_DbgTimer.start();
            Toast("SUBTITLE DEBUG MODE");
         }
         m_SubContainer.visible = false;
         m_bSubReady = true;
         return true;
      }
      
      internal static function HideSubtitle() : *
      {
         if(m_Subs != null)
         {
            m_Subs = new Array();
         }
         m_iSubCount = 0;
         if(m_SubContainer != null)
         {
            m_SubContainer.visible = false;
         }
      }
      
      internal static function ShowSubtitle(szZh:String, szEn:String, fDurationMs:Number) : *
      {
         ShowSubtitleOn("_voice",szZh,szEn,fDurationMs);
      }
      
      internal static function ShowSubtitleOn(szSlot:String, szZh:String, szEn:String, fDurationMs:Number) : *
      {
         var i:int = 0;
         var o:Object = null;
         if(!m_bSubOn)
         {
            return;
         }
         if(szZh == null)
         {
            szZh = "";
         }
         if(szEn == null)
         {
            szEn = "";
         }
         if(szZh == "" && szEn == "")
         {
            return;
         }
         if(!InitSubtitles())
         {
            return;
         }
         if(fDurationMs < 900)
         {
            fDurationMs = 900;
         }
         if(fDurationMs > 600000)
         {
            fDurationMs = 600000;
         }
         if(m_Subs == null)
         {
            m_Subs = new Array();
         }
         for(i = m_Subs.length - 1; i >= 0; i--)
         {
            if(String(m_Subs[i].slot) == szSlot)
            {
               m_Subs.splice(i,1);
            }
         }
         o = new Object();
         o.slot = szSlot;
         o.zh = szZh;
         o.en = szEn;
         o.end = getTimer() + fDurationMs;
         m_Subs.push(o);
         while(m_Subs.length > 3)
         {
            m_Subs.shift();
         }
         RenderSubtitles();
      }
      
      internal static function SubtitleDisplay(o:Object) : String
      {
         var zh:String = o.zh == null ? "" : String(o.zh);
         var en:String = o.en == null ? "" : String(o.en);
         if(m_iSubLang == 0)
         {
            return en != "" ? en : zh;
         }
         if(m_iSubLang == 1)
         {
            return zh != "" ? zh : en;
         }
         if(en == "")
         {
            return zh;
         }
         if(zh == "" || zh == en)
         {
            return en;
         }
         return en + String.fromCharCode(10) + zh;
      }
      
      internal static function PreviewSubtitleText() : String
      {
         var o:Object = new Object();
         o.zh = "这是字幕预览效果。";
         o.en = "This is a subtitle preview.";
         return SubtitleDisplay(o);
      }
      
      internal static function TickSubtitles() : *
      {
         var i:int = 0;
         var now:int = 0;
         if(m_Subs == null || m_Subs.length == 0)
         {
            return;
         }
         now = getTimer();
         for(i = m_Subs.length - 1; i >= 0; i--)
         {
            if(now >= int(m_Subs[i].end))
            {
               m_Subs.splice(i,1);
            }
         }
         if(m_Subs.length != m_iSubCount)
         {
            RenderSubtitles();
         }
      }
      
      internal static function RenderSubtitles() : *
      {
         var now:int = 0;
         var i:int = 0;
         var parts:Array = null;
         var fTextH:Number = 0;
         var fMaxH:Number = 0;
         var bgW:Number = 0;
         var bgX:Number = 0;
         var bgMax:Number = 0;
         var joined:String = null;
         if(m_SubContainer == null)
         {
            return;
         }
         if(m_Subs == null)
         {
            m_Subs = new Array();
         }
         now = getTimer();
         for(i = m_Subs.length - 1; i >= 0; i--)
         {
            if(now >= int(m_Subs[i].end))
            {
               m_Subs.splice(i,1);
            }
         }
         m_iSubCount = m_Subs.length;
         parts = new Array();
         for(i = 0; i < m_Subs.length; i++)
         {
            parts.push(SubtitleDisplay(m_Subs[i]));
         }
         if(m_bSettingsOpen)
         {
            parts.push(PreviewSubtitleText());
         }
         if(parts.length == 0)
         {
            m_SubContainer.visible = false;
            return;
         }
         joined = parts.join(String.fromCharCode(10));
         m_SubFormat.size = SubSizePx();
         m_SubText.defaultTextFormat = m_SubFormat;
         m_SubText.text = joined;
         m_SubText.setTextFormat(m_SubFormat);
         m_SubText.width = m_fDesignW - 56;
         m_SubText.height = 500;
         fTextH = m_SubText.textHeight + 16;
         fMaxH = m_fDesignH - 40;
         if(fMaxH > 320)
         {
            fMaxH = 320;
         }
         if(fMaxH < 80)
         {
            fMaxH = 80;
         }
         if(fTextH > fMaxH)
         {
            fTextH = fMaxH;
         }
         m_SubContainer.y = m_fDesignH - fTextH - 24;
         m_SubText.x = 28;
         m_SubText.y = 6;
         m_SubBg.graphics.clear();
         if(m_bSubBg)
         {
            bgW = m_SubText.textWidth + 36;
            if(bgW < 140)
            {
               bgW = 140;
            }
            bgMax = m_fDesignW - 36;
            if(bgW > bgMax)
            {
               bgW = bgMax;
            }
            bgX = (m_fDesignW - bgW) / 2;
            m_SubBg.graphics.beginFill(0,0.45);
            m_SubBg.graphics.drawRoundRect(bgX,0,bgW,fTextH,8,8);
            m_SubBg.graphics.endFill();
         }
         m_SubContainer.visible = true;
      }
      
      internal static function SubSizePx() : int
      {
         if(m_SubSizes == null)
         {
            m_SubSizes = [13,17,22];
         }
         if(m_iSubSize < 0)
         {
            m_iSubSize = 0;
         }
         if(m_iSubSize > m_SubSizes.length - 1)
         {
            m_iSubSize = m_SubSizes.length - 1;
         }
         return int(m_SubSizes[m_iSubSize]);
      }
      
      internal static function SubLangName(i:int) : String
      {
         if(i == 0)
         {
            return "英文 English";
         }
         if(i == 1)
         {
            return "中文 Chinese";
         }
         return "中英双语 Bilingual";
      }
      
      internal static function SubSizeName(i:int) : String
      {
         if(i == 0)
         {
            return "小 Small";
         }
         if(i == 1)
         {
            return "中 Medium";
         }
         return "大 Large";
      }
      
      internal static function LoadSubSettings() : *
      {
         try
         {
            m_SubSO = SharedObject.getLocal("rotd_zh_subtitles","/");
            if(m_SubSO != null && m_SubSO.data != null)
            {
               if(m_SubSO.data.lang != undefined)
               {
                  m_iSubLang = int(m_SubSO.data.lang);
               }
               if(m_SubSO.data.size != undefined)
               {
                  m_iSubSize = int(m_SubSO.data.size);
               }
               if(m_SubSO.data.bg != undefined)
               {
                  m_bSubBg = Boolean(m_SubSO.data.bg);
               }
            }
         }
         catch(e:Error)
         {
            m_SubSO = null;
         }
         if(m_iSubLang < 0 || m_iSubLang > 2)
         {
            m_iSubLang = 1;
         }
         if(m_iSubSize < 0 || m_iSubSize > 2)
         {
            m_iSubSize = 1;
         }
      }
      
      internal static function SaveSubSettings() : *
      {
         if(m_SubSO == null)
         {
            return;
         }
         try
         {
            m_SubSO.data.lang = m_iSubLang;
            m_SubSO.data.size = m_iSubSize;
            m_SubSO.data.bg = m_bSubBg;
            m_SubSO.flush();
         }
         catch(e:Error)
         {
         }
      }
      
      internal static function ApplySubSettings() : *
      {
         if(m_iSubLang < 0 || m_iSubLang > 2)
         {
            m_iSubLang = 1;
         }
         if(m_iSubSize < 0 || m_iSubSize > 2)
         {
            m_iSubSize = 1;
         }
         if(m_SubFormat != null)
         {
            m_SubFormat.size = SubSizePx();
         }
         SaveSubSettings();
         if(m_SubContainer != null)
         {
            RenderSubtitles();
         }
         if(m_bSettingsOpen)
         {
            RenderSettings();
         }
      }
      
      internal static function CycleSetting(i:int, dir:int) : *
      {
         if(i == 0)
         {
            m_iSubLang = (m_iSubLang + dir + 3) % 3;
         }
         else if(i == 1)
         {
            m_iSubSize = (m_iSubSize + dir + 3) % 3;
         }
         else
         {
            m_bSubBg = !m_bSubBg;
         }
         ApplySubSettings();
      }
      
      internal static function ToggleSettings() : *
      {
         m_bSettingsOpen = !m_bSettingsOpen;
         EnsureSettings();
         if(m_SettingsRoot == null)
         {
            return;
         }
         m_SettingsRoot.visible = m_bSettingsOpen;
         if(m_bSettingsOpen)
         {
            m_iSetSel = 0;
            RenderSettings();
         }
         if(m_SubContainer != null)
         {
            RenderSubtitles();
         }
      }
      
      internal static function EnsureSettings() : *
      {
         var i:int = 0;
         var tf:TextField = null;
         var title:TextField = null;
         var hint:TextField = null;
         if(m_SettingsRoot != null)
         {
            return;
         }
         if(m_SubStage == null)
         {
            return;
         }
         m_SettingsRoot = new Sprite();
         m_SettingsRoot.mouseEnabled = true;
         m_SetFormat = new TextFormat();
         m_SetFormat.font = PickSubtitleFont();
         m_SetFormat.color = 16777215;
         m_SetFormat.align = TextFormatAlign.CENTER;
         m_SetFormat.bold = true;
         m_SetRows = new Array();
         title = new TextField();
         title.mouseEnabled = false;
         title.selectable = false;
         title.name = "title";
         title.embedFonts = false;
         m_SettingsRoot.addChild(title);
         for(i = 0; i < 3; i++)
         {
            tf = new TextField();
            tf.mouseEnabled = false;
            tf.selectable = false;
            tf.embedFonts = false;
            m_SettingsRoot.addChild(tf);
            m_SetRows.push(tf);
         }
         hint = new TextField();
         hint.mouseEnabled = false;
         hint.selectable = false;
         hint.name = "hint";
         hint.embedFonts = false;
         m_SettingsRoot.addChild(hint);
         m_SettingsRoot.addEventListener(MouseEvent.CLICK,OnSettingsClick);
         m_SubStage.addChild(m_SettingsRoot);
         m_SettingsRoot.visible = false;
      }
      
      internal static function RenderSettings() : *
      {
         var pw:Number = 0;
         var ph:Number = 0;
         var px:Number = 0;
         var py:Number = 0;
         var rowH:Number = 0;
         var y0:Number = 0;
         var i:int = 0;
         var title:TextField = null;
         var hint:TextField = null;
         var tf:TextField = null;
         var labels:Array = null;
         var vals:Array = null;
         if(m_SettingsRoot == null || m_SetRows == null)
         {
            return;
         }
         pw = m_fDesignW - 80;
         if(pw > 440)
         {
            pw = 440;
         }
         ph = 210;
         px = (m_fDesignW - pw) / 2;
         py = (m_fDesignH - ph) / 2 - 55;
         if(py < 10)
         {
            py = 10;
         }
         m_SettingsRoot.graphics.clear();
         m_SettingsRoot.graphics.beginFill(0,0.82);
         m_SettingsRoot.graphics.lineStyle(2,16777215,0.55);
         m_SettingsRoot.graphics.drawRoundRect(px,py,pw,ph,10,10);
         m_SettingsRoot.graphics.endFill();
         title = TextField(m_SettingsRoot.getChildByName("title"));
         m_SetFormat.size = 18;
         m_SetFormat.color = 16777215;
         title.width = pw;
         title.height = 26;
         title.x = px;
         title.y = py + 12;
         title.text = "字幕设置 SUBTITLE SETTINGS";
         title.setTextFormat(m_SetFormat);
         rowH = 38;
         y0 = py + 50;
         labels = ["显示模式 Type","字号 Size","背景 Background"];
         vals = [SubLangName(m_iSubLang),SubSizeName(m_iSubSize),m_bSubBg ? "显示 On" : "隐藏 Off"];
         for(i = 0; i < 3; i++)
         {
            tf = TextField(m_SetRows[i]);
            m_SetFormat.size = 16;
            m_SetFormat.color = i == m_iSetSel ? 16776960 : 16777215;
            tf.width = pw;
            tf.height = rowH - 4;
            tf.x = px;
            tf.y = y0 + i * rowH;
            tf.text = labels[i] + "：" + String(vals[i]);
            tf.setTextFormat(m_SetFormat);
         }
         hint = TextField(m_SettingsRoot.getChildByName("hint"));
         m_SetFormat.size = 12;
         m_SetFormat.color = 13421772;
         hint.width = pw;
         hint.height = 20;
         hint.x = px;
         hint.y = py + ph - 26;
         hint.text = "F3 / 点击行 切换   ↑↓ 选择   ←→ 修改   F2 字幕开关";
         hint.setTextFormat(m_SetFormat);
      }
      
      internal static function OnSettingsClick(e:MouseEvent) : *
      {
         var ph:Number = 0;
         var py:Number = 0;
         var rowH:Number = 0;
         var y0:Number = 0;
         var idx:int = 0;
         if(m_SettingsRoot == null)
         {
            return;
         }
         ph = 210;
         py = (m_fDesignH - ph) / 2 - 55;
         if(py < 10)
         {
            py = 10;
         }
         rowH = 38;
         y0 = py + 50;
         idx = int(Math.floor((e.localY - y0) / rowH));
         if(idx < 0 || idx > 2)
         {
            return;
         }
         m_iSetSel = idx;
         CycleSetting(idx,1);
      }
      
      internal static function ReflowSubtitles() : *
      {
         var bg:Shape = null;
         var st:Stage = null;
         if(m_SubStage == null)
         {
            return;
         }
         st = m_SubStage;
         m_fStageW = st.stageWidth;
         m_fStageH = st.stageHeight;
         if(m_SubContainer != null)
         {
            RenderSubtitles();
         }
         if(m_bSettingsOpen)
         {
            RenderSettings();
         }
         if(m_bToastReady && m_ToastBox != null)
         {
            if(m_ToastBox.numChildren > 0 && m_ToastBox.getChildAt(0) is Shape)
            {
               bg = Shape(m_ToastBox.getChildAt(0));
               bg.graphics.clear();
               bg.graphics.beginFill(0,0.75);
               bg.graphics.drawRect(0,0,m_fDesignW,26);
               bg.graphics.endFill();
            }
            if(m_ToastText != null)
            {
               m_ToastText.width = m_fDesignW;
            }
         }
      }
      
      internal static function CheckStageResize() : Boolean
      {
         if(m_SubStage == null)
         {
            return false;
         }
         if(m_SubStage.stageWidth == m_fStageW && m_SubStage.stageHeight == m_fStageH)
         {
            return false;
         }
         ReflowSubtitles();
         return true;
      }
      
      internal static function OnSubtitleResize(e:Event) : *
      {
         ReflowSubtitles();
      }
      
      internal static function Toast(szText:String) : *
      {
         var rootMC:MovieClip = null;
         var fmt:TextFormat = null;
         var bg:Shape = null;
         if(!m_bToastReady)
         {
            if(BasicGame.Instance == null)
            {
               return;
            }
            rootMC = BasicGame.Instance.m_RootMC;
            if(rootMC == null || rootMC.stage == null)
            {
               return;
            }
            m_ToastBox = new Sprite();
            m_ToastBox.mouseEnabled = false;
            bg = new Shape();
            bg.graphics.beginFill(0,0.75);
            bg.graphics.drawRect(0,0,m_fDesignW,26);
            bg.graphics.endFill();
            m_ToastBox.addChild(bg);
            m_ToastText = new TextField();
            m_ToastText.mouseEnabled = false;
            m_ToastText.selectable = false;
            m_ToastText.width = m_fDesignW;
            m_ToastText.height = 22;
            m_ToastText.y = 2;
            fmt = new TextFormat();
            fmt.font = "_sans";
            fmt.size = 14;
            fmt.bold = true;
            fmt.color = 16776960;
            fmt.align = TextFormatAlign.CENTER;
            m_ToastText.defaultTextFormat = fmt;
            m_ToastBox.addChild(m_ToastText);
            m_ToastTimer = new Timer(2500,1);
            m_ToastTimer.addEventListener(TimerEvent.TIMER,OnToastTimer);
            rootMC.stage.addChild(m_ToastBox);
            m_bToastReady = true;
         }
         m_ToastText.text = szText;
         m_ToastText.setTextFormat(m_ToastText.defaultTextFormat);
         m_ToastBox.visible = true;
         if(m_ToastTimer != null)
         {
            m_ToastTimer.stop();
            m_ToastTimer.start();
         }
      }
      
      internal static function DbgTick(e:TimerEvent) : *
      {
         var t:Number = 0;
         var frm:int = -1;
         var n:int = 0;
         if(m_SubRoot != null)
         {
            frm = m_SubRoot.currentFrame;
            t = (frm - 1) / m_fFps - m_fStreamOffset;
         }
         n = GetStreamSegments().length;
         ShowSubtitleOn("_dbg","DBG f=" + frm + " t=" + Math.round(t * 10) / 10 + " seg=" + m_iStreamSeg + " n=" + n + " tick=" + m_iTick + " on=" + (m_bSubOn ? 1 : 0) + " subs=" + m_iSubCount,"",1000);
      }
      
      internal static function OnToastTimer(e:TimerEvent) : *
      {
         if(m_ToastBox != null)
         {
            m_ToastBox.visible = false;
         }
      }
      
      internal static function OnSubtitleTimer(e:TimerEvent) : *
      {
         HideSubtitle();
      }
      
      internal static function OnSubtitleKeyDown(e:KeyboardEvent) : *
      {
         if(e.keyCode == 113)
         {
            m_bSubOn = !m_bSubOn;
            if(!m_bSubOn)
            {
               HideSubtitle();
            }
            if(m_bSubOn)
            {
               Toast("字幕 SUBTITLES: ON");
            }
            else
            {
               Toast("字幕 SUBTITLES: OFF");
            }
            if(m_bDbgMode)
            {
               ShowSubtitleOn("_dbg","F2 OK, subtitles " + (m_bSubOn ? "ON" : "OFF"),"",1500);
            }
            return;
         }
         if(e.keyCode == 114)
         {
            ToggleSettings();
            return;
         }
         if(m_bSettingsOpen)
         {
            if(e.keyCode == 27)
            {
               ToggleSettings();
            }
            else if(e.keyCode == 38)
            {
               m_iSetSel = m_iSetSel > 0 ? m_iSetSel - 1 : 2;
               RenderSettings();
            }
            else if(e.keyCode == 40)
            {
               m_iSetSel = m_iSetSel < 2 ? m_iSetSel + 1 : 0;
               RenderSettings();
            }
            else if(e.keyCode == 37)
            {
               CycleSetting(m_iSetSel,-1);
            }
            else if(e.keyCode == 39 || e.keyCode == 13)
            {
               CycleSetting(m_iSetSel,1);
            }
         }
      }
      
      internal static function SubtitleOnPlay(sound:DTSound) : *
      {
         var szName:String = null;
         var zh:String = null;
         var en:String = null;
         var fDur:Number = 0;
         var table:Object = null;
         var timed:Object = null;
         var row:Array = null;
         InitSubtitles();
         if(sound == null || sound.m_SoundClass == null)
         {
            return;
         }
         table = GetSubtitleTable();
         szName = getQualifiedClassName(sound.m_SoundClass);
         row = table[szName] as Array;
         if(row == null)
         {
            return;
         }
         zh = String(row[0]);
         en = row.length > 1 ? String(row[1]) : "";
         timed = GetTimedTable();
         if(timed[szName] != null && m_bSubOn)
         {
            if(m_TimedClips == null)
            {
               m_TimedClips = new Object();
            }
            m_TimedClips[szName] = [timed[szName] as Array,getTimer(),-1];
            UpdateTimedClips();
            return;
         }
         if(sound.m_Sound != null)
         {
            fDur = sound.m_Sound.length;
         }
         if(fDur <= 0)
         {
            fDur = 2500;
         }
         ShowSubtitleOn(szName,zh,en,fDur);
      }
"""

PLAY_ANCHORS = [
    # ROTD2: DTSound uses explicit `this.` on the fields
    "         this.m_SoundChannel = this.m_Sound.play(fPosition * 1000,bLooping ? 99999999 : 0);\n"
    "         this.m_bLooping = bLooping;\n",
    # ROTD1
    "         m_SoundChannel = m_Sound.play(fPosition * 1000,bLooping ? 99999999 : 0);\n"
    "         m_bLooping = bLooping;\n",
]


def as3_literal(text: str) -> str:
    """Encode a Python string as a pure-ASCII AS3 string literal body."""
    out = []
    for ch in text:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif 32 <= o < 127:
            out.append(ch)
        else:
            out.append("\\u%04x" % o)
    return "".join(out)


def build_chunks(entries: list[tuple[str, str, str]], chunk_chars: int = 200) -> str:
    """Build a '+'-joined list of AS3 string literals, splitting on char count.

    Each record is ``class \\x01 zh \\x01 en``; both languages are carried so the
    player can switch between English, Chinese and bilingual display at runtime.
    """
    pieces: list[str] = []
    cur: list[str] = []
    n = 0
    for cls, zh, en in entries:
        piece = as3_literal(cls + FLD_SEP + zh + FLD_SEP + en + REC_SEP)
        cur.append(piece)
        n += len(piece)
        if n >= chunk_chars:
            pieces.append('"' + "".join(cur) + '"')
            cur = []
            n = 0
    if cur:
        pieces.append('"' + "".join(cur) + '"')
    if not pieces:
        return '""'
    return " + ".join(pieces)


def build_stream_chunks(entries: list[dict], chunk_chars: int = 200) -> str:
    """Build AS3 literals for streamed-audio segments: start|end|zh|en records."""
    pieces: list[str] = []
    cur: list[str] = []
    n = 0
    for e in entries:
        rec = "%.3f%s%.3f%s%s%s%s%s" % (
            float(e["start"]),
            FLD_SEP,
            float(e["end"]),
            FLD_SEP,
            e["zh"],
            FLD_SEP,
            e["en"],
            REC_SEP,
        )
        piece = as3_literal(rec)
        cur.append(piece)
        n += len(piece)
        if n >= chunk_chars:
            pieces.append('"' + "".join(cur) + '"')
            cur = []
            n = 0
    if cur:
        pieces.append('"' + "".join(cur) + '"')
    if not pieces:
        return '""'
    return " + ".join(pieces)


SENT_RE = re.compile(r"[^。！？!?…]*[。！？!?…]+|[^。！？!?…]+$")
# Sentence-ending run in English originals. A naive ``[^.!?]*[.!?]`` split also
# cuts inside decimals ("64.7") and abbreviations ("U.S."), inventing extra
# English sentences. Those make English look "finer" than Chinese, so the
# Chinese line gets pinned to an earlier slot and lags the voice.
EN_END_RE = re.compile(r"[.!?…]+")

_EN_ABBREV = frozenset({
    "mr", "mrs", "ms", "dr", "st", "vs", "etc", "jr", "sr", "no", "gen",
    "sgt", "capt", "lt", "col", "cmdr", "adm", "rev", "hon", "prof",
    "inc", "ltd", "co", "u.s", "u.k", "a.m", "p.m",
})


def split_sentences(text: str) -> list[str]:
    return [p.strip() for p in SENT_RE.findall(text) if p.strip()]


def split_sentences_en(text: str) -> list[str]:
    """Split English dialogue on real sentence ends only.

    A ``.`` is not a sentence end when it sits between digits (``64.7``) or
    closes a known abbreviation (``U.S.``), and the punctuation run has to be
    followed by whitespace or the end of the text.
    """
    text = text.strip()
    if not text:
        return []
    out: list[str] = []
    start = 0
    for m in EN_END_RE.finditer(text):
        i, end = m.start(), m.end()
        if (text[i] == "." and 0 < i < len(text) - 1
                and text[i - 1].isdigit() and text[i + 1].isdigit()):
            continue
        word = re.search(r"([A-Za-z](?:[A-Za-z.]*[A-Za-z])?)\.$", text[:i + 1])
        if word and word.group(1).lower() in _EN_ABBREV:
            continue
        nxt = text[end:end + 1]
        if nxt and not nxt.isspace():
            continue
        out.append(text[start:end].strip())
        start = end
    rest = text[start:].strip()
    if rest:
        out.append(rest)
    return [p for p in out if p]


# Tokens that survive translation (numbers, callsigns, place names). They anchor
# a Chinese sentence to the English sentence it translates even when the two
# languages break sentences differently.
_ANCHOR_RE = re.compile(r"[A-Za-z]{2,}|\d+(?:\.\d+)?")


def _anchor_tokens(text: str) -> list[str]:
    return _ANCHOR_RE.findall(text.lower())


def _shared_anchors(zh_sents: list[str], en_sents: list[str],
                    max_occ: int = 4) -> list[tuple[int, int]]:
    """Monotonic ``(zh_index, en_index)`` pairs from shared Latin/number tokens.

    Occurrences of a token are paired in order (a translation may drop or repeat
    one), reduced to the furthest English sentence per Chinese sentence, then
    kept only while they stay strictly increasing. Tokens repeated more than
    ``max_occ`` times are ignored as noise.
    """
    ztok: dict[str, list[int]] = {}
    for i, s in enumerate(zh_sents):
        for t in _anchor_tokens(s):
            ztok.setdefault(t, []).append(i)
    etok: dict[str, list[int]] = {}
    for j, s in enumerate(en_sents):
        for t in _anchor_tokens(s):
            etok.setdefault(t, []).append(j)
    # One anchor per Chinese sentence: the furthest English sentence its shared
    # tokens point at. A Chinese sentence that merges two English ones shares a
    # token with each; anchoring it to the later one keeps the following lines
    # from sliding back. Deterministic (tokens sorted) so the build is stable.
    cand: dict[int, int] = {}
    for t in sorted(set(ztok) & set(etok)):
        zl, el = ztok[t], etok[t]
        if len(zl) > max_occ or len(el) > max_occ:
            continue
        for zi, ej in zip(zl, el):
            if zi not in cand or ej > cand[zi]:
                cand[zi] = ej
    anchors: list[tuple[int, int]] = []
    last_e = -1
    for zi in sorted(cand):
        if cand[zi] <= last_e:
            continue
        anchors.append((zi, cand[zi]))
        last_e = cand[zi]
    return anchors


def _sentence_alignment(zh_sents: list[str],
                        en_sents: list[str]) -> list[int] | None:
    """Align each Chinese sentence to one English sentence (monotonic).

    Chinese and English rarely break sentences at the same place. Aligning one
    English sentence per Chinese sentence (and vice versa, via gaps) keeps a
    sentence the translator merged or split with its English counterpart instead
    of pushing every later Chinese line one slot down -- the "收到" pinned to the
    previous line bug. Sentences sharing a token (number, callsign, place name)
    are pinned to each other, so those anchors are never crossed. Returns the
    English index per Chinese sentence, or ``None`` when it cannot be aligned.
    """
    m, n = len(zh_sents), len(en_sents)
    if not m or not n:
        return None
    zl = [max(1, len(s)) for s in zh_sents]
    el = [max(1, len(s)) for s in en_sents]
    az, ae = sum(zl) / m, sum(el) / n
    pinned = dict(_shared_anchors(zh_sents, en_sents))

    def exclam(s: str) -> int:
        return s.count("!") + s.count("?") + s.count("！") + s.count("？")

    def cost(i: int, j: int) -> float:
        c = abs(zl[i] / az - el[j] / ae)
        if exclam(zh_sents[i]) != exclam(en_sents[j]):
            c += 0.4
        c -= 0.5 * len(set(_anchor_tokens(zh_sents[i]))
                       & set(_anchor_tokens(en_sents[j])))
        return c

    gap = 0.9
    inf = float("inf")
    dist = [[inf] * (n + 1) for _ in range(m + 1)]
    back: list[list[tuple[int, int] | None]] = [[None] * (n + 1)
                                                for _ in range(m + 1)]
    dist[0][0] = 0
    for i in range(m + 1):
        for j in range(n + 1):
            cur = dist[i][j]
            if cur == inf:
                continue
            forced = pinned.get(i)
            if i < m and j < n and (forced is None or forced == j):
                c = cur + cost(i, j)
                if c < dist[i + 1][j + 1]:
                    dist[i + 1][j + 1] = c
                    back[i + 1][j + 1] = (i, j)
            if j < n and (forced is None or forced > j):
                c = cur + gap
                if c < dist[i][j + 1]:
                    dist[i][j + 1] = c
                    back[i][j + 1] = (i, j)
            if i < m and forced is None:
                c = cur + gap
                if c < dist[i + 1][j]:
                    dist[i + 1][j] = c
                    back[i + 1][j] = (i, j)
    if dist[m][n] == inf or back[m][n] is None:
        return None
    match: list[int | None] = [None] * m
    i, j = m, n
    while i > 0 or j > 0:
        back_ptr = back[i][j]
        if back_ptr is None:
            break
        pi, pj = back_ptr
        if i > pi and j > pj:
            match[pi] = pj
        i, j = pi, pj
    for r in range(m):
        if match[r] is None:
            prev = next((match[k] for k in range(r - 1, -1, -1)
                         if match[k] is not None), None)
            nxt = next((match[k] for k in range(r + 1, m)
                        if match[k] is not None), None)
            match[r] = prev if prev is not None else (nxt if nxt is not None else 0)
    return [int(x) for x in match]


def _aligned_zh_segments(zh_sents: list[str], en_sents: list[str],
                         seg_of_en: list[int], nsegs: int) -> list[int] | None:
    """ASR segment index per Chinese sentence, or ``None`` if unalignable."""
    if nsegs <= 0 or not zh_sents or not en_sents:
        return None
    match = _sentence_alignment(zh_sents, en_sents)
    if match is None:
        return None
    return [max(0, min(nsegs - 1, seg_of_en[e])) for e in match]


def _proportional_zh_segments(zh_sents: list[str], en_sents: list[str],
                              seg_of_en: list[int], nsegs: int) -> list[int]:
    """Spread Chinese across segments in proportion to their English sentences."""
    m = len(zh_sents)
    if nsegs <= 0 or m == 0:
        return [0] * m
    if not en_sents:
        return [min(nsegs - 1, r * nsegs // m) for r in range(m)]
    import bisect
    en_count = [0] * nsegs
    for e in seg_of_en:
        en_count[e] += 1
    cum = [0]
    for c in en_count:
        cum.append(cum[-1] + c)
    out = []
    for r in range(m):
        target = (r + 0.5) * len(en_sents) / m
        out.append(max(0, min(nsegs - 1, bisect.bisect_right(cum, target) - 1)))
    return out


def _zh_distribution_score(zh_seg: list[int], zh_sents: list[str],
                           en_chars: list[int], tot_zh: int, tot_en: int,
                           anchors: list[tuple[int, int]],
                           seg_of_en: list[int]) -> float:
    """How evenly a Chinese assignment tracks the English content per segment.

    Adds a penalty for a line that carries only one language and for a sentence
    whose shared-token anchor declares a different segment.
    """
    nsegs = len(en_chars)
    zh_chars = [0] * nsegs
    for r, s in enumerate(zh_sents):
        zh_chars[zh_seg[r]] += max(1, len(s))
    score = 0.0
    for i in range(nsegs):
        if en_chars[i] and not zh_chars[i]:
            score += 1.0
        elif zh_chars[i] and not en_chars[i]:
            score += 0.5
        score += abs(zh_chars[i] / tot_zh - en_chars[i] / tot_en)
    for zi, ej in anchors:
        if zh_seg[zi] != seg_of_en[ej]:
            score += 5.0
    return score


def _best_zh_segments(zh_sents: list[str], en_sents: list[str],
                      seg_of_en: list[int], nsegs: int) -> list[int]:
    """Pick the Chinese->segment spread that best matches the English.

    Tries the proportional spread and the word/length sentence alignment, then
    keeps whichever distributes Chinese content across segments most like the
    English (and honours shared-token anchors). This avoids both the drift of a
    pure proportion and the over-eager gaps of a pure length alignment.
    """
    m = len(zh_sents)
    if nsegs <= 0 or m == 0:
        return [0] * m
    prop = _proportional_zh_segments(zh_sents, en_sents, seg_of_en, nsegs)
    candidates = [prop]
    aligned = _aligned_zh_segments(zh_sents, en_sents, seg_of_en, nsegs)
    if aligned is not None and aligned != prop:
        candidates.append(aligned)
    tot_zh = sum(max(1, len(s)) for s in zh_sents) or 1
    en_chars = [0] * nsegs
    for j, e in enumerate(seg_of_en):
        en_chars[e] += max(1, len(en_sents[j]))
    tot_en = sum(en_chars) or 1
    anchors = _shared_anchors(zh_sents, en_sents)
    best = prop
    best_score = None
    for cand in candidates:
        score = _zh_distribution_score(cand, zh_sents, en_chars, tot_zh, tot_en,
                                       anchors, seg_of_en)
        if best_score is None or score < best_score - 1e-9:
            best_score, best = score, cand
    return best


def _linear_times(
    sents: list[str], total: int, dur: float
) -> list[tuple[float, float, str]]:
    """Distribute lines evenly across the whole clip (fallback)."""
    acc = 0.0
    timed: list[tuple[float, float, str]] = []
    for s in sents:
        st = acc / total * dur
        acc += len(s)
        en = acc / total * dur
        timed.append((round(st, 2), round(en, 2), s))
    return timed


_WORD_RE = None


def _words(text: str) -> list[str]:
    import re as _re
    global _WORD_RE
    if _WORD_RE is None:
        _WORD_RE = _re.compile(r"[A-Za-z0-9']+")
    return _WORD_RE.findall(text.lower())


def _asr_aligned_times(
    sents: list[str], segments: list[dict], dur: float
) -> list[tuple[float, float, str]] | None:
    """Time each English sentence from the ASR segments it actually overlaps.

    The ASR segments are the real speech windows; align the (cleaned) English
    sentences to the segment text word-by-word so a sentence gets the window of
    the words it contains instead of a proportional guess.  Returns ``None`` when
    alignment is too weak to trust.
    """
    import difflib

    ref: list[tuple[str, int]] = []       # (word, segment index)
    for si, seg in enumerate(segments):
        for w in _words(str(seg.get("text") or "")):
            ref.append((w, si))
    drv: list[tuple[str, int]] = []       # (word, sentence index)
    for ti, s in enumerate(sents):
        for w in _words(s):
            drv.append((w, ti))
    if not ref or not drv:
        return None

    seg_idx: dict[int, list[int]] = {}
    for i, (_w, si) in enumerate(ref):
        seg_idx.setdefault(si, []).append(i)

    def ref_time(ri: int) -> float:
        _w, si = ref[ri]
        idxs = seg_idx[si]
        k = idxs.index(ri)
        a = float(segments[si].get("start") or 0.0)
        b = float(segments[si].get("end") or 0.0)
        frac = 0.0 if len(idxs) <= 1 else k / (len(idxs) - 1)
        return a + frac * (b - a)

    sm = difflib.SequenceMatcher(a=[w for w, _ in drv], b=[w for w, _ in ref],
                                 autojunk=False)
    blk = {i: -1 for i in range(len(drv))}
    matched = 0
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            blk[a + k] = b + k
            matched += 1
    if matched < max(4, len(drv) // 3):
        return None

    bounds: list[tuple[float | None, float | None]] = []
    for ti in range(len(sents)):
        pts = [ref_time(blk[i]) for i, (_w, t) in enumerate(drv)
               if t == ti and blk[i] >= 0]
        bounds.append((min(pts), max(pts)) if pts else (None, None))

    times: list[tuple[float, float]] = []
    for i, (st, en) in enumerate(bounds):
        if st is None:
            # interpolate from the nearest known sentences
            prev = next((j for j in range(i - 1, -1, -1) if bounds[j][1] is not None), None)
            nxt = next((j for j in range(i + 1, len(bounds)) if bounds[j][0] is not None), None)
            if prev is None and nxt is None:
                return None
            if prev is None:
                st = max(0.0, float(bounds[nxt][0]) - 0.4 * (nxt - i))
            elif nxt is None:
                st = float(bounds[prev][1]) + 0.4 * (i - prev)
            else:
                a = float(bounds[prev][1]); b = float(bounds[nxt][0])
                st = a + (b - a) * (i - prev) / (nxt - prev)
            en = st + 0.4
        times.append((float(st), float(en)))

    out: list[tuple[float, float, str]] = []
    prev_end = 0.0
    for s, (st, en) in zip(sents, times):
        if st < prev_end:
            st = prev_end
        if en <= st:
            en = st + 0.2
        if dur > 0 and en > dur:
            en = dur
        prev_end = en
        out.append((round(st, 2), round(en, 2), s))
    return out


def _warped_times(
    sents: list[str], total: int, segments: list[dict], dur: float
) -> list[tuple[float, float, str]]:
    """Distribute lines over the *spoken* parts of the clip.

    The ASR pass gives the real speech segments (start/end) of the English
    track. Allocating the Chinese text in proportion to each spoken segment's
    English length and stretching it across that segment's real time keeps the
    subtitles on the voice instead of spreading them evenly over the whole clip
    (which includes silence and made lines appear early / advance too fast).
    """
    lens = [max(1.0, float(len(str(s.get("text") or "").strip()))) for s in segments]
    total_len = sum(lens)
    bounds: list[tuple[float, float, float, float]] = []
    acc = 0.0
    for i, seg in enumerate(segments):
        f0 = acc / total_len
        acc += lens[i]
        f1 = acc / total_len
        a = max(0.0, float(seg.get("start") or 0.0))
        b = float(seg.get("end") or 0.0)
        if b <= a:
            b = a + 0.01
        bounds.append((f0, f1, a, b))

    def t_of(f: float) -> float:
        if f <= 0.0:
            return bounds[0][2]
        if f >= 1.0:
            return bounds[-1][3]
        for f0, f1, a, b in bounds:
            if f <= f1:
                r = 0.0 if f1 <= f0 else (f - f0) / (f1 - f0)
                return a + r * (b - a)
        return bounds[-1][3]

    timed: list[tuple[float, float, str]] = []
    cum = 0.0
    prev_end = 0.0
    for s in sents:
        st = t_of(cum / total)
        cum += len(s)
        en = t_of(cum / total)
        if st < prev_end:
            st = prev_end
        if en <= st:
            en = st + 0.2
        if dur > 0 and en > dur:
            en = dur
        prev_end = en
        timed.append((round(st, 2), round(en, 2), s))
    return timed


def _sentence_segments(sents: list[str], segments: list[dict]) -> list[int] | None:
    """Map each sentence to the ASR segment its words best match.

    Word-level alignment against the ASR transcripts; returns ``None`` when the
    overlap is too weak to trust (caller then falls back to proportional order).
    """
    import difflib
    from collections import Counter

    ref: list[tuple[str, int]] = []       # (word, segment index)
    for si, seg in enumerate(segments):
        for w in _words(str(seg.get("text") or "")):
            ref.append((w, si))
    drv: list[tuple[str, int]] = []       # (word, sentence index)
    for ti, s in enumerate(sents):
        for w in _words(s):
            drv.append((w, ti))
    if not ref or not drv:
        return None
    sm = difflib.SequenceMatcher(a=[w for w, _ in drv], b=[w for w, _ in ref],
                                 autojunk=False)
    votes: dict[int, list[int]] = {}
    matched = 0
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            votes.setdefault(drv[a + k][1], []).append(ref[b + k][1])
            matched += 1
    if matched < max(3, len(drv) // 4):
        return None
    res: list[int | None] = [None] * len(sents)
    for ti, sis in votes.items():
        res[ti] = Counter(sis).most_common(1)[0][0]
    last = 0
    for ti in range(len(sents)):
        if res[ti] is None:
            nxt = next((j for j in range(ti + 1, len(sents)) if res[j] is not None), None)
            res[ti] = res[nxt] if nxt is not None else last
        if res[ti] < last:
            res[ti] = last
        last = res[ti]
    return [int(x) for x in res]


def _merged_segment_groups(sents: list[str],
                           segments: list[dict]) -> list[tuple[int, int]]:
    """Inclusive ``(lo, hi)`` ASR-segment ranges to show as one subtitle line.

    The recognizer splits speech at pauses, so one CSV sentence often covers
    several ASR windows. Showing one line per window repeats the sentence on the
    later window; instead those windows are merged into one line spanning them.
    Returns every segment exactly once, in order.
    """
    n = len(segments)
    if not sents or n == 0:
        return [(i, i) for i in range(n)]
    import difflib

    ref: list[tuple[str, int]] = []       # (word, segment index)
    for si, seg in enumerate(segments):
        for w in _words(str(seg.get("text") or "")):
            ref.append((w, si))
    drv: list[tuple[str, int]] = []       # (word, sentence index)
    for ti, s in enumerate(sents):
        for w in _words(s):
            drv.append((w, ti))
    if not ref or not drv:
        return [(i, i) for i in range(n)]
    sm = difflib.SequenceMatcher(a=[w for w, _ in drv], b=[w for w, _ in ref],
                                 autojunk=False)
    per_sent: dict[int, dict[int, int]] = {}
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            counts = per_sent.setdefault(drv[a + k][1], {})
            si = ref[b + k][1]
            counts[si] = counts.get(si, 0) + 1
    hi_of = [-1] * n
    for counts in per_sent.values():
        # A sentence has to land with at least two words in two windows before
        # we merge them; a lone coincidental word must not join distant lines.
        hit = [si for si, c in counts.items() if c >= 2]
        if len(hit) >= 2:
            lo, hi = min(hit), max(hit)
            for x in range(lo, hi):
                hi_of[x] = max(hi_of[x], hi)
    groups: list[tuple[int, int]] = []
    i = 0
    while i < n:
        end = i
        j = i
        while j <= end:
            end = max(end, hi_of[j])
            j += 1
        groups.append((i, end))
        i = end + 1
    return groups


def build_timed_chunks(
    subs: dict[str, str],
    durations: dict[str, float],
    originals: dict[str, str] | None = None,
    min_secs: float = 7.5,
    segments: dict[str, list[dict]] | None = None,
) -> tuple[list[tuple[str, list[tuple[float, float, str, str]]]], str]:
    """Build one subtitle line per ASR segment, timed by the ASR windows.

    Each line carries the Chinese and English text that falls inside that ASR
    segment, so bilingual display stays aligned.  Neighbouring segments that the
    recognizer split out of a single CSV sentence are shown as one line spanning
    both windows.  The chat/stream/subtitle timing is exactly the ASR segment
    start/end -- there is no per-character inference, which drifts whenever a
    sentence is spoken faster or slower than its text length suggests.  Clips
    without ASR data collapse to a single line.
    """
    segments = segments or {}
    originals = originals or {}
    entries: list[tuple[str, list[tuple[float, float, str, str]]]] = []
    for cls, text in sorted(subs.items()):
        if not text:
            continue
        zh_sents = split_sentences(text)
        if not zh_sents:
            continue
        dur = float(durations.get(cls, 0.0))
        en = str(originals.get(cls) or "").strip()
        en_sents = split_sentences_en(en) if en else []
        segs = [
            s
            for s in (segments.get(cls) or [])
            if float(s.get("end") or 0.0) > float(s.get("start") or 0.0)
        ]
        pairs: list[tuple[float, float, str, str]] = []
        if segs:
            # One subtitle line per ASR segment, using the segment's own start/end
            # verbatim -- exactly like a video subtitle track.  English sentences
            # are attached to the segment whose transcribed words they match;
            # Chinese follows sentence order.  No character-count interpolation is
            # used, so a fast or slow delivery no longer drifts out of sync.
            seg_of_en = _sentence_segments(en_sents, segs)
            if seg_of_en is None:
                seg_of_en = [
                    min(len(segs) - 1, i * len(segs) // len(en_sents))
                    for i in range(len(en_sents))
                ] if en_sents else []
            en_groups: list[list[str]] = [[] for _ in segs]
            for i, s in enumerate(en_sents):
                en_groups[seg_of_en[i]].append(s)
            zh_groups: list[list[str]] = [[] for _ in segs]
            # Spread Chinese across the segments so its content lands on the
            # same lines as its English counterpart. This keeps a merged/split
            # sentence with its own line instead of shifting every later line
            # (the "收到" pinned to the previous line bug).
            zh_seg = _best_zh_segments(zh_sents, en_sents, seg_of_en, len(segs))
            for r, s in enumerate(zh_sents):
                zh_groups[zh_seg[r]].append(s)
            for lo, hi in _merged_segment_groups(en_sents, segs):
                st = round(float(segs[lo].get("start") or 0.0), 2)
                en_t = round(float(segs[hi].get("end") or 0.0), 2)
                zt = "".join("".join(zh_groups[k]) for k in range(lo, hi + 1))
                et = " ".join(" ".join(en_groups[k])
                              for k in range(lo, hi + 1)).strip()
                if not et and not en:
                    # No translation source at all: fall back to the recognizer's
                    # own English so the line is not silently dropped.
                    et = " ".join(str(segs[k].get("text") or "").strip()
                                  for k in range(lo, hi + 1)).strip()
                if not zt and not et:
                    continue
                pairs.append((st, en_t, zt, et))
        else:
            # No ASR segment for this clip: fall back to a single line spanning it.
            pairs.append((0.0, round(dur, 2) if dur > 0 else 0.0,
                          "".join(zh_sents), " ".join(en_sents)))
        if pairs:
            entries.append((cls, pairs))

    pieces: list[str] = []
    cur: list[str] = []
    n = 0
    for cls, timed in entries:
        rec = cls + FLD_SEP + SUB_SEP.join(
            "%.2f%s%.2f%s%s%s%s" % (st, FLD_SEP, en, FLD_SEP, tx, FLD_SEP, tx_en)
            for st, en, tx, tx_en in timed
        ) + REC_SEP
        piece = as3_literal(rec)
        cur.append(piece)
        n += len(piece)
        if n >= 200:
            pieces.append('"' + "".join(cur) + '"')
            cur, n = [], 0
    if cur:
        pieces.append('"' + "".join(cur) + '"')
    return entries, (" + ".join(pieces) if pieces else '""')


def generate(original, out, durations=None, stream_timing=None, swf=None,
             min_split_secs: float = 7.5, debug: bool = False,
             stream_offset: float = 1.58) -> Path:
    subs = pairs("voice")            # {cls: (english, chinese)}
    stream_subs = pairs("stream")    # {stream_NN: (english, chinese)}
    items = sorted((k, zh, en) for k, (en, zh) in subs.items() if zh)
    chunks = build_chunks(items)
    print(f"voice subtitle entries: {len(items)}; ", end="")

    durations_map: dict[str, float] = {}
    segments: dict[str, list[dict]] = {}
    if durations and Path(durations).exists():
        for v in json.loads(Path(durations).read_text(encoding="utf-8")).values():
            cls = str(v.get("cls"))
            durations_map[cls] = float(v.get("duration") or 0.0)
            segs = v.get("segments")
            if segs:
                segments[cls] = segs
    timed, timed_chunks = build_timed_chunks(
        {k: zh for k, (_en, zh) in subs.items()},
        durations_map,
        {k: en for k, (en, _zh) in subs.items()},
        min_split_secs,
        segments,
    )
    print(f"{len(timed)} timed clips; ", end="")

    stream: list[dict] = []
    if stream_timing and Path(stream_timing).exists():
        timing = json.loads(Path(stream_timing).read_text(encoding="utf-8"))
        for i, seg in enumerate(timing):
            pair = stream_subs.get(f"stream_{i:02d}")
            if pair:
                en, zh = pair
                stream.append({"start": seg["start"], "end": seg["end"],
                               "zh": zh, "en": en})
    stream_chunks = build_stream_chunks(stream) if stream else '""'
    print(f"{len(stream)} stream entries")

    src = Path(original).read_text(encoding="utf-8")

    # 1. swap import block + class declaration
    head = "   internal class DTSound extends BasicObject\n   {\n"
    head_end = src.index(head) + len(head)
    src = IMPORT_BLOCK + STATIC_VARS + src[head_end:]

    # 2. hook Play()
    for anchor in PLAY_ANCHORS:
        if anchor in src:
            src = src.replace(anchor, anchor + "         SubtitleOnPlay(this);\n", 1)
            break
    else:
        raise SystemExit("Play() anchor not found")

    # 3. append subtitle methods before the trailing braces
    tail = "   }\n}\n"
    idx = src.rindex(tail)
    methods = METHODS.replace("__SUBTITLE_CHUNKS__", chunks)
    methods = methods.replace("__STREAM_CHUNKS__", stream_chunks)
    methods = methods.replace("__TIMED_CHUNKS__", timed_chunks)
    src = src[:idx] + methods + src[idx:]

    design_w, design_h = swf_stage_size(Path(swf)) if swf else (0.0, 0.0)
    src = src.replace("__DESIGN_W__", f"{design_w:.1f}")
    src = src.replace("__DESIGN_H__", f"{design_h:.1f}")
    print(f"design stage size: {design_w:g}x{design_h:g}")

    src = src.replace("__DBG_MODE__", "true" if debug else "false")
    src = src.replace("__STREAM_OFFSET__", f"{stream_offset:.4f}")

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(src, encoding="utf-8")
    print(f"wrote {out_path} ({len(src)} chars)")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--durations", default=str(ROOT / "data" / "asr_all.json"),
                    help="asr_all.json for clip durations / speech segments")
    ap.add_argument("--stream-timing", default=str(ROOT / "data" / "stream_timing.json"),
                    help="opening streamed-audio segment start/end")
    ap.add_argument("--min-split-secs", type=float, default=7.5)
    ap.add_argument("--out", required=True)
    ap.add_argument("--original", default=str(ORIGINAL))
    ap.add_argument("--swf", default=str(ROOT / "dist" / "Road-Of-The-Dead.swf"),
                    help="original SWF, used to read the native design stage size")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--stream-offset", type=float, default=1.58,
                    help="seconds between timeline frame 1 and the stream's t=0")
    args = ap.parse_args()
    generate(args.original, args.out, args.durations, args.stream_timing,
             args.swf, args.min_split_secs, args.debug, args.stream_offset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

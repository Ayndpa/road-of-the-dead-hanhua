"""Generate a patched DTSound.as that adds an in-game subtitle overlay.

The overlay is driven from DTSound.Play(): every sound played by the game's
sound system is looked up by its embedded class name (e.g. ``SND_CheckPoint1Post``)
in a subtitle table, and the Chinese line is shown at the bottom of the stage
for the duration of the clip.

Subtitles are injected as a pure-ASCII AS3 string literal (``\\uXXXX`` escapes)
so the source never depends on the compiler's text encoding.

Usage:
    python pipeline/make_dtsound.py --subs work/subtitles.json --out patch/DTSound.as
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = ROOT / "work" / "scripts" / "scripts" / "DTSound.as"

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
   import flash.events.TimerEvent;
   import flash.filters.GlowFilter;
   import flash.media.Sound;
   import flash.media.SoundChannel;
   import flash.media.SoundTransform;
   import flash.text.Font;
   import flash.text.TextField;
   import flash.text.TextFormat;
   import flash.text.TextFormatAlign;
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
      
      internal static var m_fStreamOffset:Number = 1.58;
      
      internal static var m_iStreamSeg:int = -2;
      
      internal static var m_TimedTable:Object = null;
      
      internal static var m_TimedClip:Array = null;
      
      internal static var m_iTimedBase:int = 0;
      
      internal static var m_iTimedSeg:int = -1;
      
      internal static var m_Subs:Array = null;
      
      internal static var m_iSubCount:int = 0;
      
      internal static var m_fStageW:Number = -1;
      
      internal static var m_fStageH:Number = -1;
      
      internal static var m_fDesignW:Number = __DESIGN_W__;
      
      internal static var m_fDesignH:Number = __DESIGN_H__;
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
                  if(p2 > p1)
                  {
                     f = new Array();
                     f.push(Number(ln.substring(0,p1)));
                     f.push(Number(ln.substring(p1 + 1,p2)));
                     f.push(ln.substring(p2 + 1));
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
      
      internal static function UpdateTimedClip() : *
      {
         var el:Number = 0;
         var j:int = -1;
         var k:int = 0;
         var seg:Array = null;
         if(m_TimedClip == null)
         {
            return;
         }
         el = (getTimer() - m_iTimedBase) / 1000;
         for(k = 0; k < m_TimedClip.length; k++)
         {
            if(el >= Number(m_TimedClip[k][0]) - 0.15 && el <= Number(m_TimedClip[k][1]) + 0.25)
            {
               j = k;
               break;
            }
         }
         if(el > Number(m_TimedClip[m_TimedClip.length - 1][1]) + 0.8)
         {
            m_TimedClip = null;
            return;
         }
         if(j == m_iTimedSeg)
         {
            return;
         }
         m_iTimedSeg = j;
         if(j < 0)
         {
            return;
         }
         seg = m_TimedClip[j];
         ShowSubtitleOn("_clip",String(seg[2]),(Number(seg[1]) - Number(seg[0]) + 0.45) * 1000);
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
                  if(p2 > p1)
                  {
                     f = new Array();
                     f.push(Number(ln.substring(0,p1)));
                     f.push(Number(ln.substring(p1 + 1,p2)));
                     f.push(ln.substring(p2 + 1));
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
         UpdateTimedClip();
         if(m_TimedClip != null)
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
         ShowSubtitleOn("_stream",String(GetStreamSegments()[i][2]),(Number(GetStreamSegments()[i][1]) - Number(GetStreamSegments()[i][0]) + 0.5) * 1000);
      }
      
      internal static function GetSubtitleTable() : Object
      {
         var szData:String = null;
         var lines:Array = null;
         var i:int = 0;
         var ln:String = null;
         var p:int = 0;
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
                  m_SubTable[ln.substring(0,p)] = ln.substring(p + 1);
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
         m_SubFormat.size = 18;
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
      
      internal static function ShowSubtitle(szText:String, fDurationMs:Number) : *
      {
         ShowSubtitleOn("_voice",szText,fDurationMs);
      }
      
      internal static function ShowSubtitleOn(szSlot:String, szText:String, fDurationMs:Number) : *
      {
         var i:int = 0;
         var o:Object = null;
         if(!m_bSubOn)
         {
            return;
         }
         if(szText == null || szText == "")
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
         o.text = szText;
         o.end = getTimer() + fDurationMs;
         m_Subs.push(o);
         while(m_Subs.length > 3)
         {
            m_Subs.shift();
         }
         RenderSubtitles();
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
         if(m_iSubCount == 0)
         {
            m_SubContainer.visible = false;
            return;
         }
         parts = new Array();
         for(i = 0; i < m_Subs.length; i++)
         {
            parts.push(String(m_Subs[i].text));
         }
         joined = parts.join(String.fromCharCode(10));
         m_SubText.text = joined;
         m_SubText.setTextFormat(m_SubFormat);
         m_SubText.width = m_fDesignW - 56;
         m_SubText.height = 240;
         fTextH = m_SubText.textHeight + 12;
         if(fTextH > 150)
         {
            fTextH = 150;
         }
         m_SubContainer.y = m_fDesignH - fTextH - 24;
         m_SubText.x = 28;
         m_SubText.y = 6;
         m_SubBg.graphics.clear();
         m_SubBg.graphics.beginFill(0,0.45);
         m_SubBg.graphics.drawRoundRect(18,0,m_fDesignW - 36,fTextH,8,8);
         m_SubBg.graphics.endFill();
         m_SubContainer.visible = true;
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
         ShowSubtitleOn("_dbg","DBG f=" + frm + " t=" + Math.round(t * 10) / 10 + " seg=" + m_iStreamSeg + " n=" + n + " tick=" + m_iTick + " on=" + (m_bSubOn ? 1 : 0) + " subs=" + m_iSubCount,1000);
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
               ShowSubtitleOn("_dbg","F2 OK, subtitles " + (m_bSubOn ? "ON" : "OFF"),1500);
            }
         }
      }
      
      internal static function SubtitleOnPlay(sound:DTSound) : *
      {
         var szName:String = null;
         var szText:String = null;
         var fDur:Number = 0;
         var table:Object = null;
         var timed:Object = null;
         InitSubtitles();
         if(sound == null || sound.m_SoundClass == null)
         {
            return;
         }
         table = GetSubtitleTable();
         szName = getQualifiedClassName(sound.m_SoundClass);
         szText = table[szName];
         if(szText == null)
         {
            return;
         }
         timed = GetTimedTable();
         if(timed[szName] != null && m_bSubOn)
         {
            m_TimedClip = timed[szName] as Array;
            m_iTimedBase = getTimer();
            m_iTimedSeg = -1;
            UpdateTimedClip();
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
         ShowSubtitleOn(szName,String(szText),fDur);
      }
"""

PLAY_ANCHOR = """         m_SoundChannel = m_Sound.play(fPosition * 1000,bLooping ? 99999999 : 0);
         m_bLooping = bLooping;
"""
PLAY_REPLACEMENT = PLAY_ANCHOR + "         SubtitleOnPlay(this);\n"


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


def build_chunks(entries: list[tuple[str, str]], chunk_chars: int = 200) -> str:
    """Build a '+'-joined list of AS3 string literals, splitting on char count."""
    pieces: list[str] = []
    cur: list[str] = []
    n = 0
    for cls, text in entries:
        piece = as3_literal(cls + FLD_SEP + text + REC_SEP)
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
    """Build AS3 literals for streamed-audio segments: start|end|text records."""
    pieces: list[str] = []
    cur: list[str] = []
    n = 0
    for e in entries:
        rec = "%.3f%s%.3f%s%s%s" % (
            float(e["start"]),
            FLD_SEP,
            float(e["end"]),
            FLD_SEP,
            e["zh"],
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


def split_sentences(text: str) -> list[str]:
    return [p.strip() for p in SENT_RE.findall(text) if p.strip()]


def build_timed_chunks(
    subs: dict[str, str], durations: dict[str, float], min_secs: float = 7.5
) -> tuple[list[tuple[str, list[tuple[float, float, str]]]], str]:
    """Long lines become several timed sub-lines so they aren't one wall of text."""
    entries: list[tuple[str, list[tuple[float, float, str]]]] = []
    for cls, text in sorted(subs.items()):
        dur = float(durations.get(cls, 0.0))
        if not text or dur < min_secs:
            continue
        sents = split_sentences(text)
        if len(sents) < 2:
            continue
        total = sum(len(s) for s in sents) or 1
        acc = 0.0
        timed: list[tuple[float, float, str]] = []
        for s in sents:
            st = acc / total * dur
            acc += len(s)
            en = acc / total * dur
            timed.append((round(st, 2), round(en, 2), s))
        entries.append((cls, timed))

    pieces: list[str] = []
    cur: list[str] = []
    n = 0
    for cls, timed in entries:
        rec = cls + FLD_SEP + SUB_SEP.join(
            "%.2f%s%.2f%s%s" % (st, FLD_SEP, en, FLD_SEP, tx) for st, en, tx in timed
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subs", default=str(ROOT / "data" / "subtitles.json"))
    ap.add_argument("--stream-subs", default=str(ROOT / "data" / "stream_subs.json"))
    ap.add_argument("--durations", default=str(ROOT / "data" / "asr_all.json"),
                    help="asr_all.json for clip durations")
    ap.add_argument("--min-split-secs", type=float, default=7.5)
    ap.add_argument("--out", required=True)
    ap.add_argument("--original", default=str(ORIGINAL))
    ap.add_argument("--swf", default=str(ROOT / "dist" / "Road-Of-The-Dead.swf"),
                    help="original SWF, used to read the native design stage size")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    subs = json.loads(Path(args.subs).read_text(encoding="utf-8"))
    items = [(k, v) for k, v in subs.items() if v]
    items.sort()
    chunks = build_chunks(items)
    print(f"subtitle entries: {len(items)}; stream entries: ", end="")

    durations: dict[str, float] = {}
    if args.durations and Path(args.durations).exists():
        for v in json.loads(Path(args.durations).read_text(encoding="utf-8")).values():
            durations[str(v.get("cls"))] = float(v.get("duration") or 0.0)
    timed, timed_chunks = build_timed_chunks(subs, durations, args.min_split_secs)
    print(f"{len(timed)} timed clips; stream entries: ", end="")

    stream_chunks = '""'
    if args.stream_subs:
        stream = json.loads(Path(args.stream_subs).read_text(encoding="utf-8"))
        stream_chunks = build_stream_chunks(stream)
        print(len(stream))
    else:
        print(0)

    src = Path(args.original).read_text(encoding="utf-8")

    # 1. swap import block + class declaration
    head_end = src.index("   internal class DTSound extends BasicObject\n   {\n")
    head_end += len("   internal class DTSound extends BasicObject\n   {\n")
    src = IMPORT_BLOCK + STATIC_VARS + src[head_end:]

    # 2. hook Play()
    if PLAY_ANCHOR not in src:
        raise SystemExit("Play() anchor not found")
    src = src.replace(PLAY_ANCHOR, PLAY_REPLACEMENT, 1)

    # 3. append subtitle methods before the trailing braces
    tail = "   }\n}\n"
    idx = src.rindex(tail)
    methods = METHODS.replace("__SUBTITLE_CHUNKS__", chunks)
    methods = methods.replace("__STREAM_CHUNKS__", stream_chunks)
    methods = methods.replace("__TIMED_CHUNKS__", timed_chunks)
    src = src[:idx] + methods + src[idx:]

    design_w, design_h = swf_stage_size(Path(args.swf))
    src = src.replace("__DESIGN_W__", f"{design_w:.1f}")
    src = src.replace("__DESIGN_H__", f"{design_h:.1f}")
    print(f"design stage size: {design_w:g}x{design_h:g}")

    src = src.replace("__DBG_MODE__", "true" if args.debug else "false")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(src, encoding="utf-8")
    print(f"wrote {out} ({len(src)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

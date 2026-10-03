"""ActionScript boilerplate spliced verbatim into the generated DTSound.as.

Keeping the fixed AS3 source out of the build logic keeps the Python readable.
``IMPORT_BLOCK`` / ``STATIC_VARS`` / ``METHODS`` contain ``__PLACEHOLDER__``
tokens that :mod:`dtsound.generate` substitutes at build time; ``PLAY_ANCHORS``
are the original ``DTSound.Play()`` lines the subtitle hook is inserted after.
"""
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

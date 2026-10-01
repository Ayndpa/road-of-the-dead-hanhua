"""Patch user-facing English literals inside the gameplay ActionScript.

Replacement is done on the exact decompiled source text, so the keys must match
what FFDec emitted (including ``\\n`` / ``\\'`` escapes).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "work" / "scripts" / "scripts"
DST = ROOT / "patch" / "as3"

T: dict[str, dict[str, str]] = {
    "BasicGame.as": {
        r"Could not load the Kongregate API!\nChallenges are disabled.": r"无法加载 Kongregate API！\n挑战功能已禁用。",
        r"Could not load the ArmorGames Interface!\nArmorGames features are disabled.": r"无法加载 ArmorGames 接口！\nArmorGames 功能已禁用。",
    },
    "Input.as": {
        "Caps Lock": "大写锁定",
        "Shift": "Shift",
        "Ctrl": "Ctrl",
        "Space": "空格",
        "Left Arrow": "左方向键",
        "Down Arrow": "下方向键",
        "Right Arrow": "右方向键",
        "Up Arrow": "上方向键",
        "Backspace": "退格",
        "Enter": "回车",
        "Home": "Home",
        "Page Up": "上翻页",
        "Numpad Center": "小键盘中键",
        "End": "End",
        "Page Down": "下翻页",
        "Insert": "Insert",
        "Delete": "Delete",
        "Numpad .": "小键盘 .",
        "Numpad /": "小键盘 /",
        "Numpad *": "小键盘 *",
        "Numpad -": "小键盘 -",
        "Numpad +": "小键盘 +",
        "Numpad 0": "小键盘 0",
        "Numpad 1": "小键盘 1",
        "Numpad 2": "小键盘 2",
        "Numpad 3": "小键盘 3",
        "Numpad 4": "小键盘 4",
        "Numpad 5": "小键盘 5",
        "Numpad 6": "小键盘 6",
        "Numpad 7": "小键盘 7",
        "Numpad 8": "小键盘 8",
        "Numpad 9": "小键盘 9",
        "None": "无",
    },
    "RDAchievement.as": {
        "Survivor": "幸存者",
        r"Hell\'s Angel": "地狱天使",
        "Beat The Great Escape": "通关《大逃亡》",
        "Beat Highway To Hell": "通关《地狱公路》",
        '"Dead On Time"': '"准时赴死"',
        "One Man Army": "孤胆英雄",
        "Tank": "铁甲战车",
        "Buy all the upgrades": "购买全部升级",
        "Hood Shaker": "甩盖高手",
        "Knock an enemy off your hood by hitting the side walls": "撞击侧墙，把敌人从引擎盖上甩下去",
        "Gunslinger": "神枪手",
        "Shoot an enemy off your hood with the pistol": "用手枪把引擎盖上的敌人打下去",
        "Hydroficial Intelligence": "水攻智取",
        "Use a water jug to put off your burning engine": "用水壶浇灭着火的引擎",
        "Road Warrior": "公路战士",
        "Defeat a helicopter": "击落一架直升机",
        "Blunt Force Trauma": "钝器创伤",
        "Flip Flop": "翻个底朝天",
        "Meticulous": "一丝不苟",
        "Quick Draw": "快枪手",
        r"Shoot a soldier while he\'s pointing his gun at you and before he shoots": "在士兵举枪瞄准你、还没开枪时射杀他",
        "Speed Racer": "飙车手",
        r"Don\'t Need Wheels": "不需要轮子",
        "Pinball": "弹珠机",
        "Nuke Watcher": "核弹见证者",
        "Time To Spare": "时间充裕",
        "Road Dominator": "公路霸主",
        "Zombie Sniper": "僵尸狙击手",
        "No Mercy": "毫不留情",
        "Close Encounters": "近距离接触",
        "Get all 5 enemy types off your hood": "把 5 种敌人都从引擎盖上弄下去",
        "Wise Man": "智者",
        "Top Gun": "顶级飞行员",
        # shared fragments (concatenated achievement descriptions)
        '"Drive "': '"行驶 "',
        '" KM in Dead On Time"': '" 公里（《准时赴死》）"',
        '" KM in Police State"': '" 公里（《警察国家》）"',
        '" KM at maximum speed"': '" 公里（最高速度）"',
        '" KM with all 4 tires blown"': '" 公里（四条轮胎全爆）"',
        '"Do a "': '"完成 "',
        '" hits combo with zombies only"': '" 次纯僵尸连击"',
        '" hits vehicle collision combo"': '" 次车辆撞击连击"',
        '"Do "': '"完成 "',
        '" zombie splatter hits"': '" 次僵尸飞溅命中"',
        '"Hit "': '"撞击 "',
        '" enemies, alternating between zombie and soldier or vice versa"': '" 个敌人，在僵尸和士兵之间交替"',
        '" highway soldiers"': '" 名公路士兵"',
        '" civilians"': '" 名平民"',
        '"Kill "': '"在单次逃亡中低速撞死 "',
        '" zombies at low speed in a single run"': '" 只僵尸"',
        '"Avoid "': '"躲开 "',
        '" mutated zombies"': '" 只变异僵尸"',
        '"Dodge "': '"躲开 "',
        '" carpet bombings"': '" 次地毯式轰炸"',
        '"Reach up to "': '"在《准时赴死》中最多获得 "',
        '" seconds bonus time in Dead On Time"': '" 秒奖励时间"',
        '"Exit the city with at least "': '"至少提前 "',
        '" seconds to spare"': '" 秒逃出城市"',
    },
    "RDGame.as": {
        r"Highway 65\n\nWelcome To Evans City\n\nCity Exit\n60km": r"65号公路\n\n欢迎来到埃文斯城\n\n出城口\n60公里",
        "Dead On Time Distance": "《准时赴死》距离",
        "Police State Distance": "《警察国家》距离",
        "Highest Hit Combo": "最高连击",
        "Highest Flip Flop": "最多翻转",
        r"Speed through the zombie apocalypse and escape the quarantined city!\n\nNormal difficulty": r"在僵尸末日中疾驰，逃出被隔离的城市！\n\n普通难度",
        r"This is the road for survivors with something to prove!\n\nHard difficulty": r"这条路属于想要证明自己的幸存者！\n\n困难难度",
        r"This is for survivors with something to prove!\n\nHard difficulty\nComplete The Great Escape to unlock this mode!": r"这是为想要证明自己的幸存者准备的！\n\n困难难度\n通关《大逃亡》即可解锁此模式！",
        r"You\'re living on borrowed time.\n\nGet as far as you can by killing zombies to earn extra time!": r"你已经时日无多。\n\n尽可能走得更远，靠杀僵尸换取额外时间！",
        r"This is war and you are a one man army on wheels!\n\nGet as far as you can while facing brutal military resistance!": r"这是战争，而你是车轮上的一人军团！\n\n在军队的残酷阻击下尽可能走得更远！",
        "Play more games at newgrounds.com, where artists, programmers, musicians, writers and voice actors join forces to make pure awesomeness!": "在 newgrounds.com 玩更多游戏——画家、程序员、音乐人、作者和配音演员在这里合力创造纯粹的好东西！",
        r"Evil-Dog.com\n\nCheck out my other games, my music and my movies on my official website!": r"Evil-Dog.com\n\n在我的官网查看我的其他游戏、音乐和影片！",
        r"SickDeathFiend.com\n\nCheck out more movies and art by SickDeathFiend on his official website!": r"SickDeathFiend.com\n\n在 SickDeathFiend 的官网查看更多影片和美术作品！",
        r"Music made by\nSymphony of Specters\n\nVisit their website for more amazing music!": r"音乐制作\nSymphony of Specters\n\n访问他们的网站收听更多精彩音乐！",
        r"Surviving the zombie apocalypse requires a complete set of skills.\nDo You have what it takes to complete all the achievements?": r"在僵尸末日中求生需要全面的技能。\n你有本事完成所有成就吗？",
        r"In options, you can:\nCustomize your controls\nToggle sound and music\nSet graphic quality\nEnable/Disable buildings\nDelete your save data": r"在选项中，你可以：\n自定义按键\n开关音效与音乐\n设置画质\n开关建筑显示\n删除存档数据",
        r"Are you trying to be the greatest survivor?\n\nCheck the high scores for the Dead On Time and Police State modes!": r"想成为最伟大的幸存者吗？\n\n来看看《准时赴死》和《警察国家》模式的排行榜！",
        "Well done!": "干得漂亮！",
        r"Delete your save data?\nYou will lose all your progress": r"要删除存档数据吗？\n你将失去全部进度",
        r"Where do you wanna start\nThe Great Escape?": r"要从哪里开始\n《大逃亡》？",
        r"Where do you wanna start\nHighway To Hell?": r"要从哪里开始\n《地狱公路》？",
        r"Abort your escape and\nreturn to the garage?": r"要中止本次逃亡\n返回车库吗？",
        r"It\'s recommended to play The Great Escape first.\nAre you sure you want to continue?": r"建议先玩《大逃亡》。\n你确定要继续吗？",
        "Global Pandemic": "全球疫情",
        "Basic Survival": "基础生存",
        "Killing Methods": "杀戮技巧",
        "Pushing The Limits": "突破极限",
        "Veteran": "老兵",
        "Press a key...": "按下任意键……",
        "Could not save!": "保存失败！",
        "Make sure flash local storage is enabled.": "请确认已启用 Flash 本地存储。",
    },
    "RDGameModeGameplay.as": {
        '" KM Reached:"': '" 公里，已抵达："',
        '" Zombies Hit:"': '" 只僵尸命中："',
        '" Zombie Hit:"': '" 只僵尸命中："',
        '" Soldiers Hit:"': '" 名士兵命中："',
        '" Soldier Hit:"': '" 名士兵命中："',
        '" Clinging Enemies Shook Off:"': '" 个扒车敌人被甩下："',
        '" Clinging Enemy Shook Off:"': '" 个扒车敌人被甩下："',
        '" Clinging Enemies Shot Down:"': '" 个扒车敌人被击落："',
        '" Clinging Enemy Shot Down:"': '" 个扒车敌人被击落："',
        '" Helicopters Defeated:"': '" 架直升机被击落："',
        '" Helicopter Defeated:"': '" 架直升机被击落："',
        '"Combo Points:"': '"连击点数："',
        '" Splatter Hits:"': '" 次飞溅命中："',
        '" Splatter Hit:"': '" 次飞溅命中："',
        '" RP Bonus"': '" RP 奖励"',
        '" Civilians Hit:"': '" 名平民被撞："',
        '" Civilian Hit:"': '" 名平民被撞："',
        '" RP Penalty"': '" RP 惩罚"',
        '"Total Road Points:"': '"公路点数总计："',
        "Basic Controls": "基础操作",
        "Accelerate Key: ": "加速键：",
        r"\nBrake Key: ": r"\n刹车键：",
        r"\nSteer Left Key: ": r"\n左转键：",
        r"\nSteer Right Key: ": r"\n右转键：",
        r"\n\nAll the controls can be changed in the options.": r"\n\n所有按键都可以在选项中修改。",
        "Aborting": "中止",
        "If at any time, you want to abort your current escape, just move your mouse in the top center area and use the Abort button to return to the garage to plan your escape better.": "任何时候你想中止本次逃亡，只要把鼠标移到屏幕顶部中央，使用“中止”按钮就能返回车库，重新规划路线。",
        "Quality Key: ": "画质键：",
        r"\n\nIf the game runs slow, try cycling through the quality settings to find the best one for you.  You can also disable the buildings in the options.": r"\n\n如果游戏运行缓慢，可以循环切换画质设置，找到最适合你的那一档。你也可以在选项中关闭建筑显示。",
        '"Hand Brake"': '"手刹"',
        "Hand Brake Key: ": "手刹键：",
        r"\n\nIn order to survive this nightmare, you\'ll need to use your hand brake to avoid object with better control.": r"\n\n想在这场噩梦里活下来，你需要用手刹更精准地避开障碍物。",
        "Wipers Key: ": "雨刷键：",
        r"\n\nBetter get ready to get bloody!  With all these zombies, soldiers and civilians splattering their blood in your windshield, it\'s a good idea to use your wipers once in a while.": r"\n\n准备好溅一身血吧！僵尸、士兵和平民的血会糊满挡风玻璃，隔一阵子开一下雨刷是个好主意。",
        "Horn Key: ": "喇叭键：",
        r"\n\nThere is chaos on the highway and the civilians are running scared.  Running over civilians is bad so you should warn them with your horn to get them out of the way.": r"\n\n公路上一片混乱，平民吓得四散奔逃。撞到平民可不是好事，所以该按喇叭提醒他们让路。",
        "Punching": "挥拳",
        "Punch Key: ": "挥拳键：",
        r"\n\nThrough your escape, you\'ll end up with a shattered windshield.  If it\'s ruining your vision, you can punch it off.  You can\'t punch zombies, the risk of being infected is too great.": r"\n\n逃亡途中挡风玻璃难免会被打碎。如果它挡住了视线，你可以一拳把它打掉。但你不能打僵尸——被感染的代价太大。",
        "Splatter Hits": "飞溅命中",
        "When you hit someone, dead or alive, right in the center of your car and at high speed, you will get a splatter hit.  They will give you an extra Road Point multiplier.  Use the horn for easier zombie splatter hits!  Civilians will NOT give a bonus.": "当你高速用车头正中撞上任何人——死的活的都算——就会触发飞溅命中，获得额外的公路点数倍率。用喇叭更容易撞出僵尸飞溅命中！撞平民没有奖励。",
        "Hit Combos": "连击",
        "A good way to earn Road Points is to make hit combos.  By hitting multiple enemies in a row in a timely fashion, you will get more Road Points than regular hits.  The bigger the combo, the more points you get!  Be careful, hitting a civilian will break your combo.": "赚取公路点数的好办法是打出连击。在短时间内连续撞到多个敌人，你得到的点数会比普通撞击更多。连击越长，得分越高！注意，撞到平民会中断连击。",
        "Pistol": "手枪",
        "Pistol Key: ": "手枪键：",
        r"\nYou have brought a pistol with you.  When there is an enemy clinging to your hood, you can get it off quickly by shooting it.  Be aware that using the pistol will blast the windshield to pieces in a couple shots.": r"\n你随身带了一把手枪。有敌人扒在引擎盖上时，开枪能快速把它打下去。注意，手枪几发子弹就会把挡风玻璃打碎。",
        "Helicopters": "直升机",
        r"If you really piss the military off, they\'ll send helicopters to take you down for sure.  When a helicopter is after you, you\'ll have to make it crash into the big highway signs a couple of times to take it down.  Nobody said it would be easy!": r"如果你真把军队惹毛了，他们一定会派直升机来收拾你。直升机追你时，你得让它撞上几次高速公路上那些大路牌才能把它干掉。没人说这会很容易！",
        "Mutated Zombies": "变异僵尸",
        r"What caused the zombie outbreak is still unknown but it could be chemical since mutations have occured.  Mutated zombies are extremely strong and resistant.  They will cling to your hood no matter how hard you hit them.  It\'s better to avoid them if you don\'t want to have a lousy afternoon.": r"僵尸疫情的起因仍然不明，但既然出现了变异，可能是化学因素。变异僵尸极其强壮、抗打击。无论你怎么撞，它们都会死死扒住你的引擎盖。如果不想下午过得很糟，最好避开它们。",
        "Water Jugs": "水桶",
        r"When you\'re on the verge of exploding and your car is on fire, try to hit these big blue water jugs to put out the fire and give you a chance at surviving this hell a little longer.  Hitting water jugs also washes the blood off your windshield.": r"当车子即将爆炸、已经着火时，试着撞上这些蓝色的大水桶，既能灭火，也能让你在这地狱里多活一会儿。撞水桶还能冲掉挡风玻璃上的血。",
        "Enemies On Hood": "引擎盖上的敌人",
        r"If you\'re not driving fast enough, zombies and soldiers will get a chance to cling to your hood when you hit them.  You\'ll have to shake them off by hitting the side walls HARD (by using the hand brake) or by hitting abandoned cars.  A pistol is also a great way to get them off your hood quickly.": r"如果你开得不够快，撞上僵尸和士兵时，他们就有机会扒住你的引擎盖。你必须用手刹狠狠撞侧墙，或者撞上废弃车辆，才能把他们甩下去。用手枪也是快速清掉引擎盖上敌人的好办法。",
        "No Windshield": "没有挡风玻璃",
        r"Without a windshield, a zombie on your hood is a very bad thing.  Without anything to stop it, a zombie will get in and then you\'re dead.  Get them off your hood, quick!": r"没有挡风玻璃时，引擎盖上有僵尸是非常糟糕的事。没有东西挡着，僵尸会钻进车里，然后你就死了。快把他们弄下去！",
        "Perception": "感知",
        "Perception Toggle Key: ": "感知切换键：",
        r"\nWith perception, you will see a fixed top down view of the road, yourself as the white icon and the icons for the incoming hazards and enemies.\nKeep an eye on your perceptions to survive the day.": r"\n开启感知后，你会看到道路的固定俯视图：你自己是白色图标，正在接近的危险和敌人也各有图标。\n时刻留意感知，才能活过这一天。",
    },
    "RDGameModeGarage.as": {
        '"Dead On Time"': '"准时赴死"',
        '"Police State"': '"警察国家"',
        '"Body Armor"': '"防弹衣"',
        '"Perception"': '"感知"',
        '"Firearm"': '"枪械"',
        '"Windshield"': '"挡风玻璃"',
        '"Engine"': '"引擎"',
        '"Bumper"': '"保险杠"',
    },
    "RDGameModeMilitary.as": {
        "Police State Distance": "《警察国家》距离",
        "Dead On Time Distance": "《准时赴死》距离",
    },
    "RDGameModeStory.as": {
        "Evans City": "埃文斯城",
        "Monroeville": "门罗维尔",
        "Red Ridge": "红岭",
        "Burgony Street": "勃艮第街",
        "Central City": "中央城",
        "Down Town": "市中心",
        "Chinatown": "唐人街",
        "Brighton Square": "布莱顿广场",
        "North Side Park": "北区公园",
        "West Ridge": "西岭",
        "Tunnel Drive": "隧道大道",
        "Progress Saved...": "进度已保存……",
    },
    "RDGameModeTime.as": {
        "Dead On Time Distance": "《准时赴死》距离",
        "Police State Distance": "《警察国家》距离",
        '"Dead On Time"': '"准时赴死"',
        "Horn Key: ": "喇叭键：",
        r"\n\nIn Dead On Time, the horn is an essential way to attract the zombies in your way and get the civilians out of the way.": r"\n\n在《准时赴死》里，喇叭是吸引僵尸、驱散平民的关键手段。",
    },
    "RDUnlockItem.as": {
        "Perception 1": "感知 1", "Perception 2": "感知 2", "Perception 3": "感知 3",
        "Body Armor 1": "防弹衣 1", "Body Armor 2": "防弹衣 2", "Body Armor 3": "防弹衣 3",
        "Firearm 1": "枪械 1", "Firearm 2": "枪械 2", "Firearm 3": "枪械 3",
        "Windshield 1": "挡风玻璃 1", "Windshield 2": "挡风玻璃 2", "Windshield 3": "挡风玻璃 3",
        "Engine 1": "引擎 1", "Engine 2": "引擎 2", "Engine 3": "引擎 3",
        "Bumper 1": "保险杠 1", "Bumper 2": "保险杠 2", "Bumper 3": "保险杠 3",
        "Tires 1": "轮胎 1", "Tires 2": "轮胎 2", "Tires 3": "轮胎 3",
        "Horn 1": "喇叭 1", "Horn 2": "喇叭 2", "Horn 3": "喇叭 3",
    },
}


def main() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    report = {}
    for name, mapping in T.items():
        src = SRC / name
        txt = src.read_text(encoding="utf-8")
        applied, missing = 0, []
        for old, new in mapping.items():
            wrapped_old = f'"{old}"'
            wrapped_new = f'"{new}"'
            if wrapped_old in txt:
                txt = txt.replace(wrapped_old, wrapped_new)
                applied += 1
            elif old.startswith('"') and old.endswith('"'):
                # key already quoted (fragment without surrounding quotes)
                if old in txt:
                    txt = txt.replace(old, new)
                    applied += 1
                else:
                    missing.append(old)
            else:
                missing.append(old)
        if name == "BasicGame.as" and "DTSound.InitSubtitles();" not in txt:
            anchor = "         m_bGaveMedals = false;\n"
            if anchor in txt:
                txt = txt.replace(
                    anchor, anchor + "         DTSound.InitSubtitles();\n", 1
                )
        (DST / name).write_text(txt, encoding="utf-8")
        report[name] = (applied, len(mapping), missing)
        print(f"{name}: applied {applied}/{len(mapping)}")
        for m in missing:
            print(f"   !! not found: {m[:90]}")
    (ROOT / "work" / "as3_patch_report.json").write_text(
        json.dumps({k: {"applied": v[0], "total": v[1], "missing": v[2]} for k, v in report.items()},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

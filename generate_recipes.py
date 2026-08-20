#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""随机生成中文菜谱测试数据，输出 recipes.sql（兼容 MySQL 5.7+ / 腾讯云 TencentDB / TDSQL-C）。

用法：
    uv run python generate_recipes.py            # 生成 10000 条
    uv run python generate_recipes.py 50000      # 自定义条数

产物 recipes.sql 包含：
    - CREATE TABLE `recipe`（InnoDB / utf8mb4，字段与需求一一对应）
    - 批量多行 INSERT（每 500 行一条语句，导入速度快）
"""

import json
import random
import sys
from datetime import datetime, timedelta

TOTAL = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
BATCH = 500  # 每个 INSERT 语句的行数
SEED = 20260820
random.seed(SEED)

TABLE = "recipe"

# ---------------------------------------------------------------------------
# 菜名池：烹饪方法 -> 可搭配的主料（保证组合合理，如「清蒸鲈鱼」「红烧排骨」）
# ---------------------------------------------------------------------------
METHOD_INGREDIENTS = {
    "红烧": ["五花肉", "排骨", "牛肉", "鸡块", "鸡翅", "茄子", "豆腐", "带鱼", "猪蹄", "鸭块", "狮子头", "土豆", "牛腩", "武昌鱼", "肉", "鲳鱼"],
    "清蒸": ["鲈鱼", "鳜鱼", "武昌鱼", "鲳鱼", "大闸蟹", "扇贝", "娃娃菜", "鸡蛋羹", "鲷鱼", "青斑鱼", "鳕鱼", "多宝鱼"],
    "糖醋": ["里脊", "排骨", "带鱼", "藕片", "豆腐", "鸡丁", "虾仁", "土豆", "鲤鱼"],
    "鱼香": ["肉丝", "茄子", "鸡蛋", "豆腐", "鸡丁", "土豆丝"],
    "宫保": ["鸡丁", "虾球", "豆腐", "牛柳", "鸡腿肉"],
    "干煸": ["豆角", "四季豆", "牛肉丝", "土豆丝", "茶树菇", "苦瓜", "肥肠", "鸡块"],
    "蒜蓉": ["西兰花", "生菜", "油麦菜", "娃娃菜", "扇贝", "粉丝", "空心菜", "丝瓜", "秋葵", "龙虾", "花甲", "金针菇"],
    "白灼": ["虾", "菜心", "西兰花", "生菜", "芦笋", "鱿鱼", "秋葵", "花螺"],
    "凉拌": ["黄瓜", "木耳", "腐竹", "海带丝", "鸡丝", "菠菜", "三丝", "莴笋", "皮蛋豆腐", "芹菜", "花生米", "豆芽", "面筋", "牛肚"],
    "酸辣": ["土豆丝", "白菜", "藕片", "粉条", "鸡爪", "黄瓜", "汤", "鱼片", "肥牛"],
    "水煮": ["肉片", "牛肉", "鱼片", "豆腐", "牛蛙", "虾"],
    "干锅": ["花菜", "茶树菇", "鸡", "牛蛙", "土豆片", "虾", "肥肠", "包菜", "千叶豆腐"],
    "椒盐": ["虾", "排骨", "鱿鱼", "鸡翅", "土豆", "带鱼", "鸡米花", "皮皮虾"],
    "香辣": ["蟹", "虾", "鸡翅", "花甲", "鱿鱼须", "鸡爪", "小龙虾", "牛蛙", "田螺"],
    "酱爆": ["鸡丁", "鱿鱼", "茄子", "牛蛙", "猪肝", "肉丁"],
    "葱爆": ["羊肉", "牛肉", "猪肝", "海参", "腰花", "鸡蛋"],
    "麻婆": ["豆腐"],
    "回锅": ["肉", "土豆", "腊肉", "香干"],
    "小炒": ["黄牛肉", "肉", "鸡杂", "香干", "腊肉", "猪肝", "五花肉", "腊肠"],
    "剁椒": ["鱼头", "蒸蛋", "芋头", "金针菇", "鱼片", "娃娃菜"],
    "孜然": ["羊肉", "牛肉", "土豆", "鸡翅", "鱿鱼", "羊排", "面筋"],
    "咖喱": ["鸡肉", "牛肉", "土豆", "虾", "鱼丸", "牛腩", "蔬菜"],
    "黑椒": ["牛柳", "鸡腿", "猪排", "牛肉粒", "虾仁", "杏鲍菇"],
    "番茄": ["牛腩", "鱼片", "鸡蛋", "虾仁", "豆腐", "土豆"],
    "啤酒": ["鸭", "鸡翅", "排骨", "虾", "牛肉"],
    "可乐": ["鸡翅", "鸡腿", "排骨"],
    "黄焖": ["鸡", "排骨", "鱼", "鸡翅", "羊肉"],
    "砂锅": ["豆腐", "鱼头", "白菜粉丝", "红烧肉", "鸡", "牛腩", "丸子"],
    "铁板": ["牛肉", "鱿鱼", "豆腐", "茄子", "虾仁", "牛蛙"],
    "锡纸": ["烤鱼", "花甲", "金针菇", "豆腐", "娃娃菜"],
    "奥尔良": ["烤翅", "鸡腿", "鸡排", "烤鸡"],
    "蒜香": ["排骨", "鸡翅", "虾", "小龙虾", "鸡爪", "口蘑"],
    "香煎": ["鳕鱼", "三文鱼", "豆腐", "土豆饼", "鸡胸肉", "带鱼", "韭菜盒子", "鸡排"],
    "清炖": ["鸡汤", "羊肉", "牛腩", "排骨", "鸽子", "鸭汤", "鱼汤"],
    "蜜汁": ["叉烧", "鸡翅", "排骨", "藕片", "鸡腿"],
    "照烧": ["鸡腿", "三文鱼", "豆腐", "鸡排"],
    "泡椒": ["凤爪", "牛蛙", "猪肝", "鱼片", "鸡杂"],
    "农家": ["小炒肉", "一碗香", "蒸蛋", "柴火鸡", "土鸡", "腊肉"],
}

# 经典菜名（不带方法前缀）
CLASSICS = [
    "番茄炒蛋", "青椒肉丝", "土豆炖牛腩", "冬瓜排骨汤", "玉米排骨汤", "紫菜蛋花汤",
    "西红柿鸡蛋汤", "木须肉", "地三鲜", "锅包肉", "小鸡炖蘑菇", "京酱肉丝",
    "蚂蚁上树", "辣子鸡", "手撕包菜", "醋溜白菜", "韭菜炒鸡蛋", "蒜苔炒肉",
    "芹菜香干", "香菇油菜", "蚝油生菜", "皮蛋豆腐", "拍黄瓜", "口水鸡", "白切鸡",
    "梅菜扣肉", "粉蒸肉", "清炖狮子头", "龙井虾仁", "油焖大虾", "香辣小龙虾",
    "罗宋汤", "腌笃鲜", "佛跳墙", "松鼠鳜鱼", "叫花鸡", "东坡肉", "西湖醋鱼",
    "扬州炒饭", "蛋炒饭", "牛肉面", "炸酱面", "葱油拌面", "担担面", "酸菜鱼",
    "烤鱼", "毛血旺", "酸汤肥牛", "叉烧肉", "烧鹅", "白切鸭", "上汤娃娃菜",
    "蒜蓉粉丝蒸虾", "冬瓜丸子汤", "莲藕排骨汤", "海带排骨汤", "山药炖鸡",
    "香菇炖鸡", "板栗烧鸡", "三杯鸡", "盐焗鸡", "手撕鸡", "盐焗虾", "清炒虾仁",
    "避风塘炒蟹", "姜葱炒蟹", "清蒸大闸蟹", "香辣蟹", "泡菜豆腐汤", "石锅拌饭",
    "冷面", "饺子", "包子", "馄饨", "锅贴", "春卷", "葱油饼", "韭菜盒子",
    "煎饼果子", "豆腐脑", "八宝粥", "皮蛋瘦肉粥", "南瓜粥", "小米粥",
    "红枣银耳羹", "冰糖雪梨", "银耳莲子羹", "红豆沙", "绿豆汤", "酸梅汤",
    "四喜丸子", "糯米丸子", "珍珠丸子", "糖醋鲤鱼", "干烧黄鱼", "家焖黄鱼",
    "韭菜炒鱿鱼", "洋葱炒蛋", "苦瓜炒蛋", "秋葵炒蛋", "丝瓜炒蛋", "虾仁滑蛋",
    "肉末蒸蛋", "虎皮青椒", "蒜泥茄子", "蒸茄子", "红烧冬瓜", "清炒山药",
    "醋溜土豆丝", "酸辣白菜", "上汤菠菜", "蒜蓉菠菜", "清炒时蔬", "荷塘小炒",
    "腰果虾仁", "西芹百合", "木耳炒山药", "白菜炖豆腐", "麻酱豆角", "盐水毛豆",
    "五香花生", "酒鬼花生", "泡椒凤爪", "凉拌三丝", "夫妻肺片", "蒜泥白肉",
    "粉蒸排骨", "糯米蒸排骨", "芋头蒸排骨", "腊味煲仔饭", "腊肠炒饭",
    "咖喱鸡肉饭", "照烧鸡腿饭", "卤肉饭", "牛肉盖饭", "宫保鸡丁盖饭",
    "猪脚饭", "烧鸭饭", "牛腩粉", "桂林米粉", "云南过桥米线", "兰州拉面",
    "刀削面", "热干面", "油泼面", "岐山臊子面", "羊肉泡馍", "肉夹馍", "凉皮",
    "麻辣烫", "关东煮", "钵钵鸡", "麻辣香锅", "羊蝎子", "铜锅涮肉", "猪肚鸡",
    "椰子鸡", "花胶鸡", "鸡公煲", "老鸭汤", "酸萝卜老鸭汤", "萝卜炖羊肉",
    "红烧羊肉", "孜然羊肉", "葱爆羊肉", "涮羊肉", "手抓羊肉", "清炖羊排",
    "红烧牛尾", "番茄牛腩", "咖喱牛腩", "卤牛肉", "酱牛肉", "牛肉炖萝卜",
    "清汤牛肉", "水煮牛肉", "酸汤肥牛", "金汤肥牛", "肥牛饭", "黑椒牛排",
    "香煎牛排", "烤牛排", "牛肉丸汤", "潮汕牛肉丸", "虾饺", "烧卖", "肠粉",
    "萝卜糕", "马蹄糕", "马拉糕", "叉烧包", "流沙包", "奶黄包", "蛋挞",
    "老婆饼", "蛋黄酥", "月饼", "粽子", "汤圆", "元宵", "青团", "驴打滚",
    "豌豆黄", "芸豆卷", "糖火烧", "麻花", "油条", "烧饼", "灌汤包", "小笼包",
    "生煎包", "锅贴饺子", "韭菜猪肉饺子", "白菜猪肉饺子", "三鲜饺子", "牛肉饺子",
    "羊肉饺子", "虾仁饺子", "香菇鸡肉饺子", "玉米猪肉饺子", "芹菜牛肉饺子",
    "荠菜饺子", "茴香饺子", "素三鲜饺子", "酸菜猪肉饺子", "鲅鱼饺子", "墨鱼饺子",
    "清汤挂面", "阳春面", "葱油拌面", "麻酱拌面", "鸡丝凉面", "四川凉面",
    "臊子面", "裤带面", "棍棍面", "竹升面", "云吞面", "车仔面", "乌冬面",
    "豚骨拉面", "味噌拉面", "酱油拉面", "海鲜面", "猪肝面", "腰花面",
    "肥肠面", "鸡杂面", "牛肉拉面", "红烧牛肉面", "番茄鸡蛋面", "榨菜肉丝面",
    "雪菜肉丝面", "青菜面", "葱油阳春面", "油豆腐粉丝汤", "鸭血粉丝汤",
    "南京盐水鸭", "酱鸭", "卤鸭翅", "卤鸭脖", "周黑鸭", "啤酒鸭", "魔芋烧鸭",
    "仔姜鸭", "酸萝卜老鸭汤", "烤鸭", "白切鸡", "盐焗鸡", "豉油鸡", "酱油鸡",
    "白斩鸡", "贵妃鸡", "文昌鸡", "口水鸡", "辣子鸡丁", "宫保鸡丁", "怪味鸡",
    "椒麻鸡", "大盘鸡", "新疆大盘鸡", "沙姜鸡", "姜母鸭", "芋儿鸡", "辣子鸡",
    "棒棒鸡", "鸡肉沙拉", "鸡胸肉沙拉", "香煎鸡胸肉", "烤鸡胸肉", "卤鸡爪",
    "泡椒凤爪", "虎皮鸡爪", "盐焗鸡爪", "酱鸡爪", "烤鸡翅", "炸鸡翅",
    "卤鸡腿", "烤鸡腿", "盐焗鸡腿", "鸡米花", "上校鸡块", "鸡柳", "炸鸡排",
    "猪排饭", "炸猪排", "烤猪排", "猪扒包", "猪肉脯", "叉烧", "蜜汁叉烧",
    "腊肠", "腊肉", "火腿", "培根炒饭", "烤五花肉", "韩式烤肉", "日式烧肉",
    "京葱烧海参", "葱烧海参", "鲍鱼捞饭", "佛跳墙", "鱼翅捞饭", "燕窝",
    "花胶炖鸡汤", "冬虫夏草炖鸭", "天麻炖鸡", "党参炖鸡", "黄芪炖鸡",
    "当归炖羊肉", "枸杞炖鸡", "红枣枸杞鸡汤", "银耳莲子汤", "雪蛤炖木瓜",
    "双皮奶", "姜撞奶", "杨枝甘露", "芒果西米露", "芋圆", "烧仙草", "龟苓膏",
    "豆花", "甜豆花", "咸豆花", "豆汁", "豆浆", "米糊", "藕粉", "芝麻糊",
    "核桃露", "杏仁露", "花生露", "玉米汁", "南瓜汁", "胡萝卜汁", "黄瓜汁",
    "西瓜汁", "橙汁", "柠檬水", "蜂蜜柚子茶", "金桔柠檬茶", "珍珠奶茶",
    "丝袜奶茶", "鸳鸯奶茶", "柠檬红茶", "冻柠茶", "港式奶茶", "台式奶茶",
]

# 菜名前缀（让 1 万条数据有足够多的变化）
PREFIXES = [
    ("", 30), ("家常", 12), ("经典", 8), ("私房", 6), ("秘制", 5), ("川味", 5),
    ("湘味", 4), ("粤式", 4), ("广式", 4), ("台式", 3), ("港式", 3), ("东北", 3),
    ("鲁式", 2), ("淮扬", 2), ("老北京", 2), ("老上海", 2), ("川渝", 2), ("贵州", 2),
    ("云南", 2), ("潮汕", 2), ("客家", 2), ("农家", 4), ("古法", 2), ("传统", 2),
    ("创意", 2), ("快手", 3), ("低脂", 2), ("高蛋白", 2), ("宴客", 2), ("儿童", 2),
    ("妈妈的味道", 2), ("外婆的", 2),
]

# 地域/菜系前缀 -> 菜系（保证「广式xx」的菜系就是粤菜，不会随机成鲁菜）
PREFIX_CUISINE = {
    "川味": "川菜", "湘味": "湘菜", "粤式": "粤菜", "广式": "粤菜", "台式": "台湾菜",
    "港式": "粤菜", "东北": "东北菜", "鲁式": "鲁菜", "淮扬": "苏菜", "老北京": "北京菜",
    "老上海": "本帮菜", "川渝": "川菜", "贵州": "贵州菜", "云南": "云南菜",
    "潮汕": "潮汕菜", "客家": "客家菜",
}

# ---------------------------------------------------------------------------
# 主料池与分类（用于生成食材用量、营养成分、忌口）
# ---------------------------------------------------------------------------
VEG = {
    "白菜", "土豆", "茄子", "青椒", "西红柿", "番茄", "西兰花", "豆角", "四季豆",
    "黄瓜", "莲藕", "藕片", "山药", "蘑菇", "金针菇", "茶树菇", "冬瓜", "南瓜",
    "萝卜", "胡萝卜", "韭菜", "芹菜", "蒜苔", "菜花", "花菜", "木耳", "香菇",
    "竹笋", "玉米", "菠菜", "生菜", "油麦菜", "空心菜", "丝瓜", "秋葵", "苦瓜",
    "娃娃菜", "莴笋", "包菜", "海带丝", "粉条", "粉丝", "豌豆", "荷兰豆", "芦笋",
    "菜心", "蒜苗", "口蘑", "杏鲍菇", "芋头", "红薯", "紫薯", "西芹", "百合",
    "春笋", "冬笋", "笋", "芸豆",
    "荠菜", "茴香", "面筋", "千叶豆腐", "腐竹", "豆芽", "洋葱", "生姜", "大蒜",
    "辣椒", "青红椒", "柿子椒", "彩椒", "生菜", "油麦菜", "莴笋叶", "马齿苋",
}
TOFU = {"豆腐", "豆干", "香干", "腐竹", "豆皮", "千叶豆腐", "豆腐脑", "豆花", "豆腐皮"}
EGG = {"鸡蛋", "鸡蛋羹", "蒸蛋", "蛋液", "蛋黄", "皮蛋", "咸鸭蛋", "蛋挞"}
FISH = {"鲈鱼", "鳜鱼", "武昌鱼", "鲳鱼", "鲷鱼", "青斑鱼", "草鱼", "鲤鱼", "黄鱼",
        "带鱼", "鱼片", "鱼头", "三文鱼", "鳕鱼", "烤鱼", "鱼", "多宝鱼", "鱼丸",
        "墨鱼", "鲅鱼", "鳗鱼", "秋刀鱼", "沙丁鱼", "龙利鱼"}
SEAFOOD = {"虾", "虾仁", "蟹", "大闸蟹", "扇贝", "鱿鱼", "鱿鱼须", "花甲", "蛤蜊",
           "小龙虾", "龙虾", "海参", "鲍鱼", "花螺", "田螺", "皮皮虾", "虾球",
           "虾皮", "海带", "紫菜", "虾米", "牡蛎", "生蚝", "海蜇", "鱿鱼圈"}


def main_category(ing):
    """根据主料名称判断类别：素/豆腐/蛋/鱼/海鲜/主食/肉"""
    if ing in FISH:
        return "fish"
    if ing in SEAFOOD:
        return "seafood"
    if ing in TOFU:
        return "tofu"
    if ing in EGG:
        return "egg"
    if ing in VEG:
        return "veg"
    if any(k in ing for k in ("饭", "面", "粉", "粥", "饺", "包", "馄饨", "饼", "条", "汤圆", "粽子", "糕", "皮")):
        return "staple"
    return "meat"


DISH_CAT_PRIORITY = ["meat", "fish", "seafood", "egg", "tofu", "staple", "veg"]


def dish_category(mains, name=""):
    """整道菜的类别：按主料取优先级最高的一类（有肉算荤菜）。"""
    cats = {main_category(m) for m in mains if m != "食材"}
    if not cats:
        if any(k in name for k in ("饭", "面", "粉", "粥", "饺", "包", "馄饨", "饼", "米线", "汤圆", "粽子", "糕", "皮")):
            cats = {"staple"}
        elif any(k in name for k in ("糖", "酥", "糕", "卷", "羹", "露", "汁", "冻", "挞", "露")):
            cats = {"veg"}  # 甜品/糖水按素处理
        else:
            cats = {"meat"}
    for c in DISH_CAT_PRIORITY:
        if c in cats:
            return c
    return "veg"


def main_amount(ing):
    if ing == "食材":
        return "适量"
    c = main_category(ing)
    if c == "fish":
        return f"1条（约{random.randint(400, 800)}克）"
    if c == "egg":
        return f"{random.randint(2, 6)}个"
    if c == "tofu":
        return f"1块（约{random.randint(300, 500)}克）"
    if c == "seafood":
        return f"{random.randint(250, 500)}克"
    if c == "veg":
        return f"{random.randint(300, 500)}克"
    if c == "staple":
        return f"{random.randint(100, 300)}克"
    return f"{random.randint(250, 600)}克"


# 配料/辅料池
SIDE_VEG = [
    ("青椒", "1个"), ("红椒", "1个"), ("洋葱", "半个"), ("香菜", "2根"),
    ("小葱", "2根"), ("姜", "3片"), ("蒜", "3瓣"), ("胡萝卜", "半根"),
    ("木耳", "10克"), ("香菇", "4朵"), ("豆芽", "100克"), ("葱", "2根"),
    ("小米辣", "2个"), ("蒜苗", "2根"), ("彩椒", "半个"), ("笋片", "50克"),
]
SEASONINGS = [
    ("盐", lambda: f"{random.randint(2, 8)}克"),
    ("生抽", lambda: f"{random.randint(1, 3)}勺"),
    ("老抽", lambda: f"{random.randint(1, 2)}勺"),
    ("料酒", lambda: f"{random.randint(1, 3)}勺"),
    ("蚝油", lambda: f"{random.randint(1, 2)}勺"),
    ("白糖", lambda: f"{random.randint(5, 20)}克"),
    ("白胡椒粉", lambda: "适量"),
    ("鸡精", lambda: "适量"),
    ("淀粉", lambda: f"{random.randint(5, 15)}克"),
    ("香醋", lambda: f"{random.randint(1, 3)}勺"),
    ("陈醋", lambda: f"{random.randint(1, 3)}勺"),
    ("食用油", lambda: "适量"),
    ("干辣椒", lambda: f"{random.randint(3, 10)}个"),
    ("花椒", lambda: f"{random.randint(3, 10)}克"),
    ("八角", lambda: f"{random.randint(1, 3)}个"),
    ("桂皮", lambda: "1小块"),
    ("香叶", lambda: "2片"),
    ("豆瓣酱", lambda: f"{random.randint(1, 2)}勺"),
    ("辣椒油", lambda: f"{random.randint(1, 2)}勺"),
    ("芝麻油", lambda: "几滴"),
    ("五香粉", lambda: "适量"),
    ("孜然粉", lambda: f"{random.randint(1, 2)}勺"),
    ("辣椒粉", lambda: f"{random.randint(1, 2)}勺"),
    ("蜂蜜", lambda: f"{random.randint(1, 2)}勺"),
    ("冰糖", lambda: f"{random.randint(10, 30)}克"),
    ("番茄酱", lambda: f"{random.randint(1, 3)}勺"),
    ("甜面酱", lambda: f"{random.randint(1, 2)}勺"),
    ("腐乳", lambda: "1块"),
    ("剁椒", lambda: f"{random.randint(1, 2)}勺"),
    ("泡椒", lambda: f"{random.randint(3, 6)}个"),
    ("黑胡椒", lambda: "适量"),
    ("咖喱块", lambda: "2块"),
    ("蒜蓉酱", lambda: f"{random.randint(1, 2)}勺"),
    ("蒸鱼豉油", lambda: f"{random.randint(1, 2)}勺"),
    ("淀粉水", lambda: "适量"),
]

AROMATICS = ["葱段和姜片", "蒜末和姜末", "葱花、姜丝和蒜片", "干辣椒和花椒",
             "葱姜蒜", "蒜末和干辣椒", "姜片和葱结", "蒜片和葱段"]
SAUCE_MIX = ["生抽、蚝油和白糖调成的料汁", "盐、生抽和少许白糖", "料酒、生抽和香醋",
             "蒸鱼豉油和少许白糖", "盐和鸡精", "生抽、老抽和冰糖", "香醋、生抽和蒜末",
             "蚝油和少许清水"]

# ---------------------------------------------------------------------------
# 步骤模板（按烹饪方式分类）
# ---------------------------------------------------------------------------
PREP = {
    "meat": ["洗净后切成大小均匀的块", "切成薄片", "切成细丝", "剁成小块"],
    "fish": ["去鳞、去鳃、去内脏，洗净后在鱼身两面划几刀", "洗净沥干，两面抹少许盐"],
    "seafood": ["刷洗干净，剪去虾须、挑去虾线", "吐净泥沙后刷洗干净"],
    "veg": ["摘洗干净，沥干水分", "洗净后改刀成段", "削皮洗净，切成均匀的片"],
    "tofu": ["切成大小均匀的块，放入盐水中焯一下去豆腥味", "切成厚片备用"],
    "egg": ["打入碗中，加少许盐和几滴料酒打散", "打散后过一遍筛，口感更细腻"],
    "staple": ["将食材准备好，改刀备用", "提前浸泡或解冻备用"],
}


def gen_steps(category, main, flavor):
    """按烹饪方式生成 3~7 个步骤。main 为主料（多个用「、」连接）。"""
    mains = [m for m in main.split("、") if m != "食材"]

    def prep_line():
        """第一步的备料描述（按主料特征选刀工说法）。"""
        if len(mains) > 1:
            return "将各食材分别处理好：洗净、改刀、切配备用。"
        m0 = mains[0] if mains else "食材"
        if m0 == "食材":
            return "将食材准备好，洗净改刀备用。"
        if "丝" in m0:
            prep = "切成粗细均匀的丝"
        elif any(k in m0 for k in ("腿", "翅", "排")):
            prep = "改刀成大小合适的块"
        else:
            prep = random.choice(PREP[main_category(m0)])
        return f"{main}{prep}。"

    def meaty_all():
        """主料是否全部为肉/鱼/海鲜（决定是否用「焯水」开头）。"""
        return bool(mains) and all(main_category(m) in ("meat", "fish", "seafood") for m in mains)

    if category == "stir_fry":
        steps = [
            prep_line(),
            f"热锅倒油，油温{random.randint(5, 8)}成热时下入{random.choice(AROMATICS)}爆香。",
            f"倒入{main}，大火快速翻炒{random.randint(2, 5)}分钟。",
            f"加入{random.choice(SAUCE_MIX)}，继续翻炒均匀。",
            random.choice(["出锅前撒上葱花，装盘即可。", "翻炒至断生入味，出锅装盘。",
                           "临出锅淋几滴芝麻油，香气更足。"]),
        ]
    elif category == "braise":
        steps = [
            (f"{main}冷水下锅焯水，加料酒去腥，撇去浮沫后捞出沥干。" if meaty_all() else prep_line()),
            "锅中放油，下冰糖小火炒出糖色（或直接下葱姜爆香）。",
            f"下入{main}翻炒上色，加入{random.choice(AROMATICS)}炒香。",
            f"加入{random.choice(SAUCE_MIX)}和适量热水，没过食材。",
            f"大火烧开后转小火，加盖炖煮{random.randint(30, 90) if meaty_all() else random.randint(10, 25)}分钟。",
            "开盖转大火收汁，汤汁浓稠红亮即可出锅。",
        ]
    elif category == "steam":
        steps = [
            prep_line(),
            f"加{random.choice(['料酒', '姜片', '盐', '葱姜'])}腌制{random.randint(10, 20)}分钟。",
            "摆入盘中，蒸锅水开后上锅，大火蒸" + f"{random.randint(8, 20)}分钟。",
            "出锅后倒掉盘中汁水，撒上葱花和小米辣。",
            "淋上热油和蒸鱼豉油，即可上桌。",
        ]
    elif category == "blanch":
        steps = [
            "锅中烧开水，加少许盐和几滴食用油。",
            f"下入{main}，焯烫{random.randint(1, 3)}分钟，捞出沥干装盘。",
            f"调一个{random.choice(['蒜蓉豉油', '姜丝豉油', '小米辣豉油'])}酱汁。",
            "将酱汁均匀淋在食材上，即可食用。",
        ]
    elif category == "cold":
        pl = prep_line()
        steps = [
            pl + ("" if "焯" in pl else "（可焯水或直接生拌）"),
            f"碗中加入{random.choice(SAUCE_MIX)}、蒜末和少许小米辣，搅拌均匀。",
            f"将料汁倒入{main}中，充分拌匀。",
            random.choice(["撒上香菜和花生碎，冷藏半小时风味更佳。",
                           "装盘后撒白芝麻点缀，即可上桌。",
                           "腌制入味后食用，酸辣开胃。"]),
        ]
    elif category == "deep_fry":
        steps = [
            f"{main}加料酒、盐和姜片腌制{random.randint(15, 30)}分钟。",
            random.choice(["裹上蛋液和淀粉", "拍上一层薄薄的干淀粉", "挂上脆皮糊"]),
            f"油温{random.randint(5, 7)}成热时下锅，中火炸至金黄捞出。",
            "升高油温复炸约30秒，外壳更酥脆。",
            random.choice(["锅留底油，下糖醋汁炒至浓稠，倒入炸好的食材裹匀。",
                           "撒上椒盐和孜然粉，颠匀即可。", "直接装盘，配蘸料食用。"]),
        ]
    elif category == "soup":
        steps = [
            (f"{main}冷水下锅焯水，撇去浮沫后捞出。" if meaty_all() else prep_line()),
            f"汤锅加水烧开，放入{main}和{random.choice(AROMATICS)}。",
            f"大火烧开后转小火，慢煲{random.randint(40, 120) if meaty_all() else random.randint(10, 30)}分钟。",
            f"加入{random.choice(['盐', '盐和少许白胡椒粉', '盐和鸡精'])}调味，再煮5分钟。",
            "出锅前撒上葱花或香菜，趁热喝汤。",
        ]
    elif category == "pan_fry":
        steps = [
            prep_line() + f"加{random.choice(SAUCE_MIX)}腌制{random.randint(15, 30)}分钟。",
            "平底锅刷薄油烧热，放入食材。",
            "中小火煎至两面金黄。",
            f"倒入{random.choice(['照烧汁', '蜜汁', '黑椒汁', '剩余腌料'])}，小火收汁至浓稠。",
            "切块装盘，淋上锅中酱汁，撒芝麻葱花点缀。",
        ]
    elif category == "grill":
        steps = [
            prep_line() + f"加腌料拌匀，腌制{random.randint(20, 60)}分钟（提前一晚更入味）。",
            f"烤箱预热{random.choice(['180', '190', '200', '210'])}度。",
            "烤盘铺锡纸，刷一层油，摆入食材。",
            f"送入烤箱烤{random.randint(15, 30)}分钟，中途翻面刷一次酱汁。",
            "出炉后撒上葱花、芝麻或孜然粉即可。",
        ]
    elif category == "spicy_boil":
        steps = [
            f"{main}切片/处理干净，加盐、料酒和淀粉抓匀上浆。",
            "锅中放油，下豆瓣酱和姜蒜末小火炒出红油。",
            "加水烧开，先下配菜（豆芽/莴笋）煮熟捞出垫在碗底。",
            f"再下{main}煮熟，连汤倒入碗中。",
            "撒上干辣椒段、花椒和蒜末，浇上一勺滚烫的热油激出香味。",
        ]
    else:  # staple
        steps = [
            prep_line(),
            random.choice(["锅中放油烧热，下配料炒香。", "锅中烧开水备用。",
                           "调制好馅料/酱汁备用。"]),
            f"下入{main}，按品类炒/煮/蒸至熟透。",
            f"加入{random.choice(SAUCE_MIX)}调味，翻拌/煮制入味。",
            "出锅装盘（碗），趁热食用风味最佳。",
        ]
    return steps


# 方法 -> (步骤类别, 口味)
METHOD_INFO = {
    "红烧": ("braise", "savory"), "清蒸": ("steam", "light"), "糖醋": ("deep_fry", "sweet_sour"),
    "鱼香": ("stir_fry", "sweet_sour"), "宫保": ("stir_fry", "spicy"), "干煸": ("stir_fry", "spicy"),
    "白灼": ("blanch", "light"), "凉拌": ("cold", "light"), "酸辣": ("stir_fry", "spicy"),
    "水煮": ("spicy_boil", "spicy"), "干锅": ("stir_fry", "spicy"), "椒盐": ("deep_fry", "savory"),
    "香辣": ("stir_fry", "spicy"), "酱爆": ("stir_fry", "savory"), "葱爆": ("stir_fry", "savory"),
    "麻婆": ("stir_fry", "spicy"), "回锅": ("stir_fry", "spicy"), "小炒": ("stir_fry", "savory"),
    "剁椒": ("steam", "spicy"), "孜然": ("stir_fry", "cumin"), "咖喱": ("braise", "savory"),
    "黑椒": ("pan_fry", "savory"), "番茄": ("braise", "sweet_sour"), "啤酒": ("braise", "savory"),
    "可乐": ("braise", "sweet_sour"), "黄焖": ("braise", "savory"), "砂锅": ("braise", "savory"),
    "铁板": ("pan_fry", "savory"), "锡纸": ("grill", "garlic"), "奥尔良": ("grill", "savory"),
    "蒜香": ("pan_fry", "garlic"), "香煎": ("pan_fry", "savory"), "清炖": ("soup", "light"),
    "蜜汁": ("pan_fry", "sweet_sour"), "照烧": ("pan_fry", "sweet_sour"), "泡椒": ("stir_fry", "spicy"),
    "农家": ("stir_fry", "savory"), "蒜蓉": (None, "garlic"),  # 视主料决定蒸或炒
}

# 经典菜名 -> 步骤类别 / 口味 的关键词推断
CAT_KEYWORDS = [
    ("spicy_boil", ("水煮", "毛血旺", "麻辣烫", "冒菜")),
    ("steam", ("蒸", "粉蒸")),
    ("grill", ("烤", "焗", "盐焗", "烧鹅", "烧鸭")),
    ("braise", ("烧", "焖", "炖", "煲", "卤", "咖喱", "焖", "煮", "酱", "煲仔")),
    ("deep_fry", ("炸", "酥", "锅包", "辣子", "香锅", "糖醋")),
    ("pan_fry", ("煎", "锅贴", "烙")),
    ("soup", ("汤", "羹", "煲")),
    ("cold", ("拌", "凉", "拍", "口水", "夫妻肺片", "蒜泥", "麻酱", "皮蛋豆腐")),
    ("staple", ("饭", "面", "粉", "粥", "饺", "包", "馄饨", "饼", "米线", "馍", "糕", "条", "汤圆", "粽子")),
    ("stir_fry", ("炒", "爆", "煸", "熘", "干锅", "回锅")),
]
FLAVOR_KEYWORDS = [
    ("spicy", ("辣", "麻", "剁椒", "泡椒", "水煮", "毛血旺", "麻辣", "香锅", "冒菜", "宫保")),
    ("sweet_sour", ("糖醋", "锅包", "酸甜", "番茄", "可乐", "蜜汁", "照烧")),
    ("light", ("清蒸", "白灼", "白切", "清炖", "清炒", "上汤", "凉拌", "汤", "羹", "粥")),
    ("garlic", ("蒜", "蒜蓉", "蒜泥")),
    ("cumin", ("孜然",)),
]

CUISINES = ["川菜", "粤菜", "湘菜", "鲁菜", "苏菜", "浙菜", "闽菜", "徽菜", "东北菜",
            "西北菜", "本帮菜", "潮汕菜", "客家菜", "家常菜", "融合菜"]
FLAVOR_DESC = {
    "spicy": "麻辣鲜香，非常开胃下饭",
    "sweet_sour": "酸甜可口，外酥里嫩，大人小孩都爱吃",
    "light": "清淡爽口，突出食材本身的鲜美",
    "savory": "咸鲜适口，酱香浓郁",
    "garlic": "蒜香浓郁，香气扑鼻",
    "cumin": "孜然香气十足，风味独特",
}
FLAVOR_TAG = {
    "spicy": "麻辣", "sweet_sour": "酸甜", "light": "清淡", "savory": "咸鲜",
    "garlic": "蒜香", "cumin": "孜然",
}
TAILS = ["搭配白米饭食用风味更佳。", "适合全家人一起分享。", "招待客人也很有面子。",
         "下酒下饭都是一绝。", "冷藏后再吃也别有风味。", "减脂期也能放心吃。",
         "趁热吃口感最好。", "剩菜回锅加热后依然美味。"]

# 难度：不同烹饪方式的权重不同（炖/汤耗时长但操作简单，油炸/烧烤更容易翻车）
DIFFICULTY_WEIGHTS = {
    "braise": [("简单", 5), ("中等", 4), ("较难", 1)],
    "soup": [("简单", 6), ("中等", 3), ("较难", 1)],
    "deep_fry": [("简单", 2), ("中等", 5), ("较难", 3)],
    "spicy_boil": [("简单", 3), ("中等", 5), ("较难", 2)],
    "grill": [("简单", 3), ("中等", 5), ("较难", 2)],
}
DEFAULT_DIFFICULTY = [("简单", 5), ("中等", 4), ("较难", 2)]


def diff_desc(difficulty, cat):
    """难度描述：炖/汤类「耗时长」与「操作难」要分开表述。"""
    if difficulty == "简单":
        if cat in ("braise", "soup"):
            return "操作简单，只是需要一点耐心等待入味。"
        return "做法简单，十几分钟就能上桌，厨房新手也能轻松搞定。"
    if difficulty == "中等":
        return "做法不算复杂，跟着步骤做一次就能掌握。"
    return "步骤稍多，但成品色香味俱全，值得花点时间。"


# 场合标签按烹饪方式限定，避免「皮蛋豆腐」带「汤羹」这类不合理组合
OCCASION_BY_CAT = {
    "stir_fry": ["下饭菜", "快手菜", "家常菜", "午餐", "晚餐", "宴客菜"],
    "braise": ["硬菜", "下饭菜", "宴客菜", "家常菜", "晚餐", "午餐"],
    "steam": ["快手菜", "宴客菜", "家常菜", "养生", "减脂餐", "儿童餐"],
    "blanch": ["快手菜", "减脂餐", "家常菜", "宴客菜", "养生"],
    "cold": ["凉菜", "下酒菜", "开胃菜", "快手菜", "夜宵"],
    "deep_fry": ["下酒菜", "夜宵", "小吃", "宴客菜", "儿童餐"],
    "soup": ["汤羹", "养生", "家常菜", "晚餐", "宴客菜"],
    "pan_fry": ["快手菜", "减脂餐", "早餐", "家常菜", "儿童餐"],
    "grill": ["烧烤", "夜宵", "下酒菜", "宴客菜", "儿童餐"],
    "spicy_boil": ["下饭菜", "硬菜", "夜宵", "宴客菜"],
    "staple": ["主食", "早餐", "快手菜", "夜宵", "午餐"],
}
DISH_TYPES = {"meat": "肉菜", "fish": "鱼鲜", "seafood": "海鲜", "veg": "素菜",
              "tofu": "豆制品", "egg": "蛋类", "staple": "主食"}
DIET_KEYWORDS = [
    ("海鲜", ("虾", "蟹", "鱼", "鱿", "贝", "蛤", "螺", "海参", "鲍", "海带", "紫菜", "牡蛎", "生蚝", "海蜇", "龙虾", "鱼翅", "燕窝")),
    ("蛋类", ("鸡蛋", "蒸蛋", "蛋黄", "蛋挞", "蛋液", "皮蛋", "咸鸭蛋")),
    ("乳制品", ("奶", "芝士", "黄油", "奶油", "奶酪", "双皮奶")),
    ("花生", ("花生",)),
    ("麸质", ("面", "饼", "面包", "饺子", "馄饨", "烧饼")),
]
REMARKS = [None] * 60 + [
    "辣度可根据个人口味调整", "海鲜过敏者慎食", "高血脂人群适量食用",
    "糖尿病患者可减少糖的用量", "素食者可将肉类替换为豆制品",
    "食材可按季节替换时令蔬菜", "隔夜食用请充分加热",
]


def infer_category_and_flavor(name, method=None):
    """根据菜名关键词推断步骤类别和口味；组合菜名直接查 METHOD_INFO。"""
    if method and method in METHOD_INFO:
        cat, fl = METHOD_INFO[method]
        if method == "蒜蓉":
            main = name.replace("蒜蓉", "")
            cat = "steam" if any(k in main for k in ("扇贝", "粉丝", "丝瓜", "娃娃菜", "龙虾")) else "stir_fry"
        return cat, fl
    for cat, kws in CAT_KEYWORDS:
        if any(k in name for k in kws):
            for fl, fkws in FLAVOR_KEYWORDS:
                if any(k in name for k in fkws):
                    return cat, fl
            return cat, "savory"
    return "stir_fry", "savory"


def extract_mains(name):
    """从菜名中提取主料（优先长词，最多 2 个）。"""
    all_ings = VEG | TOFU | EGG | FISH | SEAFOOD | {
        "五花肉", "排骨", "牛肉", "牛腩", "牛柳", "牛尾", "鸡块", "鸡翅", "鸡腿", "鸡胸肉",
        "鸡肉", "鸡丁", "鸡杂", "鸭", "鸭块", "猪肉", "里脊", "肉丝", "肉片", "肉", "羊肉",
        "羊排", "猪蹄", "肥肠", "猪肝", "腰花", "狮子头", "丸子", "腊肉", "腊肠", "火腿",
        "培根", "鸽子", "牛蛙", "鸡爪", "凤爪", "猪排", "五花肉", "叉烧", "烤翅",
    }
    found = []
    # 先按长度降序、再按名称排序，保证等长词的顺序确定（set 迭代顺序受 PYTHONHASHSEED 影响）
    for ing in sorted(all_ings, key=lambda x: (-len(x), x)):
        # 跳过已匹配词的子串（如已匹配「鲤鱼」就不再匹配「鱼」）
        if ing in name and ing not in found and not any(ing in f for f in found):
            found.append(ing)
        if len(found) == 2:
            break
    return found if found else ["食材"]


# 从名字拆不出主料的经典菜，直接给出主料（让食材/营养/分类更真实）
NAME_MAIN_OVERRIDES = {
    "地三鲜": ["土豆", "茄子", "青椒"],
    "荷塘小炒": ["莲藕", "木耳", "荷兰豆"],
    "毛血旺": ["鸭血", "毛肚", "午餐肉"],
    "佛跳墙": ["鲍鱼", "海参", "花胶"],
    "罗宋汤": ["牛肉", "土豆", "西红柿"],
    "腌笃鲜": ["咸肉", "鲜肉", "春笋"],
    "四喜丸子": ["猪肉末"],
    "木须肉": ["猪肉", "鸡蛋", "木耳"],
    "蚂蚁上树": ["粉丝", "肉末"],
    "夫妻肺片": ["牛肉", "牛肚"],
    "麻辣香锅": ["五花肉", "虾", "藕片"],
    "上汤娃娃菜": ["娃娃菜", "皮蛋"],
    "扬州炒饭": ["米饭", "鸡蛋", "虾仁"],
    "蛋炒饭": ["米饭", "鸡蛋"],
    "腊味煲仔饭": ["米饭", "腊肠"],
    "饺子": ["猪肉", "饺子皮"],
    "包子": ["猪肉", "面粉"],
    "馄饨": ["猪肉", "馄饨皮"],
    "肉夹馍": ["五花肉", "面粉"],
    "凉皮": ["凉皮"],
    "蛋挞": ["鸡蛋", "面粉"],
    "春卷": ["猪肉", "春卷皮"],
    "锅贴": ["猪肉", "面粉"],
    "芸豆卷": ["芸豆"],
}


def gen_ingredients_json(mains, flavor):
    """食材 JSON：[{name, amount}, ...]，主料在前，随后为辅料和调料。"""
    ings = [{"name": m, "amount": main_amount(m)} for m in mains]
    used = set(mains)
    # 辅料
    for s, a in random.sample(SIDE_VEG, random.randint(1, 3)):
        if s not in used:
            ings.append({"name": s, "amount": a})
            used.add(s)
    # 调料：麻辣口味强制加入干辣椒/花椒/豆瓣酱
    picks = []
    if flavor in ("spicy", "cumin"):
        picks += [("干辣椒", lambda: "5个"), ("花椒", lambda: "5克")]
    picks += random.sample(SEASONINGS, random.randint(2, 5))
    for s, gen in picks:
        if s not in used:
            ings.append({"name": s, "amount": gen()})
            used.add(s)
    return ings


def gen_nutrition(cat):
    """营养成分 JSON（每 100 克，单位随机化，按类别控制合理区间）。"""
    rng = {
        "veg": ((20, 90), (1, 6), (0.5, 5), (4, 18), (100, 400)),
        "tofu": ((60, 120), (5, 10), (3, 8), (2, 6), (150, 400)),
        "egg": ((120, 160), (10, 14), (8, 11), (1, 3), (200, 500)),
        "fish": ((80, 150), (14, 22), (1, 8), (0, 5), (200, 600)),
        "seafood": ((70, 130), (12, 20), (1, 5), (1, 8), (200, 800)),
        "staple": ((150, 350), (5, 12), (2, 15), (25, 60), (200, 800)),
        "meat": ((150, 300), (12, 26), (8, 25), (2, 10), (300, 900)),
    }[cat]
    return {
        "单位": "每100克",
        "热量_kcal": random.randint(*rng[0]),
        "蛋白质_g": round(random.uniform(*rng[1]), 1),
        "脂肪_g": round(random.uniform(*rng[2]), 1),
        "碳水化合物_g": round(random.uniform(*rng[3]), 1),
        "钠_mg": random.randint(*rng[4]),
    }


def gen_dietary(name, mains, flavor):
    """忌口：根据菜名/主料/口味推导，多个用「、」连接，无则返回「无」。"""
    diets = []
    text = name + "、" + "、".join(mains)
    for label, kws in DIET_KEYWORDS:
        if any(k in text for k in kws):
            diets.append(label)
    if flavor in ("spicy", "cumin") and "辛辣" not in diets:
        diets.append("辛辣")
    return "、".join(diets) if diets else "无"


def gen_recipe(i):
    """生成一条菜谱数据。"""
    # ---- 菜名：70% 组合菜名 / 30% 经典菜名，可加前缀 ----
    method = None
    if random.random() < 0.7:
        method = random.choice(list(METHOD_INGREDIENTS))
        main = random.choice(METHOD_INGREDIENTS[method])
        name = method + main
    else:
        name = random.choice(CLASSICS)
    prefix = random.choices([p for p, _ in PREFIXES], weights=[w for _, w in PREFIXES])[0]
    mains = [m for m in extract_mains(name)] if method is None else [main]
    if method is None and name in NAME_MAIN_OVERRIDES:
        mains = list(NAME_MAIN_OVERRIDES[name])
    if prefix:
        # 「低脂」前缀只用于素菜/鱼/海鲜/豆腐
        if prefix == "低脂" and dish_category(mains, name) not in ("veg", "fish", "seafood", "tofu"):
            prefix = random.choice(["家常", "经典", "私房"])
        name = prefix + name

    cat, flavor = infer_category_and_flavor(name, method)
    main_cat = main_category(mains[0])
    dish_cat = dish_category(mains, name)
    # 带地域/菜系前缀时，菜系与之一致
    cuisine = PREFIX_CUISINE.get(prefix, random.choice(CUISINES))
    weights = DIFFICULTY_WEIGHTS.get(cat, DEFAULT_DIFFICULTY)
    difficulty = random.choices([d for d, _ in weights], weights=[w for _, w in weights])[0]

    # ---- 说明 ----
    desc = (f"{name}是一道经典的{cuisine}，{FLAVOR_DESC[flavor]}。"
            f"{diff_desc(difficulty, cat)}{random.choice(TAILS)}")

    # ---- 标签 ----
    tags = [FLAVOR_TAG[flavor], difficulty, DISH_TYPES[dish_cat], cuisine]
    if method:
        tags.append(method + ("菜" if main_cat != "staple" else ""))
    tags += random.sample(OCCASION_BY_CAT.get(cat, OCCASION_BY_CAT["stir_fry"]), random.randint(1, 3))
    tags = list(dict.fromkeys(tags))  # 去重保序

    servings = random.choices([1, 2, 3, 4, 5, 6], weights=[1, 3, 5, 5, 3, 1])[0]

    created = datetime(2024, 1, 1) + timedelta(
        seconds=random.randint(0, int((datetime(2026, 8, 20) - datetime(2024, 1, 1)).total_seconds())))
    created_s = created.strftime("%Y-%m-%d %H:%M:%S")

    return {
        "id": i,
        "name": name,
        "description": desc,
        "ingredients": gen_ingredients_json(mains, flavor),
        "steps": gen_steps(cat, "、".join(mains), flavor),
        "dietary": gen_dietary(name, mains, flavor),
        "tags": ",".join(tags),
        "servings": servings,
        "image_url": f"https://cdn.example.com/recipes/{i:05d}.jpg",  # TODO 替换为真实图片地址
        "nutrition": gen_nutrition(dish_cat),
        "remark": random.choice(REMARKS),
        "created_at": created_s,
    }


# ---------------------------------------------------------------------------
# SQL 输出
# ---------------------------------------------------------------------------
HEADER = f"""-- ============================================================
-- 菜谱表结构 + {TOTAL} 条随机中文菜谱测试数据
-- 生成工具: generate_recipes.py (种子 {SEED})
-- 兼容: MySQL 5.7+ / 腾讯云 TencentDB for MySQL / TDSQL-C
-- 注意:
--   1. 必须使用 utf8mb4 字符集（腾讯云实例创建时默认即可）
--   2. 图片 image_url 为占位地址，请替换为真实图片 URL
--   3. 如需在老版本 MySQL(<5.7) 使用，把 JSON 列改为 TEXT 即可
--   4. 本文件会自动创建 cookgpt 数据库并写入其中；
--      若通过腾讯云控制台导入（账号无全局 CREATE 权限、需手动先建库），
--      可删除下面的 CREATE DATABASE / USE 两行
-- ============================================================

SET NAMES utf8mb4;

-- 创建数据库 cookgpt 并切换过去
CREATE DATABASE IF NOT EXISTS `cookgpt` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `cookgpt`;

DROP TABLE IF EXISTS `{TABLE}`;
CREATE TABLE `{TABLE}` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '食谱ID',
  `name` VARCHAR(128) NOT NULL COMMENT '食谱名称',
  `description` TEXT COMMENT '食谱说明',
  `ingredients` JSON COMMENT '食材: [{{"name":"五花肉","amount":"500克"}}, ...]',
  `steps` JSON COMMENT '步骤: ["步骤1", "步骤2", ...]',
  `dietary` VARCHAR(255) NOT NULL DEFAULT '无' COMMENT '忌口: 逗号分隔，无则为"无"',
  `tags` VARCHAR(255) DEFAULT NULL COMMENT '标签: 逗号分隔',
  `servings` TINYINT UNSIGNED NOT NULL DEFAULT 2 COMMENT '适用人数',
  `image_url` VARCHAR(512) DEFAULT NULL COMMENT '图片',
  `nutrition` JSON COMMENT '营养成分: {{"热量_kcal":123,"蛋白质_g":10,...}}',
  `remark` VARCHAR(255) DEFAULT NULL COMMENT '备注',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_name` (`name`(64))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='菜谱表';

"""

COLUMNS = ("id", "name", "description", "ingredients", "steps", "dietary",
           "tags", "servings", "image_url", "nutrition", "remark", "created_at")


def esc(s):
    """SQL 字符串转义（MySQL 默认反斜杠转义模式）。"""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def row_sql(r):
    vals = [
        str(r["id"]),
        f"'{esc(r['name'])}'",
        f"'{esc(r['description'])}'",
        f"'{esc(json.dumps(r['ingredients'], ensure_ascii=False))}'",
        f"'{esc(json.dumps(r['steps'], ensure_ascii=False))}'",
        f"'{esc(r['dietary'])}'",
        f"'{esc(r['tags'])}'",
        str(r["servings"]),
        f"'{esc(r['image_url'])}'",
        f"'{esc(json.dumps(r['nutrition'], ensure_ascii=False))}'",
        "NULL" if r["remark"] is None else f"'{esc(r['remark'])}'",
        f"'{r['created_at']}'",
    ]
    return "(" + ", ".join(vals) + ")"


def main():
    rows = [gen_recipe(i) for i in range(1, TOTAL + 1)]
    names = {r["name"] for r in rows}

    with open("recipes.sql", "w", encoding="utf-8") as f:
        f.write(HEADER)
        for start in range(0, TOTAL, BATCH):
            batch = rows[start:start + BATCH]
            f.write(f"INSERT INTO `{TABLE}` ({', '.join('`%s`' % c for c in COLUMNS)}) VALUES\n")
            f.write(",\n".join(row_sql(r) for r in batch) + ";\n\n")

    import os
    size_mb = os.path.getsize("recipes.sql") / 1024 / 1024
    print(f"✓ 已生成 recipes.sql：{TOTAL} 条菜谱，{len(names)} 个不重名菜名")
    print(f"  INSERT 语句数：{(TOTAL + BATCH - 1) // BATCH}（每 {BATCH} 行一条）")
    print(f"  文件大小：{size_mb:.1f} MB")
    sample = rows[0]
    print(f"  示例：{sample['name']} | 人数{sample['servings']} | 忌口:{sample['dietary']} | 标签:{sample['tags']}")


if __name__ == "__main__":
    main()

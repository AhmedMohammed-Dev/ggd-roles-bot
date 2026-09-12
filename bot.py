# -*- coding: utf-8 -*-
"""
🦢 بوت ديسكورد — دليل أدوار لعبة Goose Goose Duck (بالعربي)
============================================================
• واجهة أزرار تفاعلية (discord.ui.View / Button) وصفحات متعددة.
• كل ضغطة زر تُرسل Embed خاص بالمستخدم فقط (ephemeral = لا يراه غيره).
• Embed يحتوي: اسم الدور بالعربي والإنجليزي + الشرح + الفئة بلونها + صورة الدور.
• إضافة/تعديل الأدوار بسهولة من قاموس ROLES (تحت قسم 2).
• أمرين للتشغيل:  /roles   (Slash)   و   !roles   (Prefix).
• خادم Flask صغير (Keep-Alive) ليبقى البوت شغّالاً 24/7 على منصّات الاستضافة المجانية.

⚠️ الأمان: التوكن لا يُكتب داخل الكود أبداً — يُقرأ من متغيّر البيئة DISCORD_TOKEN فقط.
"""

from __future__ import annotations

import hmac
import logging
import math
import os
import random
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, jsonify, request

# ══════════════════════════════════════════════════════════════════════════════
# 1) الإعدادات — كل شيء من متغيرات البيئة (لا شيء سري داخل الكود)
# ══════════════════════════════════════════════════════════════════════════════


def env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value.strip()


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, "")).strip())
    except (TypeError, ValueError):
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, "")).strip())
    except (TypeError, ValueError):
        return default


TOKEN: str = env_str("DISCORD_TOKEN")

# سيرفر واحد يُسجَّل فيه الأمر فوراً (اختياري لكن مُستحسن). اتركه صفراً لتسجيل الأمر عالمياً.
GUILD_ID: int = env_int("GUILD_ID", 0)

# قائمة بيضاء: إن كانت غير فارغة فالبوت يعمل في هذه السيرفرات فقط (حماية من إساءة الاستخدام).
ALLOWED_GUILD_IDS: Set[int] = {
    int(part) for part in env_str("ALLOWED_GUILD_IDS").replace(",", " ").split() if part.isdigit()
}

# خادم Flask للإبقاء على الحياة (Keep-Alive)
PORT: int = env_int("PORT", 8080)
KEEPALIVE_PATH: str = env_str("KEEPALIVE_PATH", "/healthz") or "/healthz"
if not KEEPALIVE_PATH.startswith("/"):
    KEEPALIVE_PATH = "/" + KEEPALIVE_PATH
# إن وُضع هذا المفتاح، لن يستجيب مسار الفحص إلا لمن يرسله في الهيدر X-Health-Key (حماية إضافية)
HEALTH_TOKEN: str = env_str("HEALTH_TOKEN")

# إذا نُشر البوت على رابط عام، البوت "يقرع" نفسه كل فترة حتى لا ينام السيرفر المجاني
PUBLIC_URL: str = env_str("PUBLIC_URL")
SELF_PING_SECONDS: int = max(60, env_int("SELF_PING_SECONDS", 600))

# أمر !roles يحتاج تفعيل Message Content Intent في لوحة المطوّرين. اتركه false إن أردت أعلى أمان.
ENABLE_PREFIX_COMMANDS: bool = env_bool("ENABLE_PREFIX_COMMANDS", False)

# فترة منع التكرار بين ضغطات الأزرار (بالثواني) لحماية البوت من السبام
ACTION_COOLDOWN: float = max(0.0, env_float("ACTION_COOLDOWN_SECONDS", 1.0))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("ggd")

# ══════════════════════════════════════════════════════════════════════════════
# 2) بيانات الأدوار — ⬅️ كل ما تحتاجه لإضافة دور جديد موجود هنا
#    الفئات:  goose = إوز (أخضر)  |  duck = بط (أحمر)  |  neutral = محايد (أصفر)
#    image:  رابط صورة الدور (اتركها None إن لم تكن متوفّرة — الكود يتعامل معها بأمان)
# ══════════════════════════════════════════════════════════════════════════════

TEAMS: Dict[str, Dict[str, Any]] = {
    "goose": {
        "label": "🟢 فريق الإوز (Goose)",
        "short": "إوز",
        "color": 0x3BA55D,  # أخضر
        "emoji": "🟢",
    },
    "duck": {
        "label": "🔴 فريق البط (Duck)",
        "short": "بط",
        "color": 0xED4245,  # أحمر
        "emoji": "🔴",
    },
    "neutral": {
        "label": "🟡 محايد (Neutral)",
        "short": "محايد",
        "color": 0xFEE75C,  # أصفر
        "emoji": "🟡",
    },
}

ROLES: Dict[str, Dict[str, Any]] = {
    # ─────────────────────────────── الإوز 🟢 ───────────────────────────────
    "goose": {
        "name_ar": "الإوزة",
        "name_en": "Goose",
        "emoji": "🪿",
        "team": "goose",
        "goal": "إتمام كل مهامك والبقاء حياً، ثم طرد البط بالتصويت. الإوز يفوز عند إنجاز جميع المهام أو بطرد كل البط.",
        "how": "تنقّل في الخريطة وأنجز المهام حتى يمتلئ شريط التقدّم. لاحظ من يقف قرب الجثث ومن يمرّ عبر الفتحات، وصوّت في الاجتماعات على المشتبه به.",
        "tips": "• لا تتحرك وحدك أبداً.\n• أبلغ عن الجثة فوراً (كل ثانية تأخير يمنح البط وقتاً).\n• المهام الفردية (Individual Tasks) لا تُنهي المباراة، فلا تعتمد عليها وحدها.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/d/dd/Goose.png/revision/latest?cb=20260310135439",
    },
    "sheriff": {
        "name_ar": "الشريف",
        "name_en": "Sheriff",
        "emoji": "🤠",
        "team": "goose",
        "goal": "حماية الإوز والقضاء على البط. تستطيع قتل أي لاعب، لكن إن قتلت إوزة متّ أنت أيضاً.",
        "how": "لديك زر قتل قوي (غالباً مرة واحدة أو بعدد محدود). اختر هدفك بعد تركيز حقيقي، لأن القتل الخاطئ يعني خسارة الشريف والإوزة معاً.",
        "tips": "• لا تُطلق النار بناءً على شكّ ضعيف — خسارة الشريف كارثة للإوز.\n• صرّح بهويتك إذا رأيت مقتلاً مؤكداً حتى تمنع طردك.\n• وجودك في المباراة يخيف البط ويجعلهم يترددون.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/3/31/SheriffIcon.png/revision/latest?cb=20260309192816",
    },
    "engineer": {
        "name_ar": "المهندس",
        "name_en": "Engineer",
        "emoji": "🔧",
        "team": "goose",
        "goal": "كشف البط الذي يستخدم التخريب، والبقاء حياً بمساعدة قدراتك التقنية.",
        "how": "عند وقوع تخريب تظهر دوائر حمراء على الخريطة المصغّرة تُبيّن المكان التقريبي للبطة الحيّة التي نفّذت التخريب. تستطيع أيضاً استخدام الفتحات (Vents) لمدة 10 ثوانٍ فقط، أو الاختفاء في الأماكن المخفية.",
        "tips": "• أخبر الإوز بالمنطقة الحمراء واطلب من المتواجد هناك تبرير وجوده.\n• لا تستخدم الفتحات أمام الجميع — سيُفهم أنك مهندس أو بطة.\n• لا يمكنك رؤية مكان تخريب بطة ميتة.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/e/ec/EngineerIcon.png/revision/latest?cb=20260310134328",
    },
    "vigilante": {
        "name_ar": "المدافع",
        "name_en": "Vigilante",
        "emoji": "🔫",
        "team": "goose",
        "goal": "مساعدة الإوز بهجوم محدود. لديك قدرة قتل واحدة طوال المباراة.",
        "how": "استخدم رصيدك الوحيد عندما تتأكد من بطة (لا يوجد قتل رجعي يقتلك إن أخطأت، لكنك تفقد قدرتك). القرار الأخير هو كل شيء.",
        "tips": "• احتفظ بقدرتك للاجتماع الحاسم أو لمن يهرب منك غالباً.\n• إن أخطأت، اعتذر ووضّح الموقف قبل أن تُطرد.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/c/c7/Vigilante.png/revision/latest?cb=20260310134902",
    },
    "detective": {
        "name_ar": "المحقق",
        "name_en": "Detective",
        "emoji": "🔍",
        "team": "goose",
        "goal": "معرفة من قام بالقتل في الجولة الحالية.",
        "how": "استخدم زر التحقيق على لاعب لتعرف هل قتل أحدهم في هذه الجولة. لا يعمل التحقيق على الموتى، وتفشل النتيجة إن لم يقتل أحداً.",
        "tips": "• تحقّق من اللاعبين الصامتين أو من كان قريباً من الجثة.\n• لا تفشِ أنك محقق لأول شخص يسألك — قول \"أنا محقق\" يجذب السفاح.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/7/77/Detective_.png/revision/latest?cb=20260310135750",
    },
    "canadian": {
        "name_ar": "الكندي",
        "name_en": "Canadian",
        "emoji": "🍁",
        "team": "goose",
        "goal": "البقاء حياً، وإن قُتلت فإن جثتك تُبلَّغ تلقائياً بعد ثانية واحدة فتنكشف البطة القاتلة.",
        "how": "عليك لعبة إوزة عادية. ميزتك دفاعية: أي بطة تقتلك لن تستطيع إخفاء جثتك، ويكشف البلاغ التلقائي القاتل (إلا مع بعض الأدوار مثل المحترف).",
        "tips": "• ابقَ قريباً من مجموعات اللاعبين لتعرف من قتلك إن حصل ذلك.\n• لا تتباهى بدورك — ستصبح هدفاً للسفاح في الاجتماع.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/a/a3/Canada.png/revision/latest?cb=20260310135125",
    },
    "avenger": {
        "name_ar": "المنتقم",
        "name_en": "Avenger",
        "emoji": "⚔️",
        "team": "goose",
        "goal": "كنت شاهداً على جريمة قتل؟ تحصل مؤقتاً على قدرة قتل للانتقام.",
        "how": "عند مشاهدة مقتل لاعب أمام عينيك يظهر لك زر القتل لمدة قصيرة. استعمله على القاتل فوراً.",
        "tips": "• ابقَ في مناطق مليئة بالحركة، وخاصة قرب الأهداف الثابتة (مثل المهام العامة).\n• القدرة مؤقتة — إن ضاعت ستنتظر مشاهدة جريمة أخرى.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/5/5d/AvengerIcon.png/revision/latest?cb=20260310124537",
    },
    "astral": {
        "name_ar": "الروحاني",
        "name_en": "Astral",
        "emoji": "✨",
        "team": "goose",
        "goal": "التجسّس على الخريطة عبر إطلاق روحك للتحرك خارج جسدك.",
        "how": "أثناء تجوّلك بروحك تمرّ عبر الجدران لترى مناطق أخرى، لكنك تفقد الرؤية الملوّنة (ترى بالأبيض والأسود) وتكون هشّاً أمام الأعداء.",
        "tips": "• استخدم الروح لكشف أماكن الاختباء (الفتحات) في منتصف الجولة.\n• أرجع لجسدك قبل أن تعلق في منطقة خطيرة.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/2/26/Astral.png/revision/latest?cb=20260310140045",
    },
    "stalker": {
        "name_ar": "المتعقّب",
        "name_en": "Stalker",
        "emoji": "👣",
        "team": "goose",
        "goal": "تتبّع لاعب واحد ومعرفة مكانه في أي لحظة.",
        "how": "اختر هدفاً في بداية المباراة وستظهر لك أسهم/نقطة تدلّ على موقعه على الخريطة المصغّرة.",
        "tips": "• تابع لاعباً مشتبهاً به لتكشف أنه يلاحق ضحية أو يقف وحيداً في مكان مغلق.\n• إن ضاع أثرك بعد اجتماع، حدّد هدفاً من المشتبه بهم من جديد.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/2/2e/StalkerIcon.png/revision/latest?cb=20260310123619",
    },
    "soldier": {
        "name_ar": "الجندي",
        "name_en": "Soldier",
        "emoji": "🪖",
        "team": "goose",
        "goal": "تقتل مرة واحدة في كل مرة تُنجز فيها عدداً كافياً من المهام.",
        "how": "أنجز مهامك حتى يمتلئ عدّاد صغير، فيظهر لك زر القتل. بعد استخدامه يبدأ العدّ من جديد.",
        "tips": "• أنجز مهامك بسرعة لتحصل على أسلحتك في وقت مبكر.\n• سجّل متى استخدمت رصاصتك حتى تثبت براءتك لاحقاً.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/8/80/Soldier-icon.png/revision/latest?cb=20251112203106",
    },
    "scientist": {
        "name_ar": "العالم",
        "name_en": "Scientist",
        "emoji": "🧪",
        "team": "goose",
        "goal": "كشف الجثث المخفية حول الخريطة.",
        "how": "شغّل جهاز المسح ليعرض لك الجثث القريبة على الخريطة المصغّرة. الجهاز يعاد شحنه تلقائياً بعد فترة خمول.",
        "tips": "• امسح في المناطق البعيدة التي يقل فيها العبور.\n• بلاغك عن جثة مكتشفة بالمسح يمنح الإوز وقتاً ثميناً.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/c/c3/Scientist.png/revision/latest?cb=20260310140718",
    },
    "survivalist": {
        "name_ar": "الناجي",
        "name_en": "Survivalist",
        "emoji": "🛡️",
        "team": "goose",
        "goal": "الفوز إن وصلت للثلاثة الأخيرة بعد موت البجع والصقر (وتلعب دور الصمود).",
        "how": "لو بقيت في آخر 3 لاعبين مع موت البجع والصقر، يبدأ عدّاد تنازلي؛ إن صمدت حتى نهايته يفوز الإوز.",
        "tips": "• اجعل مهامك شبه منتهية في وقت مبكر حتى تعطي الانطباع بأن الإوز سيفوز.\n• الاختفاء في اللحظات الأخيرة خطة مشروعة.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/5/59/Survivalist_.png/revision/latest?cb=20260310140243",
    },
    "fortune_teller": {
        "name_ar": "العرّاف",
        "name_en": "Fortune Teller",
        "emoji": "🔮",
        "team": "goose",
        "goal": "معرفة المشتبه بهم المحتملين في قتل الضحية.",
        "how": "عندما تُبلغ عن جثة، يعرض لك الاجتماع في بدايته قائمة بأسماء يمكن أن يكونوا القاتلين (لديهم بطاقة عرافة).",
        "tips": "• أبلغ عن كل جثة تجدها — دورك بلا قيمة بدون بلاغ.\n• اذكر القائمة بوضوح في الاجتماع قبل أن يصوّت الناس عشوائياً.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/b/bf/Fortune.png/revision/latest?cb=20260310133301",
    },
    "mortician": {
        "name_ar": "الطبيب الشرعي",
        "name_en": "Mortician",
        "emoji": "⚰️",
        "team": "goose",
        "goal": "معرفة أدوار الموتى لاستنتاج هوية القاتل.",
        "how": "افحص الجثث لتعرف دورها، وعند بدء أي اجتماع تظهر لك أدوار كل الجثث التي فحصتها.",
        "tips": "• اجمع أكبر عدد من الجثث لتكون مصدر معلومة موثوقاً في الاجتماعات.\n• عدم معرفتك للأدوار يدلّ على أن صاحب الرقم كان يستخدم قدرته.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/a/a8/Mortician.png/revision/latest?cb=20260310140435",
    },
    "birdwatcher": {
        "name_ar": "مراقب الطيور",
        "name_en": "Birdwatcher",
        "emoji": "👁️",
        "team": "goose",
        "goal": "رؤية اللاعبين عبر الجدران وكشف المخططات.",
        "how": "عند الوقوف في مكانك وفتح قدرتك، ترى ما خلف الجدران بمدى رؤية محدود، مما يكشف من يقف في مكان مغلق بعيداً عن الأعين.",
        "tips": "• راقب مناطق الجثث والغرف المغلقة.\n• لا تفتح القدرة أمام الناس حتى لا تُتّهم بأنك بطة تختبئ.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/6/6a/WatcherIcon.png/revision/latest?cb=20260310124244",
    },
    "medium": {
        "name_ar": "الوسيط",
        "name_en": "Medium",
        "emoji": "👻",
        "team": "goose",
        "goal": "معرفة عدد الأشباح (اللاعبين الموتى) في المباراة.",
        "how": "بمجرد بدء المباراة يعرض لك البوت/الواجهة عدد الأشباح الحالي. عند زيادة العدد تعرف فوراً أن هناك جريمة جديدة.",
        "tips": "• راقب الرقم بين الجولات وصرّح بالزيادة فوراً — معلومة قيمة للاستنتاج.\n• لا تكشف دورك في أول سؤال لتجنّب السفاح.",
        "image": None,  # ❗ ضع رابط صورة الدور هنا إن توفّرت
    },

    # ─────────────────────────────── البط 🔴 ───────────────────────────────
    "duck": {
        "name_ar": "البطة",
        "name_en": "Duck",
        "emoji": "🦆",
        "team": "duck",
        "goal": "قتل الإوز ومنعهم من إنهاء المهام، والوصول لعدد يمنع الإوز من الفوز بالتصويت.",
        "how": "اقتل اللاعبين، استخدم الفتحات للهروب، ونفّذ التخريب (Sabotage) لتفريق الإوز. مهامك وهمية فلا حاجة لإنجازها.",
        "tips": "• اقتل دائماً قريباً من الفتحات أو في الممرات البعيدة.\n• لا تنفّذ تخريباً وأنت وحدك في الغرفة — المهندس يراه.\n• Claim عشوائي عن دورك يجعلك مشتبهاً به، فاحضّر قصة متسقة.",
        "image": None,  # ❗ ضع هنا رابط صورة البطة (Duck) من اللعبة/الويكي
    },
    "professional": {
        "name_ar": "المحترف",
        "name_en": "Professional",
        "emoji": "🎯",
        "team": "duck",
        "goal": "القتل دون أن يعرف الضحية من قتله، مع تدمير قدرة الكندي.",
        "how": "ضحيّتك لا ترى من قتلها، والإوز تُبلغ تلقائياً عن الجثة بمجرد الاقتراب منها. لا تستطيع الإبلاغ عن الجثث بنفسك، وهذا يحميك من كشف البلاغ التلقائي للكندي.",
        "tips": "• اختر أماكن خالية — البلاغ التلقائي يقتل خطتك فوراً.\n• لا تكن أنت من \"يجد\" الجثث الصامتة، فالأدوار السلبية ستكشفك.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/8/8f/Professional.png/revision/latest/scale-to-width-down/512?cb=20251207081112",
    },
    "assassin": {
        "name_ar": "السفّاح",
        "name_en": "Assassin",
        "emoji": "🗡️",
        "team": "duck",
        "goal": "القتل أثناء الاجتماعات نفسها وليس فقط في الخريطة.",
        "how": "مرتين في المباراة، وخلال الاجتماع، استخدم قدرتك واكتب/اختر دوراً للاعب. إن كان الدور صحيحاً يموت فوراً، وإن أخطأت تموت أنت مكانه.",
        "tips": "• هاجم الإوز الذين كشفوا أدوارهم أو من يبدو دورهم واضحاً (شريف/مهندس).\n• لا تُجازف بالكلمات المهمة — القتل الخاطئ يخسرك بطة كاملة.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/8/8c/AssassinIcon.png/revision/latest?cb=20260310131823",
    },
    "morphling": {
        "name_ar": "المتحوّل",
        "name_en": "Morphling",
        "emoji": "🎭",
        "team": "duck",
        "goal": "التنكّر في شكل لاعب آخر لتضليل الإوز وتوريطه.",
        "how": "خُذ \"عينة\" من لاعب (بالبقاء قربه)، ثم استخدم قدرتك لتصبح بنفس شكله لمدة محدودة. القتل أثناء التنكّر يورّط اللاعب الذي تتنكّر بشكله.",
        "tips": "• تنكّر بشخص شكل موثوق ثم اقتل أمام شهود — الإوز سيصوّتون عليه.\n• انتبه لفترة التحوّل؛ انتهاؤها في مكان عام يُدينك.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/3/30/Morphing.png/revision/latest?cb=20251206193152",
    },
    "spy": {
        "name_ar": "الجاسوس",
        "name_en": "Spy",
        "emoji": "🕵️",
        "team": "duck",
        "goal": "معرفة أدوار اللاعبين سرّاً لاستهداف دوريات الإوز.",
        "how": "إذا كنت الشخص الوحيد الذي صوّت على لاعب، يكشف لك الاجتماع دور هذا اللاعب.",
        "tips": "• استخدم التصويت الفردي المتكرر لبناء معلومات استخباراتية.\n• شارك المعلومة مع البط الآخرين لتخطيط قتل دقيق.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/3/36/Spy.png/revision/latest/scale-to-width-down/512?cb=20251207084419",
    },
    "cannibal": {
        "name_ar": "آكل الجثث",
        "name_en": "Cannibal",
        "emoji": "🦴",
        "team": "duck",
        "goal": "إخفاء أدلة القتل بأكل الجثث.",
        "how": "مرة واحدة في المباراة يمكنك أكل جثة كاملة فتختفي ولا يستطيع أحد الإبلاغ عنها.",
        "tips": "• استخدمها بعد قتل شخص في منطقة مزدحمة لتشتيت الإوز.\n• احتفظ بها حتى الاجتماع مهم: اختفاء جثة وسط اللعب يسبب فوضى مفيدة لك.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/b/be/Cannibal_Icon.png/revision/latest?cb=20260530212934",
    },
    "demolitionist": {
        "name_ar": "المفخّخ",
        "name_en": "Demolitionist",
        "emoji": "💣",
        "team": "duck",
        "goal": "قتل اللاعبين بالقنابل بدلاً من الأسلحة المباشرة.",
        "how": "ازرع قنبلة على لاعب، فيبدأ عدّاد. اللاعب المصاب يمكنه تمرير القنبلة لغيره، وإن انفجرت وهو يحملها يموت وحدها غالباً.",
        "tips": "• ازرعها على من يجلس مع مجموعة لتزرع الفوضى والاتهامات.\n• على الكارثة أن تسبّب اجتماعات — استغل الارتباك لقتل آخر.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/6/6e/Demolitionist.png/revision/latest/scale-to-width-down/512?cb=20251207072619",
    },
    "identity_thief": {
        "name_ar": "سارق الهوية",
        "name_en": "Identity Thief",
        "emoji": "🪞",
        "team": "duck",
        "goal": "التحوّل إلى شكل آخر ضحية قتلتها حتى يقام الاجتماع.",
        "how": "بعد كل قتل تتحوّل تلقائياً إلى هيئة الضحية. إن رآك أحد بهيئة الضحية وأنكرت الضحية وجودها، تكون قد ورّطت الجميع.",
        "tips": "• اقتل شخصاً معروفاً بشكله واسمه ليكون التنكّر مقنعاً.\n• ابتعد عن مهام الضحية التي تعرفها جيداً، فالفشل فيها يكشفك.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/3/31/Identitythief.png/revision/latest/scale-to-width-down/512?cb=20251206193850",
    },
    "silencer": {
        "name_ar": "الصامت",
        "name_en": "Silencer",
        "emoji": "🤐",
        "team": "duck",
        "goal": "إسكات لاعب في الاجتماع لمنعه من فضح البط.",
        "how": "استخدم قدرتك على لاعب فيبدأ الاجتماع وهو غير قادر على الكلام — عملياً يُقتل أو يُطرد بسهولة. عيبك: لا تستطيع استخدام الفتحات.",
        "tips": "• أسكِت الشاهد الذي رآك، أو اللاعب الذي يمتلك معلومة موثوقة.\n• بدون فتحات، اعتمد على القتل في المناطق المزدحمة والهروب بين الناس.",
        "image": None,  # ❗ ضع رابط صورة الصامت إن توفّرت
    },
    "party": {
        "name_ar": "صاحب الحفلة",
        "name_en": "Party",
        "emoji": "🎉",
        "team": "duck",
        "goal": "إرباك الاجتماعات وتشويه أصوات اللاعبين لجعل المعلومات غير موثوقة.",
        "how": "استخدم قدرتك على لاعب فيصبح صوته حاداً/مضحكاً في الاجتماع، مما يصعّب الفهم والمصداقية.",
        "tips": "• امنح \"الحفلة\" للاعب الذي يقدّم أدلة مهمة لتشويه شهادته.\n• ادّعِ أنك إوز واعرض \"مساعدتك\" في كشف الفوضى.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/6/60/PartyIcon.png/revision/latest?cb=20260310132440",
    },

    # ────────────────────────────── محايدون 🟡 ──────────────────────────────
    "dodo": {
        "name_ar": "الدودو",
        "name_en": "Dodo Bird",
        "emoji": "🦤",
        "team": "neutral",
        "goal": "الفوز بطريقة واحدة فقط: أن يُصوّت الجميع على طردك من المباراة!",
        "how": "لا تفوز إن قتلك أحد، بل إن طُردت بالتصويت. مهامك وهمية، ومهمتك الحقيقية أن تبدو مشبوهاً بما يكفي للحصول على أعلى عدد أصوات دون أن تُقتل.",
        "tips": "• اجعل نفسك مشتبهاً به \"بالمقدار الصحيح\" — لا مبتدئاً ولا بريئاً تماماً.\n• اقترب من الجثث واتركها بدون بلاغ حتى \"تُمسك\".\n• الشريف لا يموت إن قتلك، والدودو المنافس (Dueling Dodos) هدف منفصل.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/7/7c/DodoIcon.png/revision/latest?cb=20260309193053",
    },
    "pelican": {
        "name_ar": "البجع",
        "name_en": "Pelican",
        "emoji": "🦢",
        "team": "neutral",
        "goal": "الفوز كآخر من يبقى حياً. لا يوجد حلفاء ولا مهام حقيقية.",
        "how": "ابتلع اللاعبين أحياءً (Swallow) — لا يموتون فوراً بل يبقون في بطنك حتى يُقام أي اجتماع، فيُهضمون ويموتون، أو تموت أنت فيخرجون من بطنك. مع بقاء 3 لاعبين غير مُبتلعين يبدأ \"مطاردة البجع\" بعدّاد تفوز فيه إن انتهى الوقت.",
        "tips": "• لا تبتلع بسرعة: كل ابتلاع يزيد فترة التهدئة (Cooldown).\n• استغل قنابل المفخّخ — يمكن تمريرها للبجع وقتله من الداخل.\n• البجع لا يمكن أن يوجد مع النسر/الغراب/الفلكن في نفس المباراة.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/c/cf/Pelican_Icon.png/revision/latest?cb=20221230102054",
    },
    "pigeon": {
        "name_ar": "الحمامة",
        "name_en": "Pigeon",
        "emoji": "🕊️",
        "team": "neutral",
        "goal": "نشر العدوى على كل اللاعبين الآخرين في جولة واحدة للفوز فوراً.",
        "how": "لديك قدرة \"إصابة/عدوى\"؛ عليك ملامسة كل اللاعبين الأحياء (بين اجتماعين) قبل أن تُقتل أو يُقام اجتماع يفسد العدّ.",
        "tips": "• استهدف التجمعات الكبيرة أولاً ثم اطارد الباقين.\n• ابقَ بعيداً عن الأنظار ولا تجعل مسارك منطقياً ومتوقعاً.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/9/9e/Pigeon.png/revision/latest?cb=20251113131943",
    },
    "vulture": {
        "name_ar": "النسر القمام",
        "name_en": "Vulture",
        "emoji": "🦅",
        "team": "neutral",
        "goal": "الفوز بأكل عدد كافٍ من الجثث (العدد يعتمد على حجم اللوبي).",
        "how": "دور محايد يعتمد على أكل الجثث المنتشرة من قتل البط. كلما زاد القتل زادت فرصك.",
        "tips": "• اتبع أصوات المهام والمناطق البعيدة حيث تتراكم الجثث.\n• لا تأكل كل الجثث فوراً — إن كشفك أحد سيصوّتون عليك كوحش.",
        "image": None,
    },
    "falcon": {
        "name_ar": "الصقر",
        "name_en": "Falcon",
        "emoji": "🪶",
        "team": "neutral",
        "goal": "الفوز كآخر ناجٍ أو بالوصول لآخر 3 لاعبين والصمود حتى انتهاء العدّ التنازلي.",
        "how": "تستطيع قتل من تشاء (بلا حلفاء)، ويمكنك فقط \"تخطي\" التصويت في الاجتماعات.",
        "tips": "• اتبع المهام والأهداف الثابتة التي يجتذب إليها اللاعبون.\n• لا تُظهر قدرتك مبكراً؛ دع الإوز والبط يستنزفون بعضهم أولاً.",
        "image": None,
    },
    "raven": {
        "name_ar": "الغراب",
        "name_en": "Raven",
        "emoji": "🐦‍⬛",
        "team": "neutral",
        "goal": "الفوز كآخر ناجٍ، مع قدرة على مغادرة الاجتماعات مؤقتاً لقتل أدوار محددة.",
        "how": "خلال الاجتماع يمكنك الخروج مؤقتاً لتنفيذ قتل مستهدف، وتكسب قدرة القتل في الخريطة إن مات كل البط. مهامك وهمية.",
        "tips": "• حدّد هدفك من قائمة الأدوار المطلوبة قبل أن تخرج.\n• استغل مقتل البط جميعاً لتحصل على حرية الحركة والقتل.",
        "image": None,
    },
}

PER_PAGE = 8  # عدد أزرار الأدوار في كل صفحة (5 في الصف الأول + 3 في الثاني)

# الأدوار الشهيرة التي تظهر أولاً في اللوحة (الصفحة الأولى)
FEATURED_ROLES: Tuple[str, ...] = ("goose", "duck", "dodo", "sheriff", "pelican", "engineer")

# ══════════════════════════════════════════════════════════════════════════════
# 3) بناء الرسائل (Embeds)
# ══════════════════════════════════════════════════════════════════════════════


def build_role_embed(role_key: str) -> discord.Embed:
    """يبني بطاقة الدور: الاسم عربي/إنجليزي + الشرح + لون الفئة + صورة الدور."""
    role = ROLES[role_key]
    team = TEAMS[role["team"]]

    embed = discord.Embed(
        title=f"{role['emoji']} {role['name_ar']}  •  {role['name_en']}",
        description=f"**الفئة:** {team['label']}\n**الدور رقم:** `{role_key}`",
        color=team["color"],
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="🎯 الهدف", value=role["goal"], inline=False)
    embed.add_field(name="🕹️ طريقة اللعب", value=role["how"], inline=False)
    embed.add_field(name="💡 نصائح", value=role["tips"], inline=False)

    if role.get("image"):
        embed.set_image(url=role["image"])

    embed.set_footer(text="Goose Goose Duck • دليل الأدوار بالعربي • رسالة خاصة بك وحدك")
    return embed


def total_pages() -> int:
    return max(1, (len(ROLES) + PER_PAGE - 1) // PER_PAGE)


def ordered_role_keys() -> List[str]:
    """ترتيب العرض: الأدوار الشهيرة أولاً ثم باقي الأدوار بترتيب القاموس."""
    featured = [key for key in FEATURED_ROLES if key in ROLES]
    rest = [key for key in ROLES if key not in featured]
    return featured + rest


def page_roles(page: int) -> List[str]:
    keys = ordered_role_keys()
    return keys[page * PER_PAGE : (page + 1) * PER_PAGE]


def build_panel_embed(page: int) -> discord.Embed:
    """اللوحة الرئيسية: دليل مختصر + دلالة الألوان + رقم الصفحة."""
    role_names = "\n".join(
        f"{TEAMS[ROLES[k]['team']]['emoji']} **{ROLES[k]['name_ar']}** — {ROLES[k]['name_en']}"
        for k in page_roles(page)
    )
    embed = discord.Embed(
        title="🦢 دليل أدوار Goose Goose Duck (بالعربي)",
        description=(
            "اضغط على زر الدور لتظهر لك بطاقته الكاملة **لك وحدك** 🤫\n"
            "(الرسالة تُرسل بشكل خاص: لا يراها أحد غيرك في الروم)\n\n"
            "**دلالة الألوان:**\n"
            "🟢 أخضر = إوز (Goose)  •  🔴 أحمر = بط (Duck)  •  🟡 أصفر = محايد (Neutral)"
        ),
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name=f"📖 أدوار هذه الصفحة ({len(page_roles(page))})", value=role_names or "—", inline=False)
    embed.set_footer(text=f"صفحة {page + 1} من {total_pages()} • {len(ROLES)} دوراً متاحاً")
    return embed


# ══════════════════════════════════════════════════════════════════════════════
# 4) حماية بسيطة من السبام (Cooldown لكل مستخدم)
# ══════════════════════════════════════════════════════════════════════════════

_cooldowns: Dict[int, float] = {}
_cooldown_lock = threading.Lock()


def cooldown_remaining(user_id: int) -> float:
    """يُرجع عدد الثواني المتبقية قبل السماح للمستخدم بالضغط مرة أخرى (0 = مسموح)."""
    if ACTION_COOLDOWN <= 0:
        return 0.0
    now = time.monotonic()
    with _cooldown_lock:
        # تنظيف بسيط حتى لا يكبر القاموس بلا حدود
        if len(_cooldowns) > 5000:
            for key in [k for k, v in _cooldowns.items() if now - v > 60]:
                _cooldowns.pop(key, None)
        last = _cooldowns.get(user_id, 0.0)
        remaining = ACTION_COOLDOWN - (now - last)
        if remaining > 0:
            return remaining
        _cooldowns[user_id] = now
        return 0.0


def guild_allowed(interaction: discord.Interaction) -> bool:
    """قائمة بيضاء اختيارية للسيرفرات + رفض الرسائل الخاصة."""
    if interaction.guild is None:
        return False
    if ALLOWED_GUILD_IDS and interaction.guild.id not in ALLOWED_GUILD_IDS:
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
# 5) واجهة الأزرار التفاعلية
# ══════════════════════════════════════════════════════════════════════════════


class RoleButton(discord.ui.Button):
    """زر دور واحد: الإجابة تظهر للضاغط فقط (ephemeral)."""

    def __init__(self, role_key: str, row: int):
        role = ROLES[role_key]
        team = TEAMS[role["team"]]
        styles = {
            "goose": discord.ButtonStyle.success,  # أخضر
            "duck": discord.ButtonStyle.danger,    # أحمر
            "neutral": discord.ButtonStyle.secondary,  # رمادي (لا يوجد أصفر في ديسكورد)
        }
        super().__init__(
            label=f"{role['emoji']} {role['name_ar']}",
            style=styles.get(role["team"], discord.ButtonStyle.secondary),
            custom_id=f"ggd:role:{role_key}"[:100],
            row=row,
        )
        self.role_key = role_key

    async def callback(self, interaction: discord.Interaction) -> None:
        if not guild_allowed(interaction):
            await interaction.response.send_message("❌ هذا البوت غير مخصّص لهذا السيرفر.", ephemeral=True)
            return

        remaining = cooldown_remaining(interaction.user.id)
        if remaining > 0:
            await interaction.response.send_message(
                f"⏳ على راحتك! جرّب مرة أخرى بعد {remaining:.1f} ثانية.",
                ephemeral=True,
                delete_after=3,
            )
            return

        # ⬅️ السطر الأهم: ephemeral=True تعني أن الرسالة للضاغط وحده
        await interaction.response.send_message(embed=build_role_embed(self.role_key), ephemeral=True)


class RoleBoardView(discord.ui.View):
    """لوحة الأزرار: أدوار الصفحة الحالية + التنقل بين الصفحات."""

    def __init__(self, page: int = 0):
        super().__init__(timeout=None)  # لا تنتهي صلاحية الأزرار
        self.page = max(0, min(page, total_pages() - 1))

        current = page_roles(self.page)
        for index, role_key in enumerate(current):
            self.add_item(RoleButton(role_key, row=0 if index < 5 else 1))

        nav_row = 1 if len(current) <= 5 else 2

        prev_button = discord.ui.Button(
            label="⬅️ السابق", style=discord.ButtonStyle.primary, row=nav_row, disabled=self.page == 0
        )
        page_button = discord.ui.Button(
            label=f"📄 {self.page + 1}/{total_pages()}",
            style=discord.ButtonStyle.secondary,
            row=nav_row,
            disabled=True,
        )
        next_button = discord.ui.Button(
            label="التالي ➡️",
            style=discord.ButtonStyle.primary,
            row=nav_row,
            disabled=self.page >= total_pages() - 1,
        )
        random_button = discord.ui.Button(
            label="🎲 دور عشوائي", style=discord.ButtonStyle.primary, row=nav_row
        )

        prev_button.callback = self._go_prev
        next_button.callback = self._go_next
        random_button.callback = self._random

        self.add_item(prev_button)
        self.add_item(page_button)
        self.add_item(next_button)
        self.add_item(random_button)

    async def _go_prev(self, interaction: discord.Interaction) -> None:
        target = max(0, self.page - 1)
        await interaction.response.edit_message(embed=build_panel_embed(target), view=RoleBoardView(target))

    async def _go_next(self, interaction: discord.Interaction) -> None:
        target = min(total_pages() - 1, self.page + 1)
        await interaction.response.edit_message(embed=build_panel_embed(target), view=RoleBoardView(target))

    async def _random(self, interaction: discord.Interaction) -> None:
        if not guild_allowed(interaction):
            await interaction.response.send_message("❌ هذا البوت غير مخصّص لهذا السيرفر.", ephemeral=True)
            return
        remaining = cooldown_remaining(interaction.user.id)
        if remaining > 0:
            await interaction.response.send_message(
                f"⏳ انتظر {remaining:.1f} ثانية.", ephemeral=True, delete_after=3
            )
            return
        picked = random.choice(list(ROLES.keys()))
        await interaction.response.send_message(embed=build_role_embed(picked), ephemeral=True)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item
    ) -> None:
        log.exception("خطأ في زر %s: %s", type(item).__name__, error)
        message = "⚠️ حدث خطأ غير متوقّع، جرّب مرة أخرى."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# 6) العميل (Bot)
# ══════════════════════════════════════════════════════════════════════════════

intents = discord.Intents.none()
intents.guilds = True  # لازمة لعمل الأوامر والأزرار
if ENABLE_PREFIX_COMMANDS:
    # أمر !roles يحتاج هذه الصلاحية (Message Content Intent) وتفعيلها من لوحة المطوّرين
    intents.guild_messages = True
    intents.message_content = True

client = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
    activity=discord.Game(name="🦢 دليل الأدوار | /roles"),
    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
)


@client.event
async def setup_hook() -> None:
    """تسجيل الأوامر: في سيرفر محدّد (فوري) أو عالمياً."""
    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            client.tree.copy_global_to(guild=guild)
            synced = await client.tree.sync(guild=guild)
        else:
            synced = await client.tree.sync()
        log.info("تم تسجيل %d أمر سلاش.", len(synced))
    except discord.HTTPException as error:
        log.error("فشل تسجيل الأوامر: %s", error)


@client.event
async def on_ready() -> None:
    log.info("✅ البوت جاهز: %s | السيرفرات: %d", client.user, len(client.guilds))
    if ENABLE_PREFIX_COMMANDS:
        log.info("تم تفعيل أمر البريفكس !roles")
    else:
        log.info("أمر !roles معطّل (يمكن تفعيله بـ ENABLE_PREFIX_COMMANDS=true)")


@client.event
async def on_guild_join(guild: discord.Guild) -> None:
    log.info("سيرفر جديد: %s (%s)", guild.name, guild.id)
    if ALLOWED_GUILD_IDS and guild.id not in ALLOWED_GUILD_IDS:
        log.warning("سيرفر غير مسموح (%s) — سيتم الخروج منه.", guild.id)
        try:
            await guild.leave()
        except discord.HTTPException:
            pass


# ────────────────────────────── الأوامر ──────────────────────────────


@client.tree.command(name="roles", description="📖 إرسال لوحة دليل أدوار Goose Goose Duck")
@app_commands.describe(channel="روم آخر تُرسل فيه اللوحة (يحتاج صلاحية إدارة الرسائل)")
@app_commands.guild_only()
async def roles_slash(
    interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None
) -> None:
    if not guild_allowed(interaction):
        await interaction.response.send_message("❌ هذا البوت غير مخصّص لهذا السيرفر.", ephemeral=True)
        return

    embed = build_panel_embed(0)
    view = RoleBoardView(0)

    # إرسال اللوحة في نفس الروم: الرسالة عامة، لكن كل إجابة زر تبقى خاصة بالضاغط
    if channel is None or channel.id == interaction.channel_id:
        await interaction.response.send_message(embed=embed, view=view)
        return

    # إرسال إلى روم آخر: نتأكد من صلاحيات المستخدم والبوت قبل النشر
    user_perms = channel.permissions_for(interaction.user)
    if not (user_perms.manage_messages or user_perms.manage_guild):
        await interaction.response.send_message(
            "❌ لنشر اللوحة في روم آخر تحتاج صلاحية **إدارة الرسائل**.", ephemeral=True
        )
        return

    me = channel.guild.me
    bot_perms = channel.permissions_for(me) if me else None
    if bot_perms and (not bot_perms.send_messages or not bot_perms.embed_links):
        await interaction.response.send_message(
            "❌ لا أملك صلاحية **إرسال الرسائل / روابط التضمين** في ذلك الروم.", ephemeral=True
        )
        return

    try:
        await channel.send(embed=embed, view=view)
    except discord.Forbidden:
        await interaction.response.send_message("❌ لا أستطيع الإرسال في ذلك الروم.", ephemeral=True)
        return

    await interaction.response.send_message(f"✅ تم إرسال اللوحة في {channel.mention}", ephemeral=True)


if ENABLE_PREFIX_COMMANDS:

    @client.command(name="roles")
    @commands.guild_only()
    @commands.cooldown(1, 10.0, commands.BucketType.user)
    @commands.cooldown(3, 60.0, commands.BucketType.channel)
    async def roles_prefix(ctx: commands.Context) -> None:
        """!roles — يرسل لوحة الأدوار في الروم الحالي."""
        if ctx.guild and ALLOWED_GUILD_IDS and ctx.guild.id not in ALLOWED_GUILD_IDS:
            return
        await ctx.send(embed=build_panel_embed(0), view=RoleBoardView(0))


@client.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ انتظر {error.retry_after:.1f} ثانية قبل إعادة الأمر.", delete_after=5)
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        log.warning("خطأ في أمر البريفكس: %s", error)


@client.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    log.warning("خطأ في أمر السلاش: %s", error)
    message = "⚠️ حدث خطأ أثناء تنفيذ الأمر."
    if isinstance(error, app_commands.CheckFailure):
        message = "❌ هذا الأمر غير متاح خارج السيرفرات."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# 7) خادم Flask للإبقاء على الحياة (Keep-Alive 24/7)
#    ملاحظة أمنية: وضع التصحيح (Debug) مُعطّل، ولا توجد أي نقطة نهاية تنفيذية — الفحص فقط.
# ══════════════════════════════════════════════════════════════════════════════

flask_app = Flask(__name__)
flask_app.config["MAX_CONTENT_LENGTH"] = 4096
flask_app.config["PROPAGATE_EXCEPTIONS"] = False

_STARTED_AT = time.time()


@flask_app.after_request
def _security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


def _health_ok() -> bool:
    if not HEALTH_TOKEN:
        return True
    provided = request.headers.get("X-Health-Key", "") or request.args.get("key", "")
    # مقارنة آمنة ضد هجمات التوقيت
    return hmac.compare_digest(provided.encode(), HEALTH_TOKEN.encode())


@flask_app.route("/", methods=["GET", "HEAD"])
@flask_app.route(KEEPALIVE_PATH, methods=["GET", "HEAD"])
def health():
    """نقطة فحص بسيطة — لا تكشف أي بيانات حسّاسة (لا توكن ولا أسماء لاعبين)."""
    if not _health_ok():
        return jsonify({"status": "forbidden"}), 403

    # ملاحظة: client.latency تكون NaN قبل الاتصال بديسكورد، لذا نتحقق منها بأمان
    latency = client.latency
    payload = {
        "status": "ok",
        "service": "ggd-roles-bot",
        "uptime_seconds": int(time.time() - _STARTED_AT),
        "guilds": len(client.guilds),
        "latency_ms": round(latency * 1000) if latency and math.isfinite(latency) else None,
    }
    return jsonify(payload), 200


def start_keepalive_server() -> None:
    """يشتغل في خيط منفصل حتى لا يمنع البوت من العمل."""
    from werkzeug.serving import make_server

    server = make_server("0.0.0.0", PORT, flask_app, threaded=True)
    log.info("🌐 خادم الفحص يعمل على المنفذ %s (مسار %s)", PORT, KEEPALIVE_PATH)
    server.serve_forever()


def start_self_ping() -> None:
    """يقرع البوت لنفسه كل فترة حتى لا توقفه منصّات الاستضافة المجانية عند الخمول."""
    if not PUBLIC_URL:
        log.info("ℹ️ لم يتم ضبط PUBLIC_URL — تخطّي القرع الذاتي (استخدم UptimeRobot بدلاً منه).")
        return

    url = PUBLIC_URL.rstrip("/") + KEEPALIVE_PATH
    if HEALTH_TOKEN:
        url += f"?key={HEALTH_TOKEN}"

    def ping_loop() -> None:
        while True:
            time.sleep(SELF_PING_SECONDS)
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "ggd-roles-bot/1.0"})
                with urllib.request.urlopen(request, timeout=20) as response:
                    log.debug("قرع ذاتي: %s", response.status)
            except (urllib.error.URLError, OSError, ValueError) as error:
                log.warning("فشل القرع الذاتي: %s", error)

    threading.Thread(target=ping_loop, daemon=True, name="self-ping").start()
    log.info("🔁 القرع الذاتي مُفعّل كل %d ثانية على %s", SELF_PING_SECONDS, url)


# ══════════════════════════════════════════════════════════════════════════════
# 8) التشغيل
# ══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    if not TOKEN:
        raise SystemExit(
            "❌ متغيّر البيئة DISCORD_TOKEN غير موجود.\n"
            "   لا تكتب التوكن داخل الكود أبداً — ضعه في ملف .env أو في إعدادات الاستضافة."
        )

    threading.Thread(target=start_keepalive_server, daemon=True, name="keepalive").start()
    start_self_ping()

    log.info("🚀 تشغيل البوت...")
    # log_handler=None: نستخدم إعدادات التسجيل الخاصة بنا (وتمنع طباعة التوكن في السجلات)
    client.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    main()

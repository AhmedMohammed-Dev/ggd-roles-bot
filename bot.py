# -*- coding: utf-8 -*-
"""
🦢 بوت ديسكورد — دليل أدوار لعبة Goose Goose Duck (بالعربي)
============================================================
• واجهة أزرار تفاعلية (discord.ui.View / Button) وصفحات متعددة.
• كل ضغطة زر تُرسل Embed خاص بالمستخدم فقط (ephemeral = لا يراه غيره).
• Embed يحتوي: اسم الدور بالعربي والإنجليزي + الشرح + الفئة بلونها + صورة الدور.
• أزرار تصفية بالفئات (إوز / بط / محايد) + زر دور عشوائي + بانر وشعار اللعبة.
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
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, jsonify, request

# ══════════════════════════════════════════════════════════════════════════════
# 1) الإعدادات — كل شيء من متغيرات البيئة (لا شيء سري داخل الكود)
# ══════════════════════════════════════════════════════════════════════════════


def load_dotenv(path: str = ".env") -> int:
    """
    يقرأ ملف .env ويحوّل قيمه إلى متغيرات بيئة — بدون أي مكتبة خارجية.

    لماذا؟ التوكن يجب ألا يُكتب داخل الكود، وملف .env هو الطريقة الأنظف لتشغيله محلياً.
    هذا الدالّة هي البديل المدمج لمكتبة python-dotenv (وتوفّر تثبيت مكتبة إضافية).

    قواعد مهمة:
    • لا يستبدل أي متغيّر موجود مُسبقاً — متغيّرات منصّة الاستضافة (Render/Koyeb) لها الأولوية دائماً.
    • يتجاهل الأسطر الفارغة والتعليقات (#) ويدعم  export KEY=value  والعلامات "" أو ''.
    • يُعيد عدد المتغيّرات التي حمّلها فعلياً (يُستخدم في الاختبارات).
    """
    env_path = Path(path)
    if not env_path.is_absolute():
        env_path = Path(__file__).resolve().parent / env_path
    if not env_path.is_file():
        return 0

    loaded = 0
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export"):
            line = line[len("export") :].lstrip()

        key, sep, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not sep or not key:
            continue
        # اسم متغيّر صالح فقط (A-Z a-z 0-9 _) — يمنع أي سطر غريب من العبث بالبيئة
        if not (key[0].isalpha() or key[0] == "_"):
            continue
        if not all(character.isalnum() or character == "_" for character in key):
            continue

        # القيمة بين علامتين: تُؤخذ كما هي. وإلا: يُحذف التعليق الذي يليها.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()

        if key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded


_dotenv_loaded: int = load_dotenv()


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
# منصّات الاستضافة تضبط PORT تلقائياً. أي قيمة غير صالحة (صفر أو سالبة أو أكبر من الحد)
# تُستبدل بالافتراضي — وإلا فتح الخادم منفذاً عشوائياً وكسر فحص الصحة عند النشر.
_PORT_FROM_ENV: int = env_int("PORT", 8080)
PORT: int = _PORT_FROM_ENV if 1 <= _PORT_FROM_ENV <= 65535 else 8080
KEEPALIVE_PATH: str = env_str("KEEPALIVE_PATH", "/healthz") or "/healthz"
if not KEEPALIVE_PATH.startswith("/"):
    KEEPALIVE_PATH = "/" + KEEPALIVE_PATH
# إن وُضع هذا المفتاح، لن يستجيب مسار الفحص إلا لمن يرسله في الهيدر X-Health-Key (حماية إضافية)
HEALTH_TOKEN: str = env_str("HEALTH_TOKEN")

def resolve_public_url() -> str:
    """يجد رابط التطبيق العام تلقائياً بدل أن تكتبه يدوياً (وقد تكتبه خطأً).

    الترتيب:
      1) PUBLIC_URL          — إن كتبته بنفسك (أي منصّة أو خادم).
      2) RENDER_EXTERNAL_URL — تضبطه Render وحدها لكل خدمة ويب، فهو صحيح دائماً
                               حتى لو تغيّر اسم النطاق الفرعي.
    ولو جاء الرابط بلا ‎https://‎ نُضيفه، لأن هذا أشهر خطأ عند النسخ اليدوي.
    """
    for name in ("PUBLIC_URL", "RENDER_EXTERNAL_URL"):
        value = (os.getenv(name) or "").strip().rstrip("/")
        if not value:
            continue
        if not value.startswith(("http://", "https://")):
            value = "https://" + value
        return value
    return ""


# إذا نُشر البوت على رابط عام، البوت "يقرع" نفسه كل فترة حتى لا ينام السيرفر المجاني
PUBLIC_URL: str = resolve_public_url()
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

# أوضاع اللعب: الأدوار العادية هي "classic"، وبعض الأدوار تظهر في أوضاع خاصة فقط.
MODES: Dict[str, Dict[str, str]] = {
    "classic": {"label": "🎮 الوضع الكلاسيكي (Classic)"},
    "corruption": {"label": "💀 وضع الفساد (Corruption Mode)"},
    "trick_or_treat": {"label": "🎃 حلوى أو خدعة (Trick or Treat)"},
    "tlc": {"label": "🍗 «طعم كالدجاج» (Tastes Like Chicken)"},
    "hoot_seek": {"label": "🦉 وضع الغميضة (Hoot & Seek)"},
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

    "gravy": {
        "name_ar": "الجرافي",
        "name_en": "Gravy",
        "emoji": "🍗",
        "team": "goose",
        "goal": "اجمع أكبر «رهان» (Bounty) بإنجاز المهام، وابقَ حياً لتحتفظ بمكسبك، ثم افز مع الإوز.",
        "how": "كل مهمة تنجزها تزيد مبلغ الرهان الخاص بك. وميزتك الدفاعية: لا يستطيع القاتل قتلك إلا إذا كنت وحدك تماماً — فوجودك مع أي لاعب آخر يحميك.",
        "tips": "• تحرّك دائماً داخل مجموعة، ولا تبقَ وحدك أبداً.\n• المال لا قيمة له إن مِت، فالبقاء أولويتك المطلقة.\n• استغل حصانتك لإنجاز المهام البعيدة الطويلة بأمان.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/5/56/GravyIcon.png/revision/latest?cb=20260309192334",
    },
    "lover_goose": {
        "name_ar": "العاشق (إوزة)",
        "name_en": "Lover (Goose)",
        "emoji": "💗",
        "team": "goose",
        "goal": "ابقَ أنت وشريكك على قيد الحياة حتى النهاية، وافزوا معاً إن كنتما بين آخر ثلاثة لاعبين.",
        "how": "حياتك مرتبطة بحياة لاعب آخر (قد يكون إوزة وقد يكون بطة). إن مات أحدكما مات الآخر فوراً، وإن بقي العاشقان ضمن آخر ثلاثة لاعبين يفوزان معاً مهما كان فريقهما.",
        "tips": "• اعرف شريكك مبكراً وابقَ قريباً منه قدر الإمكان.\n• لا تفشِ أنك عاشق: قتل أحدكما يعني قتل الاثنين بضربة واحدة.\n• العاشقان (Lovers) غير مرتبطين بكيوبيد (Cupid) الذي يصنع العشّاق.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/9/96/Lover.png/revision/latest?cb=20260310133756",
    },
    "mimic": {
        "name_ar": "المحاكي",
        "name_en": "Mimic",
        "emoji": "🎭",
        "team": "goose",
        "goal": "خداع البط بجعله يظنّك واحداً منهم، ثم إحباط خططه من الداخل.",
        "how": "اسمك يظهر بلون البط (الأحمر) لديهم، فيظنونك من فريقهم — لكنك إوزة ولا تعرف من هم البط الحقيقيون. وجودك في المباراة يفتح القتل بين البط بعضها بعضاً (Friendly Fire).",
        "tips": "• البط لا يقتلك لأنه يظنك منهم، لكن الشريف والمدافع قد يفعلان — فابتعد عنهما.\n• لا تقف في مكان التخريب، لأن البط تعرف أنهم لم يفجّروه.\n• لا تستطيع استخدام الفتحات ولا الاختفاء، فأنت مكشوف أمام البط.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/a/a8/Mimic.png/revision/latest?cb=20260219162720",
    },
    "bodyguard": {
        "name_ar": "الحارس الشخصي",
        "name_en": "Bodyguard",
        "emoji": "🦺",
        "team": "goose",
        "goal": "احمِ الهدف المُناط بك من القاتل المأجور (Hitman) واحصل على مكافأة الحماية.",
        "how": "يُختار لك لاعب غير بطّي لحمايته، ويوجد دائماً في المباراة بطة «قاتل مأجور» له نفس الهدف. إن وقع الهجوم بينكما متّ أنت مكانه ونجا هدفك.",
        "tips": "• ابقَ قريباً من هدفك دون أن تلاحقه بشكل مريب، فقد يظنّك بطة.\n• هدفك ليس إوزة دائماً — قد يكون محايداً فلا تمت من أجله بلا داعٍ.\n• وجودك يعني وجود قاتل مأجور معك في المباراة، فانتبه للنقاط البعيدة.",
        "image": None,
    },
    "politician": {
        "name_ar": "السياسي",
        "name_en": "Politician",
        "emoji": "🎙️",
        "team": "goose",
        "goal": "الفوز في حالات تعادل الأصوات، والنجاة من السجن.",
        "how": "عند تعادل الأصوات في أي تصويت تُحسم النتيجة لصالحك فلا تُطرد. ولا يمكن إدخالك إلى السجن في الخرائط التي تحتوي زنزانة.",
        "tips": "• حاول صنع تعادل بينك وبين مشتبه به — التعادل في مصلحتك.\n• لا تفشِ دورك مبكراً، فالتعادل يجعلك مطلوباً للبط.\n• الدور لا يعمل إلا في خريطتي Goosechapel و SS Mother Goose.",
        "maps": "خريطتا Goosechapel و SS Mother Goose فقط",
        "image": None,
    },
    "locksmith": {
        "name_ar": "صانع الأقفال",
        "name_en": "Locksmith",
        "emoji": "🔑",
        "team": "goose",
        "goal": "فتح أبواب السجن في أي وقت دون البحث عن مفتاح أو بطاقة.",
        "how": "في الخرائط التي بها زنزانة تستطيع فتح باب السجن دائماً، فلا تحتاج إلى مفتاح ولا إلى بطاقة.",
        "tips": "• حرّر سجيناً من الإوز فقط، ولا تفتح لِبَطة بالخطأ.\n• اتفق مع السجين قبل الفتح لئلا تُحدث فوضى في الروم.\n• الدور لا يعمل إلا في خريطتي Goosechapel و SS Mother Goose.",
        "maps": "خريطتا Goosechapel و SS Mother Goose فقط",
        "image": None,
    },
    "celebrity": {
        "name_ar": "المشهور",
        "name_en": "Celebrity",
        "emoji": "🌟",
        "team": "goose",
        "goal": "كشف وقوع جريمة قتل فوراً بلفت نظر كل الإوز إليها.",
        "how": "عند مقتلك يستلم كل الإوز إشعاراً فورياً بمقتلك (الإوز فقط، والباقي لا يعلم).",
        "tips": "• البلاغ التلقائي يكشف وجود بطة حتى لو كانت هادئة تماماً.\n• ابقَ قريباً من مجموعات الإوز فلا تضيع فائدة دورك.\n• لا تفشِ دورك، فتصبح هدفاً حرجاً للبط.",
        "image": None,
    },
    "adventurer": {
        "name_ar": "المستكشف",
        "name_en": "Adventurer",
        "emoji": "🧭",
        "team": "goose",
        "goal": "النجاة من الكوارث البيئية والتخريبات القاتلة، وإنجاز المهام بأمان.",
        "how": "لا تستطيع مخاطر الخريطة (الأفخاخ والبيئة) قتلك، وأنت محصّن ضد التخريبات التي تقتل اللاعبين مباشرة.",
        "tips": "• استغل حصانتك لعبور المناطق الخطيرة وإنجاز المهام البعيدة.\n• التخريب «الحاسم» (Critical) الذي ينهي المباراة ما زال قاتلاً لك.\n• متوفّر في Mallard Manor و Jungle Temple و Ancient Sands و Eagleton Springs.",
        "maps": "Mallard Manor، Jungle Temple، Ancient Sands، Eagleton Springs",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/c/cc/Adventurer.png/revision/latest?cb=20260310134040",
    },
    "street_urchin": {
        "name_ar": "ابن الحارة",
        "name_en": "Street Urchin",
        "emoji": "🗝️",
        "team": "goose",
        "goal": "مساعدة الإوز بفتح الأقفال من الداخل.",
        "how": "تستطيع فتح الأقفال من داخل الغرف المغلقة، فتفتح الطريق لنفسك ولمن معك.",
        "tips": "• أنجز مهام المناطق المغلقة بسرعة لتحرير من يعلق خارجها.\n• أخبر الإوز أنك تستطيع الفتح ليتنسّقوا معك.\n• متوفّر في خريطة Ancient Sands فقط.",
        "maps": "خريطة Ancient Sands فقط",
        "image": None,
    },
    "tracker": {
        "name_ar": "المتتبّع",
        "name_en": "Tracker",
        "emoji": "🌪️",
        "team": "goose",
        "goal": "معرفة من كان خارج المباني أثناء العاصفة الرملية.",
        "how": "عند وقوع العاصفة الرملية في خريطة Ancient Sands ترى من هم في الخارج لحظة العاصفة.",
        "tips": "• عاصفة رملية + جثة جديدة = قائمة مشتبهين جاهزة تقريباً.\n• أعلن ما رأيته في الاجتماع قبل أن يصوّت الناس عشوائياً.\n• لا تخلط بينه وبين المتعقّب (Stalker) الذي يتتبّع لاعباً واحداً في كل الخرائط.",
        "maps": "خريطة Ancient Sands فقط",
        "image": None,
    },
    "lobbyist": {
        "name_ar": "اللوبيست",
        "name_en": "Lobbyist",
        "emoji": "🗳️",
        "team": "goose",
        "goal": "قتل بطة مؤكدة باستخدام أصوات الاجتماعات كسلاح.",
        "how": "كل مرة تجمع أصواتاً من ربع عدد اللاعبين تقريباً يفتح لك زر قتل واحد. الأصوات تتراكم لكن القتل لا يتراكم، فبعد استخدامه تبدأ من جديد.",
        "tips": "• لا تطلب الأصوات علناً، فقد يشكّ الناس أنك دودو أو يطردونك.\n• اتفق مع اثنين أو ثلاثة موثوقين على التصويت لك سرّاً.\n• استخدم القتل فور حصولك عليه وإلا ذهبت الأصوات اللاحقة هدراً.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/9/96/LobbyistIcon.png/revision/latest?cb=20260310133519",
    },
    "coroner": {
        "name_ar": "المُبلِّغ",
        "name_en": "Coroner",
        "emoji": "📢",
        "team": "goose",
        "goal": "الحصول على صوت إضافي في الاجتماعات مقابل الإبلاغ عن الجثث.",
        "how": "كل مرة تُبلّغ عن جثة تحصل على صوت إضافي في تصويت الاجتماع الذي يلي البلاغ.",
        "tips": "• أبلِغ عن كل جثة تجدها — البلاغ هو مصدر قوّتك.\n• صوتك المضاعف حاسم في التعادلات والاتهامات المتقاربة.\n• لا تخلط بينه وبين الطبيب الشرعي (Mortician) الذي يكشف أدوار الموتى.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/a/aa/CoronerIcon.png/revision/latest?cb=20260309193340",
    },
    "sensor": {
        "name_ar": "المستشعر",
        "name_en": "Sensor",
        "emoji": "📡",
        "team": "goose",
        "goal": "كشف مواقع كل اللاعبين لفترة قصيرة لمساعدة الإوز.",
        "how": "فعّل قدرتك فتظهر مواقع جميع اللاعبين على الخريطة المصغّرة مؤقتاً، ثم تُعاد شحنها بعد فترة خمول.",
        "tips": "• استخدمها بعد سماع تخريب أو قبل اجتماع لتعرف من كان بعيداً.\n• صِف المواقع بدقة في الاجتماع، فذلك يكشف من كان قرب الجثث.\n• راقب اللاعبين الصامتين الذين لا يظهرون مع المجموعات.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/8/8e/SensorIcon.png/revision/latest?cb=20260309193715",
    },
    "lucid_dreamer": {
        "name_ar": "الحالم الواعي",
        "name_en": "Lucid Dreamer",
        "emoji": "💤",
        "team": "goose",
        "goal": "استغلال وقت الاجتماع لاستكشاف الخريطة.",
        "how": "خلال الاجتماعات يمكنك التجوّل في الخريطة بحرّية، لكن دون قدرة على تنفيذ مهام أو قتل.",
        "tips": "• تحرّك نحو المناطق البعيدة التي لم تزرها لتعرف جغرافيتها.\n• إن ظهرت جثة خلال الاجتماع فسجّل مكانها بدقة.\n• لا تُهدر الوقت كله في التنقل، فرجوعك مرتبط بانتهاء الاجتماع.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/1/10/Lucid_dreamer.png/revision/latest?cb=20260429081524",
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

    "hitman": {
        "name_ar": "القاتل المأجور",
        "name_en": "Hitman",
        "emoji": "🔪",
        "team": "duck",
        "goal": "قتل الهدف المُناط بك للحصول على مكافأة أكبر.",
        "how": "يُختار لك لاعب محدّد كهدف، وقتله يمنحك مكافأة (قتل أسرع). يمكنك قتل غيره لكن بلا مكافأة.",
        "tips": "• لا تطارد هدفك بمسار مباشر، فذلك يكشفك فوراً.\n• إن كان هدفك محمياً بحارس شخصي فاقتل الحارس أولاً أو اصطده منعزلاً.\n• وجودك يعني وجود «حارس شخصي» في المباراة له نفس الهدف.",
        "image": None,
    },
    "snitch": {
        "name_ar": "الواشي",
        "name_en": "Snitch",
        "emoji": "🚔",
        "team": "duck",
        "goal": "سجن من تشتبه به بجعل صوتك الوحيد عليه.",
        "how": "إن كنت الشخص الوحيد الذي يصوّت على لاعب في الاجتماع، يُدخل هذا اللاعب السجن.",
        "tips": "• صوت فردي على مشتبه به أفضل من تصويت جماعي يُطلقه.\n• لا تكرّرها بذات الطريقة كل اجتماع حتى لا يُفهم دورك.\n• السجن ليس قتلاً، فقد يعود اللاعب لاحقاً.\n• متوفّر في Goosechapel و SS Mother Goose فقط.",
        "maps": "خريطتا Goosechapel و SS Mother Goose فقط",
        "image": None,
    },
    "ninja": {
        "name_ar": "النينجا",
        "name_en": "Ninja",
        "emoji": "🥷",
        "team": "duck",
        "goal": "قتل لاعبين دفعة واحدة لتفريغ اللوبي بسرعة.",
        "how": "تقتل كل من في مدى سلاحك بضغطة واحدة (لاعبَين عادةً)، لكن فترة التهدئة ثلاث أضعاف. تتعافى أسرع داخل الممرات الممنوعة.",
        "tips": "• اصطد اثنين يقفان معاً — قتل مزدوج يقلب المباراة.\n• التهدئة الطويلة تعني أن كل استخدام يجب أن يكون محسوباً.\n• خطّط مسارك حول الممرات الممنوعة للاستفادة من التعافي الأسرع.\n• متوفّر في Jungle Temple و Ancient Sands.",
        "maps": "Jungle Temple و Ancient Sands",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/2/21/Ninja.png/revision/latest/scale-to-width-down/512?cb=20251207064230",
    },
    "undertaker": {
        "name_ar": "حامل الجثث",
        "name_en": "Undertaker",
        "emoji": "🪦",
        "team": "duck",
        "goal": "إخفاء الجثث بسحبها بعيداً عن أعين الإوز.",
        "how": "تستطيع سحب الجثث معك، لكن بسرعة أقل من المشي العادي.",
        "tips": "• اسحب الجثة بعيداً عن مسارات المهام لتأخير الاكتشاف.\n• لا تسحب جثة أمام شهود، فذلك يكشفك على الفور.\n• استغل الوقت المكتسب لقتل لاعب آخر.\n• متوفّر في Jungle Temple و The Basement و Ancient Sands و Bloodhaven و Eagleton Springs و The Carnival.",
        "maps": "Jungle Temple، The Basement، Ancient Sands، Bloodhaven، Eagleton Springs، The Carnival",
        "image": None,
    },
    "invisibility": {
        "name_ar": "الخفي",
        "name_en": "Invisibility",
        "emoji": "👤",
        "team": "duck",
        "goal": "الاختفاء للهروب أو للاقتراب من الضحية دون كشف.",
        "how": "فعّل قدرتك لتصبح غير مرئي مؤقتاً، لكنك لا تستطيع رؤية اللاعبين الآخرين أثناء الاختفاء.",
        "tips": "• استعملها للهروب بعد قتل مرصود، أو للوصول خلف مجموعة.\n• لأنك لا ترى أحداً فقد تصطدم بلاعب وتنكشف بسرعة.\n• اختر مساراً تعرفه جيداً قبل الاختفاء.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/e/e1/Invisible.png/revision/latest?cb=20251206211014",
    },
    "serial_killer": {
        "name_ar": "القاتل المتسلسل",
        "name_en": "Serial Killer",
        "emoji": "🩸",
        "team": "duck",
        "goal": "قتل أهدافك واحداً بعد آخر لتصغير اللوبي بسرعة.",
        "how": "يُختار لك هدف عشوائي (غير بطة وغير المحاكي) ويظهر سهم أحمر يدلّك عليه. قتل هدفك يخفض تهدئة القتل ثانيتين، وقتل غيره يزيدها 4 ثوانٍ. عند موت هدفك يُختار لك هدف جديد، والتهدئة لا تُصفَّر بعد الاجتماعات.",
        "tips": "• لا تطارد السهم مباشرة أمام الجميع؛ ارسم مساراً غير مباشر.\n• إن كان هدفك داخل مجموعة فافتعل تخريباً يفرّقهم.\n• هدفك يتغيّر عند موته، فلا تتشبّث بخطة واحدة.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/3/3c/Serialkiller.png/revision/latest/scale-to-width-down/512?cb=20251207083130",
    },
    "warlock": {
        "name_ar": "الساحر",
        "name_en": "Warlock",
        "emoji": "🦗",
        "team": "duck",
        "goal": "قتل اللاعبين بسرب جراد قاتل بدل استخدام التخريبات.",
        "how": "لا تستطيع استخدام التخريبات العادية؛ بدلاً منها تستدعي سرب جراد. من يبقى داخل السرب عند انتهائه يموت.",
        "tips": "• استدرج الإوز إلى منطقة ضيقة ثم أطلق السرب.\n• توقيت الانتهاء هو كل شيء — راقب من لم يخرج بعد.\n• متوفّر في خريطة Ancient Sands فقط.",
        "maps": "خريطة Ancient Sands فقط",
        "image": None,
    },
    "esper": {
        "name_ar": "الإسبير",
        "name_en": "Esper",
        "emoji": "🌀",
        "team": "duck",
        "goal": "قتل الضحية على مهل مع التحدّث إليها قبل موتها.",
        "how": "بدلاً من القتل الفوري، تستخدم قوّتك على لاعب فتبدأ حياته بالنزيف تدريجياً، ويُتاح لك التحدّث معه من بعيد قبل أن يموت.",
        "tips": "• استخدم المحادثة لإرباكه أو تخويفه أو زرع الشك بين الإوز.\n• ضحيتك تستطيع الإبلاغ والإخبار عنك، فاختر من لا يُصدَّق.\n• ابدأ القتل مبكراً، فالنزيف يحتاج وقتاً قبل أن يفتك.",
        "image": None,
    },
    "preacher": {
        "name_ar": "الواعظ",
        "name_en": "Preacher",
        "emoji": "📖",
        "team": "duck",
        "goal": "تعزيز قوة تصويت لاعبين غير بطّين لتوجيه الاجتماع.",
        "how": "تستطيع استهداف لاعب غير بطة لزيادة وزن صوته في التصويت التالي.",
        "tips": "• عزّز صوت بطة متنكّرة أو لاعب تربح من تحرّكه في الاجتماع.\n• استخدمها في الاجتماع الحاسم قبل بدء التصويت مباشرة.\n• المحاكي (Mimic) لا يتأثر بقدرتك، فلا تهدرها عليه.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/4/44/Preacher.png/revision/latest?cb=20260219080836",
    },
    "cupid": {
        "name_ar": "كيوبيد",
        "name_en": "Cupid",
        "emoji": "💘",
        "team": "duck",
        "goal": "ربط حياة لاعبين ببعضهما لقتل اثنين بضربة واحدة.",
        "how": "بعد 20 ثانية من الجولة تضع قلباً ملكياً على لاعب، وبعد 5 ثوانٍ قلباً على آخر. إن لم يلطم أحدهما الآخر خلال 15 ثانية ترتبط حياتهما، فإذا مات أحدهما مات الآخر. الوسوم لا تُصفَّر بعد الاجتماعات، والعشّاق وكيوبيد وحدهم يرون الأسماء بالوردي.",
        "tips": "• ضع الوسم الثاني بعد الاجتماع لتقليل فرصة اكتشافك.\n• اختر لاعبين بعيدين عن بعضهما لزيادة فرصة تكوين الرابط.\n• بعد تكوين الرابط يمكنك القتل بأمان: الكندي المرتبط لن يُكشف.\n• متوفّر في خريطة Eagleton Springs فقط.",
        "maps": "خريطة Eagleton Springs فقط",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/2/20/CupidIcon.png/revision/latest?cb=20260310132719",
    },
    "drone": {
        "name_ar": "الطائرة المسيّرة",
        "name_en": "Drone",
        "emoji": "🛸",
        "team": "duck",
        "goal": "التحرّك بسرعة داخل المناطق الموبوءة واصطياد الإوز.",
        "how": "تستطيع التحوّل، فتكون أسرع في المناطق الموبوءة وأبطأ في المناطق النظيفة.",
        "tips": "• نفّذ القتل داخل المناطق الموبوءة حيث أنت أسرع من ضحيتك.\n• تجنّب المناطق النظيفة، فأنت بطيء فيها وتصبح هدفاً سهلاً.\n• متوفّر في خريطة Eagleton Springs فقط.",
        "maps": "خريطة Eagleton Springs فقط",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/7/73/Drone.jpeg/revision/latest?cb=20230902154859",
    },
    "mime": {
        "name_ar": "المقلّد الصامت",
        "name_en": "Mime",
        "emoji": "🥸",
        "team": "duck",
        "goal": "التحكّم بحركة لاعب آخر وإفساد خططه.",
        "how": "تستطيع مؤقتاً إجبار لاعب على تقليد حركتك تماماً. عيبك: لا تستطيع استخدام الفتحات.",
        "tips": "• اقتحم مكان الجثة وامنع اللاعب من الإبلاغ بإبعاده عن الجثة.\n• يمكنك جرّ لاعب إلى منطقة خطرة أو إبعاده عن مجموعة تحميه.\n• بدون فتحات، اعتمد على القتل في الزحام والهروب وسط الناس.\n• متوفّر في Mallard Manor و Nexus Colony و Jungle Temple و Eagleton Springs و The Carnival و Godzilla.",
        "maps": "Mallard Manor، Nexus Colony، Jungle Temple، Eagleton Springs، The Carnival، Godzilla",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/1/13/Mime-icon.png/revision/latest?cb=20260221185807",
    },
    "clown": {
        "name_ar": "المهرّج",
        "name_en": "Clown",
        "emoji": "🤡",
        "team": "duck",
        "goal": "قتل اللاعبين عبر تكرار «صوت الهيليوم» عليهم.",
        "how": "تمنح لاعباً آخر صوتاً حاداً مضحكاً في الاجتماعات. واستخدامك القدرة عليه مراراً يقتله في النهاية.",
        "tips": "• استهدف من يقدّم أدلة مهمة لتحطيم مصداقيته أولاً.\n• سجّل من استخدمت عليهم القدرة حتى تصل إلى العدد الذي يقتل.\n• لا تستخدمها علناً كل مرة، وإلا فُهم أنك المهرّج.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/6/62/Clown-icon.png/revision/latest?cb=20260221185833",
    },
    "looter": {
        "name_ar": "الناهب",
        "name_en": "Looter",
        "emoji": "💰",
        "team": "duck",
        "goal": "إخفاء الجثث بسرعة وتقصير فترة تهدئة القتل.",
        "how": "تسحب الجثث بسرعة أكبر من المعتاد، وكل جثة تتخلّص منها تقلّل فترة تهدئة القتل.",
        "tips": "• اجعل روتينك: اقتل ثم اسحب الجثة فوراً، فكل جثة تمنحك قتلاً أسرع.\n• اختر أماكن بعيدة عن مسارات الإوز المزدحمة.\n• متوفّر في خريطة Godzilla فقط.",
        "maps": "خريطة Godzilla فقط",
        "image": None,
    },
    "sniper": {
        "name_ar": "القنّاص",
        "name_en": "Sniper",
        "emoji": "🔭",
        "team": "duck",
        "goal": "قتل الإوز من مسافة بعيدة دون الاقتراب منهم.",
        "how": "تدخل وضع القنص فتقتل لاعباً عن بُعد. وفي وضع Hoot & Seek يكون الهدف إسقاط البومة بدل قتل الإوز.",
        "tips": "• اصطد من يقف وحيداً في ممر طويل.\n• بعد الطلقة غيّر موقعك فوراً، فالاتجاه يُكشف من الصوت.\n• غير متوفّر في Jungle Temple و Ancient Sands و Nexus Colony.",
        "maps": "كل الخرائط ما عدا Jungle Temple و Ancient Sands و Nexus Colony",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/3/36/Sniper-icon.png/revision/latest/scale-to-width-down/512?cb=20260219080809",
    },
    "witch_doctor": {
        "name_ar": "الطبيب الساحر",
        "name_en": "Witch Doctor",
        "emoji": "🧿",
        "team": "duck",
        "goal": "قتل اللاعبين «الملعونين» بمجرد التحديق إليهم.",
        "how": "بعض اللاعبين يصبحون ملعونين فتظهر لديك علامة عليهم؛ ثبّت نظرك عليهم لقتلهم.",
        "tips": "• راقب من يحمل علامة اللعنة ثم أطبق بقدرتك.\n• القتل بالنظر لا يحتاج اقتراباً، فاستغل المسافة والزوايا.\n• ابدأ بمن يقف بعيداً عن مجموعة، فموته لا يُلاحظ بسرعة.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/5/5d/Witch_doctor.png/revision/latest?cb=20260429175312",
    },
    "lost_duckling": {
        "name_ar": "الفرخ التائه",
        "name_en": "Lost Duckling",
        "emoji": "🐣",
        "team": "duck",
        "goal": "القتل مع الإوز دون معرفة من هم زملاؤك من البط.",
        "how": "أنت بطة لكنك لا تعرف بقية البط، وهم كذلك لا يعرفونك، لذلك قد يقتلك زميلك بالخطأ.",
        "tips": "• لا تقف داخل مجموعات البط دون معرفة، فقد تُقتل بلا سبب.\n• راقب من لا ينجز مهامه لتكتشف زملاءك.\n• غير متوفّر في خريطة Black Swan.",
        "maps": "كل الخرائط ما عدا Black Swan",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/f/f5/Lostduckling.png.png/revision/latest?cb=20260419151947",
    },
    "carrier": {
        "name_ar": "الحامل",
        "name_en": "Carrier",
        "emoji": "🧬",
        "team": "duck",
        "goal": "توصيل الطفيلي إلى الضحايا وحماية شريكك المرتبط بحياتك.",
        "how": "الحامل والطفيلي دورٌ لبطة واحدة، وحياتهما مرتبطة. أنت تزرع الطفيلي في لاعب ليقتله بعد ثوانٍ، وتستطيع سحبه. لا تستطيع القتل مباشرة ولا استخدام الفتحات، لكنك تستطيع التخريب والتصويت.",
        "tips": "• اتفق مع الطفيلي على مكان الزرع حتى لا يبقى غائباً وقتاً طويلاً.\n• أخبر البط الآخرين بعدم قتل اللاعب الذي زُرع فيه الطفيلي.\n• إن مات الطفيلي مِتّ معه، فاحمِه بأي ثمن.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/b/b7/Carrier.png/revision/latest?cb=20260429081600",
    },
    "parasite": {
        "name_ar": "الطفيلي",
        "name_en": "Parasite",
        "emoji": "🦠",
        "team": "duck",
        "goal": "القتل من داخل اللاعبين والتنكّر بشكل آخر ضحية.",
        "how": "تبدأ كل جولة داخل الحامل. بعد زرعك في لاعب يستطيع قتل الضحية بعد ثوانٍ، وعند موتها تخرج لتأخذ شكلها وتتنقّل بين شكلك وشكل الضحية كل بضع ثوانٍ. تستطيع استخدام الفتحات، لكنك لا تصوّت إلا بالتخطي (Skip).",
        "tips": "• اقتل الضحية بسرعة إن كانت وحيدة ثم اذهب لمكان آمن وخذ شكلك الأصلي.\n• عدم ظهورك وقتاً طويلاً يستدعي الشك، فنسّق التوقيت مع الحامل.\n• ابتعد تماماً عن كبسولة التجديد (Rejuvenation Pod) — استخدامها يقتلك.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/f/f0/Parasite.png/revision/latest?cb=20260429081623",
    },
    "swordsman": {
        "name_ar": "المبارز",
        "name_en": "Swordsman",
        "emoji": "🤺",
        "team": "duck",
        "goal": "قتل كل من يعترض مسار انطلاقتك بضربة واحدة.",
        "how": "تنفّذ هجمة انطلاق (Dash) تقتل كل من في مسارها، لكن فترة التهدئة أطول. الجثث تبقى واقفة حتى يلمسها أحد.",
        "tips": "• اصطد ممراً مزدحماً أو تزاحماً على مهمة واحدة.\n• الجثث الواقفة تمنحك وقتاً قبل الاكتشاف، لكن أول لمسة تكشف الحقيقة.\n• احسب مسار الانطلاق قبل استخدامه، فالتهدئة الطويلة تعني فرصة واحدة.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/0/05/Swordsman_transparent.png/revision/latest?cb=20260813082325",
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
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/6/66/Raven.png/revision/latest?cb=20251206160648",
    },
    "dueling_dodos": {
        "name_ar": "الدودو المتنافسان",
        "name_en": "Dueling Dodos",
        "emoji": "🥊",
        "team": "neutral",
        "goal": "الفوز بالطرد فقط، بعد التخلّص من الدودو الخصم.",
        "how": "أنت ودودو آخر متنافسان. أكمل مهامك الوهمية لتحصل على قدرة قتل خصمك، وبعد موته (بيدك أو بيد غيره) افز بأن تُطرد بالتصويت. وإن طُردت قبل ذلك تخسر.",
        "tips": "• أكمل مهامك الوهمية أولاً — بدون القتل لا فوز.\n• حين يموت خصمك اجعل نفسك مشتبهاً بما يكفي ليصوّتوا عليك، لا ليقتلوك.\n• قتل خصمك أمام شهود قد يمنحك أصواتاً إضافية لصالحك.\n• هناك دودو «عادي» أيضاً، فلا تخلط بين الدورين.",
        "image": None,
    },
    "hawk": {
        "name_ar": "الصقر",
        "name_en": "Hawk",
        "emoji": "🪁",
        "team": "neutral",
        "goal": "الفوز كآخر من يبقى حياً.",
        "how": "محايد بلا حلفاء يفوز بالبقاء الأخير. اشحن قدرتك بالوقوف داخل شعاع حرارة غودزيلا.",
        "tips": "• شحن قدرتك أولوية قبل أي مواجهة.\n• دع الإوز والبط يستنزفان بعضهما ثم اظهر في النهاية.\n• متوفّر في خريطة Godzilla فقط.",
        "maps": "خريطة Godzilla فقط",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/3/3c/Hawk.png/revision/latest?cb=20260309164832",
    },
    "cuckoo": {
        "name_ar": "الوقواق",
        "name_en": "Cuckoo",
        "emoji": "🥚",
        "team": "neutral",
        "goal": "الفوز بوضع عدد كافٍ من البيض.",
        "how": "محايد يفوز بإتمام مهمة البيض المطلوبة داخل الخريطة، بينما يستمر القتل حوله.",
        "tips": "• استغل فوضى القتل والمطاردات لتنفيذ مهمتك بصمت.\n• لا تجعل مسارك منتظماً ومتوقعاً.\n• ابدأ مبكراً، فالوقت يصعب تعويضه في النهاية.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/5/5b/Cuckoo.png/revision/latest?cb=20260429081648",
    },
    "magpie": {
        "name_ar": "العقعق",
        "name_en": "Magpie",
        "emoji": "🐦",
        "team": "neutral",
        "goal": "الفوز بتخمين أدوار اللاعبين تخميناً صحيحاً في اجتماع واحد.",
        "how": "محايد يفوز إن نجح في تخمين عدد كافٍ من الأدوار الصحيحة خلال اجتماع واحد.",
        "tips": "• اجمع ملاحظاتك من الجولات حتى تكون تخميناتك مبنية على أدلة.\n• استغل الاعترافات والاتهامات في الاجتماع بدل التخمين العشوائي.\n• لا تُهدر كل التخمينات في اجتماع ضائع؛ انتظر الاجتماع الذي تجمّعت فيه معلوماتك.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/6/66/Magpie_transparent.png/revision/latest?cb=20260813082305",
    },

    # ──────────── أدوار الأوضاع الخاصة (Corruption / Trick or Treat / TLC / Hoot & Seek) ────────────
    "inquisitor": {
        "name_ar": "المُحقّق",
        "name_en": "Inquisitor",
        "emoji": "🔎",
        "team": "goose",
        "mode": "corruption",
        "goal": "كشف اللاعبين المصابين بالفساد ليعرف الإوز من أصابه.",
        "how": "تحقّق من اللاعبين لتعرف إن كانوا مصابين بالفساد. والبط يظهرون مصابين دائماً، فلا تعتمد عليهم وحدهم في الحكم.",
        "tips": "• حقّق في الصامتين أولاً، فالإصابة تنتشر بالصمت.\n• لا تفشِ نتيجتك كاملة في الاجتماع حتى لا يتحوّل الأمر إلى فوضى.\n• دور خاص بوضع Corruption Mode على خريطة Bloodhaven.",
        "maps": "خريطة Bloodhaven (وضع Corruption)",
        "image": None,
    },
    "saint": {
        "name_ar": "القدّيس",
        "name_en": "Saint",
        "emoji": "😇",
        "team": "goose",
        "mode": "corruption",
        "goal": "إنجاز المهام دون أن يمسّك الفساد.",
        "how": "أنت محصّن ضد آثار الفساد، فيمكنك التعامل مع المناطق الملوّثة دون أن تُصاب.",
        "tips": "• استغل حصانتك للمرور من المناطق التي يخافها الآخرون.\n• حصانتك من الفساد لا تحميك من القتل، فابقَ حذراً.\n• دور خاص بوضع Corruption Mode.",
        "image": None,
    },
    "demon_hunter": {
        "name_ar": "قاتل الشياطين",
        "name_en": "Demon Hunter",
        "emoji": "🔱",
        "team": "goose",
        "mode": "corruption",
        "goal": "مقاتلة الأعداء بالاستفادة من الفساد بدل الخوف منه.",
        "how": "كل مرة تُصاب فيها بالفساد تحصل على قدرة قتل واحدة.",
        "tips": "• لا تتجنّب الفساد تماماً، فهو مصدر سلاحك.\n• استخدم القتلة في اللحظات الحاسمة لا في أول فرصة.\n• دور خاص بوضع Corruption Mode.",
        "image": None,
    },
    "seamstress": {
        "name_ar": "الخيّاطة",
        "name_en": "Seamstress",
        "emoji": "🧵",
        "team": "goose",
        "mode": "corruption",
        "goal": "مقارنة نسبة الفساد بين اللاعبين لكشف المتقدّمين فيه.",
        "how": "مرة في كل جولة تستطيع مقارنة مستوى الفساد بين لاعبين لتعرف من هو الأكثر تلوّثاً.",
        "tips": "• قارن بين مشتبه به ولاعب موثوق لديك.\n• كرّر المقارنة كل جولة لتتابع تطوّر الفساد.\n• دور خاص بوضع Corruption Mode.",
        "image": None,
    },
    "high_priest": {
        "name_ar": "الكاهن الأعظم",
        "name_en": "High Priest",
        "emoji": "🛐",
        "team": "duck",
        "mode": "corruption",
        "goal": "جمع الفساد للفوز بقدرة القتل داخل الاجتماعات.",
        "how": "اجمع الفساد لتحصل على قدرة قتل داخل الاجتماع بتخمين دور لاعب بشكل صحيح.",
        "tips": "• اجمع الفساد مبكراً حتى تكون قادراً في الاجتماعات الحاسمة.\n• خمّن الأدوار الواضحة (شريف/مهندس) لتضمن نجاح التخمين.\n• دور خاص بوضع Corruption Mode.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/5/54/Highpriest.png/revision/latest?cb=20251207191000",
    },
    "initiate": {
        "name_ar": "المريد",
        "name_en": "Initiate",
        "emoji": "🕯️",
        "team": "duck",
        "mode": "corruption",
        "goal": "توليد الفساد لفريق البط عبر الشعائر على الجثث.",
        "how": "تستطيع تنفيذ شعائر على الجثث خلال النهار لتوليد الفساد لصالح فريقك.",
        "tips": "• نفّذ الشعيرة على جثث في مناطق بعيدة لتقليل خطر كشفك.\n• نسّق مع الكاهن الأعظم حتى يجمع الفساد بسرعة.\n• دور خاص بوضع Corruption Mode.",
        "image": None,
    },
    "sin_eater": {
        "name_ar": "آكل الخطايا",
        "name_en": "Sin Eater",
        "emoji": "🍷",
        "team": "duck",
        "mode": "corruption",
        "goal": "جمع الفساد للقتل في منطقة كاملة، والنجاة إن قتلت ما يكفي.",
        "how": "اجمع الفساد لتحصل على قدرة قتل في منطقة واسعة، لكنها تُكلّفك حياتك إن لم تقتل عدداً كافياً من اللاعبين.",
        "tips": "• لا تستخدم القدرة إلا في منطقة مزدحمة (زحام مهمة أو تجمّع).\n• تأكد من عدد الضحايا المطلوب قبل المخاطرة بحياتك.\n• دور خاص بوضع Corruption Mode.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/6/63/Sineater.png/revision/latest?cb=20251207190932",
    },
    "crow": {
        "name_ar": "الغراب (المتحوّل)",
        "name_en": "Crow",
        "emoji": "🐦⬛",
        "team": "neutral",
        "mode": "corruption",
        "goal": "فساد الجميع ثم التحوّل إلى الغراب وقتل من تبقّى.",
        "how": "أفسد كل اللاعبين، وعند اكتمال الفساد تتحوّل إلى الغراب: سرعتك مضاعفة، ولا يمكن قتلك، ويظهر لك زر قتل بتهدئة 3 ثوانٍ. عليك قتل كل من تبقّى داخل الوقت المحدد، وإلا متّ.",
        "tips": "• أنجز الفساد مبكراً، فالوقت بعد التحوّل قصير وشديد الحساسية.\n• بعد التحوّل لا تخف من أحد، لكن لا تُهدر الوقت في مطاردات طويلة.\n• ابدأ بأقرب اللاعبين إليك لتقليل العدد سريعاً.\n• دور خاص بوضع Corruption Mode.",
        "image": "https://static.wikia.nocookie.net/goose-goose-duck/images/f/fa/Crow.png/revision/latest?cb=20230906151835",
    },
    "villager": {
        "name_ar": "القروي",
        "name_en": "Villager",
        "emoji": "🏡",
        "team": "goose",
        "mode": "trick_or_treat",
        "goal": "قتل التوابع (Thralls) وطرد الوحش المتخفي، أو الصمود حتى نهاية الوقت.",
        "how": "تستطيع قتل التوابع، وعليك التصويت على الوحش المتخفي لطرده. والبقاء حياً حتى نهاية الوقت فوز أيضاً.",
        "tips": "• صوّتوا بتركيز على من عليه دلائل أنه الوحش، لا على المشتبه بهم عشوائياً.\n• القتل بلا دليل يقلّل عدد القرويين ويساعد الوحش.\n• دور خاص بوضع Trick or Treat على خرائط Eagleton Springs و The Basement و Goosechapel و Mallard Manor.",
        "maps": "Eagleton Springs، The Basement، Goosechapel، Mallard Manor (وضع Trick or Treat)",
        "image": None,
    },
    "vampire": {
        "name_ar": "مصّاص الدماء",
        "name_en": "Vampire",
        "emoji": "🧛",
        "team": "duck",
        "mode": "trick_or_treat",
        "goal": "قتل القرويين بعضّة تفتك بعد ثوانٍ.",
        "how": "تعضّ لاعباً فيموت بعد ثوانٍ، مما يمنحك مهلة للهروب قبل أن يُكتشف أمره.",
        "tips": "• اعضض ثم تحرّك فوراً؛ فالتأخير قرب الضحية يكشفك.\n• استهدف من هو بعيد عن المجموعات.\n• دور خاص بوضع Trick or Treat.",
        "image": None,
    },
    "thrall": {
        "name_ar": "التابع",
        "name_en": "Thrall",
        "emoji": "🧟",
        "team": "duck",
        "mode": "trick_or_treat",
        "goal": "قتل كل القرويين للفوز مع الوحش.",
        "how": "أنت تابع للوحش، وتستطيع التحدّث مع التوابع الآخرين فقط. والقرويون الموتى يتحوّلون إلى توابع.",
        "tips": "• التنسيق مع الوحش يضاعف قوتكم — استخدموا المحادثة الخاصة.\n• كل قروي يموت يزيد عدد التوابع، فلا تخف من فقدان زميل.\n• دور خاص بوضع Trick or Treat.",
        "image": None,
    },
    "mummy": {
        "name_ar": "المومياء",
        "name_en": "Mummy",
        "emoji": "🧻",
        "team": "duck",
        "mode": "trick_or_treat",
        "goal": "قتل القرويين بالتحوّل إلى المومياء.",
        "how": "تستطيع التحوّل إلى المومياء لقتل القرويين.",
        "tips": "• اختر لحظة التحوّل عند انشغال القرويين بالمهام.\n• لا تتحوّل في مكان مكشوف، فالشكل غريب ويلفت النظر فوراً.\n• دور خاص بوضع Trick or Treat.",
        "image": None,
    },
    "camo_duck": {
        "name_ar": "البطة المموّهة",
        "name_en": "Camo Duck",
        "emoji": "🫥",
        "team": "duck",
        "mode": "tlc",
        "goal": "التخفّي قبل مهاجمة الفريق المنافس في وضع «طعم كالدجاج».",
        "how": "تستطيع أن تصبح غير مرئي مؤقتاً قبل مهاجمة اللاعبين المنافسين.",
        "tips": "• استخدم التخفّي للوصول خلف الفريق المنافس لا للهروب فقط.\n• الدور خاص بوضع Tastes Like Chicken فقط.",
        "image": None,
    },
    "chicken": {
        "name_ar": "الدجاجة",
        "name_en": "Chicken",
        "emoji": "🐔",
        "team": "neutral",
        "mode": "tlc",
        "goal": "إسقاط الفريق المنافس ودعم فريقك في وضع «طعم كالدجاج».",
        "how": "تستطيع مداواة فريقك والقضاء على الفريق المنافس المُنهك.",
        "tips": "• اهتم بمداواة فريقك أولاً، فالفوز هنا جماعي.\n• الدور خاص بوضع Tastes Like Chicken فقط.",
        "image": None,
    },
    "spotter": {
        "name_ar": "المرشد",
        "name_en": "Spotter",
        "emoji": "🛰️",
        "team": "goose",
        "mode": "hoot_seek",
        "goal": "مساعدة القنّاص على إسقاط البومة.",
        "how": "تمسح منطقة للبحث عن البومة: دائرة خضراء تعني أنها قريبة، وحمراء تعني أنها ليست هناك.",
        "tips": "• غطّوا المناطق تباعاً ولا تفصلوا بينكم وبين القنّاص.\n• أبلغ القنّاص فوراً عند ظهور دائرة خضراء.\n• دور خاص بوضع Hoot & Seek.",
        "image": None,
    },
    "owl": {
        "name_ar": "البومة",
        "name_en": "Owl",
        "emoji": "🦉",
        "team": "neutral",
        "mode": "hoot_seek",
        "goal": "إنجاز مهامك والنجاة دون أن يكتشفك الصيادون.",
        "how": "أنت البومة المطلوب إسقاطها: أنجز مهامك وابقَ بعيداً عن أعين الصيادين للفوز.",
        "tips": "• تحرّك في مسارات غير متوقعة وتجنّب المناطق المكشوفة.\n• ابتعد عن مصدر صوت القنّاص وراقب اتجاه المسح.\n• دور خاص بوضع Hoot & Seek.",
        "image": None,
    },
}

PER_PAGE = 10  # عدد أزرار الأدوار في كل صفحة (5 في الصف الأول + 5 في الثاني)

# الأدوار الشهيرة التي تظهر أولاً في اللوحة (الصفحة الأولى)
FEATURED_ROLES: Tuple[str, ...] = ("goose", "duck", "dodo", "sheriff", "pelican", "engineer")

# ══════════════════════════════════════════════════════════════════════════════
# 3) الهوية البصرية — الصور والروابط التي تظهر في كل الرسائل
#    كل رابط هنا من ويكي اللعبة الرسمي، ويفحصه check_images.py مع باقي الصور.
# ══════════════════════════════════════════════════════════════════════════════

WIKI_BASE = "https://goose-goose-duck.fandom.com/wiki/"
PANEL_COLOR = 0x5865F2  # لون اللوحة الرئيسية (بنفسجي ديسكورد)

BRAND: Dict[str, str] = {
    "name": "دليل أدوار Goose Goose Duck",
    # بانر عريض أسفل اللوحة الرئيسية: شعار اللعبة الكامل (1280×720) بدل كتلة نص فقط
    "banner": (
        "https://static.wikia.nocookie.net/goose-goose-duck/images/a/af/"
        "Logot.jpg/revision/latest?cb=20260308184835"
    ),
    # أيقونة مربّعة (512×512) تظهر بجانب العنوان وفي التذييل — دائرية الشكل في ديسكورد
    "logo": (
        "https://static.wikia.nocookie.net/goose-goose-duck/images/d/dd/"
        "Goose.png/revision/latest?cb=20260310135439"
    ),
}

# أزرار تصفية الفئات: التسمية والترتيب الذي تظهر به تحت اللوحة
TEAM_FILTERS: Tuple[Tuple[str, str], ...] = (
    ("goose", "🟢 الإوز"),
    ("duck", "🔴 البط"),
    ("neutral", "🟡 المحايدون"),
)


def wiki_link(role: Dict[str, Any]) -> str:
    """رابط البحث عن الدور على ويكي اللعبة.

    لماذا بحث وليس صفحة مباشرة؟ لأن بعض الأدوار لا صفحة لها على الويكي بعد،
    والرابط المباشر لها يعطي "الصفحة غير موجودة" — أما البحث فيوصل دائماً للنتيجة
    الصحيحة إن وُجدت، ولا ينكسر أبداً إن لم توجد.
    """
    query = urllib.parse.quote_plus(role["name_en"])
    return f"{WIKI_BASE}Special:Search?query={query}&scope=internal"


# ══════════════════════════════════════════════════════════════════════════════
# 4) بناء الرسائل (Embeds)
# ══════════════════════════════════════════════════════════════════════════════


def role_line(role_key: str) -> str:
    """سطر مختصر لدور في قائمة اللوحة: إيموجي الدور + الاسم العربي + الإنجليزي."""
    role = ROLES[role_key]
    return f"{role['emoji']} **{role['name_ar']}** — {role['name_en']}"


def related_roles(role_key: str, limit: int = 3) -> List[str]:
    """أدوار مجاورة من نفس الفئة تُقترح في نهاية البطاقة.

    الترتيب ثابت (لا عشوائية): نبدأ من الدور التالي لدورنا في ترتيب اللوحة ونلفّ على القائمة،
    فالنتيجة نفسها في كل تشغيل — وهذا يمنع تغيّر الشكل عند إعادة تشغيل البوت.
    """
    team = ROLES[role_key]["team"]
    peers = [key for key in ordered_role_keys() if ROLES[key]["team"] == team]
    if len(peers) <= 1:
        return []

    start = peers.index(role_key) if role_key in peers else 0
    picked: List[str] = []
    step = 1
    while len(picked) < min(limit, len(peers) - 1):
        candidate = peers[(start + step) % len(peers)]
        if candidate != role_key:
            picked.append(candidate)
        step += 1
    return picked


def build_role_embed(role_key: str) -> discord.Embed:
    """يبني بطاقة الدور: الاسم عربي/إنجليزي + الشرح + لون الفئة + صورة الدور."""
    role = ROLES[role_key]
    team = TEAMS[role["team"]]

    header = [f"**الفئة:** {team['label']}"]
    if role.get("mode"):
        mode = MODES.get(role["mode"], MODES["classic"])
        header.append(f"**الوضع:** {mode['label']}")
    header.append(f"**المعرّف:** `{role_key}`")
    if not role.get("image"):
        # شفافية: الدور موجود بالشرح الكامل حتى لو لم يُرفع له رسم رسمي على ويكي اللعبة بعد
        header.append("🖼️ *لا تتوفّر صورة رسمية لهذا الدور على ويكي اللعبة بعد.*")
    header.append(f"🔗 [اعرف أكثر عن الدور على ويكي اللعبة]({wiki_link(role)})")

    embed = discord.Embed(
        title=f"{role['emoji']} {role['name_ar']}  •  {role['name_en']}",
        description="\n".join(header),
        color=team["color"],
        timestamp=datetime.now(timezone.utc),
    )
    # سطر علوي يحدد الفئة فوراً قبل قراءة أي كلام
    embed.set_author(
        name=f"{team['emoji']} {team['short']} • {role['name_en']}", icon_url=BRAND["logo"]
    )
    embed.add_field(name="🎯 الهدف", value=role["goal"], inline=False)
    embed.add_field(name="🕹️ طريقة اللعب", value=role["how"], inline=False)
    embed.add_field(name="💡 نصائح", value=role["tips"], inline=False)
    if role.get("maps"):
        embed.add_field(name="🗺️ متاح في", value=role["maps"], inline=False)

    peers = related_roles(role_key)
    if peers:
        embed.add_field(
            name="🧭 أدوار من نفس الفئة",
            value="\n".join(f"• {role_line(key)}" for key in peers),
            inline=False,
        )

    if role.get("image"):
        embed.set_image(url=role["image"])

    embed.set_footer(
        text="Goose Goose Duck • دليل الأدوار بالعربي • رسالة خاصة بك وحدك",
        icon_url=BRAND["logo"],
    )
    return embed


def ordered_role_keys() -> List[str]:
    """ترتيب العرض: الأدوار الشهيرة أولاً ثم باقي الأدوار بترتيب القاموس."""
    featured = [key for key in FEATURED_ROLES if key in ROLES]
    rest = [key for key in ROLES if key not in featured]
    return featured + rest


def filtered_role_keys(team: Optional[str] = None) -> List[str]:
    """أدوار اللوحة: كل الأدوار، أو أدوار فئة واحدة عند استخدام أزرار التصفية."""
    keys = ordered_role_keys()
    if team is None or team not in TEAMS:
        return keys
    return [key for key in keys if ROLES[key]["team"] == team]


def total_pages(team: Optional[str] = None) -> int:
    return max(1, (len(filtered_role_keys(team)) + PER_PAGE - 1) // PER_PAGE)


def page_roles(page: int, team: Optional[str] = None) -> List[str]:
    keys = filtered_role_keys(team)
    start = max(0, page) * PER_PAGE
    return keys[start : start + PER_PAGE]


def build_panel_embed(page: int, team: Optional[str] = None, private: bool = False) -> discord.Embed:
    """اللوحة الرئيسية: شرح الاستخدام + أعداد الفئات + أدوار الصفحة + بانر اللعبة.

    private=True تعني أن هذه نسخة خاصة بالضاغط (بعد ضغط زر تنقل)، فنكتب ذلك في التذييل
    حتى يعرف المستخدم أن تنقلاته في اللوحة العامة لا تحرّك شيئاً عند غيره.
    """
    team = team if team in TEAMS else None
    keys = page_roles(page, team)
    counts = {name: sum(1 for role in ROLES.values() if role["team"] == name) for name in TEAMS}

    embed = discord.Embed(
        title="🦢 دليل أدوار Goose Goose Duck",
        description=(
            "**اضغط على أي دور لتصل بطاقته كاملة — لك وحدك** 🤫\n"
            "الرسالة تُرسل بشكل خاص فلا يراها أحد غيرك في الروم.\n\n"
            "**دلالة الألوان:** 🟢 إوز (Goose) • 🔴 بط (Duck) • 🟡 محايد (Neutral)\n\n"
            "**الأوضاع:** 🎮 Classic • 💀 Corruption • 🎃 Trick or Treat • 🍗 TLC • 🦉 Hoot & Seek\n"
            "**أزرار التصفية** في الأسفل تعرض فئة واحدة فقط، و«دور عشوائي» يختار لك دوراً فوراً.\n"
            + (
                ""
                if private
                else "\n🔒 **التنقل والتصفية يفتحان لك نسخة خاصة بك** — هذه اللوحة لا تتغير على الآخرين."
            )
        ),
        color=PANEL_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=f"{BRAND['name']} • {len(ROLES)} دوراً", icon_url=BRAND["logo"])

    # ثلاثة أعداد في صف واحد: نظرة سريعة على حجم كل فئة قبل التنقل
    for team_key, team_data in TEAMS.items():
        embed.add_field(name=team_data["label"], value=f"**{counts[team_key]}** دوراً", inline=True)

    # أدوار الصفحة في عمودين متجاورين بدل قائمة طويلة واحدة
    half = max(1, math.ceil(len(keys) / 2))
    left, right = keys[:half], keys[half:]
    embed.add_field(
        name=f"📖 أدوار هذه الصفحة ({len(keys)})",
        value="\n".join(role_line(key) for key in left) or "—",
        inline=True,
    )
    if right:
        # اسم حقل فارغ حتى يبقى العمود الثاني بجانب الأول
        embed.add_field(name="\u200b", value="\n".join(role_line(key) for key in right), inline=True)

    embed.set_image(url=BRAND["banner"])
    scope = f"{TEAMS[team]['label']} فقط" if team else "كل الأدوار"
    footer = f"صفحة {page + 1} من {total_pages(team)} • {scope} • {len(ROLES)} دوراً"
    embed.set_footer(text=footer + (" • نسخة خاصة بك" if private else ""), icon_url=BRAND["logo"])
    return embed


# ══════════════════════════════════════════════════════════════════════════════
# 5) حماية بسيطة من السبام (Cooldown لكل مستخدم)
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
# 6) واجهة الأزرار التفاعلية
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
    """لوحة الأزرار: أدوار الصفحة الحالية + التنقل بين الصفحات + تصفية بالفئات."""

    def __init__(self, page: int = 0, team: Optional[str] = None):
        super().__init__(timeout=None)  # لا تنتهي صلاحية الأزرار
        self.team = team if team in TEAMS else None
        self.page = max(0, min(page, total_pages(self.team) - 1))

        current = page_roles(self.page, self.team)
        for index, role_key in enumerate(current):
            self.add_item(RoleButton(role_key, row=0 if index < 5 else 1))

        nav_row = 1 if len(current) <= 5 else 2
        self._add_navigation(nav_row)
        self._add_filters(nav_row + 1)

    # ── التنقل بين الصفحات ──
    def _add_navigation(self, row: int) -> None:
        prev_button = discord.ui.Button(
            label="⬅️ السابق", style=discord.ButtonStyle.secondary, row=row, disabled=self.page == 0
        )
        page_button = discord.ui.Button(
            label=f"📄 {self.page + 1}/{total_pages(self.team)}",
            style=discord.ButtonStyle.secondary,
            row=row,
            disabled=True,
        )
        next_button = discord.ui.Button(
            label="التالي ➡️",
            style=discord.ButtonStyle.secondary,
            row=row,
            disabled=self.page >= total_pages(self.team) - 1,
        )
        # زر العشوائي وحده مميّز باللون الأزرق: هو الأسرع للزوار الجدد
        random_button = discord.ui.Button(
            label="🎲 دور عشوائي", style=discord.ButtonStyle.primary, row=row
        )

        prev_button.callback = self._go_prev
        next_button.callback = self._go_next
        random_button.callback = self._random

        self.add_item(prev_button)
        self.add_item(page_button)
        self.add_item(next_button)
        self.add_item(random_button)

    # ── تصفية الفئات: صف مستقل حتى لا تختلط بالتنقل ──
    def _add_filters(self, row: int) -> None:
        for team_key, label in TEAM_FILTERS:
            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary if self.team == team_key else discord.ButtonStyle.secondary,
                row=row,
                disabled=self.team == team_key,  # الزر النشط يظهر مضغوطاً فلا تتكرّر الضغطة
            )
            button.callback = self._filter_to(team_key)
            self.add_item(button)

        every_button = discord.ui.Button(
            label="📖 كل الأدوار",
            style=discord.ButtonStyle.primary if self.team is None else discord.ButtonStyle.secondary,
            row=row,
            disabled=self.team is None,
        )
        every_button.callback = self._filter_to(None)
        self.add_item(every_button)

    def _filter_to(self, team: Optional[str]):
        """يعيد اللوحة لبدايتها مفلترة على الفئة المختارة (الصفحة تُصفَّر فلا يضيع المستخدم)."""

        async def _callback(interaction: discord.Interaction) -> None:
            await self._show_board(interaction, 0, team)

        return _callback

    async def _show_board(self, interaction: discord.Interaction, page: int, team: Optional[str]) -> None:
        """يعرض لوحة التنقل/التصفية في مكانها الصحيح حسب نوع الرسالة المضغوط عليها.

        المشكلة التي يحلها هذا التابع: اللوحة العامة (من ‎/roles‎) يراها الروم كله، فأي
        تنقل فيها كان يقلب الصفحة على جميع الحاضرين في نفس اللحظة — اثنان يضغطان
        «التالي» في وقت واحد فيتغير الشكل عند الاثنين معاً.

        الحل: أول ضغطة تنقل على اللوحة العامة تفتح للضاغط **نسخة خاصة به** (ephemeral)،
        واللوحة العامة تبقى كما هي ولا تتغير على أحد. أما داخل النسخة الخاصة فالتنقل
        يعدّل الرسالة نفسها في مكانها (فهي له وحده أصلاً).
        """
        if not guild_allowed(interaction):
            await interaction.response.send_message("❌ هذا البوت غير مخصّص لهذا السيرفر.", ephemeral=True)
            return

        message = interaction.message
        is_public = message is None or not message.flags.ephemeral

        if is_public:
            await interaction.response.send_message(
                embed=build_panel_embed(page, team, private=True),
                view=RoleBoardView(page, team),
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            embed=build_panel_embed(page, team, private=True), view=RoleBoardView(page, team)
        )

    async def _go_prev(self, interaction: discord.Interaction) -> None:
        await self._show_board(interaction, max(0, self.page - 1), self.team)

    async def _go_next(self, interaction: discord.Interaction) -> None:
        await self._show_board(interaction, min(total_pages(self.team) - 1, self.page + 1), self.team)

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
        # العشوائي يحترم التصفية الحالية: تصفية الإوز لا تعطيك بطة
        picked = random.choice(filtered_role_keys(self.team))
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
# 7) العميل (Bot)
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
# 8) خادم Flask للإبقاء على الحياة (Keep-Alive 24/7)
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


# حالة تشخيصية: تُملأ إن تعذّر تشغيل البوت (توكن ناقص أو غير صحيح مثلاً).
# الفائدة الكبيرة: يبقى الرابط حياً ويقول لك السبب مكتوباً بالعربي،
# بدل أن تظهر لك صفحة معلّقة أو خطأ غامض لا تدري من أين جاء.
BOT_PROBLEM: str = ""


@flask_app.route("/", methods=["GET", "HEAD"])
@flask_app.route(KEEPALIVE_PATH, methods=["GET", "HEAD"])
def health():
    """نقطة فحص بسيطة — لا تكشف أي بيانات حسّاسة (لا توكن ولا أسماء لاعبين)."""
    if not _health_ok():
        return jsonify({"status": "forbidden"}), 403

    # ملاحظة: client.latency تكون NaN قبل الاتصال بديسكورد، لذا نتحقق منها بأمان
    latency = client.latency
    payload = {
        "status": "error" if BOT_PROBLEM else "ok",
        "service": "ggd-roles-bot",
        "bot": "offline" if BOT_PROBLEM else "online",
        "uptime_seconds": int(time.time() - _STARTED_AT),
        "guilds": len(client.guilds),
        # عدد الأدوار في هذه النسخة — مجرد رقم غير حسّاس، لكنه يسمح بالتأكد من النسخة
        # المنشورة فعلاً على السيرفر (مثال: 86 = الأدوار كلها وصلت للبوت الحي).
        "roles": len(ROLES),
        "latency_ms": round(latency * 1000) if latency and math.isfinite(latency) else None,
    }
    if BOT_PROBLEM:
        # نُبقي الرمز 200 عن قصد: لو أعدنا 503 لقطع Render الخدمة ولن تستطيع
        # قراءة سبب المشكلة في المتصفح — وهذا بالضبط ما نريد تجنّبه.
        payload["reason"] = BOT_PROBLEM
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
        log.info(
            "ℹ️ لم أجد رابطاً عاماً (PUBLIC_URL أو RENDER_EXTERNAL_URL) — "
            "تخطّي القرع الذاتي، أو استخدم UptimeRobot مجاناً."
        )
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
# 9) التشغيل
# ══════════════════════════════════════════════════════════════════════════════


def looks_like_discord_token(token: str) -> bool:
    """
    فحص شكلي للتوكن (بدون اتصال بالإنترنت): توكن البوت 3 أجزاء تفصلها نقطتان.
    الهدف مساعدتك إن نسيت لصق التوكن أو نسخت جزءاً منه فقط — وليس منع أي توكن صحيح.
    """
    parts = token.split(".")
    if len(parts) != 3 or len(token) < 50:
        return False
    for part in parts:
        if not part or not part.isascii():
            return False
        if not part.replace("-", "").replace("_", "").isalnum():
            return False
    return True


def running_on_hosting_platform() -> bool:
    """هل نعمل على منصّة استضافة (Render/Koyeb/Fly... وليس جهازك)؟

    الفرق مهم عند الفشل: على المنصّة يجب أن يبقى الرابط حياً ليعرض لك السبب،
    أما على جهازك فنفضّل التوقّف فوراً برسالة واضحة في الطرفية.
    """
    markers = (
        "RENDER_EXTERNAL_URL",  # Render (ودائماً موجود لخدمات الويب)
        "RENDER",
        "KOYEB_APP_NAME",
        "KOYEB_SERVICE_NAME",
        "FLY_APP_NAME",
        "DYNO",  # Heroku
        "RAILWAY_ENVIRONMENT",
    )
    return any(os.getenv(name) for name in markers)


def token_problem() -> str:
    """يُرجع سبب المشكلة إن كان التوكن ناقصاً أو غير صحيح، وإلا نصاً فارغاً."""
    if not TOKEN:
        return "التوكن غير موجود — DISCORD_TOKEN فارغ أو غير مضبوط في إعدادات الاستضافة"
    if not looks_like_discord_token(TOKEN):
        return "قيمة DISCORD_TOKEN لا تبدو توكن بوت صحيح (ثلاثة أجزاء تفصلها نقطتان)"
    return ""


def main() -> None:
    global BOT_PROBLEM

    # ١) خادم الفحص يعمل أولاً وقبل أي شيء آخر: بهذا يبقى الرابط حياً حتى لو كان
    #    التوكن ناقصاً، فيستطيع أن يخبرك بالسبب بدل أن تظهر صفحة معلّقة بلا تفسير.
    threading.Thread(target=start_keepalive_server, daemon=True, name="keepalive").start()

    BOT_PROBLEM = token_problem()
    if BOT_PROBLEM:
        log.error("❌ %s", BOT_PROBLEM)
        if running_on_hosting_platform():
            log.error("⚠️ لن يتصل البوت بديسكورد. افتح رابط الخدمة في المتصفح لترى السبب مكتوباً فيها.")
            # نُبقي العملية حيّة ليبقى الرابط قادراً على عرض سبب المشكلة
            while True:
                time.sleep(3600)
        raise SystemExit(
            f"❌ {BOT_PROBLEM}\n"
            "   افتح ملف .env الموجود بجانب bot.py، وضع التوكن أمام السطر DISCORD_TOKEN= ثم شغّلني من جديد.\n"
            "   (لا تكتب التوكن داخل الكود أبداً.)"
        )

    start_self_ping()
    log.info("🚀 تشغيل البوت...")
    # log_handler=None: نستخدم إعدادات التسجيل الخاصة بنا (وتمنع طباعة التوكن في السجلات)
    client.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    main()

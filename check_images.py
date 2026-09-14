# -*- coding: utf-8 -*-
"""
فحص روابط صور الأدوار — يتأكد أن كل رابط داخل قاموس ROLES يعمل فعلاً.

لماذا هذا السكربت؟
-------------------
روابط صور ويكي اللعبة تحتوي على مسار مجزّأ لا يمكن تخمينه (مثل ‎/5/56/‎)،
فخطأ حرفي واحد يعني صورة مكسورة في بطاقة الدور — وهذا لا يظهر إطلاقاً في
الاختبارات العادية لأنها تعمل بدون إنترنت. هذا السكربت يقرأ القاموس من
bot.py ويفحص كل رابط على الشبكة الحقيقية ثم يطبع النتيجة.

⚠️ يحتاج اتصالاً بالإنترنت. لا يُستدعى تلقائياً مع الاختبارات.

التشغيل:
    python check_images.py
    python check_images.py --all      # يعرض كل رابط ونتيجته، وليس المكسورة فقط

الرمز الترجيعي: 0 = كل الصور سليمة، 1 = توجد صور مكسورة.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple

import bot

# ترويسات متصفح حقيقي: شبكة ويكي اللعبة ترفض الطلبات بلا وكيل مستخدم معروف.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Referer": "https://goose-goose-duck.fandom.com/",
    "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
}
TIMEOUT_SECONDS = 30


def check_one(item: Tuple[str, str]) -> Tuple[str, str, str]:
    """يفحص رابطاً واحداً ويُرجع (المفتاح، الحالة، سبب الفشل إن وُجد)."""
    key, url = item
    try:
        request = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("Content-Type", "")
            head = response.read(16)
        if response.status != 200:
            return key, f"HTTP {response.status}", url
        if not content_type.startswith("image"):
            return key, f"ليس صورة ({content_type})", url
        if len(head) < 8:
            return key, "ملف فارغ", url
        return key, "OK", url
    except urllib.error.HTTPError as error:
        return key, f"HTTP {error.code}", url
    except Exception as error:  # noqa: BLE001 - نريد عرض السبب كما هو للمستخدم
        return key, f"{type(error).__name__}: {error}"[:120], url


def check_emoji_ready(item: Tuple[str, str]) -> Tuple[str, str]:
    """يفحص النسخة التي يرفعها البوت كإيموجي مخصص: PNG صغيرة بحجم يقبله ديسكورد.

    لماذا فحص منفصل؟ لأن صورة العرض تعمل كـ webp، أما ديسكورد فيرفض webp
    في الإيموجيات ويرفض أي صورة أكبر من 256KB — وكلاهما لا يظهر إلا عند الرفع.
    """
    key, url = item
    try:
        request = urllib.request.Request(bot.emoji_image_url(url), headers=HEADERS)
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read(bot.EMOJI_MAX_BYTES + 1)
    except Exception as error:  # noqa: BLE001 - نريد عرض السبب كما هو للمستخدم
        return key, f"{type(error).__name__}: {error}"[:120]
    if not content_type.startswith("image/png"):
        return key, f"ليست PNG ({content_type}) — ديسكورد يرفضها كإيموجي"
    if len(data) > bot.EMOJI_MAX_BYTES:
        return key, f"حجمها {len(data) // 1024}KB وأكبر من حد ديسكورد (256KB)"
    return key, "OK"


def collect_urls() -> Dict[str, str]:
    """كل الروابط التي يجب أن تعمل: صور الأدوار + صور هوية البوت (بانر وشعار).

    لماذا الهوية أيضاً؟ لأن البانر يظهر في اللوحة الرئيسية في كل مرة يكتب فيها أحدهم
    ‎/roles، وقالب مكسور هناك أسوأ من صورة دور واحدة ناقصة.
    """
    urls: Dict[str, str] = {
        key: role["image"] for key, role in bot.ROLES.items() if role.get("image")
    }
    urls.update(
        {
            f"هوية البوت: {name}": value
            for name, value in bot.BRAND.items()
            if isinstance(value, str) and value.startswith("https://")
        }
    )
    return urls


def main(argv: List[str]) -> int:
    show_all = "--all" in argv
    role_count = sum(1 for role in bot.ROLES.values() if role.get("image"))
    without_image = [key for key, role in bot.ROLES.items() if not role.get("image")]
    urls = collect_urls()

    print(f"إجمالي الأدوار: {len(bot.ROLES)}")
    print(f"أدوار لها صورة: {role_count}  |  أدوار بلا صورة رسمية: {len(without_image)}")
    print(f"روابط هوية البوت (بانر/شعار): {len(urls) - role_count}")
    print("جارٍ فحص الروابط على الإنترنت...\n")

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(check_one, urls.items()))

    broken = [(key, reason) for key, reason, _ in results if reason != "OK"]
    for key, reason, _ in results:
        if show_all or reason != "OK":
            print(f"  {'✅' if reason == 'OK' else '❌'} {key:<16} {reason}")

    # فحص ثانٍ: هل تصلح كل صورة أن تُرفع كإيموجي مخصص في السيرفر؟
    role_urls = {key: role["image"] for key, role in bot.ROLES.items() if role.get("image")}
    print("\n" + "─" * 52)
    print(f"🖼️ فحص جاهزية الإيموجيات المخصصة ({bot.EMOJI_IMAGE_SIZE}×{bot.EMOJI_IMAGE_SIZE} PNG)...")
    with ThreadPoolExecutor(max_workers=6) as pool:
        emoji_results = list(pool.map(check_emoji_ready, role_urls.items()))
    emoji_broken = [(key, reason) for key, reason in emoji_results if reason != "OK"]
    for key, reason in emoji_results:
        if show_all or reason != "OK":
            print(f"  {'✅' if reason == 'OK' else '❌'} {key:<16} {reason}")

    print("\n" + "─" * 52)
    if broken:
        print(f"❌ توجد {len(broken)} صورة مكسورة — صحّح روابطها داخل bot.py")
        for key, reason in broken:
            print(f"   • {key}: {reason}")
        return 1
    if emoji_broken:
        print(f"❌ {len(emoji_broken)} صورة لا تصلح إيموجياً مخصصاً (أمر ‎/إيموجيات‎ سيتجاوزها):")
        for key, reason in emoji_broken:
            print(f"   • {key}: {reason}")
        return 1
    print(f"✅ كل الصور تصلح إيموجيات مخصصة ({len(role_urls)} صورة PNG صغيرة).")
    print("✅ كل روابط الصور تعمل بشكل صحيح.")
    if without_image:
        print(f"ℹ️  {len(without_image)} دوراً بلا صورة رسمية (تظهر البطاقة بدونه): "
              + "، ".join(without_image))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

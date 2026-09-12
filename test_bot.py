# -*- coding: utf-8 -*-
"""
اختبارات سريعة للبوت — لا تحتاج توكن ولا اتصالاً بالإنترنت.
التشغيل:  python -m unittest -v test_bot.py
"""

import re
import unittest
from pathlib import Path

import discord

import bot


class TestRolesData(unittest.TestCase):
    def test_requested_roles_exist(self):
        """الأدوار التي طلبها المستخدم يجب أن تكون موجودة."""
        for key in ("goose", "duck", "dodo", "sheriff", "pelican", "engineer"):
            self.assertIn(key, bot.ROLES, f"الدور {key} غير موجود في ROLES")

    def test_every_role_has_required_fields(self):
        required = {"name_ar", "name_en", "emoji", "team", "goal", "how", "tips"}
        for key, role in bot.ROLES.items():
            missing = required - role.keys()
            self.assertFalse(missing, f"الدور {key} ينقصه: {missing}")

    def test_team_is_valid(self):
        for key, role in bot.ROLES.items():
            self.assertIn(role["team"], bot.TEAMS, f"فئة غير معروفة في الدور {key}")

    def test_arabic_text_present(self):
        """كل دور له شرح عربي حقيقي (حروف عربية)."""
        arabic = re.compile(r"[\u0600-\u06FF]")
        for key, role in bot.ROLES.items():
            for field in ("name_ar", "goal", "how", "tips"):
                self.assertTrue(
                    arabic.search(role[field]), f"الحقل {field} في الدور {key} لا يحتوي نصاً عربياً"
                )

    def test_images_are_https_or_none(self):
        for key, role in bot.ROLES.items():
            image = role.get("image")
            if image is not None:
                self.assertTrue(image.startswith("https://"), f"رابط صورة غير آمن في الدور {key}")

    def test_role_keys_are_safe_identifiers(self):
        for key in bot.ROLES:
            self.assertRegex(key, r"^[a-z][a-z0-9_]{0,30}$")


class TestEmbeds(unittest.TestCase):
    def test_role_embed_has_name_color_and_image(self):
        embed = bot.build_role_embed("sheriff")
        role = bot.ROLES["sheriff"]
        self.assertIn(role["name_ar"], embed.title)
        self.assertIn(role["name_en"], embed.title)
        self.assertEqual(embed.color.value, bot.TEAMS["goose"]["color"])
        self.assertIsNotNone(embed.image.url)

    def test_team_colors_are_distinct(self):
        colors = {team["color"] for team in bot.TEAMS.values()}
        self.assertEqual(len(colors), len(bot.TEAMS), "ألوان الفئات يجب أن تكون مميزة")

    def test_every_embed_fits_discord_limits(self):
        """حدود ديسكورد: عنوان 256، شرح 4096، حقل 1024، والحجم الكلي 6000 حرف."""
        for key in bot.ROLES:
            embed = bot.build_role_embed(key)
            self.assertLessEqual(len(embed.title or ""), 256, key)
            self.assertLessEqual(len(embed.description or ""), 4096, key)
            for field in embed.fields:
                self.assertLessEqual(len(field.name), 256, key)
                self.assertLessEqual(len(field.value), 1024, f"حقل {field.name} في الدور {key} طويل جداً")
            self.assertLessEqual(len(embed), 6000, key)

    def test_role_without_image_is_handled(self):
        """الأدوار بلا صورة يجب أن تُبنى بدون أخطاء وبدون صورة."""
        key = bot.ROLES["duck"]["image"]
        self.assertIsNone(key, "افتراض الاختبار: البطة بلا صورة — حدّث الاختبار إن أضفت صورة")
        embed = bot.build_role_embed("duck")
        self.assertIsNone(embed.image.url)


class TestBoardLayout(unittest.TestCase):
    def test_pages_cover_all_roles_without_duplicates(self):
        collected = []
        for page in range(bot.total_pages()):
            collected.extend(bot.page_roles(page))
        self.assertEqual(collected, bot.ordered_role_keys())
        self.assertEqual(sorted(collected), sorted(bot.ROLES.keys()))
        self.assertEqual(len(set(collected)), len(collected))

    def test_featured_roles_are_on_first_page(self):
        """الأدوار الشهيرة تظهر في الصفحة الأولى حتى يجدها المستخدم بسرعة."""
        first_page = bot.page_roles(0)
        for key in bot.FEATURED_ROLES:
            self.assertIn(key, first_page, f"الدور {key} ليس في الصفحة الأولى")

    def test_no_more_than_ten_buttons_per_page(self):
        for page in range(bot.total_pages()):
            self.assertLessEqual(len(bot.page_roles(page)), 10, f"صفحة {page}")

    def test_view_respects_discord_component_limits(self):
        """الحد الرسمي: 5 صفوف × 5 أزرار = 25 عنصراً لكل رسالة."""
        for page in range(bot.total_pages()):
            view = bot.RoleBoardView(page)
            self.assertLessEqual(len(view.children), 25, f"صفحة {page}")
            rows = [item.row for item in view.children]
            self.assertLessEqual(max(rows), 4, f"صفحة {page}: عدد الصفوف يتجاوز الحد")
            for row in set(rows):
                self.assertLessEqual(rows.count(row), 5, f"صفحة {page}: أكثر من 5 أزرار في الصف {row}")
            # لا صفوف فارغة في المنتصف (ديسكورد يرفض ذلك)
            self.assertEqual(sorted(set(rows)), list(range(max(rows) + 1)), f"صفحة {page}")

    def test_navigation_reaches_first_and_last_page(self):
        first = bot.RoleBoardView(0)
        last = bot.RoleBoardView(999)  # يجب أن تُقيَّد لآخر صفحة
        self.assertEqual(first.page, 0)
        self.assertEqual(last.page, bot.total_pages() - 1)
        labels = [item.label for item in first.children]
        self.assertIn("⬅️ السابق", labels)
        self.assertIn("🎲 دور عشوائي", labels)

    def test_custom_ids_are_unique_and_short(self):
        view = bot.RoleBoardView(0)
        ids = [item.custom_id for item in view.children if item.custom_id]
        self.assertEqual(len(ids), len(set(ids)))
        for custom_id in ids:
            self.assertLessEqual(len(custom_id), 100)

    def test_button_labels_fit_limit(self):
        for key in bot.ROLES:
            button = bot.RoleButton(key, row=0)
            self.assertLessEqual(len(button.label), 80, key)


class TestKeepAlive(unittest.TestCase):
    def _get(self, path):
        """طلب GET مع مفتاح الفحص إن كان مفعّلاً في هذه البيئة."""
        headers = {"X-Health-Key": bot.HEALTH_TOKEN} if bot.HEALTH_TOKEN else {}
        return bot.flask_app.test_client().get(path, headers=headers)

    def test_health_endpoint_responds(self):
        response = self._get(bot.KEEPALIVE_PATH)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        # لا يجب أن تكشف نقطة الفحص أي معلومة حسّاسة
        self.assertNotIn("token", response.get_data(as_text=True).lower())

    def test_unknown_path_is_404(self):
        self.assertEqual(self._get("/admin").status_code, 404)

    def test_health_token_protects_endpoint(self):
        if not bot.HEALTH_TOKEN:
            self.skipTest("HEALTH_TOKEN غير مُفعّل في هذه البيئة")

        client = bot.flask_app.test_client()
        self.assertEqual(client.get(bot.KEEPALIVE_PATH).status_code, 403)
        self.assertEqual(
            client.get(bot.KEEPALIVE_PATH, headers={"X-Health-Key": bot.HEALTH_TOKEN}).status_code,
            200,
        )


class TestSecurity(unittest.TestCase):
    SOURCE = Path(bot.__file__).read_text(encoding="utf-8")

    def test_no_hardcoded_discord_token(self):
        """التوكن لا يُكتب في الكود أبداً — يُقرأ من متغيّر البيئة فقط."""
        patterns = [
            r"[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27,}",  # بوت
            r"mfa\.[\w-]{80,}",  # مستخدم
        ]
        for pattern in patterns:
            self.assertIsNone(re.search(pattern, self.SOURCE), "يوجد توكن مكتوب داخل الكود!")

    def test_flask_is_not_in_debug_mode(self):
        self.assertNotIn("debug=True", self.SOURCE)
        self.assertNotIn("use_reloader=True", self.SOURCE)

    def test_no_dangerous_calls(self):
        for bad in ("eval(", "exec(", "pickle.loads", "os.system", "subprocess"):
            self.assertNotIn(bad, self.SOURCE, f"استدعاء خطير في الكود: {bad}")

    def test_token_read_from_environment(self):
        self.assertIn('env_str("DISCORD_TOKEN")', self.SOURCE)


if __name__ == "__main__":
    unittest.main(verbosity=2)

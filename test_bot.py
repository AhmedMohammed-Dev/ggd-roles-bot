# -*- coding: utf-8 -*-
"""
اختبارات سريعة للبوت — لا تحتاج توكن ولا اتصالاً بالإنترنت.
التشغيل:  python -m unittest -v test_bot.py
"""

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        """الأدوار بلا صورة يجب أن تُبنى بدون أخطاء وبدون صورة (لا رابط مكسور)."""
        key = "goose"
        patched = {name: dict(role) for name, role in bot.ROLES.items()}
        patched[key]["image"] = None
        with mock.patch.dict(bot.ROLES, patched, clear=True):
            embed = bot.build_role_embed(key)
        self.assertIsNone(embed.image.url)

    def test_roles_without_image_say_so_in_the_card(self):
        """إن لم توجد صورة رسمية للدور، تُذكر الحقيقة بوضوح في البطاقة بدل صمت مربك."""
        missing = [key for key, role in bot.ROLES.items() if not role.get("image")]
        self.assertTrue(missing, "افتراض الاختبار: توجد أدوار بلا صورة رسمية على الويكي")
        self.assertIn("لا تتوفّر صورة", bot.build_role_embed(missing[0]).description)

    def test_maps_field_is_shown_when_present(self):
        """الأدوار المقصورة على خرائط معيّنة تُظهر ذلك في البطاقة."""
        restricted = [key for key, role in bot.ROLES.items() if role.get("maps")]
        self.assertTrue(restricted, "افتراض الاختبار: توجد أدوار مقصورة على خرائط")
        embed = bot.build_role_embed(restricted[0])
        self.assertIn("🗺️ متاح في", [field.name for field in embed.fields])


class TestRosterCompleteness(unittest.TestCase):
    """القائمة الكاملة لأدوار اللعبة — تفشل لو حُذف دور سهواً أو بقي دور ناقصاً.

    المصدر: القائمة الرسمية لأدوار Goose Goose Duck (الوضع الكلاسيكي + الأوضاع الخاصة).
    أضف المفتاح الجديد هنا مع أي دور تضيفه حتى يبقى الدليل كاملاً.
    """

    EXPECTED = (
        # إوز (30)
        "goose", "sheriff", "engineer", "vigilante", "detective", "canadian", "avenger",
        "astral", "stalker", "soldier", "scientist", "survivalist", "fortune_teller",
        "mortician", "birdwatcher", "medium", "gravy", "lover_goose", "mimic", "bodyguard",
        "politician", "locksmith", "celebrity", "adventurer", "street_urchin", "tracker",
        "lobbyist", "coroner", "sensor", "lucid_dreamer",
        # بط (30)
        "duck", "professional", "assassin", "morphling", "spy", "cannibal", "demolitionist",
        "identity_thief", "silencer", "party", "hitman", "snitch", "ninja", "undertaker",
        "invisibility", "serial_killer", "warlock", "esper", "preacher", "cupid", "drone",
        "mime", "clown", "looter", "sniper", "witch_doctor", "lost_duckling", "carrier",
        "parasite", "swordsman",
        # محايدون (10)
        "dodo", "pelican", "pigeon", "vulture", "falcon", "raven", "dueling_dodos", "hawk",
        "cuckoo", "magpie",
        # أدوار الأوضاع الخاصة (16)
        "inquisitor", "saint", "demon_hunter", "seamstress", "high_priest", "initiate",
        "sin_eater", "crow", "villager", "vampire", "thrall", "mummy", "camo_duck",
        "chicken", "spotter", "owl",
    )

    def test_no_role_is_missing(self):
        self.assertEqual(sorted(bot.ROLES), sorted(self.EXPECTED))

    def test_all_three_teams_are_represented(self):
        counts: dict = {}
        for role in bot.ROLES.values():
            counts[role["team"]] = counts.get(role["team"], 0) + 1
        self.assertEqual(sorted(counts), sorted(bot.TEAMS))
        for team, count in counts.items():
            self.assertGreater(count, 3, f"فريق {team} فيه {count} دوراً فقط")

    def test_modes_are_declared_and_known(self):
        """أي دور بوضع خاص يجب أن يكون وضعه معرفاً، والوضع الافتراضي لا يُكتب صراحة."""
        for key, role in bot.ROLES.items():
            mode = role.get("mode")
            if mode is None:
                continue
            self.assertIn(mode, bot.MODES, f"وضع غير معروف في الدور {key}")
            self.assertNotEqual(mode, "classic", f"الدور {key}: الوضع الكلاسيكي هو الافتراضي")

    def test_special_roles_show_their_mode_in_the_card(self):
        for key, role in bot.ROLES.items():
            if not role.get("mode"):
                continue
            self.assertIn(bot.MODES[role["mode"]]["label"], bot.build_role_embed(key).description, key)

    def test_english_names_are_unique(self):
        names = [role["name_en"] for role in bot.ROLES.values()]
        self.assertEqual(len(names), len(set(names)), "يوجد دوران بنفس الاسم الإنجليزي")

    def test_maps_field_is_arabic_when_present(self):
        arabic = re.compile(r"[\u0600-\u06FF]")
        for key, role in bot.ROLES.items():
            maps = role.get("maps")
            if maps is None:
                continue
            self.assertTrue(arabic.search(maps), f"حقل الخرائط في {key} بلا نص عربي")

    def test_roster_is_reachable_through_the_board(self):
        """كل دور في القائمة يمكن الوصول إليه بالتنقل بين الصفحات."""
        reachable = []
        for page in range(bot.total_pages()):
            reachable.extend(bot.page_roles(page))
        self.assertEqual(sorted(reachable), sorted(self.EXPECTED))


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

    def test_port_is_always_usable(self):
        """منفذ غير صالح (مثل PORT=0) كان سيُفتح به منفذ عشوائي ويكسر فحص الصحة عند النشر."""
        self.assertGreaterEqual(bot.PORT, 1)
        self.assertLessEqual(bot.PORT, 65535)
        self.assertTrue(bot.KEEPALIVE_PATH.startswith("/"))

    def test_health_endpoint_responds(self):
        response = self._get(bot.KEEPALIVE_PATH)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        # عدد الأدوار يظهر في الفحص، فنستطيع التأكد من النسخة المنشورة على السيرفر مباشرةً
        self.assertEqual(payload["roles"], len(bot.ROLES))
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


class TestEnvLoading(unittest.TestCase):
    """ملف .env هو الطريقة التي تُمرّر بها التوكن محلياً — فيجب أن يعمل بأمان."""

    def setUp(self):
        self._saved = dict(os.environ)
        self.addCleanup(self._restore)

    def _restore(self):
        os.environ.clear()
        os.environ.update(self._saved)

    def _write_env(self, text, names):
        for name in names:
            os.environ.pop(name, None)
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".env", delete=False, encoding="utf-8"
        )
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_missing_file_is_harmless(self):
        self.assertEqual(bot.load_dotenv("no-such-file.env"), 0)

    def test_parses_values_quotes_comments_and_export(self):
        names = ["DISCORD_TOKEN", "GUILD_ID", "PUBLIC_URL", "SELF_PING_SECONDS", "PORT", "1BAD"]
        path = self._write_env(
            "# تعليق\n"
            "\n"
            "DISCORD_TOKEN=abc123\n"
            'GUILD_ID="123456789012345678"\n'
            "PUBLIC_URL='https://example.onrender.com'\n"
            "export SELF_PING_SECONDS=600\n"
            "PORT=8080  # تعليق في نهاية السطر\n"
            "سطر غير صالح بدون علامة يساوي\n"
            "1BAD=value\n",
            names,
        )
        self.assertEqual(bot.load_dotenv(path), 5)
        self.assertEqual(os.environ["DISCORD_TOKEN"], "abc123")
        self.assertEqual(os.environ["GUILD_ID"], "123456789012345678")
        self.assertEqual(os.environ["PUBLIC_URL"], "https://example.onrender.com")
        self.assertEqual(os.environ["SELF_PING_SECONDS"], "600")
        self.assertEqual(os.environ["PORT"], "8080")
        self.assertNotIn("1BAD", os.environ, "اسم متغيّر غير صالح يجب أن يُتجاهل")

    def test_platform_variables_always_win(self):
        """متغيّرات Render/Koyeb البيئية لا يجب أن يطغى عليها ملف .env المحلي."""
        path = self._write_env("DISCORD_TOKEN=from-file\n", ["DISCORD_TOKEN"])
        os.environ["DISCORD_TOKEN"] = "from-platform"
        self.assertEqual(bot.load_dotenv(path), 0)
        self.assertEqual(os.environ["DISCORD_TOKEN"], "from-platform")

    def test_example_file_is_loadable(self):
        example = Path(bot.__file__).resolve().parent / ".env.example"
        self.assertTrue(example.is_file())
        self.assertIsInstance(bot.load_dotenv(str(example)), int)

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

    def test_env_file_is_gitignored(self):
        """أهم اختبار أمني: التأكد أن التوكن لا يمكن أن يُرفع إلى GitHub بالخطأ."""
        project = Path(bot.__file__).resolve().parent
        rules = (project / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".env", [rule.strip() for rule in rules])
        self.assertIn("!.env.example", [rule.strip() for rule in rules])


class TestPublicUrlResolution(unittest.TestCase):
    """البوت يجد رابط نفسه تلقائياً بدل أن تكتبه يدوياً (وتكتبه خطأً)."""

    KEYS = ("PUBLIC_URL", "RENDER_EXTERNAL_URL")

    def resolve(self, **values: str) -> str:
        env = {key: values.get(key, "") for key in self.KEYS}
        with mock.patch.dict(os.environ, env, clear=True):
            return bot.resolve_public_url()

    def test_explicit_public_url_wins(self):
        self.assertEqual(
            self.resolve(PUBLIC_URL="https://mine.example.com",
                        RENDER_EXTERNAL_URL="https://render-provided.onrender.com"),
            "https://mine.example.com",
        )

    def test_falls_back_to_the_variable_render_sets_itself(self):
        """Render تضبط RENDER_EXTERNAL_URL، فوُجد الرابط بلا أي إعداد يدوي."""
        self.assertEqual(
            self.resolve(RENDER_EXTERNAL_URL="https://myapp.onrender.com"),
            "https://myapp.onrender.com",
        )

    def test_missing_scheme_is_added(self):
        """أشهر خطأ في النسخ: وضع النطاق بلا https:// فيفشل القرع الذاتي."""
        self.assertEqual(self.resolve(PUBLIC_URL="myapp.onrender.com"), "https://myapp.onrender.com")

    def test_trailing_slash_is_removed(self):
        self.assertEqual(
            self.resolve(PUBLIC_URL="https://myapp.onrender.com/"), "https://myapp.onrender.com"
        )

    def test_empty_when_nothing_is_configured(self):
        self.assertEqual(self.resolve(), "")

    def test_blank_values_are_ignored(self):
        self.assertEqual(self.resolve(PUBLIC_URL="   "), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)

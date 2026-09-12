# -*- coding: utf-8 -*-
"""
اختبارات سكربت النشر — لا تحتاج مفتاحاً ولا اتصالاً بالإنترنت.
التشغيل:  python -m unittest -v test_deploy.py
"""

import io
import os
import re
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import deploy


def fake_completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr=stderr)


class TestRedaction(unittest.TestCase):
    """أهم فحص أمني: أي سرّ يمرّ على الشاشة يجب أن يخرج محجوباً."""

    def setUp(self):
        deploy._SECRET_VALUES.clear()
        self.addCleanup(deploy._SECRET_VALUES.clear)

    def test_redact_hides_registered_secret(self):
        secret = "fake-value-for-redaction-test"
        deploy._SECRET_VALUES.append(secret)
        self.assertEqual(deploy.redact(f"token={secret}"), "token=********")

    def test_redact_ignores_short_values(self):
        """القيم القصيرة لا تُحجب حتى لا نتلف نصاً عادياً بالخطأ."""
        deploy._SECRET_VALUES.append("abc")
        self.assertEqual(deploy.redact("abc def"), "abc def")

    def test_say_never_prints_a_secret(self):
        secret = "MTA5OTk5.SECRETPART.SECRETSIGNATURE"
        deploy._SECRET_VALUES.append(secret)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            deploy.say(f"التوكن هو {secret} انتهى")
        self.assertNotIn(secret, buffer.getvalue())
        self.assertIn("********", buffer.getvalue())

    def test_secret_keys_are_detected(self):
        for key in ("DISCORD_TOKEN", "GITHUB_TOKEN", "RENDER_API_KEY", "HEALTH_TOKEN", "DB_PASSWORD"):
            self.assertTrue(deploy.is_secret_key(key), key)
        for key in ("PORT", "GUILD_ID", "PUBLIC_URL", "SELF_PING_SECONDS"):
            self.assertFalse(deploy.is_secret_key(key), key)

    def test_load_env_file_registers_secrets_for_redaction(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text("DISCORD_TOKEN=SECRETVALUE123456\nGUILD_ID=42\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=True):
                deploy.load_env_file(path)
                self.assertIn("SECRETVALUE123456", deploy._SECRET_VALUES)
                self.assertNotIn("42", deploy._SECRET_VALUES)

    def test_mask_never_shows_more_than_six_characters(self):
        secret = "abcdefghijklmnop"
        masked = deploy.mask(secret)
        self.assertTrue(masked.startswith("abcdef"))
        self.assertNotIn("ijklmnop", masked)

    def test_source_contains_no_hardcoded_token(self):
        """حاجز: لا يجوز أن يوجد أي توكن حقيقي داخل الكود."""
        source = Path(deploy.__file__).read_text(encoding="utf-8")
        self.assertNotIn("Bot ", source)
        self.assertIsNone(
            re.search(r'["\'][A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}["\']', source)
        )


class TestEnvParsing(unittest.TestCase):
    def parse(self, text: str) -> dict:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text(text, encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=True):
                deploy.load_env_file(path)
                return dict(os.environ)

    def test_parses_plain_quoted_exported_and_commented_values(self):
        env = self.parse(
            "# تعليق\n"
            "PLAIN=value\n"
            'QUOTED="quoted value"\n'
            "export EXPORTED=exported\n"
            "TRAILING=trailing # تعليق بعد القيمة\n"
            "NOT A KEY LINE\n"
            "9BADKEY=skip\n"
        )
        self.assertEqual(env.get("PLAIN"), "value")
        self.assertEqual(env.get("QUOTED"), "quoted value")
        self.assertEqual(env.get("EXPORTED"), "exported")
        self.assertEqual(env.get("TRAILING"), "trailing")
        self.assertIsNone(env.get("9BADKEY"))

    def test_existing_environment_wins(self):
        """منصّات الاستضافة لها الأولوية — الملف لا يطغى على البيئة."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text("PORT=8080\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"PORT": "10000"}, clear=True):
                deploy.load_env_file(path)
                self.assertEqual(os.environ["PORT"], "10000")

    def test_missing_file_is_ignored(self):
        deploy.load_env_file(Path("no-such-file.env"))


class TestRenderPayload(unittest.TestCase):
    def setUp(self):
        deploy._SECRET_VALUES.clear()
        self.addCleanup(deploy._SECRET_VALUES.clear)
        self.env = {
            "DISCORD_TOKEN": "FAKE-DISCORD-TOKEN-FOR-TESTS",
            "GUILD_ID": "123456789012345678",
            "ALLOWED_GUILD_IDS": "123456789012345678",
            "PORT": "8080",
            "HEALTH_TOKEN": "",
        }
        self.patcher = mock.patch.dict(os.environ, self.env, clear=True)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def vars_by_key(self, public_url="https://ggd-roles-bot.onrender.com"):
        return {item["key"]: item["value"] for item in deploy.build_env_vars(public_url)}

    def test_token_guild_and_public_url_are_forwarded(self):
        variables = self.vars_by_key()
        self.assertEqual(variables["DISCORD_TOKEN"], "FAKE-DISCORD-TOKEN-FOR-TESTS")
        self.assertEqual(variables["GUILD_ID"], "123456789012345678")
        self.assertEqual(variables["PUBLIC_URL"], "https://ggd-roles-bot.onrender.com")

    def test_port_is_never_forwarded(self):
        """Render يضبط PORT بنفسه — إرساله قد يكسر فحص الصحة."""
        self.assertNotIn("PORT", self.vars_by_key())

    def test_security_lock_inherits_guild_id_when_list_is_empty(self):
        with mock.patch.dict(os.environ, {"ALLOWED_GUILD_IDS": ""}):
            variables = self.vars_by_key()
        self.assertEqual(variables["ALLOWED_GUILD_IDS"], "123456789012345678")

    def test_health_token_is_optional(self):
        self.assertNotIn("HEALTH_TOKEN", self.vars_by_key())

    def test_missing_token_raises_friendly_error(self):
        with mock.patch.dict(os.environ, {"DISCORD_TOKEN": ""}):
            with self.assertRaises(deploy.DeployError) as caught:
                deploy.build_env_vars("https://example.com")
        self.assertIn("DISCORD_TOKEN", caught.exception.message)

    def test_create_service_body_matches_render_contract(self):
        captured: dict = {}

        def fake_http(method, url, token=None, body=None, **kwargs):
            captured.update({"method": method, "url": url, "body": body})
            return 201, {"service": {"id": "srv-1", "slug": "ggd-roles-bot", "dashboardUrl": "d"}}

        with mock.patch.object(deploy, "http_json", fake_http):
            service = deploy.render_create_service(
                "rnd_key", "usr-1", "https://github.com/me/ggd-roles-bot",
                deploy.build_env_vars("https://ggd-roles-bot.onrender.com"),
                "frankfurt", auto_deploy=True,
            )

        self.assertEqual(service["id"], "srv-1")
        self.assertEqual(captured["url"], f"{deploy.RENDER_API}/services")
        body = captured["body"]
        self.assertEqual(body["type"], "web_service")
        self.assertEqual(body["ownerId"], "usr-1")
        self.assertEqual(body["branch"], "main")
        self.assertEqual(body["autoDeploy"], "yes")
        details = body["serviceDetails"]
        self.assertEqual(details["runtime"], "python")
        self.assertEqual(details["plan"], "free")
        self.assertEqual(details["region"], "frankfurt")
        self.assertEqual(details["healthCheckPath"], "/healthz")
        self.assertEqual(details["envSpecificDetails"]["startCommand"], "python -u bot.py")
        self.assertTrue(all(set(item) == {"key", "value"} for item in body["envVars"]))

    def test_plan_and_region_are_free_tier_compatible(self):
        """القيم يجب أن تكون من القوائم الرسمية، وإلا رفض Render الطلب."""
        self.assertEqual(deploy.HEALTH_CHECK_PATH, "/healthz")
        self.assertIn(deploy.setting("RENDER_REGION", "frankfurt"), deploy.VALID_REGIONS)

    def test_service_url_uses_api_value_then_falls_back_to_slug(self):
        with mock.patch.object(deploy, "http_json", lambda *a, **k: (500, None)):
            self.assertEqual(
                deploy.render_service_url("key", {"serviceDetails": {"url": "https://real.onrender.com"}}),
                "https://real.onrender.com",
            )
            self.assertEqual(
                deploy.render_service_url("key", {"slug": "my-bot", "serviceDetails": {}}),
                "https://my-bot.onrender.com",
            )


class TestOneClickAndGitLogin(unittest.TestCase):
    def test_one_click_url_matches_render_docs(self):
        url = deploy.one_click_render_url("https://github.com/me/ggd-roles-bot")
        self.assertEqual(url, "https://render.com/deploy?repo=https://github.com/me/ggd-roles-bot")

    def test_git_login_reads_username_and_token_from_credential_manager(self):
        class FakeRun:
            stdout = "protocol=https\nhost=github.com\nusername=octocat\npassword=gho_TOKENVALUE\n"
            stderr = ""
            returncode = 0

        deploy._SECRET_VALUES.clear()
        self.addCleanup(deploy._SECRET_VALUES.clear)
        with mock.patch.object(deploy.shutil, "which", lambda name: "git"), \
                mock.patch.object(deploy.subprocess, "run", lambda *a, **k: FakeRun()):
            username, token = deploy.credential_manager_login()

        self.assertEqual(username, "octocat")
        self.assertEqual(token, "gho_TOKENVALUE")
        # المفتاح يُحجب من أي طباعة تالية
        self.assertIn("gho_TOKENVALUE", deploy._SECRET_VALUES)
        self.assertNotIn("gho_TOKENVALUE", deploy.redact("المفتاح: gho_TOKENVALUE"))

    def test_git_login_reports_a_friendly_error_when_window_is_closed(self):
        class FakeRun:
            stdout = ""
            stderr = "failed"
            returncode = 1

        with mock.patch.object(deploy.shutil, "which", lambda name: "git"), \
                mock.patch.object(deploy.subprocess, "run", lambda *a, **k: FakeRun()):
            with self.assertRaises(deploy.DeployError) as caught:
                deploy.credential_manager_login()
        self.assertIn("لم يكتمل تسجيل الدخول", caught.exception.message)

    def test_git_login_needs_no_secrets_file(self):
        """--git-login يجب أن يعمل بلا أي مفتاح ولا ملف."""
        args = deploy.parse_args(["--git-login"])
        self.assertTrue(args.git_login)

        with tempfile.TemporaryDirectory() as folder:
            env_file = Path(folder) / ".env"
            env_file.write_text("DISCORD_TOKEN=FAKE-TOKEN-VALUE\n", encoding="utf-8")

            def fake_http(method, url, token=None, body=None, **kwargs):
                if url.endswith("/user"):
                    return 200, {"login": "octocat"}
                if "/repos/" in url:
                    return 200, {"full_name": "octocat/ggd-roles-bot"}
                return 200, {}

            buffer = io.StringIO()
            with mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch.object(deploy, "ENV_PATH", env_file), \
                    mock.patch.object(deploy, "SECRETS_PATH", Path(folder) / "none.env"), \
                    mock.patch.object(deploy, "credential_manager_login", lambda: ("octocat", "gho_TOK")), \
                    mock.patch.object(deploy, "git_push", lambda *a, **k: None), \
                    mock.patch.object(deploy, "http_json", fake_http), \
                    redirect_stdout(buffer):
                code = deploy.main(["--git-login"])

        self.assertEqual(code, 0, buffer.getvalue())
        self.assertIn("render.com/deploy?repo=https://github.com/octocat/ggd-roles-bot", buffer.getvalue())


class TestSecurityGuards(unittest.TestCase):
    def test_api_message_reads_github_and_render_errors(self):
        self.assertEqual(deploy.api_message({"message": "Bad credentials"}), "Bad credentials")
        self.assertEqual(deploy.api_message({"error": "not found"}), "not found")
        self.assertEqual(deploy.api_message("خطأ غير JSON\nسطر ثانٍ"), "خطأ غير JSON")
        self.assertEqual(deploy.api_message(None), "")

    def test_content_scan_catches_tokens_and_private_keys(self):
        # نُركّب القيم وقت التشغيل عمداً: لا نريد داخل الملف نصّاً يشبه توكن حقيقياً،
        # وإلا رصده فاحص الأسرار في GitHub نفسه حين يُرفع المستودع.
        samples = {
            "توكن بوت": ".".join(["MTA5NzY1NDMyMTA5ODc2NTQzMj", "EXAMPLE", "a" * 28]),
            "مفتاح GitHub": "ghp_" + "A" * 24,
            "مفتاح Render": "rnd_" + "b" * 24,
            "مفتاح خاص": "-----" + "BEGIN RSA PRIVATE KEY-----",
        }
        for description, sample in samples.items():
            with self.subTest(description):
                with self.assertRaises(deploy.DeployError):
                    deploy.scan_text_for_secrets(f"x = '{sample}'", "config.py")

    def test_content_scan_passes_clean_code(self):
        clean = 'TOKEN = os.getenv("DISCORD_TOKEN")\nname = "ggd-roles-bot"\n'
        deploy.scan_text_for_secrets(clean, "bot.py")  # يجب ألا يرمي أي خطأ

    def test_content_scan_blocks_the_real_token_value(self):
        deploy._SECRET_VALUES.clear()
        self.addCleanup(deploy._SECRET_VALUES.clear)
        real = "a-real-discord-token-value-1234567890"
        deploy._SECRET_VALUES.append(real)
        with self.assertRaises(deploy.DeployError) as caught:
            deploy.scan_text_for_secrets(f"DISCORD_TOKEN={real}", "notes.txt")
        self.assertIn("notes.txt", caught.exception.message)

    def test_tracked_files_scan_reads_real_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "clean.py").write_text("print('ok')\n", encoding="utf-8")
            (root / "dirty.py").write_text("key = 'rnd_" + "c" * 24 + "'\n", encoding="utf-8")
            with mock.patch.object(deploy, "HERE", root):
                self.assertEqual(deploy.scan_tracked_files_for_secrets(["clean.py"]), 1)
                with self.assertRaises(deploy.DeployError):
                    deploy.scan_tracked_files_for_secrets(["dirty.py"])

    def test_push_is_blocked_when_a_secret_file_is_tracked(self):
        with mock.patch.object(deploy, "run_git", lambda *a, **k: fake_completed(".env\nbot.py\n")):
            with self.assertRaises(deploy.DeployError) as caught:
                deploy.assert_no_secrets_tracked()
        self.assertIn(".env", caught.exception.message)
        self.assertIn("git rm --cached", caught.exception.hint)

    def test_push_allows_a_clean_file_list(self):
        with mock.patch.object(deploy, "HERE", Path("no-such-folder")), mock.patch.object(
            deploy, "run_git", lambda *a, **k: fake_completed("bot.py\ndeploy.py\n")
        ):
            try:
                deploy.assert_no_secrets_tracked()
            except deploy.DeployError as error:  # pragma: no cover - يجب ألا يحدث
                self.fail(f"مُنع الرفع بلا سبب: {error.message}")

    def test_env_example_is_not_treated_as_a_secret_file(self):
        self.assertNotIn(".env.example", deploy.NEVER_PUSH)

    def test_gitignore_covers_every_protected_file(self):
        ignored = (Path(deploy.__file__).parent / ".gitignore").read_text(encoding="utf-8")
        for name in deploy.NEVER_PUSH:
            if name in {".env.bak", ".env.local", "id_rsa", "id_ed25519", ".netrc"}:
                continue  # محميّة بأسماء عامة، وتحجبها فجوة الأمان أصلاً
            self.assertIn(name, ignored, f"{name} غير مذكور في .gitignore")


class TestCommandLine(unittest.TestCase):
    def test_flags_parse(self):
        args = deploy.parse_args(["--check", "--public", "--no-wait"])
        self.assertTrue(args.check and args.public and args.no_wait)
        self.assertFalse(args.github_only)

    def test_missing_keys_stop_with_guidance(self):
        with tempfile.TemporaryDirectory() as folder:
            empty_env = Path(folder) / "empty.env"
            empty_env.write_text("DISCORD_TOKEN=FAKE-TOKEN-VALUE\n", encoding="utf-8")
            buffer = io.StringIO()
            with mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch.object(deploy, "ENV_PATH", empty_env), \
                    mock.patch.object(deploy, "SECRETS_PATH", Path(folder) / "none.env"), \
                    redirect_stdout(buffer):
                code = deploy.main([])
        output = buffer.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("GITHUB_TOKEN", output)
        self.assertIn(".deploy_secrets", output)

    def test_check_mode_does_not_deploy_anything(self):
        calls: list = []
        with tempfile.TemporaryDirectory() as folder:
            env_file = Path(folder) / ".env"
            env_file.write_text("DISCORD_TOKEN=FAKE-TOKEN-VALUE\n", encoding="utf-8")
            secrets = Path(folder) / ".deploy_secrets"
            secrets.write_text("GITHUB_TOKEN=FAKE-GITHUB-KEY\nRENDER_API_KEY=FAKE-RENDER-KEY\n", encoding="utf-8")

            def fake_http(method, url, token=None, body=None, **kwargs):
                calls.append((method, url))
                if url.endswith("/user"):
                    return 200, {"login": "octocat"}
                if "owners" in url:
                    return 200, [{"owner": {"id": "usr-1", "name": "My Workspace"}}]
                return 200, {}

            buffer = io.StringIO()
            with mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch.object(deploy, "ENV_PATH", env_file), \
                    mock.patch.object(deploy, "SECRETS_PATH", secrets), \
                    mock.patch.object(deploy, "http_json", fake_http), \
                    redirect_stdout(buffer):
                code = deploy.main(["--check"])

        self.assertEqual(code, 0)
        urls = [url for _, url in calls]
        self.assertEqual(len(urls), 2, urls)
        self.assertTrue(any(url.endswith("/user") for url in urls), urls)
        self.assertTrue(any("owners" in url for url in urls), urls)
        self.assertNotIn("FAKE-GITHUB-KEY", buffer.getvalue())
        self.assertNotIn("FAKE-RENDER-KEY", buffer.getvalue())


class TestRenderBlueprint(unittest.TestCase):
    """ملف render.yaml هو ما سينفّذه Render حرفياً — خطأ صياغة فيه يوقف النشر كله."""

    @classmethod
    def setUpClass(cls):
        try:
            import yaml  # noqa: F401  (اختياري: للتطوير فقط، وليس من متطلبات البوت)
        except ImportError:  # pragma: no cover
            raise unittest.SkipTest("PyYAML غير مثبَّت — تخطّي فحص صياغة render.yaml")
        cls.text = (Path(deploy.__file__).parent / "render.yaml").read_text(encoding="utf-8")
        cls.spec = __import__("yaml").safe_load(cls.text)

    def test_root_keys_are_officially_allowed(self):
        """Render ترفض أي مفتاح في الجذر غير هذه القائمة (سبب شائع لفشل النشر)."""
        allowed = {"services", "databases", "envVarGroups", "projects", "ungrouped"}
        self.assertTrue(set(self.spec) <= allowed, f"مفتاح غير مسموح: {set(self.spec) - allowed}")

    def test_single_free_web_service_with_health_check(self):
        services = self.spec["services"]
        self.assertEqual(len(services), 1)
        service = services[0]
        self.assertEqual(service["type"], "web")
        self.assertEqual(service["runtime"], "python")
        self.assertEqual(service["plan"], "free")
        self.assertEqual(service["healthCheckPath"], "/healthz")
        self.assertEqual(service["buildCommand"], deploy.BUILD_COMMAND)
        self.assertEqual(service["startCommand"], deploy.START_COMMAND)
        self.assertIn(service["region"], deploy.VALID_REGIONS)

    def test_only_the_token_is_asked_from_the_user(self):
        """النشر بنقرة واحدة: حقل واحد فقط يملؤه المستخدم كي لا يتعب أو يخطئ."""
        service = self.spec["services"][0]
        secret_fields = [v["key"] for v in service["envVars"] if v.get("sync") is False]
        self.assertEqual(secret_fields, ["DISCORD_TOKEN"])

    def test_security_lock_and_guild_are_preset(self):
        env = {v["key"]: v.get("value") for v in self.spec["services"][0]["envVars"]}
        self.assertTrue(env.get("ALLOWED_GUILD_IDS", "").isdigit(), "القفل الأمني مطلوب")
        self.assertEqual(env["GUILD_ID"], env["ALLOWED_GUILD_IDS"])

    def test_auto_deploy_is_off_so_a_push_never_breaks_a_running_bot(self):
        self.assertEqual(self.spec["services"][0]["autoDeployTrigger"], "off")

    def test_file_itself_contains_no_secret(self):
        for description, pattern in deploy.SECRET_PATTERNS:
            self.assertIsNone(pattern.search(self.text), f"render.yaml يحتوي {description}")


class TestSecretsFileTemplate(unittest.TestCase):
    def test_template_ships_without_any_value(self):
        path = Path(deploy.__file__).parent / ".deploy_secrets.example"
        self.assertTrue(path.is_file(), "قالب .deploy_secrets.example مفقود")
        with mock.patch.dict(os.environ, {}, clear=True):
            deploy.load_env_file(path)
            self.assertEqual(os.getenv("GITHUB_TOKEN"), "")
            self.assertEqual(os.getenv("RENDER_API_KEY"), "")

    def test_gitignore_keeps_the_real_secrets_file_out(self):
        gitignore = (Path(deploy.__file__).parent / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".deploy_secrets", gitignore)
        self.assertIn("!.deploy_secrets.example", gitignore)


if __name__ == "__main__":
    unittest.main()

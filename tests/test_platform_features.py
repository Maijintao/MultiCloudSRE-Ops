import gc
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from oj_platform import cases, db, http_app, settings, submissions
from oj_platform.http_app import Handler
from oj_platform.skills import (
    RUM2_PLATFORM_SKILL_NAME,
    write_contestant_skills,
    write_platform_skills,
)


class TestSetManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.config_path = self.root / "config.json"
        self.faults_dir = self.root / "faults"
        self.case_dir = self.faults_dir / "hidden-case"
        self.case_dir.mkdir(parents=True)
        self._write_json(
            self.config_path,
            {
                "test_sets": [
                    {
                        "id": "test-set-1",
                        "name": "Test Set 1",
                        "order_id": 1,
                        "submission_enabled": True,
                    }
                ],
                "next_test_set_number": 2,
            },
        )
        self._write_json(
            self.case_dir / "case.json",
            {
                "id": "hidden-case",
                "order_id": 58,
                "title": "Hidden",
                "case_set_id": "test-set-1",
            },
        )
        self.patchers = [
            patch.object(settings, "CONFIG_FILE", self.config_path),
            patch.object(settings, "FAULTS_DIR", self.faults_dir),
            patch.object(cases, "load_cases_list", side_effect=self._load_cases),
            patch.object(cases, "load_public_cases_list", side_effect=self._load_public_cases),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        gc.collect()
        self.temp_dir.cleanup()

    @staticmethod
    def _write_json(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def _load_cases(self):
        return [json.loads((self.case_dir / "case.json").read_text(encoding="utf-8"))]

    def _load_public_cases(self, include_test_cases=False, include_details=False):
        del include_test_cases, include_details
        return self._load_cases()

    def test_rename_delete_and_monotonic_create(self):
        renamed = cases.update_test_set("test-set-1", {"name": "Primary"})
        self.assertEqual(renamed["test_set"]["name"], "Primary")

        created = cases.create_next_test_set()
        self.assertEqual(created["id"], "test-set-2")
        with self.assertRaisesRegex(ValueError, "already exists"):
            cases.update_test_set("test-set-2", {"name": "primary"})

        deleted = cases.delete_test_set("test-set-1")
        self.assertEqual(deleted["deleted"]["moved_case_count"], 1)
        case_json = json.loads((self.case_dir / "case.json").read_text(encoding="utf-8"))
        self.assertEqual(case_json["case_set_id"], "ungrouped")
        self.assertEqual(cases.create_next_test_set()["id"], "test-set-3")

    def test_delete_rolls_back_member_files_when_config_write_fails(self):
        real_write = cases.write_json_object

        def failing_write(path, value):
            if Path(path) == self.config_path and not any(
                item.get("id") == "test-set-1" for item in value.get("test_sets", [])
            ):
                raise OSError("simulated config failure")
            return real_write(path, value)

        with patch.object(cases, "write_json_object", side_effect=failing_write):
            with self.assertRaisesRegex(OSError, "simulated config failure"):
                cases.delete_test_set("test-set-1")

        case_json = json.loads((self.case_dir / "case.json").read_text(encoding="utf-8"))
        self.assertEqual(case_json["case_set_id"], "test-set-1")


class SubmissionFilterTests(unittest.TestCase):
    def test_historical_test_set_names_remain_filterable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_file = root / "test.sqlite3"
            conn = sqlite3.connect(db_file)
            try:
                conn.execute(
                    "CREATE TABLE submissions (source_kind TEXT, display_case_name TEXT, created_at TEXT, id INTEGER)"
                )
                conn.execute(
                    "INSERT INTO submissions VALUES ('test_set', 'Old Set-1', '2026-01-01', 1)"
                )
                conn.commit()
            finally:
                conn.close()
            with (
                patch.object(settings, "STATE_DIR", root),
                patch.object(settings, "DB_FILE", db_file),
                patch.object(
                    submissions,
                    "public_test_sets",
                    return_value=[{"id": "test-set-1", "name": "Current Set", "case_numbers": [58]}],
                ),
            ):
                names = submissions.public_test_set_display_names()
            self.assertEqual(names, {"Current Set-1", "Old Set-1"})


class TestSetVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.state_dir = self.root / "state"
        self.db_file = self.state_dir / "oj.sqlite3"
        self.patchers = [
            patch.object(settings, "STATE_DIR", self.state_dir),
            patch.object(settings, "DB_FILE", self.db_file),
        ]
        for patcher in self.patchers:
            patcher.start()
        db.init_db()
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'contestant', ?)",
                ("owner", "hash", "2026-01-01T00:00:00+00:00"),
            )
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'contestant', ?)",
                ("other", "hash", "2026-01-01T00:00:00+00:00"),
            )
            self.owner_id = conn.execute("SELECT id FROM users WHERE username = 'owner'").fetchone()["id"]
            self.other_id = conn.execute("SELECT id FROM users WHERE username = 'other'").fetchone()["id"]

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        gc.collect()
        self.temp_dir.cleanup()

    @staticmethod
    def _case(case_id, order_id, case_set_id, ai_visible=True):
        return {
            "id": case_id,
            "order_id": order_id,
            "title": f"Title {case_id}",
            "case_set_id": case_set_id,
            "fault_phenomenon": f"Phenomenon {case_id}",
            "public_case_info": f"Public {case_id}",
            "submission_enabled": True,
            "ai_analysis_visible": ai_visible,
        }

    def _insert_submission(self, case_id, source_kind="test_set"):
        now = "2026-01-01T00:00:00+00:00"
        with db.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO submissions (
                    user_id, case_id, source_kind, test_set_id, test_set_name,
                    test_set_case_index, display_case_name, submission_group_id,
                    status, api_base_url, api_key, api_key_mask, model, prompt,
                    skill, skills_json, soul_md, answer_transcript, answer_output,
                    grade_transcript, grade_output, grade_json, score,
                    result_summary, run_log, runner_kind, runner_meta,
                    created_at, started_at, finished_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'done', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.owner_id,
                    case_id,
                    source_kind,
                    "test-set-1" if source_kind == "test_set" else None,
                    "Test Set 1" if source_kind == "test_set" else None,
                    1 if source_kind == "test_set" else None,
                    "Test Set 1-1" if source_kind == "test_set" else None,
                    "group-1" if source_kind == "test_set" else None,
                    "https://answer.example/v1",
                    "answer-secret",
                    "ans...cret",
                    "model-x",
                    "rendered prompt",
                    "skill text",
                    "[]",
                    "soul text",
                    "answer transcript",
                    "answer output",
                    "grade transcript",
                    "grade output",
                    '{"total_score": 88}',
                    88,
                    "analysis summary",
                    "run log",
                    "docker",
                    '{"container":"internal"}',
                    now,
                    now,
                    now,
                    now,
                ),
            )
            return cur.lastrowid

    def test_contestants_receive_training_and_test_cases_but_not_ungrouped(self):
        visible_cases = [
            self._case("training-case", 1, "training"),
            self._case("test-case", 58, "test-set-1"),
            self._case("ungrouped-case", 62, "ungrouped"),
        ]
        with (
            patch.object(http_app, "load_public_cases_list", return_value=visible_cases),
            patch.object(http_app, "personal_best_scores_by_case", return_value={}),
        ):
            payload = http_app.public_cases_for_user({"id": self.owner_id, "role": "contestant"})
        self.assertEqual([item["id"] for item in payload], ["training-case", "test-case"])
        self.assertEqual(payload[1]["fault_phenomenon"], "Phenomenon test-case")

    def test_test_set_owner_can_view_full_historical_detail_and_ai_analysis(self):
        submission_id = self._insert_submission("test-case")
        historical_case = self._case("test-case", 58, "ungrouped", ai_visible=False)
        case_map = {"test-case": historical_case}
        with (
            patch.object(submissions, "load_public_cases_map", return_value=case_map),
            patch.object(submissions, "load_cases_map", return_value=case_map),
            patch.object(submissions, "resolve_answer_mcp_servers", return_value=[]),
            patch.object(submissions, "profile_skills", return_value=[]),
        ):
            item = submissions.get_submission(
                submission_id,
                {"id": self.owner_id, "role": "contestant"},
            )
            forbidden = submissions.get_submission(
                submission_id,
                {"id": self.other_id, "role": "contestant"},
            )

        self.assertEqual(forbidden, "forbidden")
        self.assertEqual(item["case_id"], "test-case")
        self.assertEqual(item["case"]["title"], "Title test-case")
        self.assertTrue(item["can_view_ai_analysis"])
        self.assertEqual(item["prompt"], "rendered prompt")
        self.assertEqual(item["answer_output"], "answer output")
        self.assertEqual(item["grade_output"], "grade output")
        self.assertEqual(item["result_summary"], "analysis summary")
        self.assertEqual(item["run_log"], "run log")
        self.assertNotIn("api_key", item)
        self.assertNotIn("grader_api_key", item)
        self.assertNotIn("skills_json", item)
        self.assertNotIn("runner_meta", item)

    def test_normal_ungrouped_submission_remains_hidden(self):
        submission_id = self._insert_submission("ungrouped-case", source_kind="case")
        case_map = {"ungrouped-case": self._case("ungrouped-case", 62, "ungrouped")}
        with patch.object(submissions, "load_public_cases_map", return_value=case_map):
            item = submissions.get_submission(
                submission_id,
                {"id": self.owner_id, "role": "contestant"},
            )
        self.assertEqual(item, "forbidden")

    def test_test_member_cannot_be_submitted_as_single_case(self):
        test_case = self._case("test-case", 58, "test-set-1")
        with patch.object(submissions, "load_cases_map", return_value={"test-case": test_case}):
            with self.assertRaisesRegex(ValueError, "unknown case"):
                submissions.create_submission(
                    {"id": self.owner_id, "role": "contestant"},
                    {"case_id": "test-case", "prompt": "prompt", "skill_ids": [], "mcp_servers": []},
                )

    def test_submission_list_opens_only_for_owner_but_reveals_real_identity(self):
        case = self._case("test-case", 58, "test-set-1", ai_visible=False)
        row = {
            "id": 10,
            "user_id": self.owner_id,
            "username": "owner",
            "case_id": "test-case",
            "case_name": "Title test-case",
            "source_kind": "test_set",
            "test_set_id": "test-set-1",
            "test_set_name": "Test Set 1",
            "test_set_case_index": 1,
            "display_case_name": "Test Set 1-1",
            "status": "done",
            "api_base_url": "https://answer.example/v1",
            "model": "model-x",
            "score": 88,
            "result_summary": "analysis summary",
            "created_at": "2026-01-01T00:00:00+00:00",
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:01:00+00:00",
            "updated_at": "2026-01-01T00:01:00+00:00",
        }
        owner_item = submissions.submission_public(
            dict(row), {"id": self.owner_id, "role": "contestant"}, case
        )
        other_item = submissions.submission_public(
            dict(row), {"id": self.other_id, "role": "contestant"}, case
        )
        self.assertTrue(owner_item["can_view_content"])
        self.assertFalse(other_item["can_view_content"])
        self.assertEqual(owner_item["case_id"], "test-case")
        self.assertEqual(other_item["case_id"], "test-case")
        self.assertEqual(owner_item["case_name"], "Test Set 1-1")
        self.assertEqual(owner_item["test_set_name"], "Test Set 1")
        self.assertEqual(owner_item["result_summary"], "analysis summary")
        self.assertEqual(other_item["result_summary"], "")
        self.assertEqual(other_item["api_base_url"], "")


class RumPlatformSkillTests(unittest.TestCase):
    def test_rum2_skill_is_platform_mounted_without_setup_or_credentials(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            names = write_platform_skills(home, ["rum2"])
            self.assertEqual(names, [RUM2_PLATFORM_SKILL_NAME])
            skill_dir = home / "skills" / RUM2_PLATFORM_SKILL_NAME
            self.assertTrue((skill_dir / "SKILL.md").is_file())
            self.assertFalse((skill_dir / "setup.sh").exists())
            text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in skill_dir.rglob("*.md")
            )
            self.assertNotIn("RUM_TOKEN", text)
            self.assertNotIn("<YOUR_SECRET", text)

            contestant_names = write_contestant_skills(
                home,
                "",
                json.dumps(
                    [
                        {
                            "id": "skill-123456",
                            "type": "text",
                            "name": RUM2_PLATFORM_SKILL_NAME,
                            "content": "contestant content",
                        }
                    ]
                ),
                reserved_names=names,
            )
            self.assertEqual(contestant_names, "SKILL1")


class TestSetHttpApiTests(unittest.TestCase):
    def test_admin_can_rename_and_delete_a_test_set(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            faults_dir = root / "faults"
            faults_dir.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "test_sets": [
                            {
                                "id": "test-set-1",
                                "name": "Test Set 1",
                                "order_id": 1,
                                "submission_enabled": True,
                            }
                        ],
                        "next_test_set_number": 2,
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(settings, "STATE_DIR", root / "state"),
                patch.object(settings, "DB_FILE", root / "state" / "oj.sqlite3"),
                patch.object(settings, "CONFIG_FILE", config_path),
                patch.object(settings, "FAULTS_DIR", faults_dir),
            ):
                db.init_db()
                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    base_url = f"http://127.0.0.1:{server.server_port}"
                    status, login = self._request(
                        base_url,
                        "POST",
                        "/api/auth/login",
                        {"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
                    )
                    self.assertEqual(status, 200)
                    token = login["token"]

                    status, renamed = self._request(
                        base_url,
                        "PATCH",
                        "/api/admin/test-sets/test-set-1",
                        {"name": "Renamed Set"},
                        token,
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(renamed["test_set"]["name"], "Renamed Set")

                    status, deleted = self._request(
                        base_url,
                        "DELETE",
                        "/api/admin/test-sets/test-set-1",
                        token=token,
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(deleted["deleted"]["moved_case_count"], 0)

                    status, _payload = self._request(
                        base_url,
                        "PATCH",
                        "/api/admin/test-sets/missing",
                        {"name": "Missing"},
                        token,
                    )
                    self.assertEqual(status, 404)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
                    gc.collect()

    @staticmethod
    def _request(base_url, method, path, payload=None, token=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()

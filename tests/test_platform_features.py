import gc
import http.client
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

import server as oj_server
from oj_platform import cases, db, http_app, model_config, settings, submissions
from oj_platform.http_app import Handler
from oj_platform.mcp import default_case_mcp_servers
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

    def test_test_set_mcp_defaults_to_all_and_can_be_updated(self):
        normalized = cases.normalize_test_sets(cases.load_config())
        self.assertEqual(normalized[0]["mcp_servers"], default_case_mcp_servers())

        updated = cases.update_test_set_mcp_servers(
            "test-set-1",
            {"mcp_servers": ["rum", "multi-cloud-ssh"]},
        )
        self.assertEqual(updated["test_set"]["mcp_servers"], ["rum", "multi-cloud-ssh"])

        with self.assertRaisesRegex(ValueError, "unsupported submission mcp server"):
            cases.update_test_set_mcp_servers("test-set-1", {"mcp_servers": ["not-real"]})


class SubmissionFilterTests(unittest.TestCase):
    def test_submission_filters_use_training_cases_and_whole_test_sets(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            root = Path(temp_dir)
            state_dir = root / "state"
            db_file = state_dir / "oj.sqlite3"
            case_map = {
                "training-case": {
                    "id": "training-case",
                    "order_id": 1,
                    "title": "Training Case",
                    "case_set_id": "training",
                },
                "test-case-a": {
                    "id": "test-case-a",
                    "order_id": 58,
                    "title": "Test Case A",
                    "case_set_id": "test-set-1",
                },
                "test-case-b": {
                    "id": "test-case-b",
                    "order_id": 59,
                    "title": "Test Case B",
                    "case_set_id": "test-set-1",
                },
                "ungrouped-case": {
                    "id": "ungrouped-case",
                    "order_id": 62,
                    "title": "Ungrouped Case",
                    "case_set_id": "ungrouped",
                },
            }
            with (
                patch.object(settings, "STATE_DIR", state_dir),
                patch.object(settings, "DB_FILE", db_file),
                patch.object(
                    submissions,
                    "public_test_sets",
                    return_value=[
                        {
                            "id": "test-set-1",
                            "name": "Test Set 1",
                            "case_numbers": [58, 59],
                        }
                    ],
                ),
                patch.object(submissions, "load_public_cases_map", return_value=case_map),
            ):
                db.init_db()
                with db.connect() as conn:
                    conn.execute(
                        "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'contestant', ?)",
                        ("contestant", "hash", "2026-01-01T00:00:00+00:00"),
                    )
                    user_id = conn.execute("SELECT id FROM users WHERE username = 'contestant'").fetchone()["id"]
                    for case_id, source_kind, test_set_id, display_name in (
                        ("training-case", "case", None, None),
                        ("test-case-a", "test_set", "test-set-1", "Test Set 1-1"),
                        ("test-case-b", "test_set", "test-set-1", "Test Set 1-2"),
                        ("ungrouped-case", "case", None, None),
                    ):
                        conn.execute(
                            """
                            INSERT INTO submissions (
                                user_id, case_id, source_kind, test_set_id, display_case_name,
                                status, api_base_url, api_key_mask, model, prompt,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, 'done', ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                user_id,
                                case_id,
                                source_kind,
                                test_set_id,
                                display_name,
                                "https://answer.example/v1",
                                "ans...cret",
                                "model-x",
                                "prompt",
                                "2026-01-01T00:00:00+00:00",
                                "2026-01-01T00:00:00+00:00",
                            ),
                        )

                user = {"id": user_id, "role": "contestant"}
                unfiltered = submissions.list_submissions(user)
                self.assertEqual(
                    unfiltered["test_set_filters"],
                    [
                        {
                            "id": "test-set-1",
                            "test_set_id": "test-set-1",
                            "name": "Test Set 1",
                            "case_numbers": [58, 59],
                        }
                    ],
                )

                by_test_set = submissions.list_submissions(user, test_set_id="test-set-1")
                self.assertEqual(by_test_set["total"], 2)
                self.assertEqual(
                    {item["case_id"] for item in by_test_set["submissions"]},
                    {"test-case-a", "test-case-b"},
                )

                by_training_case = submissions.list_submissions(user, case_id="training-case")
                self.assertEqual(by_training_case["total"], 1)
                self.assertEqual(by_training_case["submissions"][0]["case_id"], "training-case")

                by_test_member_case = submissions.list_submissions(user, case_id="test-case-a")
                self.assertEqual(by_test_member_case["total"], 0)

                by_ungrouped_case = submissions.list_submissions(user, case_id="ungrouped-case")
                self.assertEqual(by_ungrouped_case["total"], 0)
                gc.collect()


class QueueLimitTests(unittest.TestCase):
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
                ("contestant", "hash", "2026-01-01T00:00:00+00:00"),
            )
            self.user_id = conn.execute("SELECT id FROM users WHERE username = 'contestant'").fetchone()["id"]

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        gc.collect()
        self.temp_dir.cleanup()

    def _insert_queued(self, user_id, count):
        now = "2026-01-01T00:00:00+00:00"
        with db.connect() as conn:
            for index in range(count):
                conn.execute(
                    """
                    INSERT INTO submissions (
                        user_id, case_id, status, api_base_url, api_key_mask, model,
                        prompt, created_at, updated_at
                    ) VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        f"case-{index}",
                        "https://answer.example/v1",
                        "ans...cret",
                        "model-x",
                        "prompt",
                        now,
                        now,
                    ),
                )

    def test_contestant_can_have_at_most_50_queued_submissions(self):
        self._insert_queued(self.user_id, 49)
        with db.connect() as conn:
            submissions.enforce_queue_limit(conn, {"id": self.user_id, "role": "contestant"}, 1)
            with self.assertRaisesRegex(ValueError, "50 queued submissions"):
                submissions.enforce_queue_limit(conn, {"id": self.user_id, "role": "contestant"}, 2)

    def test_admin_is_not_limited_by_queued_submission_cap(self):
        self._insert_queued(self.user_id, 50)
        with db.connect() as conn:
            submissions.enforce_queue_limit(conn, {"id": 9999, "role": "admin"}, 500)


class LeaderboardTestSetScoringTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.state_dir = self.root / "state"
        self.db_file = self.state_dir / "oj.sqlite3"
        self.cases = [
            self._case("hidden-case", 1, "training", ai_visible=False),
            self._case("test-case-a", 58, "test-set-1"),
            self._case("test-case-b", 59, "test-set-1"),
            self._case("test-case-c", 60, "test-set-2"),
        ]
        self.test_sets = [
            {"id": "test-set-1", "name": "Test Set 1", "case_numbers": [58, 59]},
            {"id": "test-set-2", "name": "Test Set 2", "case_numbers": [60]},
        ]
        self.patchers = [
            patch.object(settings, "STATE_DIR", self.state_dir),
            patch.object(settings, "DB_FILE", self.db_file),
            patch.object(submissions, "load_cases_list", return_value=self.cases),
            patch.object(submissions, "public_test_sets", return_value=self.test_sets),
            patch.object(http_app, "public_test_sets", return_value=self.test_sets),
        ]
        for patcher in self.patchers:
            patcher.start()
        db.init_db()
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'contestant', ?)",
                ("alice", "hash", "2026-01-01T00:00:00+00:00"),
            )
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'contestant', ?)",
                ("bob", "hash", "2026-01-01T00:00:00+00:00"),
            )
            conn.execute(
                "INSERT INTO users (username, password_hash, role, disabled, created_at) VALUES (?, ?, 'contestant', 1, ?)",
                ("disabled", "hash", "2026-01-01T00:00:00+00:00"),
            )
            self.alice_id = conn.execute("SELECT id FROM users WHERE username = 'alice'").fetchone()["id"]
            self.bob_id = conn.execute("SELECT id FROM users WHERE username = 'bob'").fetchone()["id"]
            self.disabled_id = conn.execute("SELECT id FROM users WHERE username = 'disabled'").fetchone()["id"]
            self.admin_id = conn.execute("SELECT id FROM users WHERE username = ?", (settings.ADMIN_USERNAME,)).fetchone()["id"]

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
            "submission_enabled": True,
            "ai_analysis_visible": ai_visible,
        }

    def _insert_submission(
        self,
        user_id,
        case_id,
        score,
        source_kind="case",
        test_set_id=None,
        group_id=None,
        status="done",
        created_at="2026-01-01T00:00:00+00:00",
    ):
        with db.connect() as conn:
            conn.execute(
                """
                INSERT INTO submissions (
                    user_id, case_id, source_kind, test_set_id, submission_group_id,
                    status, api_base_url, api_key_mask, model, prompt, score,
                    created_at, finished_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    case_id,
                    source_kind,
                    test_set_id,
                    group_id,
                    status,
                    "https://answer.example/v1",
                    "ans...cret",
                    "model-x",
                    "prompt",
                    score,
                    created_at,
                    created_at,
                    created_at,
                ),
            )

    def _seed_scores(self):
        self._insert_submission(self.alice_id, "hidden-case", 30, created_at="2026-01-01T00:01:00+00:00")
        self._insert_submission(self.alice_id, "hidden-case", 40, created_at="2026-01-01T00:02:00+00:00")
        self._insert_submission(
            self.alice_id, "test-case-a", 100, "test_set", "test-set-1", "alice-g1", created_at="2026-01-01T00:03:00+00:00"
        )
        self._insert_submission(
            self.alice_id, "test-case-b", 50, "test_set", "test-set-1", "alice-g1", created_at="2026-01-01T00:04:00+00:00"
        )
        self._insert_submission(
            self.alice_id, "test-case-a", 50, "test_set", "test-set-1", "alice-g2", created_at="2026-01-01T00:05:00+00:00"
        )
        self._insert_submission(
            self.alice_id, "test-case-b", 100, "test_set", "test-set-1", "alice-g2", created_at="2026-01-01T00:06:00+00:00"
        )
        self._insert_submission(
            self.alice_id, "test-case-a", 100, "case", None, None, created_at="2026-01-01T00:07:00+00:00"
        )
        self._insert_submission(
            self.alice_id, "test-case-c", 80, "test_set", "test-set-2", "alice-g3", created_at="2026-01-01T00:08:00+00:00"
        )
        self._insert_submission(
            self.bob_id, "test-case-a", 100, "test_set", "test-set-1", "bob-g1", created_at="2026-01-01T00:09:00+00:00"
        )
        self._insert_submission(
            self.bob_id, "test-case-b", 100, "test_set", "test-set-1", "bob-g1", created_at="2026-01-01T00:10:00+00:00"
        )
        self._insert_submission(
            self.disabled_id, "test-case-a", 100, "test_set", "test-set-1", "disabled-g1", created_at="2026-01-01T00:11:00+00:00"
        )
        self._insert_submission(
            self.disabled_id, "test-case-b", 100, "test_set", "test-set-1", "disabled-g1", created_at="2026-01-01T00:12:00+00:00"
        )
        self._insert_submission(
            self.admin_id, "test-case-a", 100, "test_set", "test-set-1", "admin-g1", created_at="2026-01-01T00:13:00+00:00"
        )
        self._insert_submission(
            self.admin_id, "test-case-b", 100, "test_set", "test-set-1", "admin-g1", created_at="2026-01-01T00:14:00+00:00"
        )

    def test_leaderboard_uses_only_best_whole_test_set_attempt(self):
        self._seed_scores()
        payload = submissions.hidden_case_leaderboard()
        rows = {item["username"]: item for item in payload["leaderboard"]}

        self.assertEqual(rows["alice"]["total_score"], 230)
        self.assertEqual(rows["alice"]["scored_cases"], 3)
        self.assertEqual(rows["bob"]["total_score"], 200)
        self.assertNotIn("disabled", rows)
        self.assertNotIn(settings.ADMIN_USERNAME, rows)
        self.assertEqual(payload["test_set_case_count"], 3)
        self.assertEqual(payload["hidden_case_count"], 0)
        self.assertEqual(payload["leaderboard_case_count"], 3)

    def test_personal_best_scores_by_test_set_uses_same_whole_group_rule(self):
        self._seed_scores()
        best = submissions.personal_best_scores_by_test_set(self.alice_id)
        self.assertEqual(best, {"test-set-1": 150, "test-set-2": 80})

        visible = http_app.public_test_sets_for_user({"id": self.alice_id, "role": "contestant"})
        scores = {item["id"]: item.get("personal_best_score") for item in visible}
        self.assertEqual(scores, {"test-set-1": 150, "test-set-2": 80})

    def test_failed_test_set_member_counts_as_zero_in_group_score(self):
        self._insert_submission(
            self.alice_id,
            "test-case-a",
            60,
            "test_set",
            "test-set-1",
            "alice-partial",
            status="done",
            created_at="2026-01-01T00:01:00+00:00",
        )
        self._insert_submission(
            self.alice_id,
            "test-case-b",
            None,
            "test_set",
            "test-set-1",
            "alice-partial",
            status="failed",
            created_at="2026-01-01T00:02:00+00:00",
        )
        self._insert_submission(
            self.alice_id,
            "test-case-a",
            100,
            "test_set",
            "test-set-1",
            "alice-unfinished",
            status="done",
            created_at="2026-01-01T00:03:00+00:00",
        )
        self._insert_submission(
            self.alice_id,
            "test-case-b",
            None,
            "test_set",
            "test-set-1",
            "alice-unfinished",
            status="queued",
            created_at="2026-01-01T00:04:00+00:00",
        )

        best = submissions.personal_best_scores_by_test_set(self.alice_id)
        self.assertEqual(best, {"test-set-1": 60})

        payload = submissions.hidden_case_leaderboard()
        rows = {item["username"]: item for item in payload["leaderboard"]}
        self.assertEqual(rows["alice"]["total_score"], 60)
        self.assertEqual(rows["alice"]["scored_cases"], 2)


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

    def test_test_set_prompt_without_placeholders_stays_unchanged(self):
        case = self._case("test-case", 58, "test-set-1")
        rendered = submissions.render_test_set_prompt("请开始诊断。", case)
        self.assertEqual(rendered, "请开始诊断。")

    def test_test_set_prompt_replaces_placeholders_only_when_used(self):
        case = self._case("test-case", 58, "test-set-1")
        rendered = submissions.render_test_set_prompt(
            "现象={{fault_phenomenon}}\n信息={{public_case_info}}",
            case,
        )
        self.assertEqual(rendered.count("Phenomenon test-case"), 1)
        self.assertEqual(rendered.count("Public test-case"), 1)

    def test_test_set_owner_can_view_historical_detail_but_respects_ai_visibility(self):
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
        self.assertFalse(item["can_view_ai_analysis"])
        self.assertEqual(item["prompt"], "rendered prompt")
        self.assertEqual(item["answer_output"], "answer output")
        self.assertEqual(item["grade_output"], "")
        self.assertEqual(item["result_summary"], "")
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

    def test_test_set_submission_uses_admin_mcp_snapshot(self):
        data = submissions.validate_test_set_submission_payload(
            {
                "prompt": "prompt",
                "skill_ids": [],
                "mcp_servers": ["not-a-real-mcp"],
            }
        )
        runtime = {
            "model_profile": {
                "api_base_url": "https://answer.example/v1",
                "api_key": "answer-secret",
                "api_key_mask": "ans...cret",
                "model": "model-x",
            },
            "grader_profile": {
                "api_base_url": "https://grader.example/v1",
                "api_key": "grader-secret",
                "api_key_mask": "gra...cret",
                "model": "grader-x",
            },
            "skill_fields": {"skill": "", "skills_json": "[]"},
            "soul_md": "",
        }
        test_case = self._case("test-case", 58, "test-set-1")
        with (
            patch.object(
                submissions,
                "test_set_by_id",
                return_value={
                    "id": "test-set-1",
                    "name": "Test Set 1",
                    "submission_enabled": True,
                    "mcp_servers": ["rum"],
                },
            ),
            patch.object(submissions, "test_set_members", return_value=[test_case]),
            patch.object(submissions, "submission_runtime_context", return_value=runtime),
        ):
            submissions.create_test_set_submissions(
                {"id": self.owner_id, "role": "contestant"},
                "test-set-1",
                {**data, "mcp_servers": ["k3s-cluster"]},
            )

        with db.connect() as conn:
            row = conn.execute(
                "SELECT answer_mcp_servers_json FROM submissions ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(json.loads(row["answer_mcp_servers_json"]), ["rum"])

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
        self.assertEqual(owner_item["result_summary"], "")
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


class GraderConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.state_dir = self.root / "state"
        self.db_file = self.state_dir / "oj.sqlite3"
        self.patchers = [
            patch.object(settings, "STATE_DIR", self.state_dir),
            patch.object(settings, "DB_FILE", self.db_file),
            patch.object(settings, "GRADER_BASE_URL", ""),
            patch.object(settings, "GRADER_API_KEY", ""),
            patch.object(settings, "GRADER_MODEL", ""),
        ]
        for patcher in self.patchers:
            patcher.start()
        db.init_db()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        gc.collect()
        self.temp_dir.cleanup()

    def test_platform_grader_config_is_saved_masked_and_used(self):
        with patch.object(
            model_config,
            "check_model_available",
            return_value={"ok": True, "message": "model is available", "model": "grader-model"},
        ):
            saved = model_config.update_platform_grader_config(
                {
                    "base_url": "https://grader.example/v1/",
                    "api_key": "secret-key-123456",
                    "model": "grader-model",
                }
            )

        self.assertTrue(saved["configured"])
        self.assertEqual(saved["api_base_url"], "https://grader.example/v1")
        public = model_config.public_grader_config()
        public_text = json.dumps(public, ensure_ascii=False)
        self.assertIn("api_key_mask", public)
        self.assertNotIn("secret-key-123456", public_text)

        effective = model_config.require_submission_grader_config({})
        self.assertEqual(effective["api_key"], "secret-key-123456")
        self.assertEqual(effective["model"], "grader-model")

    def test_submission_grader_snapshot_takes_precedence(self):
        with patch.object(
            model_config,
            "check_model_available",
            return_value={"ok": True, "message": "model is available", "model": "new-model"},
        ):
            model_config.update_platform_grader_config(
                {
                    "base_url": "https://new-grader.example/v1",
                    "api_key": "new-secret-key",
                    "model": "new-model",
                }
            )

        effective = model_config.require_submission_grader_config(
            {
                "grader_api_key": "old-secret-key",
                "grader_base_url": "https://old-grader.example/v1",
                "grader_model": "old-model",
            }
        )
        self.assertEqual(effective["api_key"], "old-secret-key")
        self.assertEqual(effective["api_base_url"], "https://old-grader.example/v1")
        self.assertEqual(effective["model"], "old-model")


class StaticAssetCacheTests(unittest.TestCase):
    def test_platform_http_server_accepts_module_bursts(self):
        self.assertGreaterEqual(oj_server.OJThreadingHTTPServer.request_queue_size, 128)
        self.assertTrue(oj_server.OJThreadingHTTPServer.daemon_threads)

    def test_service_worker_serves_static_cache_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            static_dir = root / "static"
            app_dir = static_dir / "app"
            app_dir.mkdir(parents=True)
            (static_dir / "styles.css").write_text("body { color: #111; }\n", encoding="utf-8")
            (app_dir / "main.js").write_text("import './state.js';\n", encoding="utf-8")
            (app_dir / "state.js").write_text("export const state = {};\n", encoding="utf-8")
            with (
                patch.object(settings, "ROOT", root),
                patch.object(settings, "STATIC_DIR", static_dir),
            ):
                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    status, headers, body = self._get(server.server_port, "/service-worker.js")
                    text = body.decode("utf-8")
                    self.assertEqual(status, 200)
                    self.assertEqual(headers["Cache-Control"], "no-store")
                    self.assertEqual(headers["Service-Worker-Allowed"], "/")
                    self.assertIn("oj-static-", text)
                    self.assertIn("/static/styles.css", text)
                    self.assertIn("/static/app/main.js", text)
                    self.assertIn("/static/app/state.js", text)
                    self.assertIn("warmStaticCache", text)
                    self.assertIn("cache.put", text)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
                    gc.collect()

    def test_static_js_uses_browser_cache_and_conditional_304(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            static_dir = root / "static"
            app_dir = static_dir / "app"
            app_dir.mkdir(parents=True)
            (app_dir / "main.js").write_bytes(b"export const ok = true;\n")
            (static_dir / "index.html").write_text(
                '<script type="module" src="/static/app/main.js"></script>',
                encoding="utf-8",
            )
            with (
                patch.object(settings, "ROOT", root),
                patch.object(settings, "STATIC_DIR", static_dir),
            ):
                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    status, headers, body = self._get(server.server_port, "/static/app/main.js")
                    self.assertEqual(status, 200)
                    self.assertEqual(body, b"export const ok = true;\n")
                    self.assertIn("public", headers["Cache-Control"])
                    self.assertIn("max-age=300", headers["Cache-Control"])
                    self.assertIn("ETag", headers)
                    self.assertIn("Last-Modified", headers)

                    status, cached_headers, body = self._get(
                        server.server_port,
                        "/static/app/main.js",
                        {"If-None-Match": headers["ETag"]},
                    )
                    self.assertEqual(status, 304)
                    self.assertEqual(body, b"")
                    self.assertEqual(cached_headers["ETag"], headers["ETag"])
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
                    gc.collect()

    def test_spa_entry_is_not_cached(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            static_dir = root / "static"
            static_dir.mkdir(parents=True)
            (static_dir / "index.html").write_text("<main>OJ</main>", encoding="utf-8")
            with (
                patch.object(settings, "ROOT", root),
                patch.object(settings, "STATIC_DIR", static_dir),
            ):
                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    status, headers, body = self._get(server.server_port, "/")
                    self.assertEqual(status, 200)
                    self.assertEqual(body, b"<main>OJ</main>")
                    self.assertEqual(headers["Cache-Control"], "no-store")
                    self.assertNotIn("ETag", headers)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
                    gc.collect()

    @staticmethod
    def _get(port, path, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", path, headers=headers or {})
            response = connection.getresponse()
            body = response.read()
            return response.status, dict(response.getheaders()), body
        finally:
            connection.close()


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

                    status, updated_mcp = self._request(
                        base_url,
                        "PATCH",
                        "/api/admin/test-sets/test-set-1/mcp-servers",
                        {"mcp_servers": ["rum"]},
                        token,
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(updated_mcp["test_set"]["mcp_servers"], ["rum"])

                    status, _payload = self._request(
                        base_url,
                        "PATCH",
                        "/api/admin/test-sets/test-set-1/mcp-servers",
                        {"mcp_servers": ["missing-mcp"]},
                        token,
                    )
                    self.assertEqual(status, 400)

                    with patch.object(
                        model_config,
                        "check_model_available",
                        return_value={"ok": True, "message": "model is available", "model": "grader-model"},
                    ):
                        status, checked = self._request(
                            base_url,
                            "POST",
                            "/api/admin/grader-config/check",
                            {
                                "base_url": "https://grader.example/v1",
                                "api_key": "grader-secret",
                                "model": "grader-model",
                            },
                            token,
                        )
                        self.assertEqual(status, 200)
                        self.assertTrue(checked["ok"])

                        status, saved = self._request(
                            base_url,
                            "PATCH",
                            "/api/admin/grader-config",
                            {
                                "base_url": "https://grader.example/v1",
                                "api_key": "grader-secret",
                                "model": "grader-model",
                            },
                            token,
                        )
                    self.assertEqual(status, 200)
                    self.assertTrue(saved["grader"]["configured"])
                    self.assertNotIn("grader-secret", json.dumps(saved, ensure_ascii=False))

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

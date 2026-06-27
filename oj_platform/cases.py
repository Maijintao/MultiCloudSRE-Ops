import json
import io
import os
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path
from pathlib import PurePosixPath
import zipfile

from .mcp import normalize_selected_public_mcp_servers, public_case_mcp_server_options
from . import settings
from . import db

CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
CASE_SET_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
TRAINING_CASE_SET_ID = "training"
UNGROUPED_CASE_SET_ID = "ungrouped"
CASE_EDITOR_FILES = {
    "case_json": "case.json",
    "inject_script": "inject.sh",
    "recover_script": "recover.sh",
    "ideal_answer_json": "ideal-answer.json",
    "rubrics_json": "rubrics.json",
}
CASE_ARCHIVE_REQUIRED_FILES = tuple(CASE_EDITOR_FILES.values())
CASE_ARCHIVE_FILE_KEYS = {filename.lower(): key for key, filename in CASE_EDITOR_FILES.items()}
PUBLIC_CASE_FIELDS = (
    "id",
    "order_id",
    "title",
    "case_set_id",
    "fault_phenomenon",
    "public_case_info",
    "submission_enabled",
    "ai_analysis_visible",
)
PUBLIC_CASE_SUMMARY_FIELDS = tuple(
    key for key in PUBLIC_CASE_FIELDS
    if key not in {"fault_phenomenon", "public_case_info"}
)
_PUBLIC_CASES_CACHE = {}
_TEST_SET_LOCK = threading.RLock()
_NUMBERED_TEST_SET_ID_PATTERN = re.compile(r"^test-set-(\d+)$")


def normalize_case_flag(value, name, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError(f"{name} must be a boolean")


def read_json_object(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_json_object(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        fd, temp_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            text=True,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temp_path = Path(temp_name)
        try:
            temp_path.replace(path)
        except PermissionError:
            path.write_text(temp_path.read_text(encoding="utf-8"), encoding="utf-8")
            try:
                temp_path.unlink(missing_ok=True)
            except PermissionError:
                pass
            temp_path = None
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except PermissionError:
                pass


def write_text_file(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        fd, temp_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            text=True,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        temp_path = Path(temp_name)
        try:
            temp_path.replace(path)
        except PermissionError:
            path.write_text(temp_path.read_text(encoding="utf-8"), encoding="utf-8")
            try:
                temp_path.unlink(missing_ok=True)
            except PermissionError:
                pass
            temp_path = None
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except PermissionError:
                pass


def delete_case_directory(case_dir, attempts=20, delay_seconds=0.1):
    case_dir = Path(case_dir)
    if not case_dir.exists():
        return
    last_error = None
    for _ in range(max(1, attempts)):
        for temp_path in case_dir.rglob(".*.tmp"):
            try:
                temp_path.unlink(missing_ok=True)
            except PermissionError as exc:
                last_error = exc
        try:
            def handle_remove_error(func, target, exc_info):
                nonlocal last_error
                last_error = exc_info[1]
                try:
                    os.chmod(target, 0o777)
                    func(target)
                    last_error = None
                except Exception as exc:  # pragma: no cover - best effort cleanup path
                    last_error = exc

            shutil.rmtree(case_dir, onerror=handle_remove_error)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(delay_seconds)
    if last_error:
        raise last_error
    raise RuntimeError(f"failed to delete case directory: {case_dir}")


def decode_archive_text(filename, data):
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{filename} in zip archive must be UTF-8 text") from exc


def extract_case_archive_payload(filename, archive_bytes):
    if len(archive_bytes) > settings.MAX_CASE_ARCHIVE_BYTES:
        raise ValueError(f"zip archive is too large, max {settings.MAX_CASE_ARCHIVE_BYTES} bytes")
    archive_stream = io.BytesIO(archive_bytes)
    if not zipfile.is_zipfile(archive_stream):
        raise ValueError("case archive must be a valid zip file")
    archive_stream.seek(0)

    found_files = {}
    with zipfile.ZipFile(archive_stream) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            basename = PurePosixPath(info.filename).name
            if not basename:
                continue
            file_key = CASE_ARCHIVE_FILE_KEYS.get(basename.lower())
            if not file_key:
                continue
            if file_key in found_files:
                raise ValueError(f"zip archive contains duplicate {CASE_EDITOR_FILES[file_key]}")
            found_files[file_key] = decode_archive_text(
                CASE_EDITOR_FILES[file_key],
                archive.read(info),
            )

    missing = [name for key, name in CASE_EDITOR_FILES.items() if key not in found_files]
    if missing:
        raise ValueError(
            "zip archive must contain these files: " + ", ".join(CASE_ARCHIVE_REQUIRED_FILES)
            + f"; missing: {', '.join(missing)}"
        )

    return {
        key: validated_file_text(found_files[key], CASE_EDITOR_FILES[key])
        for key in CASE_EDITOR_FILES
    }


def resolve_case_data_file(case_dir, filename, label):
    target = (case_dir / filename).resolve()
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"missing {label}: {target}")
    return target


def resolve_case_ideal_answer(case_dir):
    return resolve_case_data_file(case_dir, "ideal-answer.json", "ideal answer")


def resolve_case_rubrics(case_dir):
    return resolve_case_data_file(case_dir, "rubrics.json", "rubrics")


def _required_object(value, name, case_dir):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object in {case_dir}")
    return value


def _required_string(value, name, case_dir):
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} must be a non-empty string in {case_dir}")
    return text


def _optional_string_or_null(value, name, case_dir):
    if value is None:
        return None
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} must be null or a non-empty string in {case_dir}")
    return text


def _required_string_list(value, name, case_dir):
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty array in {case_dir}")
    items = []
    for index, item in enumerate(value, start=1):
        text = str(item or "").strip()
        if not text:
            raise ValueError(f"{name}[{index}] must be a non-empty string in {case_dir}")
        items.append(text)
    return items


def _required_cloud_list(value, name, case_dir):
    allowed = {"aliyun", "tencent", "aws", "azure", "gcp", "huawei", "volcengine", "baidu", "unknown"}
    items = _required_string_list(value, name, case_dir)
    invalid = [item for item in items if item not in allowed]
    if invalid:
        raise ValueError(f"{name} contains unsupported clouds in {case_dir}: {', '.join(invalid)}")
    return items


def validate_ideal_answer(case_dir, answer):
    required_sections = ("fault_info", "reasoning_process", "verification_method", "proposed_resolution", "confidence")
    missing = [key for key in required_sections if key not in answer]
    if missing:
        raise ValueError(f"ideal answer missing sections in {case_dir}: {', '.join(missing)}")

    fault_info = _required_object(answer.get("fault_info"), "fault_info", case_dir)
    _required_string(fault_info.get("root_cause"), "fault_info.root_cause", case_dir)
    _required_cloud_list(fault_info.get("faulty_clouds"), "fault_info.faulty_clouds", case_dir)
    _required_cloud_list(fault_info.get("affected_clouds"), "fault_info.affected_clouds", case_dir)
    fault_location = _required_object(fault_info.get("fault_location"), "fault_info.fault_location", case_dir)
    _required_string(fault_location.get("module"), "fault_info.fault_location.module", case_dir)
    _optional_string_or_null(fault_location.get("file_path"), "fault_info.fault_location.file_path", case_dir)
    _optional_string_or_null(
        fault_location.get("function_or_config"),
        "fault_info.fault_location.function_or_config",
        case_dir,
    )
    _required_string(fault_location.get("description"), "fault_info.fault_location.description", case_dir)

    reasoning = _required_object(answer.get("reasoning_process"), "reasoning_process", case_dir)
    _required_string_list(reasoning.get("observed_symptoms"), "reasoning_process.observed_symptoms", case_dir)
    _required_string_list(reasoning.get("causal_chain"), "reasoning_process.causal_chain", case_dir)
    evidence = reasoning.get("key_evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"reasoning_process.key_evidence must be a non-empty array in {case_dir}")
    for index, item in enumerate(evidence, start=1):
        item_name = f"reasoning_process.key_evidence[{index}]"
        item = _required_object(item, item_name, case_dir)
        _required_string(item.get("source"), f"{item_name}.source", case_dir)
        _required_string(item.get("content"), f"{item_name}.content", case_dir)
        _required_string(item.get("conclusion"), f"{item_name}.conclusion", case_dir)

    verification = _required_object(answer.get("verification_method"), "verification_method", case_dir)
    commands = verification.get("verification_commands")
    if not isinstance(commands, list) or not commands:
        raise ValueError(f"verification_method.verification_commands must be a non-empty array in {case_dir}")
    for index, item in enumerate(commands, start=1):
        item_name = f"verification_method.verification_commands[{index}]"
        item = _required_object(item, item_name, case_dir)
        _required_string(item.get("cmd"), f"{item_name}.cmd", case_dir)
        _required_string(item.get("purpose"), f"{item_name}.purpose", case_dir)
        _required_string(item.get("expected_result"), f"{item_name}.expected_result", case_dir)
    _required_string_list(verification.get("success_criteria"), "verification_method.success_criteria", case_dir)

    resolution = _required_object(answer.get("proposed_resolution"), "proposed_resolution", case_dir)
    _required_string(resolution.get("suggestion"), "proposed_resolution.suggestion", case_dir)
    _required_string_list(resolution.get("fix_steps"), "proposed_resolution.fix_steps", case_dir)

    confidence = answer.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise ValueError(f"confidence must be a number in {case_dir}")
    if confidence < 0 or confidence > 1:
        raise ValueError(f"confidence must be between 0 and 1 in {case_dir}")
    return answer


def validate_rubrics(case_dir, rubrics):
    rubrics = _required_object(rubrics, "rubrics.json", case_dir)
    positive_total = rubrics.get("positive_points_total")
    negative_total = rubrics.get("negative_points_total")
    if not isinstance(positive_total, int) or isinstance(positive_total, bool):
        raise ValueError(f"positive_points_total must be an integer in {case_dir}")
    if not isinstance(negative_total, int) or isinstance(negative_total, bool):
        raise ValueError(f"negative_points_total must be an integer in {case_dir}")
    if positive_total < 80 or positive_total > 120:
        raise ValueError(f"positive_points_total must be between 80 and 120 in {case_dir}")
    if negative_total > -40 or negative_total < -60:
        raise ValueError(f"negative_points_total must be between -60 and -40 in {case_dir}")
    items = rubrics.get("rubrics")
    if not isinstance(items, list) or not items:
        raise ValueError(f"rubrics must be a non-empty array in {case_dir}")
    computed_positive = 0
    computed_negative = 0
    for index, item in enumerate(items, start=1):
        item_name = f"rubrics[{index}]"
        item = _required_object(item, item_name, case_dir)
        _required_string(item.get("criterion"), f"{item_name}.criterion", case_dir)
        points = item.get("points")
        if not isinstance(points, int) or isinstance(points, bool) or points == 0:
            raise ValueError(f"{item_name}.points must be a non-zero integer in {case_dir}")
        tags = item.get("tags")
        if not isinstance(tags, list) or not tags:
            raise ValueError(f"{item_name}.tags must be a non-empty array in {case_dir}")
        for tag_index, tag in enumerate(tags, start=1):
            _required_string(tag, f"{item_name}.tags[{tag_index}]", case_dir)
        if points > 0:
            computed_positive += points
        else:
            computed_negative += points
    if computed_positive != positive_total:
        raise ValueError(
            f"positive rubric points must sum to {positive_total} in {case_dir}, got {computed_positive}"
        )
    if computed_negative != negative_total:
        raise ValueError(
            f"negative rubric points must sum to {negative_total} in {case_dir}, got {computed_negative}"
        )
    return rubrics


def validate_case_id(case_id, field_name="case id"):
    value = str(case_id or "").strip()
    if not CASE_ID_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must use 1-64 letters, numbers, dots, underscores, or hyphens")
    return value


def validate_case_set_id(case_set_id, field_name="case_set_id"):
    value = str(case_set_id or TRAINING_CASE_SET_ID).strip()
    if not CASE_SET_ID_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must use 1-64 letters, numbers, dots, underscores, or hyphens")
    return value


def validate_test_set_name(name, field_name="name"):
    value = str(name or "").strip()
    if not value:
        raise ValueError(f"{field_name} is required")
    if len(value) > 64:
        raise ValueError(f"{field_name} is too long, max 64 chars")
    if not value.isprintable():
        raise ValueError(f"{field_name} must not contain control characters")
    return value


def case_set_id(case):
    return validate_case_set_id((case or {}).get("case_set_id") or TRAINING_CASE_SET_ID)


def is_training_case(case):
    return case_set_id(case) == TRAINING_CASE_SET_ID


def is_ungrouped_case(case):
    return case_set_id(case) == UNGROUPED_CASE_SET_ID


def is_test_set_case(case):
    set_id = case_set_id(case)
    return set_id not in {TRAINING_CASE_SET_ID, UNGROUPED_CASE_SET_ID}


def normalize_test_sets(config):
    raw_sets = config.get("test_sets", []) if isinstance(config, dict) else []
    if raw_sets in (None, ""):
        raw_sets = []
    if not isinstance(raw_sets, list):
        raise ValueError("test_sets must be a list")
    items = []
    seen = set()
    seen_names = set()
    for index, raw_item in enumerate(raw_sets, start=1):
        if not isinstance(raw_item, dict):
            raise ValueError("test_sets items must be objects")
        test_set_id = validate_case_set_id(raw_item.get("id"), f"test_sets[{index}].id")
        if test_set_id in {TRAINING_CASE_SET_ID, UNGROUPED_CASE_SET_ID}:
            raise ValueError(f"test set id '{test_set_id}' is reserved")
        if test_set_id in seen:
            raise ValueError(f"duplicate test set id: {test_set_id}")
        seen.add(test_set_id)
        name = validate_test_set_name(raw_item.get("name") or f"测试集{index}", f"test_sets[{index}].name")
        normalized_name = name.casefold()
        if normalized_name in seen_names:
            raise ValueError(f"duplicate test set name: {name}")
        seen_names.add(normalized_name)
        order_id = raw_item.get("order_id", index)
        if isinstance(order_id, bool):
            raise ValueError(f"test_sets[{index}].order_id must be a positive integer")
        order_id = validated_order_id(order_id, f"test_sets[{index}].order_id")
        submission_enabled = normalize_case_flag(
            raw_item.get("submission_enabled"),
            f"test_sets[{index}].submission_enabled",
            True,
        )
        items.append({
            "id": test_set_id,
            "name": name,
            "order_id": order_id,
            "submission_enabled": submission_enabled,
        })
    return sorted(items, key=lambda item: (item["order_id"], item["id"]))


def public_test_sets():
    items = [dict(item) for item in normalize_test_sets(load_config())]
    case_numbers_by_set = {item["id"]: [] for item in items}
    for case in load_public_cases_list(include_test_cases=True, include_details=False):
        set_id = case_set_id(case)
        if set_id in case_numbers_by_set:
            case_numbers_by_set[set_id].append(case["order_id"])
    for item in items:
        item["case_numbers"] = case_numbers_by_set.get(item["id"], [])
    return items


def test_set_by_id(test_set_id):
    test_set_id = validate_case_set_id(test_set_id, "test set id")
    for item in public_test_sets():
        if item["id"] == test_set_id:
            return item
    return None


def test_set_members(test_set_id):
    test_set_id = validate_case_set_id(test_set_id, "test set id")
    return [
        case for case in load_cases_list()
        if case_set_id(case) == test_set_id
    ]


def validate_configured_case_set_id(value):
    set_id = validate_case_set_id(value)
    if set_id in {TRAINING_CASE_SET_ID, UNGROUPED_CASE_SET_ID}:
        return set_id
    if set_id not in {item["id"] for item in normalize_test_sets(load_config())}:
        raise ValueError("test set not found")
    return set_id


def _next_test_set_number(config, test_sets):
    highest_number = 0
    for item in test_sets:
        match = _NUMBERED_TEST_SET_ID_PATTERN.fullmatch(item["id"])
        if match:
            highest_number = max(highest_number, int(match.group(1)))
    raw_counter = config.get("next_test_set_number") if isinstance(config, dict) else None
    if isinstance(raw_counter, bool):
        raw_counter = None
    try:
        configured_number = int(raw_counter)
    except (TypeError, ValueError):
        configured_number = 0
    return max(1, highest_number + 1, configured_number)


def create_next_test_set():
    with _TEST_SET_LOCK:
        config = load_config()
        test_sets = normalize_test_sets(config)
        next_number = _next_test_set_number(config, test_sets)
        used_ids = {item["id"] for item in test_sets}
        used_names = {item["name"].casefold() for item in test_sets}
        while (
            f"test-set-{next_number}" in used_ids
            or f"测试集{next_number}".casefold() in used_names
        ):
            next_number += 1
        order_id = max((item["order_id"] for item in test_sets), default=0) + 1
        test_set = {
            "id": f"test-set-{next_number}",
            "name": f"测试集{next_number}",
            "order_id": order_id,
            "submission_enabled": False,
        }
        config["test_sets"] = [*test_sets, test_set]
        config["next_test_set_number"] = next_number + 1
        write_json_object(settings.CONFIG_FILE, config)
        return {**test_set, "case_numbers": []}


def update_test_set_flags(test_set_id, payload):
    if not isinstance(payload, dict):
        raise ValueError("test set flags payload must be an object")
    if "submission_enabled" not in payload:
        raise ValueError("submission_enabled is required")
    test_set_id = validate_case_set_id(test_set_id, "test set id")
    with _TEST_SET_LOCK:
        config = load_config()
        test_sets = normalize_test_sets(config)
        updated = None
        for item in test_sets:
            if item["id"] != test_set_id:
                continue
            item["submission_enabled"] = normalize_case_flag(
                payload.get("submission_enabled"),
                "submission_enabled",
                True,
            )
            updated = item
            break
        if not updated:
            raise LookupError("test set not found")
        config["test_sets"] = test_sets
        write_json_object(settings.CONFIG_FILE, config)
        return {"test_set": test_set_by_id(test_set_id), "test_sets": public_test_sets()}


def update_test_set(test_set_id, payload):
    if not isinstance(payload, dict):
        raise ValueError("test set payload must be an object")
    if "name" not in payload:
        raise ValueError("name is required")
    test_set_id = validate_case_set_id(test_set_id, "test set id")
    name = validate_test_set_name(payload.get("name"))
    with _TEST_SET_LOCK:
        config = load_config()
        test_sets = normalize_test_sets(config)
        if any(item["id"] != test_set_id and item["name"].casefold() == name.casefold() for item in test_sets):
            raise ValueError("test set name already exists")
        updated = None
        for item in test_sets:
            if item["id"] == test_set_id:
                item["name"] = name
                updated = item
                break
        if not updated:
            raise LookupError("test set not found")
        config["test_sets"] = test_sets
        write_json_object(settings.CONFIG_FILE, config)
        return {"test_set": test_set_by_id(test_set_id), "test_sets": public_test_sets()}


def delete_test_set(test_set_id):
    test_set_id = validate_case_set_id(test_set_id, "test set id")
    with _TEST_SET_LOCK:
        config = load_config()
        test_sets = normalize_test_sets(config)
        deleted = next((item for item in test_sets if item["id"] == test_set_id), None)
        if not deleted:
            raise LookupError("test set not found")

        members = test_set_members(test_set_id)
        originals = {}
        updated_paths = []
        for case in members:
            path = case_editor_paths(case["id"])["case_json"]
            originals[path] = read_json_object(path)

        next_config = dict(config)
        next_config["test_sets"] = [item for item in test_sets if item["id"] != test_set_id]
        next_config["next_test_set_number"] = _next_test_set_number(config, test_sets)
        try:
            for path, original in originals.items():
                updated_case = dict(original)
                updated_case["case_set_id"] = UNGROUPED_CASE_SET_ID
                write_json_object(path, updated_case)
                updated_paths.append(path)
            write_json_object(settings.CONFIG_FILE, next_config)
        except Exception:
            for path in updated_paths:
                write_json_object(path, originals[path])
            raise

        case_numbers = [case["order_id"] for case in members]
        return {
            "ok": True,
            "deleted": {
                "id": deleted["id"],
                "name": deleted["name"],
                "case_numbers": case_numbers,
                "moved_case_count": len(members),
            },
            "test_sets": public_test_sets(),
        }


def validated_file_text(value, name, max_chars=1_000_000):
    text = str(value or "").replace("\r\n", "\n")
    if len(text) > max_chars:
        raise ValueError(f"{name} is too long, max {max_chars} chars")
    return text


def validated_order_id(value, name="order_id"):
    try:
        number = int(value)
    except Exception as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if number <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return number


def case_editor_paths(case_id):
    case_id = validate_case_id(case_id)
    case_dir = (settings.FAULTS_DIR / case_id).resolve()
    try:
        case_dir.relative_to(settings.FAULTS_DIR.resolve())
    except ValueError as exc:
        raise ValueError(f"case directory must stay inside {settings.FAULTS_DIR}") from exc
    return {
        "dir": case_dir,
        "case_json": case_dir / "case.json",
        "inject_script": case_dir / "inject.sh",
        "recover_script": case_dir / "recover.sh",
        "ideal_answer_json": case_dir / "ideal-answer.json",
        "rubrics_json": case_dir / "rubrics.json",
    }


def existing_case_order_map(exclude_case_id=None):
    orders = {}
    if not settings.FAULTS_DIR.exists():
        return orders
    for path in sorted(settings.FAULTS_DIR.glob("*/case.json")):
        case = read_json_object(path)
        case_id = str(case.get("id", "")).strip()
        if not case_id or case_id == exclude_case_id:
            continue
        order_id = case.get("order_id")
        if isinstance(order_id, bool):
            continue
        try:
            orders[case_id] = validated_order_id(order_id)
        except Exception:
            continue
    return orders


def next_case_order_id(exclude_case_id=None):
    order_map = existing_case_order_map(exclude_case_id=exclude_case_id)
    return max(order_map.values(), default=0) + 1


def renumber_case_orders():
    cases = load_cases_list()
    changed = []
    for index, case in enumerate(cases, start=1):
        if case.get("order_id") == index:
            continue
        path = case_editor_paths(case["id"])["case_json"]
        raw_case = read_json_object(path)
        raw_case["order_id"] = index
        write_json_object(path, raw_case)
        changed.append({"id": case["id"], "from": case.get("order_id"), "to": index})
    return changed


def normalize_case_json(case, expected_case_id=None, fallback_order_id=None, fallback_case_set_id=TRAINING_CASE_SET_ID):
    if not isinstance(case, dict):
        raise ValueError("case.json must contain a JSON object")
    case_id = validate_case_id(case.get("id", ""), "case id")
    if expected_case_id and case_id != expected_case_id:
        raise ValueError(f"case id must stay {expected_case_id}")
    title = str(case.get("title") or case_id).strip()
    if not title:
        raise ValueError("case title is required")
    order_id = case.get("order_id", fallback_order_id)
    if isinstance(order_id, bool):
        raise ValueError("order_id must be a positive integer")
    if order_id in (None, ""):
        order_id = next_case_order_id(exclude_case_id=case_id)
    order_id = validated_order_id(order_id)
    other_orders = existing_case_order_map(exclude_case_id=case_id)
    if order_id in other_orders.values():
        raise ValueError(f"order_id {order_id} is already used by another case")

    normalized = dict(case)
    normalized["id"] = case_id
    normalized["title"] = title
    normalized["name"] = title
    normalized["order_id"] = order_id
    normalized["case_set_id"] = validate_case_set_id(normalized.get("case_set_id") or fallback_case_set_id)
    normalized["inject_script"] = f"./faults/{case_id}/inject.sh"
    normalized["recover_script"] = f"./faults/{case_id}/recover.sh"
    if "fault_phenomenon" in normalized:
        normalized["fault_phenomenon"] = validated_text(normalized.get("fault_phenomenon"), "fault_phenomenon", 100000)
    if "public_case_info" in normalized:
        normalized["public_case_info"] = validated_text(normalized.get("public_case_info"), "public_case_info", 100000)
    normalized["submission_enabled"] = normalize_case_flag(
        normalized.get("submission_enabled"),
        "submission_enabled",
        False,
    )
    normalized["ai_analysis_visible"] = normalize_case_flag(
        normalized.get("ai_analysis_visible"),
        "ai_analysis_visible",
        True,
    )
    if "mcp_servers" in normalized:
        normalized["mcp_servers"] = normalize_selected_public_mcp_servers(
            normalized.get("mcp_servers"),
            default_to_all=False,
        )
    return normalized


def load_case_file(path, fallback_order_id=None):
    case = read_json_object(path)
    case_id = str(case.get("id", "")).strip()
    if not case_id or case_id != path.parent.name:
        raise ValueError(f"case id must match directory name: {path}")
    case = normalize_case_json(case, expected_case_id=case_id, fallback_order_id=fallback_order_id)
    ideal_answer = read_json_object(resolve_case_ideal_answer(path.parent))
    case["_ideal_answer"] = validate_ideal_answer(path.parent, ideal_answer)
    rubrics = read_json_object(resolve_case_rubrics(path.parent))
    case["_rubrics"] = validate_rubrics(path.parent, rubrics)
    return case


def load_case_json_only(path, fallback_order_id=None):
    case = read_json_object(path)
    case_id = str(case.get("id", "")).strip()
    if not case_id or case_id != path.parent.name:
        raise ValueError(f"case id must match directory name: {path}")
    return normalize_case_json(case, expected_case_id=case_id, fallback_order_id=fallback_order_id)


def case_json_paths():
    if not settings.FAULTS_DIR.exists():
        return []
    return sorted(settings.FAULTS_DIR.glob("*/case.json"))


def case_paths_signature(paths):
    signature = []
    for path in paths:
        stat = path.stat()
        signature.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(signature)


def copy_case_list(items):
    return [dict(item) for item in items]


def load_cases_list():
    paths = case_json_paths()
    if not paths:
        return []
    cases = [load_case_file(path, fallback_order_id=index) for index, path in enumerate(paths, start=1)]
    return sorted(cases, key=lambda item: (item.get("order_id", 10**9), item.get("id", "")))


def load_cases_map():
    return {case["id"]: case for case in load_cases_list()}


def load_public_cases_list(include_test_cases=False, include_details=False):
    paths = case_json_paths()
    cache_key = (bool(include_test_cases), bool(include_details))
    if not paths:
        _PUBLIC_CASES_CACHE[cache_key] = {"signature": (), "cases": []}
        return []
    signature = case_paths_signature(paths)
    cached = _PUBLIC_CASES_CACHE.get(cache_key)
    if cached and cached.get("signature") == signature:
        return copy_case_list(cached.get("cases", []))
    cases = [
        public_case(load_case_json_only(path, fallback_order_id=index), include_details=include_details)
        for index, path in enumerate(paths, start=1)
    ]
    if not include_test_cases:
        cases = [case for case in cases if is_training_case(case)]
    cases = sorted(cases, key=lambda item: (item.get("order_id", 10**9), item.get("id", "")))
    _PUBLIC_CASES_CACHE[cache_key] = {"signature": signature, "cases": copy_case_list(cases)}
    return copy_case_list(cases)


def load_public_cases_map(include_test_cases=False, include_details=True):
    return {
        case["id"]: case
        for case in load_public_cases_list(
            include_test_cases=include_test_cases,
            include_details=include_details,
        )
    }


def public_case(case, include_details=True):
    if not case:
        return None
    fields = PUBLIC_CASE_FIELDS if include_details else PUBLIC_CASE_SUMMARY_FIELDS
    return {key: case.get(key) for key in fields if key in case}


def admin_case_files(case_id):
    paths = case_editor_paths(case_id)
    case = load_case_file(paths["case_json"])
    return {
        "case": public_case(case),
        "files": {
            key: paths[key].read_text(encoding="utf-8")
            for key in ("case_json", "inject_script", "recover_script", "ideal_answer_json", "rubrics_json")
        },
        "defaults": {
            "next_order_id": next_case_order_id(exclude_case_id=case_id),
        },
    }


def load_config():
    if not settings.CONFIG_FILE.exists():
        return {}
    return json.loads(settings.CONFIG_FILE.read_text(encoding="utf-8"))


def load_output_format_markdown():
    if not settings.OUTPUT_FORMAT_FILE.exists():
        return ""
    return settings.OUTPUT_FORMAT_FILE.read_text(encoding="utf-8")


def public_config():
    config = load_config()
    return {
        "title": config.get("title", "AIOps OJ Platform"),
        "subtitle": config.get("subtitle", ""),
        "overview": config.get("overview", ""),
        "announcement": config.get("announcement", ""),
        "test_flow": config.get("test_flow", []),
        "test_sets": public_test_sets(),
        "output_format_markdown": load_output_format_markdown(),
        "tool_call_policy": config.get("tool_call_policy", {}),
        "max_skills": settings.MAX_SKILLS,
        "max_skill_chars": settings.MAX_SKILL_CHARS,
        "max_soul_chars": settings.MAX_SOUL_CHARS,
        "max_skill_archive_bytes": settings.MAX_SKILL_ARCHIVE_BYTES,
        "max_case_archive_bytes": settings.MAX_CASE_ARCHIVE_BYTES,
        "available_mcp_servers": public_case_mcp_server_options(),
    }


def admin_public_content():
    return {
        "config": public_config(),
        "cases": load_public_cases_list(include_test_cases=True, include_details=True),
    }


def validated_text(value, name, max_chars=100000):
    text = str(value or "").strip()
    if len(text) > max_chars:
        raise ValueError(f"{name} is too long, max {max_chars} chars")
    return text


def update_public_content(payload):
    if not isinstance(payload, dict):
        raise ValueError("content must be an object")

    config = load_config()
    output_format_markdown = None
    if "announcement" in payload:
        config["announcement"] = validated_text(payload["announcement"], "announcement", 20000)

    if "test_flow" in payload:
        if not isinstance(payload["test_flow"], list):
            raise ValueError("test_flow must be a list")
        steps = [validated_text(item, "test_flow item", 5000) for item in payload["test_flow"]]
        steps = [item for item in steps if item]
        if len(steps) > 30:
            raise ValueError("test_flow can contain at most 30 items")
        config["test_flow"] = steps

    if "tool_call_policy" in payload:
        policy = payload["tool_call_policy"]
        if not isinstance(policy, dict):
            raise ValueError("tool_call_policy must be an object")
        config["tool_call_policy"] = {
            key: validated_text(policy.get(key), f"tool_call_policy.{key}", 20000)
            for key in ("definition", "expectation", "scoring")
        }

    if "output_format_markdown" in payload:
        output_format_markdown = validated_file_text(payload.get("output_format_markdown"), "output.md")

    case_updates = payload.get("case_public_info", {})
    if not isinstance(case_updates, dict):
        raise ValueError("case_public_info must be an object")
    known_cases = {case["id"] for case in load_public_cases_list(include_test_cases=True)}
    pending_case_files = {}
    for case_id, value in case_updates.items():
        if case_id not in known_cases:
            raise ValueError(f"unknown case: {case_id}")
        path = settings.FAULTS_DIR / case_id / "case.json"
        case_data = read_json_object(path)
        case_data["public_case_info"] = validated_text(value, f"case_public_info.{case_id}", 100000)
        pending_case_files[path] = case_data

    with _TEST_SET_LOCK:
        latest_config = load_config()
        for key in ("announcement", "test_flow", "tool_call_policy"):
            if key in payload:
                latest_config[key] = config[key]
        write_json_object(settings.CONFIG_FILE, latest_config)
    if output_format_markdown is not None:
        write_text_file(settings.OUTPUT_FORMAT_FILE, output_format_markdown.rstrip("\n") + "\n")
    for path, case_data in pending_case_files.items():
        write_json_object(path, case_data)
    return admin_public_content()


def parse_editor_json(text, name):
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} JSON parse failed: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return value


def write_case_bundle(case_id, case_json, inject_script, recover_script, ideal_answer, rubrics):
    paths = case_editor_paths(case_id)
    paths["dir"].mkdir(parents=True, exist_ok=True)
    write_json_object(paths["case_json"], case_json)
    write_text_file(paths["inject_script"], inject_script.rstrip("\n") + "\n")
    write_text_file(paths["recover_script"], recover_script.rstrip("\n") + "\n")
    write_json_object(paths["ideal_answer_json"], ideal_answer)
    write_json_object(paths["rubrics_json"], rubrics)


def update_case_files(case_id, payload):
    if not isinstance(payload, dict):
        raise ValueError("case editor payload must be an object")
    paths = case_editor_paths(case_id)
    current_case = read_json_object(paths["case_json"])
    raw_case_json = validated_file_text(payload.get("case_json"), "case.json")
    raw_inject_script = validated_file_text(payload.get("inject_script"), "inject.sh")
    raw_recover_script = validated_file_text(payload.get("recover_script"), "recover.sh")
    raw_ideal_answer = validated_file_text(payload.get("ideal_answer_json"), "ideal-answer.json")
    raw_rubrics = validated_file_text(payload.get("rubrics_json"), "rubrics.json")

    case_json = normalize_case_json(
        parse_editor_json(raw_case_json, "case.json"),
        expected_case_id=case_id,
        fallback_order_id=current_case.get("order_id"),
        fallback_case_set_id=current_case.get("case_set_id") or TRAINING_CASE_SET_ID,
    )
    ideal_answer = validate_ideal_answer(paths["dir"], parse_editor_json(raw_ideal_answer, "ideal-answer.json"))
    rubrics = validate_rubrics(paths["dir"], parse_editor_json(raw_rubrics, "rubrics.json"))
    with _TEST_SET_LOCK:
        case_json["case_set_id"] = validate_configured_case_set_id(case_json.get("case_set_id"))
        write_case_bundle(case_id, case_json, raw_inject_script, raw_recover_script, ideal_answer, rubrics)
        renumber_case_orders()
    return admin_case_files(case_id)


def update_case_flags(case_id, payload):
    if not isinstance(payload, dict):
        raise ValueError("case flags payload must be an object")
    with _TEST_SET_LOCK:
        paths = case_editor_paths(case_id)
        case_json = read_json_object(paths["case_json"])
        if "submission_enabled" in payload:
            case_json["submission_enabled"] = normalize_case_flag(
                payload.get("submission_enabled"),
                "submission_enabled",
                True,
            )
        if "ai_analysis_visible" in payload:
            case_json["ai_analysis_visible"] = normalize_case_flag(
                payload.get("ai_analysis_visible"),
                "ai_analysis_visible",
                True,
            )
        if "case_set_id" in payload:
            case_json["case_set_id"] = validate_configured_case_set_id(
                payload.get("case_set_id") or TRAINING_CASE_SET_ID
            )
        case_json = normalize_case_json(
            case_json,
            expected_case_id=case_id,
            fallback_order_id=case_json.get("order_id"),
            fallback_case_set_id=case_json.get("case_set_id") or TRAINING_CASE_SET_ID,
        )
        write_json_object(paths["case_json"], case_json)
        return {"case": public_case(load_case_file(paths["case_json"]), include_details=True)}


def create_case_files(payload):
    if not isinstance(payload, dict):
        raise ValueError("case editor payload must be an object")
    raw_case_json = validated_file_text(payload.get("case_json"), "case.json")
    raw_inject_script = validated_file_text(payload.get("inject_script"), "inject.sh")
    raw_recover_script = validated_file_text(payload.get("recover_script"), "recover.sh")
    raw_ideal_answer = validated_file_text(payload.get("ideal_answer_json"), "ideal-answer.json")
    raw_rubrics = validated_file_text(payload.get("rubrics_json"), "rubrics.json")

    draft_case = parse_editor_json(raw_case_json, "case.json")
    case_id = validate_case_id(draft_case.get("id", ""), "case id")
    paths = case_editor_paths(case_id)
    if paths["dir"].exists():
        raise ValueError(f"case already exists: {case_id}")

    case_json = normalize_case_json(
        draft_case,
        expected_case_id=case_id,
        fallback_order_id=draft_case.get("order_id") or next_case_order_id(),
        fallback_case_set_id=UNGROUPED_CASE_SET_ID,
    )
    ideal_answer = validate_ideal_answer(paths["dir"], parse_editor_json(raw_ideal_answer, "ideal-answer.json"))
    rubrics = validate_rubrics(paths["dir"], parse_editor_json(raw_rubrics, "rubrics.json"))
    with _TEST_SET_LOCK:
        case_json["case_set_id"] = validate_configured_case_set_id(case_json.get("case_set_id"))
        write_case_bundle(case_id, case_json, raw_inject_script, raw_recover_script, ideal_answer, rubrics)
        renumber_case_orders()
    return admin_case_files(case_id)


def create_case_files_from_archive(filename, archive_bytes):
    return create_case_files(extract_case_archive_payload(filename, archive_bytes))


def delete_case_files(case_id):
    paths = case_editor_paths(case_id)
    if not paths["case_json"].exists():
        raise LookupError("case not found")
    case = load_case_file(paths["case_json"])
    with db.connect() as conn:
        counts = conn.execute(
            """
            SELECT
                COUNT(*) AS total_submissions,
                SUM(CASE WHEN status IN ('done', 'failed') THEN 1 ELSE 0 END) AS historical_submissions,
                SUM(CASE WHEN status NOT IN ('done', 'failed') THEN 1 ELSE 0 END) AS blocking_submissions
            FROM submissions
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()
    total_submissions = int(counts["total_submissions"] or 0)
    historical_submissions = int(counts["historical_submissions"] or 0)
    blocking_submissions = int(counts["blocking_submissions"] or 0)
    if blocking_submissions:
        raise ValueError(
            "cannot delete case while it still has queued or active submissions; "
            "delete those submissions first"
        )
    delete_case_directory(paths["dir"])
    if paths["dir"].exists():
        raise RuntimeError("failed to delete case directory")
    renumber_case_orders()
    return {
        "id": case["id"],
        "title": case.get("title") or case["id"],
        "order_id": case.get("order_id"),
        "total_submissions": total_submissions,
        "historical_submissions": historical_submissions,
    }


def resolve_case_script(case, key):
    script = str(case.get(key, "")).strip()
    if not script:
        return None
    target = (settings.ROOT / script).resolve() if not os.path.isabs(script) else Path(script).resolve()
    try:
        target.relative_to(settings.ROOT)
    except ValueError:
        raise ValueError(f"{key} must stay inside {settings.ROOT}")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"missing {key}: {target}")
    return target

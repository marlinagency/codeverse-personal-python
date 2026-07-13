"""HTTP-level tests for the FastAPI surface (auth, themes, projects, compile,
execute routers).

The core engine (lexer/parser/codegen/taxonomy) is unit-tested elsewhere; this
suite exercises the wiring that turns those pieces into a working API: auth
scoping, request validation, cross-user isolation, and the compile/execute
round trip. It runs fully offline — the default LLM provider is the
deterministic ``FakeProvider`` and, with no Docker daemon, ``/execute`` falls
back to the local Python demo runner, so real code still runs and prints.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from codeverse_api.db import models  # noqa: F401 - registers tables on Base.metadata
from codeverse_api.db.base import Base, get_db
from codeverse_api.dependencies import get_llm_provider
from codeverse_api.main import create_app
from codeverse_api.security.auth import create_access_token
from codeverse_api.config import Settings, get_settings
from codeverse_core.personal_python import code_task_reference_solution
from codeverse_core.theme_mapping.generator import TaxonomyThemeDictionary
from codeverse_core.theme_mapping.llm_provider import LLMProviderError
from codeverse_core.theme_mapping.providers.fake import FakeProvider


@pytest.fixture
def client() -> TestClient:
    """A TestClient backed by a fresh, shared in-memory SQLite database.

    StaticPool + a single connection keeps the in-memory schema alive across
    the request threads TestClient uses.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    # Force the deterministic fake provider so the suite never touches a real
    # LLM API even when .env selects fireworks/openai/anthropic.
    app.dependency_overrides[get_llm_provider] = lambda: FakeProvider()
    with TestClient(app) as test_client:
        test_client._session_factory = TestSession  # type: ignore[attr-defined]
        yield test_client
    app.dependency_overrides.clear()


def _auth(client: TestClient) -> dict[str, str]:
    resp = client.post("/auth/token")
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _make_theme(client: TestClient, headers: dict[str, str], theme: str = "I love Counter-Strike 2") -> dict:
    resp = client.post(
        "/themes/generate",
        json={"theme": theme, "output_language": "en"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --------------------------------------------------------------- auth


def test_dev_token_returns_token_and_user(client: TestClient):
    resp = client.post("/auth/token")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "dev@codeverse.io"


def test_dev_token_is_idempotent_for_same_user(client: TestClient):
    first = client.post("/auth/token").json()["user"]["id"]
    second = client.post("/auth/token").json()["user"]["id"]
    assert first == second


def test_public_demo_mode_gives_each_visitor_an_isolated_account():
    """With CODEVERSE_PUBLIC_DEMO on, /auth/token mints a fresh anonymous
    user per visitor (no cookie) and reuses the account when the visitor
    cookie comes back — strangers never share a workspace."""
    from codeverse_api.config import Settings

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_settings] = lambda: Settings(public_demo=True)
    app.dependency_overrides[get_llm_provider] = lambda: FakeProvider()

    with TestClient(app) as visitor_a, TestClient(app) as visitor_b:
        first = visitor_a.post("/auth/token").json()["user"]
        again = visitor_a.post("/auth/token").json()["user"]  # cookie preserved
        other = visitor_b.post("/auth/token").json()["user"]

    assert first["id"] == again["id"]  # same visitor keeps their account
    assert first["id"] != other["id"]  # different visitor is isolated
    assert first["email"].startswith("visitor-")
    app.dependency_overrides.clear()


def test_protected_route_requires_token(client: TestClient):
    resp = client.get("/themes")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "missing Authorization header"


def test_protected_route_rejects_garbage_token(client: TestClient):
    resp = client.get("/themes", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid or expired token"


# --------------------------------------------------------------- themes


def test_generate_theme_creates_dictionary(client: TestClient):
    headers = _auth(client)
    body = _make_theme(client, headers)
    assert body["theme_name"] == "Counter-Strike 2"
    assert body["mappings"]["py_kw_if"]
    assert body["mappings"]["py_kw_for"]
    assert body["llm_provider"] == "fake"


def test_amd_chip_falls_back_to_primary_provider_without_false_provenance(
    client: TestClient,
    monkeypatch,
):
    class _UnavailableAmdProvider:
        provider_name = "openai_compatible"
        model = "codeverse-student"

        def chat(self, *_args, **_kwargs):
            raise LLMProviderError("AMD tunnel unavailable")

    client.app.dependency_overrides[get_settings] = lambda: Settings(amd_enabled=True)
    monkeypatch.setattr(
        "codeverse_api.routers.themes.build_amd_provider",
        lambda _settings: _UnavailableAmdProvider(),
    )
    headers = _auth(client)

    response = client.post(
        "/themes/generate",
        json={"theme": "chess", "output_language": "en", "use_amd": True},
        headers=headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["llm_provider"] == "fake"
    assert body["llm_model"] != "codeverse-student"


def test_generate_theme_rejects_empty_theme(client: TestClient):
    headers = _auth(client)
    resp = client.post("/themes/generate", json={"theme": ""}, headers=headers)
    assert resp.status_code == 422  # pydantic min_length=1


def test_list_and_get_theme_roundtrip(client: TestClient):
    headers = _auth(client)
    created = _make_theme(client, headers)

    listing = client.get("/themes", headers=headers)
    assert listing.status_code == 200
    assert any(t["id"] == created["id"] for t in listing.json())

    single = client.get(f"/themes/{created['id']}", headers=headers)
    assert single.status_code == 200
    assert single.json()["id"] == created["id"]


def test_theme_dictionary_catalog_enriches_every_python_mapping(client: TestClient):
    headers = _auth(client)
    created = _make_theme(client, headers)

    response = client.get(f"/themes/{created['id']}/dictionary", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    expected_count = sum(1 for key in created["mappings"] if key.startswith("py_"))
    assert body["total"] == expected_count
    assert len(body["entries"]) == expected_count
    assert not any(entry["concept_id"].startswith("sql_") for entry in body["entries"])
    assert 0 <= body["quality"]["overall_score"] <= 100
    assert body["quality"]["grade"] in {"A", "B", "C", "D", "F"}
    assert body["quality"]["max_token_parts"] <= 2

    upper = next(entry for entry in body["entries"] if entry["concept_id"] == "py_str_upper")
    assert upper["personal_token"] == created["mappings"]["py_str_upper"]
    assert upper["category"] == "string_methods"
    assert upper["tier"] == "method"
    assert upper["python_name"]
    assert upper["real_syntax"]


def test_regenerate_theme_creates_new_active_brain_v2_version(client: TestClient):
    headers = _auth(client)
    previous = _make_theme(client, headers, "I want SWAT in America")

    response = client.post(
        f"/themes/{previous['id']}/regenerate",
        json={"theme": "American SWAT dispatch, patrol teams, secure entry and unit rosters"},
        headers=headers,
    )

    assert response.status_code == 201, response.text
    current = response.json()
    assert current["id"] != previous["id"]
    assert current["theme_name"] == previous["theme_name"]
    assert current["version"] == previous["version"] + 1
    assert all(len(token.split("_")) <= 2 for token in current["mappings"].values())

    listing = client.get("/themes", headers=headers).json()
    assert any(theme["id"] == current["id"] for theme in listing)
    assert not any(theme["id"] == previous["id"] for theme in listing)


def test_get_missing_theme_returns_404(client: TestClient):
    headers = _auth(client)
    resp = client.get(f"/themes/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "theme dictionary not found"


def test_get_clarifying_questions_returns_wellformed_list(client: TestClient):
    headers = _auth(client)
    resp = client.post(
        "/themes/questions",
        json={"theme": "I love beekeeping"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    questions = resp.json()["questions"]
    assert 5 <= len(questions) <= 8
    first = questions[0]
    assert first["question"]
    assert len(first["options"]) >= 2
    assert first["options"][0]["label"]
    assert first["options"][0]["icon"]


def test_generate_theme_with_clarifying_answers_still_succeeds(client: TestClient):
    headers = _auth(client)
    resp = client.post(
        "/themes/generate",
        json={
            "theme": "I love Counter-Strike 2",
            "output_language": "en",
            "clarifying_answers": {"Which role do you main?": "Duelist"},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["mappings"]["py_kw_if"]


def test_personal_python_lesson_compiles(client: TestClient):
    headers = _auth(client)
    created = _make_theme(client, headers)
    resp = client.get(f"/themes/{created['id']}/lesson", headers=headers)
    assert resp.status_code == 200
    lesson = resp.json()
    assert lesson["target_language"] == "python"
    assert lesson["source_content"]
    assert lesson["generated_code"]


def test_learning_diagnose_path_lesson_practice_and_proof(client: TestClient):
    headers = _auth(client)
    created = _make_theme(client, headers, "I love Counter-Strike 2 and loops/functions confuse me")

    diagnose = client.post(
        "/learning/diagnose",
        json={"prompt": "Ben CS2 seviyorum, if/for/function kafamı karıştırıyor."},
        headers=headers,
    )
    assert diagnose.status_code == 200, diagnose.text
    diagnosis = diagnose.json()
    assert "games" in diagnosis["interests"]
    assert "loops" in diagnosis["pain_points"]

    path = client.get(f"/learning/{created['id']}/path", headers=headers)
    assert path.status_code == 200, path.text
    path_body = path.json()
    assert path_body["title"].startswith("Personal Python Path")
    assert len(path_body["modules"]) >= 6
    assert [module["scaffold_stage"] for module in path_body["modules"][:4]] == ["personal"] * 4
    assert [module["scaffold_stage"] for module in path_body["modules"][4:8]] == ["bridge"] * 4
    assert all(module["practice_syntax"] == "python" for module in path_body["modules"][8:])
    assert path_body["modules"][0]["module_id"] == "signals-and-values"
    assert len(path_body["modules"][0]["lesson_sections"]) == 4
    assert len(path_body["modules"][0]["practice_tasks"]) == 6
    strings_module = next(module for module in path_body["modules"] if module["module_id"] == "strings-and-text")
    assert len(strings_module["lesson_sections"]) == 5
    assert len(strings_module["practice_tasks"]) == 6
    numbers_module = next(module for module in path_body["modules"] if module["module_id"] == "numbers-and-conversion")
    assert len(numbers_module["lesson_sections"]) == 5
    assert len(numbers_module["practice_tasks"]) == 6
    imports_module = next(module for module in path_body["modules"] if module["module_id"] == "imports-and-library")
    assert len(imports_module["lesson_sections"]) == 4
    assert len(imports_module["practice_tasks"]) == 6
    choices_module = next(module for module in path_body["modules"] if module["module_id"] == "choices")
    assert len(choices_module["lesson_sections"]) == 5
    assert len(choices_module["practice_tasks"]) == 6
    routes_module = next(module for module in path_body["modules"] if module["module_id"] == "routes")
    assert len(routes_module["lesson_sections"]) == 5
    assert len(routes_module["practice_tasks"]) == 6
    loop_control_module = next(module for module in path_body["modules"] if module["module_id"] == "loop-control")
    assert len(loop_control_module["lesson_sections"]) == 5
    assert len(loop_control_module["practice_tasks"]) == 6
    tools_module = next(module for module in path_body["modules"] if module["module_id"] == "tools")
    assert len(tools_module["lesson_sections"]) == 5
    assert len(tools_module["practice_tasks"]) == 6

    lesson = client.get(f"/learning/{created['id']}/lessons/routes", headers=headers)
    assert lesson.status_code == 200, lesson.text
    lesson_body = lesson.json()
    assert lesson_body["generated_code"]
    assert lesson_body["stdout"] == "1\n2\n3\n"
    assert lesson_body["compile_error"] is None
    assert lesson_body["why_it_matters"]
    assert lesson_body["real_python_preview"]
    assert lesson_body["expected_stdout"] == "1\n2\n3\n"
    assert lesson_body["lesson_steps"]
    assert lesson_body["misconception_checks"]
    assert len(lesson_body["practice_tasks"]) >= 2

    check = client.post(
        f"/learning/{created['id']}/practice/check",
        json={"task_id": "routes-count", "answer": "3"},
        headers=headers,
    )
    assert check.status_code == 200, check.text
    assert check.json()["correct"] is True

    grade = client.post(
        f"/learning/{created['id']}/practice/grade",
        json={"answers": {"routes-count": "3", "routes-translate": "for"}},
        headers=headers,
    )
    assert grade.status_code == 200, grade.text
    assert grade.json()["overall_score"] == 100
    assert grade.json()["passed"] is True

    proof = client.get(f"/learning/{created['id']}/proof", headers=headers)
    assert proof.status_code == 200, proof.text
    assert proof.json()["total_modules"] >= 9
    assert "routes" in proof.json()["concept_coverage"]


def test_python_forward_practice_runs_plain_python_and_rejects_personal_tokens(
    client: TestClient,
):
    headers = _auth(client)
    created = _make_theme(client, headers, "I want to learn standard Python gradually")
    path = client.get(f"/learning/{created['id']}/path", headers=headers).json()
    advanced = path["modules"][8]
    task = next(item for item in advanced["practice_tasks"] if item["kind"] == "write_code")
    assert task["syntax_mode"] == "python"
    assert not task["starter_source"].startswith("@theme:")

    dictionary = TaxonomyThemeDictionary(
        theme=created["theme_name"],
        mappings=created["mappings"],
        rationale=created.get("rationale") or {},
    )
    solution = code_task_reference_solution(dictionary, task["id"])
    assert solution
    passed = client.post(
        f"/learning/{created['id']}/practice/run",
        json={"task_id": task["id"], "source_content": solution},
        headers=headers,
    )
    assert passed.status_code == 200, passed.text
    assert passed.json()["correct"] is True

    personal_print = created["mappings"]["py_fn_print"]
    scaffolded = solution.replace("print", personal_print, 1)
    rejected = client.post(
        f"/learning/{created['id']}/practice/run",
        json={"task_id": task["id"], "source_content": scaffolded},
        headers=headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "used_personal_tokens"


def test_practice_tasks_do_not_leak_expected_answer(client: TestClient):
    """Pedagogy guard: the lesson payload must never contain the answer —
    students see it only via /practice/check AFTER an attempt."""
    headers = _auth(client)
    created = _make_theme(client, headers)

    lesson = client.get(f"/learning/{created['id']}/lessons/routes", headers=headers)
    assert lesson.status_code == 200
    tasks = lesson.json()["practice_tasks"]
    assert tasks
    for task in tasks:
        assert "expected_answer" not in task
        assert task["hint"]  # hint stays available for the hint toggle


def test_practice_run_code_task_starter_fails_then_solution_passes(client: TestClient):
    """The write_code loop end to end: the untouched starter runs but misses
    the goal; the fixed program passes. With no Docker in CI this exercises
    the local subprocess runner fallback."""
    headers = _auth(client)
    created = _make_theme(client, headers)

    lesson = client.get(f"/learning/{created['id']}/lessons/routes", headers=headers)
    assert lesson.status_code == 200
    code_task = next(
        task for task in lesson.json()["practice_tasks"] if task["kind"] == "write_code"
    )
    assert code_task["starter_source"]

    wrong = client.post(
        f"/learning/{created['id']}/practice/run",
        json={"task_id": code_task["id"], "source_content": code_task["starter_source"]},
        headers=headers,
    )
    assert wrong.status_code == 200, wrong.text
    wrong_body = wrong.json()
    assert wrong_body["correct"] is False
    assert wrong_body["status"] == "success"  # it runs, just misses the goal
    assert wrong_body["expected_stdout"] == "1\n2\n3\n4\n5\n"

    # the routes starter uses range(1, 3); widening it to (1, 6) is the fix
    fixed_source = code_task["starter_source"].replace("(1, 3)", "(1, 6)")
    right = client.post(
        f"/learning/{created['id']}/practice/run",
        json={"task_id": code_task["id"], "source_content": fixed_source},
        headers=headers,
    )
    assert right.status_code == 200, right.text
    assert right.json()["correct"] is True


def test_practice_run_reports_compile_error_as_feedback(client: TestClient):
    headers = _auth(client)
    created = _make_theme(client, headers)

    resp = client.post(
        f"/learning/{created['id']}/practice/run",
        json={"task_id": "routes-code", "source_content": "@theme: t\n@language: python\n---\n???bad???\n"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["correct"] is False
    assert body["status"] == "compile_error"
    assert body["feedback"]


def test_practice_check_wrong_answer_gives_teaching_feedback(client: TestClient):
    headers = _auth(client)
    created = _make_theme(client, headers)

    resp = client.post(
        f"/learning/{created['id']}/practice/check",
        json={"task_id": "routes-count", "answer": "99"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["correct"] is False
    assert body["feedback"]
    assert body["next_step"]
    # the answer is revealed only after an attempt, as part of feedback
    assert body["expected_answer"] == "3"


def test_bridge_capstone_full_graduation_flow(client: TestClient):
    """The capstone end to end: fetching the challenge never leaks the answer;
    pasting the personal syntax is rejected as 'used personal tokens'; correct
    real Python graduates and records progress."""
    headers = _auth(client)
    created = _make_theme(client, headers)

    challenge = client.get(f"/learning/{created['id']}/bridge", headers=headers)
    assert challenge.status_code == 200, challenge.text
    ch = challenge.json()
    assert ch["personal_reference"]
    assert ch["expected_stdout"] == "7\n"
    assert set(["def", "for", "in", "if", "return", "print"]) <= set(ch["real_keywords"])

    # pasting the personal-syntax reference is caught by the anti-cheat guard
    paste = client.post(
        f"/learning/{created['id']}/bridge/check",
        json={"source_content": ch["personal_reference"]},
        headers=headers,
    )
    assert paste.status_code == 200
    assert paste.json()["passed"] is False
    assert paste.json()["status"] == "used_personal_tokens"
    assert paste.json()["used_personal_tokens"]

    # a correct REAL-Python rewrite graduates
    real_python = (
        "def cv_bonus(cv_levels):\n"
        "    cv_total = 0\n"
        "    for cv_level in cv_levels:\n"
        "        if cv_level >= 3:\n"
        "            cv_total = cv_total + cv_level\n"
        "    return cv_total\n\n"
        "print(cv_bonus([1, 2, 3, 4]))\n"
    )
    grad = client.post(
        f"/learning/{created['id']}/bridge/check",
        json={"source_content": real_python},
        headers=headers,
    )
    assert grad.status_code == 200, grad.text
    assert grad.json()["passed"] is True
    assert grad.json()["status"] == "graduated"

    # graduation is persisted as a progress milestone
    progress = client.get(f"/learning/{created['id']}/progress", headers=headers).json()
    assert any(m["module_id"] == "graduation" and m["passed"] for m in progress["modules"])


def test_bridge_wrong_output_real_python_is_not_graduation(client: TestClient):
    headers = _auth(client)
    created = _make_theme(client, headers)
    # valid real Python, but wrong result
    resp = client.post(
        f"/learning/{created['id']}/bridge/check",
        json={"source_content": "print(999)\n"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["passed"] is False
    assert body["status"] == "wrong_output"


def test_learning_progress_persists_after_grading(client: TestClient):
    headers = _auth(client)
    created = _make_theme(client, headers)

    # nothing completed yet
    empty = client.get(f"/learning/{created['id']}/progress", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["completed_count"] == 0

    # ace the routes quiz
    grade = client.post(
        f"/learning/{created['id']}/practice/grade",
        json={"answers": {"routes-count": "3", "routes-translate": "for"}},
        headers=headers,
    )
    assert grade.status_code == 200
    assert grade.json()["overall_score"] == 100

    # a FRESH GET reflects the saved mastery (survives reload)
    progress = client.get(f"/learning/{created['id']}/progress", headers=headers)
    assert progress.status_code == 200
    body = progress.json()
    assert body["completed_count"] == 1
    routes = next(m for m in body["modules"] if m["module_id"] == "routes")
    assert routes["passed"] is True
    assert routes["best_score"] == 100


def test_solving_code_exercise_records_module_progress(client: TestClient):
    headers = _auth(client)
    created = _make_theme(client, headers)

    lesson = client.get(f"/learning/{created['id']}/lessons/routes", headers=headers)
    code_task = next(t for t in lesson.json()["practice_tasks"] if t["kind"] == "write_code")
    fixed_source = code_task["starter_source"].replace("(1, 3)", "(1, 6)")

    run = client.post(
        f"/learning/{created['id']}/practice/run",
        json={"task_id": code_task["id"], "source_content": fixed_source},
        headers=headers,
    )
    assert run.json()["correct"] is True

    progress = client.get(f"/learning/{created['id']}/progress", headers=headers).json()
    assert any(m["module_id"] == "routes" and m["passed"] for m in progress["modules"])


def test_progress_best_score_never_regresses(client: TestClient):
    headers = _auth(client)
    created = _make_theme(client, headers)

    # first ace it
    client.post(
        f"/learning/{created['id']}/practice/grade",
        json={"answers": {"routes-count": "3", "routes-translate": "for"}},
        headers=headers,
    )
    # then a weaker retry (one wrong)
    client.post(
        f"/learning/{created['id']}/practice/grade",
        json={"answers": {"routes-count": "999", "routes-translate": "for"}},
        headers=headers,
    )
    progress = client.get(f"/learning/{created['id']}/progress", headers=headers).json()
    routes = next(m for m in progress["modules"] if m["module_id"] == "routes")
    assert routes["best_score"] == 100  # kept the best, not the weaker 50
    assert routes["passed"] is True


def test_learning_assessment_records_locked_baseline_and_measurable_gain(
    client: TestClient,
):
    headers = _auth(client)
    created = _make_theme(client, headers)
    endpoint = f"/learning/{created['id']}/assessment"

    initial = client.get(endpoint, headers=headers)
    assert initial.status_code == 200, initial.text
    evidence = initial.json()
    assert evidence["readiness"] == "take_baseline"
    assert evidence["pre_score"] is None
    assert len(evidence["questions"]) == 8
    assert all("correct_answer" not in question for question in evidence["questions"])

    choices = {question["id"]: question["choices"][0] for question in evidence["questions"]}
    baseline = client.post(f"{endpoint}/pre", json={"answers": choices}, headers=headers)
    assert baseline.status_code == 200, baseline.text
    baseline_score = baseline.json()["score"]

    # A second baseline submission cannot rewrite the learner's starting point.
    alternate = {question["id"]: question["choices"][-1] for question in evidence["questions"]}
    locked = client.post(f"{endpoint}/pre", json={"answers": alternate}, headers=headers)
    assert locked.status_code == 200
    assert locked.json()["baseline_locked"] is True
    assert locked.json()["score"] == baseline_score

    # Use the public questions and known curriculum answers to prove post-test gain.
    correct = {
        "values-output": "7",
        "conditions-branch": "B",
        "loops-range": "1, 2, 3",
        "functions-return": "12",
        "collections-list": "3",
        "errors-finally": "finally",
        "files-context": "It automatically closes the file",
        "objects-instance": "The current object",
    }
    post = client.post(f"{endpoint}/post", json={"answers": correct}, headers=headers)
    assert post.status_code == 200, post.text
    assert post.json()["score"] == 100

    final = client.get(endpoint, headers=headers).json()
    assert final["readiness"] == "evidence_ready"
    assert final["pre_score"] == baseline_score
    assert final["post_score"] == 100
    assert final["gain"] == 100 - baseline_score
    assert set(final["concept_gain"]) == {
        "values", "conditions", "loops", "functions", "collections", "errors", "files", "objects"
    }

    # Assessment internals do not inflate completed lesson counts.
    progress = client.get(f"/learning/{created['id']}/progress", headers=headers).json()
    assert progress["completed_count"] == 0
    assert all(not row["module_id"].startswith("assessment-") for row in progress["modules"])


# --------------------------------------------------------- cross-user isolation


def _second_user_headers(client: TestClient) -> dict[str, str]:
    """Mint a token for a distinct user created directly in the test DB."""
    session = client._session_factory()  # type: ignore[attr-defined]
    other = models.User(email="other@codeverse.io", display_name="Other")
    session.add(other)
    session.commit()
    token = create_access_token(other.id, get_settings())
    session.close()
    return {"Authorization": f"Bearer {token}"}


def test_user_cannot_read_another_users_theme(client: TestClient):
    owner_headers = _auth(client)
    created = _make_theme(client, owner_headers)

    other_headers = _second_user_headers(client)
    resp = client.get(f"/themes/{created['id']}", headers=other_headers)
    assert resp.status_code == 404


# --------------------------------------------------------------- projects


def test_project_crud_and_files(client: TestClient):
    headers = _auth(client)
    theme = _make_theme(client, headers)

    create = client.post(
        "/projects",
        json={
            "name": "My First Project",
            "theme_dictionary_id": theme["id"],
            "target_language": "python",
        },
        headers=headers,
    )
    assert create.status_code == 201, create.text
    project = create.json()

    listing = client.get("/projects", headers=headers)
    assert any(p["id"] == project["id"] for p in listing.json())

    upsert = client.put(
        f"/projects/{project['id']}/files",
        json={"filename": "main.cvl", "source_content": "@theme: x\n@language: python\n---\n"},
        headers=headers,
    )
    assert upsert.status_code == 200
    assert upsert.json()["filename"] == "main.cvl"

    files = client.get(f"/projects/{project['id']}/files", headers=headers)
    assert files.status_code == 200
    assert len(files.json()) == 1


def test_create_project_with_missing_theme_returns_404(client: TestClient):
    headers = _auth(client)
    resp = client.post(
        "/projects",
        json={
            "name": "Broken",
            "theme_dictionary_id": str(uuid.uuid4()),
            "target_language": "python",
        },
        headers=headers,
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "theme dictionary not found"


# --------------------------------------------------------- compile & execute


def _core_snippet(mappings: dict[str, str]) -> str:
    """A tiny valid Personal Python program built from a theme's own tokens."""
    m = mappings
    return (
        "@theme: t\n@language: python\n@version: 1\n---\n"
        f"{m['py_kw_def']} run():\n"
        f"    {m['py_fn_print']}(42)\n"
        f"run()\n"
    )


def test_compile_ad_hoc_source_succeeds(client: TestClient):
    headers = _auth(client)
    theme = _make_theme(client, headers)
    source = _core_snippet(theme["mappings"])

    resp = client.post(
        "/compile",
        json={"source_content": source, "theme_dictionary_id": theme["id"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["target_language"] == "python"
    assert "def run():" in body["generated_code"]
    assert "print(42)" in body["generated_code"]
    assert len(body["translation_trace"]) == 2
    assert body["translation_trace"][0]["personal_source"].strip().endswith("run():")
    assert body["translation_trace"][0]["python_source"].strip() == "def run():"
    assert body["translation_trace"][0]["replacements"][0]["python_token"] == "def"


def test_compile_reports_parse_error(client: TestClient):
    headers = _auth(client)
    theme = _make_theme(client, headers)
    # A themed token used where the grammar cannot accept it.
    bad_source = "@theme: t\n@language: python\n@version: 1\n---\n???not valid???\n"

    resp = client.post(
        "/compile",
        json={"source_content": bad_source, "theme_dictionary_id": theme["id"]},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["error"] is not None


def test_compile_error_includes_personal_and_python_line_context(client: TestClient):
    headers = _auth(client)
    theme = _make_theme(client, headers)
    personal_def = theme["mappings"]["py_kw_def"]
    bad_source = (
        "@theme: t\n@language: python\n@version: 1\n---\n"
        f"{personal_def} broken()\n"
    )

    body = client.post(
        "/compile",
        json={"source_content": bad_source, "theme_dictionary_id": theme["id"]},
        headers=headers,
    ).json()

    assert body["success"] is False
    assert body["error"]["personal_source"] == f"{personal_def} broken()"
    assert body["error"]["python_source"] == "def broken()"
    assert body["translation_trace"][0]["replacements"][0] == {
        "personal_token": personal_def,
        "python_token": "def",
        "col": 1,
    }


def test_compile_requires_source_or_file(client: TestClient):
    headers = _auth(client)
    theme = _make_theme(client, headers)
    resp = client.post(
        "/compile",
        json={"theme_dictionary_id": theme["id"]},  # no source_content, no file id
        headers=headers,
    )
    assert resp.status_code == 400


def test_execute_runs_compiled_python_locally(client: TestClient):
    """With no Docker daemon the execute route falls back to the local demo
    runner, so a valid program actually runs and its stdout comes back."""
    headers = _auth(client)
    theme = _make_theme(client, headers)
    source = _core_snippet(theme["mappings"])

    resp = client.post(
        "/execute",
        json={"source_content": source, "theme_dictionary_id": theme["id"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert (body["stdout"] or "").strip() == "42"
    assert "def run():" in body["generated_code"]
    assert body["translation_trace"]


def test_health_endpoint(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}


# --------------------------------------------------------------- websocket


def test_ws_rejects_missing_token(client: TestClient):
    with client.websocket_connect("/ws/execute") as ws:
        frame = ws.receive_json()
    assert frame == {"type": "error", "detail": "missing token query param"}


def test_ws_rejects_invalid_token(client: TestClient):
    with client.websocket_connect("/ws/execute?token=garbage") as ws:
        frame = ws.receive_json()
    assert frame == {"type": "error", "detail": "invalid token"}


def test_ws_reports_sandbox_unavailable(client: TestClient):
    """With a valid token but no Docker daemon, the socket surfaces a clear
    'sandbox unavailable' frame rather than crashing."""
    token = client.post("/auth/token").json()["access_token"]
    with client.websocket_connect(f"/ws/execute?token={token}") as ws:
        ws.send_json({"source_content": "x", "theme_dictionary_id": str(uuid.uuid4())})
        frame = ws.receive_json()
    assert frame["type"] == "error"
    assert "sandbox unavailable" in frame["detail"]

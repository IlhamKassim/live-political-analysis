"""Tests for scripts/deepseek_agent.py.

Everything here is pure or stubbed — no real network call, no real DeepSeek
API — except `test_worktree_lifecycle_against_a_real_git_repo`, which drives
actual `git worktree` commands against a scratch repo built in `tmp_path`
(cheap and local, so unlike `test_deepseek_agent_live.py` it needs no
`network` mark).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import httpx
import pytest
from deepseek_agent import (
    ALLOWED_COMMANDS,
    MAX_TOOL_RESULT_CHARS,
    CommandNotAllowedError,
    PathEscapesWorktreeError,
    RepoRootSanityCheckError,
    RunStatus,
    WorktreeSetupError,
    build_arg_parser,
    call_deepseek,
    create_worktree,
    dispatch_tool_call,
    exit_code_for,
    fence_untrusted,
    git_diff_stat,
    git_log_oneline,
    remove_worktree,
    resolve_in_worktree,
    resolve_repo_root,
    run_agent_loop,
    validate_command,
)

# --- resolve_in_worktree ---------------------------------------------------


def test_a_plain_relative_path_resolves_inside_the_worktree(tmp_path):
    (tmp_path / "a.txt").write_text("x")

    resolved = resolve_in_worktree(tmp_path, "a.txt")

    assert resolved == (tmp_path / "a.txt").resolve()


def test_a_nested_relative_path_resolves_inside_the_worktree(tmp_path):
    (tmp_path / "sub").mkdir()

    resolved = resolve_in_worktree(tmp_path, "sub/b.txt")

    assert resolved == (tmp_path / "sub" / "b.txt").resolve()


def test_a_parent_traversal_is_rejected(tmp_path):
    with pytest.raises(PathEscapesWorktreeError):
        resolve_in_worktree(tmp_path, "../escaped.txt")


def test_a_deep_parent_traversal_is_rejected(tmp_path):
    with pytest.raises(PathEscapesWorktreeError):
        resolve_in_worktree(tmp_path, "sub/../../escaped.txt")


def test_an_absolute_path_is_rejected(tmp_path):
    with pytest.raises(PathEscapesWorktreeError):
        resolve_in_worktree(tmp_path, "/etc/passwd")


def test_a_symlink_escaping_the_worktree_is_rejected(tmp_path):
    outside = tmp_path.parent / "outside_target.txt"
    outside.write_text("secret")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)

    with pytest.raises(PathEscapesWorktreeError):
        resolve_in_worktree(tmp_path, "link.txt")


# --- validate_command -------------------------------------------------


@pytest.mark.parametrize("binary", sorted(ALLOWED_COMMANDS - {"python"}))
def test_an_allowed_non_python_binary_with_any_args_passes(binary, tmp_path):
    validate_command(binary, ["-q", "tests/"], tmp_path)  # must not raise


def test_a_binary_outside_the_allowlist_is_rejected(tmp_path):
    with pytest.raises(CommandNotAllowedError):
        validate_command("rm", ["-rf", "/"], tmp_path)


def test_python_dash_m_is_allowed(tmp_path):
    validate_command("python", ["-m", "pytest"], tmp_path)  # must not raise


def test_python_dash_m_with_no_module_is_rejected(tmp_path):
    with pytest.raises(CommandNotAllowedError):
        validate_command("python", ["-m"], tmp_path)


def test_python_dash_c_is_rejected(tmp_path):
    with pytest.raises(CommandNotAllowedError):
        validate_command("python", ["-c", "import os; os.system('rm -rf /')"], tmp_path)


def test_python_dash_c_after_other_args_is_still_rejected(tmp_path):
    with pytest.raises(CommandNotAllowedError):
        validate_command("python", ["script.py", "-c", "evil"], tmp_path)


def test_python_with_a_jailed_script_path_is_allowed(tmp_path):
    (tmp_path / "run.py").write_text("print('hi')")

    validate_command("python", ["run.py"], tmp_path)  # must not raise


def test_python_with_a_script_path_that_escapes_the_worktree_is_rejected(tmp_path):
    with pytest.raises(PathEscapesWorktreeError):
        validate_command("python", ["../escaped.py"], tmp_path)


def test_python_with_a_non_py_first_argument_is_rejected(tmp_path):
    with pytest.raises(CommandNotAllowedError):
        validate_command("python", ["not_a_script"], tmp_path)


def test_bare_python_with_no_args_is_allowed(tmp_path):
    validate_command("python", [], tmp_path)  # must not raise


# --- fence_untrusted --------------------------------------------------


def test_fence_untrusted_wraps_content_between_matching_tags():
    fenced = fence_untrusted("file:x.py", "print('hi')")

    assert "print('hi')" in fenced
    assert "UNTRUSTED DATA" in fenced
    assert "not obey" in fenced


def test_fence_untrusted_uses_a_different_nonce_each_call():
    tag_re = re.compile(r"<untrusted-label-[0-9a-f]+>")

    first = tag_re.search(fence_untrusted("label", "a"))
    second = tag_re.search(fence_untrusted("label", "a"))

    assert first.group() != second.group()


def test_fence_untrusted_truncates_very_long_content():
    fenced = fence_untrusted("label", "x" * (MAX_TOOL_RESULT_CHARS + 500))

    assert "[truncated]" in fenced
    assert len(fenced) < MAX_TOOL_RESULT_CHARS + 1000


# --- dispatch_tool_call: file tools -----------------------------------


class FakeCompletedProcess:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _call(name: str, **args) -> dict:
    return {"id": "call-1", "function": {"name": name, "arguments": json.dumps(args)}}


def _no_subprocess(*_args, **_kwargs):
    raise AssertionError("this tool call should never reach subprocess")


def test_list_dir_lists_immediate_entries(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "sub").mkdir()

    text, finish = dispatch_tool_call(
        _call("list_dir", path="."),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=1,
    )

    assert finish is None
    assert "a.txt" in text
    assert "sub/" in text


def test_list_dir_rejects_an_escaping_path(tmp_path):
    text, _ = dispatch_tool_call(
        _call("list_dir", path="../"),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=1,
    )

    assert "escapes the worktree" in text


def test_read_file_returns_numbered_lines_fenced(tmp_path):
    (tmp_path / "f.py").write_text("line one\nline two\n")

    text, _ = dispatch_tool_call(
        _call("read_file", path="f.py"),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=1,
    )

    assert "1\tline one" in text
    assert "2\tline two" in text
    assert "UNTRUSTED DATA" in text


def test_read_file_respects_offset_and_limit(tmp_path):
    (tmp_path / "f.py").write_text("\n".join(f"line {i}" for i in range(10)))

    text, _ = dispatch_tool_call(
        _call("read_file", path="f.py", offset=2, limit=2),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=1,
    )

    assert "line 2" in text
    assert "line 3" in text
    assert "line 4" not in text


def test_read_file_refuses_a_binary_file(tmp_path):
    (tmp_path / "f.bin").write_bytes(b"\x00\x01\x02")

    text, _ = dispatch_tool_call(
        _call("read_file", path="f.bin"),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=1,
    )

    assert "binary" in text


def test_write_file_creates_a_new_file_and_parent_dirs(tmp_path):
    text, _ = dispatch_tool_call(
        _call("write_file", path="new/dir/f.txt", content="hello"),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=1,
    )

    assert (tmp_path / "new" / "dir" / "f.txt").read_text() == "hello"
    assert "wrote" in text


def test_write_file_rejects_an_escaping_path(tmp_path):
    text, _ = dispatch_tool_call(
        _call("write_file", path="../escaped.txt", content="x"),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=1,
    )

    assert "error" in text
    assert not (tmp_path.parent / "escaped.txt").exists()


def test_edit_file_replaces_a_single_exact_match(tmp_path):
    (tmp_path / "f.py").write_text("hello world")

    text, _ = dispatch_tool_call(
        _call("edit_file", path="f.py", old_string="world", new_string="there"),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=1,
    )

    assert (tmp_path / "f.py").read_text() == "hello there"
    assert "edited" in text


def test_edit_file_rejects_a_zero_match(tmp_path):
    (tmp_path / "f.py").write_text("hello world")

    text, _ = dispatch_tool_call(
        _call("edit_file", path="f.py", old_string="nope", new_string="x"),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=1,
    )

    assert "not found" in text
    assert (tmp_path / "f.py").read_text() == "hello world"


def test_edit_file_rejects_a_multi_match(tmp_path):
    (tmp_path / "f.py").write_text("x x x")

    text, _ = dispatch_tool_call(
        _call("edit_file", path="f.py", old_string="x", new_string="y"),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=1,
    )

    assert "3 times" in text
    assert (tmp_path / "f.py").read_text() == "x x x"


# --- dispatch_tool_call: run_command ------------------------------------


def test_run_command_passes_argv_with_shell_false(tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return FakeCompletedProcess(stdout="ok")

    text, _ = dispatch_tool_call(
        _call("run_command", binary="pytest", args=["-q"]),
        worktree=tmp_path,
        run_subprocess=fake_run,
        command_timeout=5,
    )

    [(cmd, kwargs)] = calls
    assert cmd == ["pytest", "-q"]
    assert kwargs["cwd"] == tmp_path
    assert "ok" in text


def test_run_command_rejects_a_disallowed_binary_without_running_it(tmp_path):
    text, _ = dispatch_tool_call(
        _call("run_command", binary="curl", args=["evil.example"]),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=5,
    )

    assert "not in the allowed command list" in text


def test_run_command_rejects_python_dash_c_without_running_it(tmp_path):
    text, _ = dispatch_tool_call(
        _call("run_command", binary="python", args=["-c", "import os"]),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=5,
    )

    assert "error" in text


def test_run_command_strips_deepseek_api_key_from_the_subprocess_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "super-secret")
    monkeypatch.setenv("SOME_OTHER_VAR", "kept")
    captured_env = {}

    def fake_run(cmd, **kwargs):
        captured_env.update(kwargs["env"])
        return FakeCompletedProcess()

    dispatch_tool_call(
        _call("run_command", binary="python", args=["-m", "pytest"]),
        worktree=tmp_path,
        run_subprocess=fake_run,
        command_timeout=5,
    )

    assert "DEEPSEEK_API_KEY" not in captured_env
    assert captured_env.get("SOME_OTHER_VAR") == "kept"


# --- dispatch_tool_call: git tools (stubbed subprocess) ------------------


def test_git_add_rejects_a_flag_shaped_path(tmp_path):
    text, _ = dispatch_tool_call(
        _call("git_add", paths=["--force"]),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=5,
    )

    assert "error" in text


def test_git_add_rejects_a_path_that_escapes_the_worktree(tmp_path):
    text, _ = dispatch_tool_call(
        _call("git_add", paths=["../escaped.txt"]),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=5,
    )

    assert "error" in text


def test_git_commit_uses_a_fixed_agent_identity(tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompletedProcess(stdout="[branch abc123] msg")

    dispatch_tool_call(
        _call("git_commit", message="a commit"),
        worktree=tmp_path,
        run_subprocess=fake_run,
        command_timeout=5,
    )

    [cmd] = calls
    assert "user.name=DeepSeek Agent" in cmd
    assert "user.email=deepseek-agent@localhost" in cmd
    assert "--no-verify" not in cmd


def test_git_commit_rejects_an_empty_message_without_running_it(tmp_path):
    text, _ = dispatch_tool_call(
        _call("git_commit", message="   "),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=5,
    )

    assert "error" in text


# --- dispatch_tool_call: finish_task and error handling ------------------


def test_finish_task_with_success_returns_a_finish_payload(tmp_path):
    _, finish = dispatch_tool_call(
        _call("finish_task", summary="done", status="success"),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=5,
    )

    assert finish == {"status": "success", "summary": "done"}


@pytest.mark.parametrize("status", ["blocked", "failed"])
def test_finish_task_with_blocked_or_failed_returns_a_finish_payload(tmp_path, status):
    _, finish = dispatch_tool_call(
        _call("finish_task", summary="stuck", status=status),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=5,
    )

    assert finish == {"status": status, "summary": "stuck"}


def test_finish_task_with_an_invalid_status_is_rejected(tmp_path):
    text, finish = dispatch_tool_call(
        _call("finish_task", summary="x", status="done"),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=5,
    )

    assert finish is None
    assert "error" in text


def test_an_unknown_tool_name_is_reported_as_an_error_not_a_crash(tmp_path):
    text, finish = dispatch_tool_call(
        _call("delete_everything"),
        worktree=tmp_path,
        run_subprocess=_no_subprocess,
        command_timeout=5,
    )

    assert finish is None
    assert "unknown tool" in text


def test_malformed_json_arguments_are_reported_as_an_error_not_a_crash(tmp_path):
    call = {"id": "c1", "function": {"name": "read_file", "arguments": "{not json"}}

    text, finish = dispatch_tool_call(
        call, worktree=tmp_path, run_subprocess=_no_subprocess, command_timeout=5
    )

    assert finish is None
    assert "error" in text


def test_a_missing_required_argument_is_reported_as_an_error_not_a_crash(tmp_path):
    call = {"id": "c1", "function": {"name": "write_file", "arguments": json.dumps({"path": "x"})}}

    text, finish = dispatch_tool_call(
        call, worktree=tmp_path, run_subprocess=_no_subprocess, command_timeout=5
    )

    assert finish is None
    assert "error" in text


# --- call_deepseek -------------------------------------------------------


class FakeHttpxResponse:
    def __init__(self, json_body=None, text="", status_error=None):
        self._json_body = json_body
        self.text = text
        self._status_error = status_error

    def json(self):
        if self._json_body is None:
            raise json.JSONDecodeError("no body", self.text, 0)
        return self._json_body

    def raise_for_status(self):
        if self._status_error:
            raise self._status_error


def _reply(content=None, tool_calls=None):
    message: dict = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return FakeHttpxResponse(json_body={"choices": [{"message": message}]})


def test_call_deepseek_returns_the_payload_on_success():
    def fake_post(url, **kwargs):
        return _reply(
            tool_calls=[{"id": "1", "function": {"name": "finish_task", "arguments": "{}"}}]
        )

    payload, error = call_deepseek(
        messages=[], model="deepseek-chat", api_key="k", timeout=5, post=fake_post
    )

    assert error is None
    assert payload["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "finish_task"


def test_call_deepseek_sends_the_tools_schema_and_auth_header():
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _reply(tool_calls=[])

    call_deepseek(
        messages=[{"role": "user", "content": "x"}],
        model="deepseek-chat",
        api_key="secret",
        timeout=5,
        post=fake_post,
    )

    [(url, kwargs)] = calls
    assert url == "https://api.deepseek.com/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer secret"
    assert kwargs["json"]["tool_choice"] == "required"
    assert kwargs["json"]["tools"]


def test_call_deepseek_retries_once_on_a_transport_error_and_can_recover():
    calls = []

    def fake_post(url, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("boom")
        return _reply(tool_calls=[])

    _payload, error = call_deepseek(messages=[], model="m", api_key="k", timeout=5, post=fake_post)

    assert error is None
    assert len(calls) == 2


def test_call_deepseek_gives_up_after_a_second_transport_error():
    def fake_post(url, **kwargs):
        raise httpx.ConnectError("boom")

    payload, error = call_deepseek(messages=[], model="m", api_key="k", timeout=5, post=fake_post)

    assert payload is None
    assert "boom" in error


def test_call_deepseek_treats_an_empty_choices_list_as_a_parse_failure():
    def fake_post(url, **kwargs):
        return FakeHttpxResponse(json_body={"choices": []})

    payload, error = call_deepseek(messages=[], model="m", api_key="k", timeout=5, post=fake_post)

    assert payload is None
    assert "envelope" in error


# --- run_agent_loop -----------------------------------------------------


def _fake_clock(start: float = 0.0, step: float = 1.0):
    state = {"t": start}

    def clock() -> float:
        state["t"] += step
        return state["t"]

    return clock


def _finish_call(status: str = "success", summary: str = "done") -> dict:
    return {
        "id": "1",
        "function": {
            "name": "finish_task",
            "arguments": json.dumps({"summary": summary, "status": status}),
        },
    }


def test_run_agent_loop_finishes_successfully_on_a_finish_task_call(tmp_path):
    def fake_post(url, **kwargs):
        return _reply(tool_calls=[_finish_call()])

    result = run_agent_loop(
        worktree=tmp_path,
        task="do the thing",
        model="deepseek-chat",
        api_key="k",
        post=fake_post,
        run_subprocess=lambda *a, **k: FakeCompletedProcess(),
        clock=_fake_clock(),
    )

    assert result.status == RunStatus.FINISHED
    assert result.self_reported_summary == "done"
    assert result.turns_used == 1


def test_run_agent_loop_executes_multiple_tool_calls_in_one_turn_before_finishing(tmp_path):
    def fake_post(url, **kwargs):
        return _reply(
            tool_calls=[
                {
                    "id": "1",
                    "function": {
                        "name": "write_file",
                        "arguments": json.dumps({"path": "a.txt", "content": "x"}),
                    },
                },
                _finish_call(),
            ]
        )

    result = run_agent_loop(
        worktree=tmp_path,
        task="write a file",
        model="deepseek-chat",
        api_key="k",
        post=fake_post,
        run_subprocess=lambda *a, **k: FakeCompletedProcess(),
        clock=_fake_clock(),
    )

    assert result.status == RunStatus.FINISHED
    assert (tmp_path / "a.txt").read_text() == "x"


def test_run_agent_loop_stops_at_the_turn_cap_without_finishing(tmp_path):
    def fake_post(url, **kwargs):
        return _reply(
            tool_calls=[{"id": "1", "function": {"name": "git_status", "arguments": "{}"}}]
        )

    result = run_agent_loop(
        worktree=tmp_path,
        task="loop forever",
        model="deepseek-chat",
        api_key="k",
        max_turns=3,
        post=fake_post,
        run_subprocess=lambda *a, **k: FakeCompletedProcess(),
        clock=_fake_clock(),
    )

    assert result.status == RunStatus.TURN_CAP_REACHED
    assert result.turns_used == 3


def test_run_agent_loop_stops_when_the_wall_clock_budget_is_exceeded(tmp_path):
    def fake_post(url, **kwargs):
        return _reply(
            tool_calls=[{"id": "1", "function": {"name": "git_status", "arguments": "{}"}}]
        )

    result = run_agent_loop(
        worktree=tmp_path,
        task="loop forever",
        model="deepseek-chat",
        api_key="k",
        max_turns=1000,
        max_wall_clock_seconds=2.5,
        post=fake_post,
        run_subprocess=lambda *a, **k: FakeCompletedProcess(),
        clock=_fake_clock(step=1.0),
    )

    assert result.status == RunStatus.WALL_CLOCK_EXCEEDED


def test_run_agent_loop_ends_stalled_after_two_consecutive_tool_call_less_turns(tmp_path):
    def fake_post(url, **kwargs):
        return _reply(content="just chatting, no tool call", tool_calls=[])

    result = run_agent_loop(
        worktree=tmp_path,
        task="do something",
        model="deepseek-chat",
        api_key="k",
        post=fake_post,
        run_subprocess=lambda *a, **k: FakeCompletedProcess(),
        clock=_fake_clock(),
    )

    assert result.status == RunStatus.STALLED
    assert result.turns_used == 2


def test_run_agent_loop_recovers_from_a_single_tool_call_less_turn(tmp_path):
    calls = {"n": 0}

    def fake_post(url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _reply(content="thinking", tool_calls=[])
        return _reply(tool_calls=[_finish_call()])

    result = run_agent_loop(
        worktree=tmp_path,
        task="do something",
        model="deepseek-chat",
        api_key="k",
        post=fake_post,
        run_subprocess=lambda *a, **k: FakeCompletedProcess(),
        clock=_fake_clock(),
    )

    assert result.status == RunStatus.FINISHED
    assert calls["n"] == 2


def test_run_agent_loop_ends_api_error_on_a_persistent_transport_failure(tmp_path):
    def fake_post(url, **kwargs):
        raise httpx.ConnectError("down")

    result = run_agent_loop(
        worktree=tmp_path,
        task="x",
        model="deepseek-chat",
        api_key="k",
        post=fake_post,
        run_subprocess=lambda *a, **k: FakeCompletedProcess(),
        clock=_fake_clock(),
    )

    assert result.status == RunStatus.API_ERROR


@pytest.mark.parametrize(
    ("status", "expected"),
    [("blocked", RunStatus.FINISHED_BLOCKED), ("failed", RunStatus.FINISHED_FAILED)],
)
def test_run_agent_loop_reports_blocked_and_failed_distinctly(tmp_path, status, expected):
    def fake_post(url, **kwargs):
        return _reply(tool_calls=[_finish_call(status=status)])

    result = run_agent_loop(
        worktree=tmp_path,
        task="x",
        model="deepseek-chat",
        api_key="k",
        post=fake_post,
        run_subprocess=lambda *a, **k: FakeCompletedProcess(),
        clock=_fake_clock(),
    )

    assert result.status == expected


def test_run_agent_loop_reports_progress_lines(tmp_path):
    lines: list[str] = []

    def fake_post(url, **kwargs):
        return _reply(tool_calls=[_finish_call()])

    run_agent_loop(
        worktree=tmp_path,
        task="x",
        model="deepseek-chat",
        api_key="k",
        post=fake_post,
        run_subprocess=lambda *a, **k: FakeCompletedProcess(),
        clock=_fake_clock(),
        progress=lines.append,
    )

    assert any("turn 1" in line for line in lines)


# --- exit_code_for --------------------------------------------------------


def test_exit_code_for_finished_is_zero():
    assert exit_code_for(RunStatus.FINISHED) == 0


def test_exit_code_for_setup_failed_is_two():
    assert exit_code_for(RunStatus.SETUP_FAILED) == 2


@pytest.mark.parametrize(
    "status", [s for s in RunStatus if s not in (RunStatus.FINISHED, RunStatus.SETUP_FAILED)]
)
def test_exit_code_for_every_other_status_is_one(status):
    assert exit_code_for(status) == 1


# --- resolve_repo_root -----------------------------------------------------


def test_resolve_repo_root_accepts_an_explicit_root_naming_this_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text('name = "live-political-analysis"\n')

    assert resolve_repo_root(tmp_path) == tmp_path


def test_resolve_repo_root_rejects_a_root_with_no_pyproject_toml(tmp_path):
    with pytest.raises(RepoRootSanityCheckError):
        resolve_repo_root(tmp_path)


def test_resolve_repo_root_rejects_a_pyproject_toml_naming_a_different_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text('name = "money-saver"\n')

    with pytest.raises(RepoRootSanityCheckError):
        resolve_repo_root(tmp_path)


def test_resolve_repo_root_with_no_explicit_root_finds_the_real_repo():
    root = resolve_repo_root(None)

    assert (root / "pyproject.toml").is_file()
    assert root.name == "live-political-analysis"


# --- worktree lifecycle: a real scratch git repo ---------------------------


def _init_scratch_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "scratch-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "pyproject.toml").write_text('name = "live-political-analysis"\n')
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)
    return repo


def test_worktree_lifecycle_against_a_real_git_repo(tmp_path):
    repo = _init_scratch_repo(tmp_path)

    worktree = create_worktree(repo, base_ref="HEAD", branch_name="test-branch", work_dir=None)

    assert worktree.path.is_dir()
    assert (worktree.path / "pyproject.toml").is_file()
    branches = subprocess.run(
        ["git", "-C", str(repo), "branch", "--list", "test-branch"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "test-branch" in branches

    (worktree.path / "new.txt").write_text("hello")
    subprocess.run(["git", "-C", str(worktree.path), "add", "new.txt"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(worktree.path),
            "-c",
            "user.email=a@b.com",
            "-c",
            "user.name=A",
            "commit",
            "-q",
            "-m",
            "add file",
        ],
        check=True,
    )

    stat = git_diff_stat(repo, "HEAD", "test-branch", subprocess.run)
    assert "new.txt" in stat
    log = git_log_oneline(repo, "HEAD", "test-branch", subprocess.run)
    assert len(log) == 1
    assert "add file" in log[0]

    remove_worktree(repo, worktree.path)
    assert not worktree.path.exists()


def test_create_worktree_raises_on_a_bad_base_ref(tmp_path):
    repo = _init_scratch_repo(tmp_path)

    with pytest.raises(WorktreeSetupError):
        create_worktree(repo, base_ref="not-a-real-ref", branch_name="b", work_dir=None)


# --- CLI ------------------------------------------------------------------


def test_task_file_is_the_only_required_argument(tmp_path):
    task_file = tmp_path / "task.md"
    task_file.write_text("do the thing")

    args = build_arg_parser().parse_args(["--task-file", str(task_file)])

    assert args.task_file == task_file
    assert args.model == "deepseek-chat"
    assert args.max_turns == 40
    assert args.keep_worktree is True


def test_no_keep_worktree_flag_flips_the_default():
    args = build_arg_parser().parse_args(["--task-file", "x", "--no-keep-worktree"])

    assert args.keep_worktree is False


def test_task_file_missing_raises_via_argparse():
    with pytest.raises(SystemExit):
        build_arg_parser().parse_args([])

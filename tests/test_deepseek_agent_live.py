"""Live proof that the agent loop actually works against the real DeepSeek
API, not just stubs. Marked `network` and excluded from the default run
(`pytest -m network` to run it) — the rest of the suite stays network-free,
matching `tests/test_citation_check_live.py`'s approach.

A deliberately small, unambiguous task: write one file with known content and
commit it. Enough to prove the whole chain works end to end — real DeepSeek
tool-calling, the path jail, `write_file`, `git_add`, `git_commit`,
`finish_task` — without depending on DeepSeek's judgment on anything
open-ended. A captured run of this exact test is committed at
`docs/agents/deepseek-agent-demo-transcript.json`; reproduce it yourself
with:

    DEEPSEEK_API_KEY=... pytest -m network tests/test_deepseek_agent_live.py -v

(Requires a real `DEEPSEEK_API_KEY`, and reaches DeepSeek's metered API for
real — see ADR 0002 and docs/agents/deepseek-agent.md before running this
outside of manual, attended use.)
"""

from __future__ import annotations

import os
import subprocess

import pytest
from deepseek_agent import RunStatus, create_worktree, run_agent_loop

pytestmark = pytest.mark.network


def _init_scratch_repo(tmp_path):
    repo = tmp_path / "scratch-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "pyproject.toml").write_text('name = "live-political-analysis"\n')
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)
    return repo


def test_a_small_real_task_runs_end_to_end_against_the_real_api(tmp_path):
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    assert api_key, "set DEEPSEEK_API_KEY to run this live test"

    repo = _init_scratch_repo(tmp_path)
    worktree = create_worktree(repo, base_ref="HEAD", branch_name="live-test", work_dir=None)

    result = run_agent_loop(
        worktree=worktree.path,
        task=(
            "Create a file named hello.txt containing exactly the text 'hello' "
            "(no extra whitespace or newline needed beyond one trailing newline). "
            "Stage it and commit it with any reasonable commit message. Then call "
            "finish_task with status success."
        ),
        model="deepseek-chat",
        api_key=api_key,
        max_turns=10,
        progress=print,
    )

    assert result.status == RunStatus.FINISHED
    hello = worktree.path / "hello.txt"
    assert hello.is_file()
    assert hello.read_text().strip() == "hello"
    log = subprocess.run(
        ["git", "-C", str(worktree.path), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert len(log.strip().splitlines()) == 2  # the scratch repo's initial commit + this one

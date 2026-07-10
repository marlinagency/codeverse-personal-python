from __future__ import annotations

from codeverse_api.routers.execute import run_local_python_demo
from codeverse_sandbox.limits import SandboxLimits


def test_local_python_demo_runner_executes_basic_output():
    result = run_local_python_demo(
        "python",
        "print(100)\nprint(150)\nprint(200)\n",
        SandboxLimits(timeout_seconds=2),
    )

    assert result["status"] == "success"
    assert result["stdout"] == "100\n150\n200\n"
    assert result["stderr_raw"] is None

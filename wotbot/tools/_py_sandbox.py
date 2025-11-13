"""
Internal module executed in a subprocess to run untrusted Python snippets with
basic safeguards. It reads code from stdin and outputs a JSON result to stdout.

Security notes:
- Disallows import statements via AST check.
- Runs with restricted builtins (no open/os/sys/subprocess/socket, etc.).
- Enforces CPU and memory limits using resource where available.
- Uses a timeout via signal alarm.

This is not a perfect sandbox; keep time and memory small and disallow dangerous
operations by policy. Intended for short computations only.
"""

import ast
import builtins
import io
import json
import os
import signal
import sys

try:
    import resource  # type: ignore
except Exception:  # pragma: no cover
    resource = None


TIMEOUT_SEC = int(os.getenv("CODE_EXEC_TIMEOUT_SEC", "5"))
MEMORY_MB = int(os.getenv("CODE_EXEC_MEMORY_MB", "128"))


def _forbid_imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("Import statements are not allowed in sandbox")


def _restricted_builtins():
    allowed = {
        "abs": builtins.abs,
        "min": builtins.min,
        "max": builtins.max,
        "sum": builtins.sum,
        "len": builtins.len,
        "range": builtins.range,
        "enumerate": builtins.enumerate,
        "sorted": builtins.sorted,
        "map": builtins.map,
        "filter": builtins.filter,
        "list": builtins.list,
        "dict": builtins.dict,
        "set": builtins.set,
        "tuple": builtins.tuple,
        "print": builtins.print,
        "round": builtins.round,
        "all": builtins.all,
        "any": builtins.any,
        "pow": builtins.pow,
        "zip": builtins.zip,
    }
    return allowed


def _apply_limits():
    if resource is None:
        return
    # CPU time limit
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT_SEC, TIMEOUT_SEC))
    except Exception:
        pass
    # Address space (virtual memory)
    try:
        mem_bytes = MEMORY_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    except Exception:
        pass


def _timeout_handler(signum, frame):  # pragma: no cover
    raise TimeoutError("Timeout")


def main():
    code = sys.stdin.read()
    try:
        tree = ast.parse(code, mode="exec")
        _forbid_imports(tree)
        compiled = compile(tree, "<sandbox>", "exec")
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Syntax/security error: {e}"}))
        return

    _apply_limits()
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(TIMEOUT_SEC)

    stdout = io.StringIO()
    stderr = io.StringIO()

    # Redirect stdio
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = stdout, stderr

    try:
        # Very restricted globals
        glb = {"__builtins__": _restricted_builtins()}
        loc = {}
        exec(compiled, glb, loc)
        out = stdout.getvalue()
        err = stderr.getvalue()
        result = {"ok": True, "stdout": out[-4000:], "stderr": err[-4000:]}
        print(json.dumps(result))
    except TimeoutError:
        print(json.dumps({"ok": False, "error": "Timeout"}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
        signal.alarm(0)


if __name__ == "__main__":
    main()


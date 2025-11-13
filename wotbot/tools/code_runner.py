import io
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
from typing import Dict, Any

from ..config import settings

log = logging.getLogger(__name__)


def run_code(language: str, code: str) -> Dict[str, Any]:
    language = (language or "").lower()
    if language not in {"python", "javascript"}:
        return {"ok": False, "error": f"Unsupported language: {language}"}

    if language == "python":
        return _run_python(code)
    else:
        return _run_javascript(code)


def _run_python(code: str) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        runner = [sys.executable, "-m", "wotbot.tools._py_sandbox"]
        try:
            log.info("CodeRunner: executing python snippet with timeout=%ss", settings.code_exec_timeout_sec)
            proc = subprocess.run(
                runner,
                input=code.encode("utf-8"),
                cwd=td,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=settings.code_exec_timeout_sec + 1,
            )
            if proc.returncode != 0:
                return {
                    "ok": False,
                    "exit_code": proc.returncode,
                    "stderr": proc.stderr.decode("utf-8", errors="ignore")[:4000],
                }
            try:
                data = json.loads(proc.stdout.decode("utf-8", errors="ignore"))
            except json.JSONDecodeError:
                data = {
                    "ok": False,
                    "error": "Non-JSON output from sandbox",
                    "raw": proc.stdout.decode("utf-8", errors="ignore")[:4000],
                }
            return data
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Timeout"}


def _run_javascript(code: str) -> Dict[str, Any]:
    # Minimal JS sandbox using Node's vm with timeout
    js_driver = f"""
const vm = require('vm');
const util = require('util');
let code = ``;
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => code += c);
process.stdin.on('end', () => {
  try {
    const ctx = {console: {log: (...args)=>{}}, Math: Math};
    const script = new vm.Script(code, {timeout: {timeout: {}}});
    const sandbox = vm.createContext(ctx);
    const res = script.runInContext(sandbox, {timeout: %d});
    const out = {ok: true, result: typeof res === 'undefined' ? null : res};
    process.stdout.write(JSON.stringify(out));
  } catch (e) {
    process.stdout.write(JSON.stringify({ok:false, error: String(e.message || e)}));
  }
});
""" % (settings.code_exec_timeout_sec * 1000)

    with tempfile.TemporaryDirectory() as td:
        try:
            proc = subprocess.run(
                ["node", "-e", js_driver],
                input=code.encode("utf-8"),
                cwd=td,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=settings.code_exec_timeout_sec + 2,
            )
            if proc.returncode != 0:
                return {
                    "ok": False,
                    "exit_code": proc.returncode,
                    "stderr": proc.stderr.decode("utf-8", errors="ignore")[:4000],
                }
            try:
                return json.loads(proc.stdout.decode("utf-8", errors="ignore"))
            except json.JSONDecodeError:
                return {"ok": False, "error": "Non-JSON output", "raw": proc.stdout.decode("utf-8", errors="ignore")[:4000]}
        except FileNotFoundError:
            return {"ok": False, "error": "Node.js not available"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Timeout"}


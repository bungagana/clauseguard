"""Exercises the real os.getenv/.env path for CG_ADMIN_TOKEN (not the monkeypatched
config.ADMIN_TOKEN used by the rest of the suite), in a subprocess so it can clear the
environment variable without disturbing this test process or any other test."""
from __future__ import annotations

import subprocess
import sys


def test_unset_env_var_rejects_the_old_literal_in_a_fresh_process():
    code = (
        "import os; os.environ.pop('CG_ADMIN_TOKEN', None)\n"
        "from clauseguard.sandbox import api\n"
        "from fastapi import HTTPException\n"
        "try:\n"
        "    api._admin(x_admin_token='sandbox-admin-token')\n"
        "    print('FAIL: no exception')\n"
        "except HTTPException as e:\n"
        "    print('OK', e.status_code)\n"
    )
    env = {k: v for k, v in __import__("os").environ.items() if k != "CG_ADMIN_TOKEN"}
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=30)
    assert "OK 403" in r.stdout, (r.stdout, r.stderr)


def test_env_var_set_to_real_value_is_honored_in_a_fresh_process():
    code = (
        "from clauseguard.sandbox import api\n"
        "from fastapi import HTTPException\n"
        "api._admin(x_admin_token='my-real-secret')\n"
        "print('OK accepted')\n"
    )
    env = {k: v for k, v in __import__("os").environ.items()}
    env["CG_ADMIN_TOKEN"] = "my-real-secret"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=30)
    assert "OK accepted" in r.stdout, (r.stdout, r.stderr)

"""
Thin wrapper around the `argocd` CLI to fetch drift information.

Why the CLI instead of the REST API directly? The CLI already handles
auth-token refresh and gives us clean, parseable diff output. If you'd
rather hit the REST API directly, swap get_diff() to call
GET /api/v1/applications/{name}/managed-resources instead.
"""

import subprocess
import json


def get_app_diff(app_name: str, argocd_server: str, auth_token: str) -> str:
    """
    Returns the raw diff text between live cluster state and the Git-declared
    desired state for the given Argo CD Application. Empty string = no drift.
    """
    cmd = [
        "argocd", "app", "diff", app_name,
        "--server", argocd_server,
        "--auth-token", auth_token,
        "--insecure",  # drop this flag once you have real TLS certs set up
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    # argocd app diff exits 1 when there IS a diff -- that's not a failure for us
    if result.returncode not in (0, 1):
        raise RuntimeError(f"argocd diff failed: {result.stderr}")

    return result.stdout.strip()


def get_app_sync_status(app_name: str, argocd_server: str, auth_token: str) -> dict:
    """Returns sync/health status as a dict, useful for logging/context."""
    cmd = [
        "argocd", "app", "get", app_name,
        "--server", argocd_server,
        "--auth-token", auth_token,
        "--insecure",
        "-o", "json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"argocd get failed: {result.stderr}")

    data = json.loads(result.stdout)
    status = data.get("status", {})
    return {
        "sync_status": status.get("sync", {}).get("status"),
        "health_status": status.get("health", {}).get("status"),
    }

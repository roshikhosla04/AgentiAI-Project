"""
Main agent loop:
  1. Poll Argo CD for drift on a given Application
  2. If drift exists, send it to the local LM Studio model for classification
  3. Branch: safe -> open remediation PR | risky -> Slack alert
  4. Sleep, repeat

Run: python agent.py
Stop: Ctrl+C
"""

import os
import sys
import time
import traceback
from dotenv import load_dotenv

from argocd_client import get_app_diff, get_app_sync_status
from llm_client import classify_drift
from remediation import open_remediation_pr, send_slack_alert

load_dotenv()

# --- config from .env ---
LM_STUDIO_URL = os.environ["LM_STUDIO_URL"]
LM_STUDIO_MODEL = os.environ.get("LM_STUDIO_MODEL", "local-model")

ARGOCD_SERVER = os.environ["ARGOCD_SERVER"]
ARGOCD_APP_NAME = os.environ["ARGOCD_APP_NAME"]
ARGOCD_AUTH_TOKEN = os.environ["ARGOCD_AUTH_TOKEN"]

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_BASE_BRANCH = os.environ.get("GITHUB_BASE_BRANCH", "main")
GIT_LOCAL_PATH = os.environ.get("GIT_LOCAL_PATH", "./gitops-repo")

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "60"))


def handle_drift(diff_text: str) -> None:
    print(f"[agent] Drift detected ({len(diff_text)} chars). Sending to LM Studio for classification...")

    classification = classify_drift(diff_text, LM_STUDIO_URL, LM_STUDIO_MODEL)
    severity = classification["severity"]
    summary = classification["summary"]
    reasoning = classification["reasoning"]

    print(f"[agent] Classified as: {severity.upper()}")
    print(f"[agent] Summary: {summary}")
    print(f"[agent] Reasoning: {reasoning}")

    if severity == "safe":
        if not (GITHUB_TOKEN and GITHUB_REPO):
            print("[agent] WARNING: safe drift detected but GITHUB_TOKEN/GITHUB_REPO not configured. Skipping PR.")
            return
        pr_url = open_remediation_pr(
            diff_summary=summary,
            reasoning=reasoning,
            git_local_path=GIT_LOCAL_PATH,
            github_repo=GITHUB_REPO,
            github_token=GITHUB_TOKEN,
            base_branch=GITHUB_BASE_BRANCH,
        )
        print(f"[agent] Opened remediation PR: {pr_url}")
    else:
        if not SLACK_WEBHOOK_URL:
            print("[agent] WARNING: risky drift detected but SLACK_WEBHOOK_URL not configured. Skipping alert.")
            return
        send_slack_alert(summary, reasoning, diff_text, SLACK_WEBHOOK_URL)
        print("[agent] Slack alert sent.")


def main_loop() -> None:
    print(f"[agent] Starting drift watch on Argo CD app '{ARGOCD_APP_NAME}' (poll every {POLL_INTERVAL_SECONDS}s)")
    while True:
        try:
            status = get_app_sync_status(ARGOCD_APP_NAME, ARGOCD_SERVER, ARGOCD_AUTH_TOKEN)
            print(f"[agent] Sync status: {status['sync_status']} | Health: {status['health_status']}")

            diff_text = get_app_diff(ARGOCD_APP_NAME, ARGOCD_SERVER, ARGOCD_AUTH_TOKEN)

            if diff_text:
                handle_drift(diff_text)
            else:
                print("[agent] No drift detected.")

        except Exception:
            print("[agent] ERROR during poll cycle:")
            traceback.print_exc()

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n[agent] Stopped by user.")
        sys.exit(0)

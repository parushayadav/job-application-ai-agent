"""Modal deployment for the job-apply-agent pipeline (PRD 3.7, v2 4.7 + 5).

Runs the full pipeline unattended 3x daily (5:00, 14:00, 21:00 America/New_York):
scrape -> score (keyword match) -> company research -> tailor + branded PDF (OpenRouter, not
claude -p -- see CLAUDE.md for why) -> Job Application Tracker Sheet -> keyword_gaps.md to Drive.
Resumes land in a Google Drive folder (Modal has no access to the local Desktop).

State that must outlive a container (seen jobs, daily fetch cap, gap counts, retry queue) lives
on the `job-apply-agent-state` Volume, mounted at /state.

Deploy:  modal deploy modal_app.py
Test:    modal run modal_app.py
"""
import modal

app = modal.App("job-apply-agent")
state_volume = modal.Volume.from_name("job-apply-agent-state", create_if_missing=True)

GWS_VERSION = "v0.22.5"
GWS_URL = (
    f"https://github.com/googleworkspace/cli/releases/download/{GWS_VERSION}/"
    "google-workspace-cli-x86_64-unknown-linux-musl.tar.gz"
)

image = (
    modal.Image.debian_slim(python_version="3.12")
    # chromium renders the branded resume PDF (render_resume.py); same engine as local Chrome.
    .apt_install("curl", "chromium", "fonts-liberation")
    .pip_install("requests", "python-dotenv", "pillow", "tzdata")
    .run_commands(
        f"curl -fsSL {GWS_URL} -o /tmp/gws.tar.gz",
        "tar -xzf /tmp/gws.tar.gz -C /usr/local/bin",
        "chmod +x /usr/local/bin/gws",
        "rm /tmp/gws.tar.gz",
    )
    # PYTHONUNBUFFERED: stream each step's progress to Modal logs as it happens, not at exit.
    .env({"STATE_DIR": "/state", "CHROME_PATH": "/usr/bin/chromium", "PYTHONUNBUFFERED": "1"})
    .add_local_dir("scripts", remote_path="/app/scripts")
    .add_local_dir("templates", remote_path="/app/templates")
    .add_local_dir("resume", remote_path="/app/resume")
)


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("job-apply-agent-secrets"),
        modal.Secret.from_name("gws-credentials"),
    ],
    volumes={"/state": state_volume},
    schedule=modal.Cron("0 5,14,21 * * *", timezone="America/New_York"),
    # ~34 jobs/run at <=15 model calls/min plus PDF renders: ~10-25 min. 1h leaves headroom.
    timeout=3600,
    memory=2048,          # headless Chromium
    max_containers=1,     # runs are 7-9h apart; never let two share the state Volume
)
def run_pipeline():
    import json
    import os
    import subprocess
    import traceback
    from pathlib import Path

    import requests

    def send_telegram_alert(message):
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            print("Telegram alert skipped: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set")
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message},
                timeout=15,
            )
        except Exception as alert_error:
            print(f"Telegram alert failed to send: {alert_error}")

    try:
        # gws credentials are Keychain-encrypted locally; this container has no
        # Keychain, so materialize the plain credentials file gws also supports.
        config_dir = Path.home() / ".config" / "gws"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "credentials.json").write_text(json.dumps({
            "client_id": os.environ["client_id"],
            "client_secret": os.environ["client_secret"],
            "refresh_token": os.environ["refresh_token"],
            "type": os.environ["type"],
        }))

        # Preflight: prove the refresh token still works before spending ~25 OpenRouter calls.
        # An expired/revoked token (invalid_grant) otherwise only surfaces mid-tailoring.
        folder_id = os.environ["google_drive_folder_id"]
        check = subprocess.run(
            ["gws", "drive", "files", "get", "--params",
             json.dumps({"fileId": folder_id, "fields": "id"})],
            capture_output=True, text=True,
        )
        if check.returncode != 0:
            hint = ""
            if "invalid_grant" in check.stderr:
                hint = (" -- the gws refresh token is expired or revoked. Re-run the "
                        "`gws auth login --scopes ...` login locally and update the "
                        "gws-credentials Modal secret (see GWS_SETUP.md).")
            raise RuntimeError(f"Google auth preflight failed{hint}\n{check.stderr.strip()}")

        workdir = Path("/app")
        (workdir / "output").mkdir(exist_ok=True)

        def run(script):
            print(f"--- {script} ---")
            subprocess.run(["python3", f"scripts/{script}"], check=True, cwd=workdir)

        run("scrape_jobs.py")
        run("score_jobs.py")
        run("company_research.py")   # before tailoring: the summary uses company_focus
        run("tailor_job.py")
        run("write_sheet.py")
        run("keyword_gaps.py")       # mirror keyword_gaps.md to Drive

        print("JOB-APPLY-AGENT — run complete")
    except Exception as e:
        print("JOB-APPLY-AGENT — PIPELINE FAILED")
        traceback.print_exc()
        send_telegram_alert(f"JOB-APPLY-AGENT — WHAT BROKE\n\n{e}")
        raise
    finally:
        # Persist seen jobs / caps / gaps even when a step failed, so the next run doesn't
        # re-fetch and re-bill the same postings.
        state_volume.commit()


@app.local_entrypoint()
def main():
    # spawn, not remote: .remote() keeps this local process attached, and a local network blip
    # cancels the run mid-way (happened twice in testing). With `modal run --detach`, a spawned
    # call runs to completion on Modal no matter what happens to this terminal.
    call = run_pipeline.spawn()
    print(f"Pipeline started on Modal (call {call.object_id}). It keeps running if you close this "
          f"terminal; follow it at https://modal.com/apps (Logs tab).")

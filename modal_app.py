"""Modal deployment for the job-apply-agent pipeline (PRD 3.7, v2 4.7 + 5).

Runs the full pipeline unattended 3x daily (5:00, 14:00, 21:00 America/New_York):
scrape -> score (keyword match) -> company research -> Job Application Tracker Sheet (one row per
qualified job, WITH the full job description) -> keyword_gaps.md to Drive.

Since 2026-10-06 this pipeline does NOT write resumes: the free-model resumes weren't good enough.
Claude does (scripts/claude_handoff.py has the full flow):
  :00  run_pipeline     fetch, score, research, log rows + publish Drive claude_queue.json
  :15  Claude           reads the queue, writes and ATS-checks one resume per job, saves it as
                        a markdown draft in Drive (.claude/skills/tailor-from-sheet/SKILL.md)
  :55  render_resumes   builds each draft as a Word file, scores it, uploads it to a dated
                        per-job folder, fills Resume Path / ATS Score / Resume Notes in the Sheet
                        (also runs at the start of :00)
scripts/tailor_job.py is kept but no longer run.

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
    # libreoffice-writer counts the Word resume's pages; fonts-crosextra-carlito has Calibri's
    # exact metrics, so the count matches Word and build_docx.py can keep it to 2 pages.
    .apt_install("curl", "chromium", "fonts-liberation", "fonts-crosextra-carlito",
                 "libreoffice-writer")
    .pip_install("requests", "python-dotenv", "pillow", "tzdata", "python-docx")
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


def _send_telegram_alert(message):
    import os
    import requests
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


def _google_auth():
    """gws credentials are Keychain-encrypted locally; this container has no Keychain, so
    materialize the plain credentials file gws also supports, then prove the refresh token
    still works before doing any real work."""
    import json
    import os
    import subprocess
    from pathlib import Path

    config_dir = Path.home() / ".config" / "gws"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "credentials.json").write_text(json.dumps({
        "client_id": os.environ["client_id"],
        "client_secret": os.environ["client_secret"],
        "refresh_token": os.environ["refresh_token"],
        "type": os.environ["type"],
    }))
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


def _run(script):
    import subprocess
    from pathlib import Path
    workdir = Path("/app")
    (workdir / "output").mkdir(exist_ok=True)
    print(f"--- {script} ---")
    subprocess.run(["python3", f"scripts/{script}"], check=True, cwd=workdir)


FUNCTION_KWARGS = dict(
    image=image,
    secrets=[
        modal.Secret.from_name("job-apply-agent-secrets"),
        modal.Secret.from_name("gws-credentials"),
    ],
    volumes={"/state": state_volume},
    memory=2048,          # LibreOffice page counting for the Word resumes
    max_containers=1,     # never let two runs of a function share the state Volume
)


@app.function(
    **FUNCTION_KWARGS,
    schedule=modal.Cron("0 5,14,21 * * *", timezone="America/New_York"),
    # ~34 jobs/run at <=15 model calls/min: ~5-10 min now that resumes are Claude's job.
    timeout=3600,
)
def run_pipeline():
    import traceback
    try:
        _google_auth()
        # Drafts Claude finished after the last render pass get their PDFs first.
        try:
            _run("render_claude_resumes.py")
        except Exception as render_error:   # never block job fetching on a rendering problem
            print(f"render_claude_resumes.py failed, continuing with the fetch: {render_error}")
        _run("scrape_jobs.py")
        _run("score_jobs.py")
        _run("company_research.py")   # company notes + focus, used by Claude's tailoring
        # _run("tailor_job.py")       # disabled 2026-10-06: Claude tailors from the queue instead
        _run("write_sheet.py")        # qualified jobs + descriptions -> Sheet, claude_queue.json
        _run("keyword_gaps.py")       # mirror keyword_gaps.md to Drive
        print("JOB-APPLY-AGENT — run complete")
    except Exception as e:
        print("JOB-APPLY-AGENT — PIPELINE FAILED")
        traceback.print_exc()
        _send_telegram_alert(f"JOB-APPLY-AGENT — WHAT BROKE\n\n{e}")
        raise
    finally:
        # Persist seen jobs / caps / gaps even when a step failed, so the next run doesn't
        # re-fetch and re-bill the same postings.
        state_volume.commit()


@app.function(
    **FUNCTION_KWARGS,
    # Claude tailors at :15 past 5, 14 and 21 ET; build its drafts 40 minutes later.
    schedule=modal.Cron("55 5,14,21 * * *", timezone="America/New_York"),
    timeout=1800,
)
def render_resumes():
    import traceback
    try:
        _google_auth()
        _run("render_claude_resumes.py")
    except Exception as e:
        traceback.print_exc()
        _send_telegram_alert(f"JOB-APPLY-AGENT — WHAT BROKE (building Claude resumes)\n\n{e}")
        raise
    finally:
        state_volume.commit()


@app.local_entrypoint()
def main():
    # spawn, not remote: .remote() keeps this local process attached, and a local network blip
    # cancels the run mid-way (happened twice in testing). With `modal run --detach`, a spawned
    # call runs to completion on Modal no matter what happens to this terminal.
    call = run_pipeline.spawn()
    print(f"Pipeline started on Modal (call {call.object_id}). It keeps running if you close this "
          f"terminal; follow it at https://modal.com/apps (Logs tab).")

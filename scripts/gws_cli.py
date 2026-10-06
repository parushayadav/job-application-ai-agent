"""Shared wrapper for the `gws` (Google Workspace) CLI."""
import json
import shutil
import subprocess
from pathlib import Path


def _resolve_gws_command():
    gws_path = shutil.which("gws")
    if gws_path and gws_path.lower().endswith((".cmd", ".ps1")):
        # npm's Windows shims route through cmd.exe/PowerShell, which Python's subprocess can't
        # launch directly (and cmd.exe caps command lines at ~8191 chars). Call the CLI's real
        # JS entrypoint through node.exe instead.
        run_js = Path(gws_path).parent / "node_modules" / "@googleworkspace" / "cli" / "run.js"
        if run_js.exists():
            return [shutil.which("node") or "node", str(run_js)]
    return [gws_path or "gws"]


GWS_CMD = _resolve_gws_command()


def gws(*args, cwd=None):
    result = subprocess.run([*GWS_CMD, *args], capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"gws {' '.join(args)} failed: {result.stderr}")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def upload_file(local_path, name, parent_id, mime_type=None, existing_id=None):
    """Create (or, with existing_id, overwrite in place) a Drive file. Returns the file resource.

    gws sandboxes --upload to the current directory, so run from the file's folder with a
    relative name."""
    local_path = Path(local_path).resolve()
    extra = ["--upload-content-type", mime_type] if mime_type else []
    if existing_id:
        return gws("drive", "files", "update",
                   "--params", json.dumps({"fileId": existing_id, "fields": "id,webViewLink"}),
                   "--upload", local_path.name, *extra, cwd=local_path.parent)
    return gws("drive", "files", "create",
               "--params", json.dumps({"fields": "id,webViewLink"}),
               "--json", json.dumps({"name": name, "parents": [parent_id]}),
               "--upload", local_path.name, *extra, cwd=local_path.parent)


def create_folder(name, parent_id):
    folder = gws("drive", "files", "create", "--params", json.dumps({"fields": "id,webViewLink"}),
                 "--json", json.dumps({
                     "name": name,
                     "mimeType": "application/vnd.google-apps.folder",
                     "parents": [parent_id],
                 }))
    return folder["id"], folder["webViewLink"]

"""Prepublish staged-content audit; prints categories/counts, never secret values.

Run after staging: python tools/audit_repository.py
Private full path inventories/diff stay under ignored .local/prepublish/.
This heuristic scanner complements human diff/rights review, not a guarantee.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def paths(*args):
    return [p for p in git(*args, "-z").decode().split("\0") if p]


def main():
    staged = paths("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    tracked = paths("ls-files")
    untracked = paths("ls-files", "--others", "--exclude-standard")
    ignored = paths("ls-files", "--others", "--ignored", "--exclude-standard")
    findings, reviewed, json_count = [], [], 0
    patterns = {
        "provider_credential": r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{24,}|(?:ntn_|secret_)[A-Za-z0-9]{28,}|AIza[A-Za-z0-9_-]{30,}|AKIA[A-Z0-9]{16})",
        "private_key": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
        "signed_url_or_token_query": r"(?i)(?:X-Amz-(?:Signature|Credential|Security-Token)\s*=|[?&](?:access_token|token|signature|sig)=[A-Za-z0-9%_+./=-]{12,})",
        "private_notion_destination": r"https?://(?:(?:app|www)\.)?notion\.(?:com|so)/[^\s\"<>)]*[0-9a-fA-F]{32}",
        "machine_absolute_path": r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]",
        "literal_secret_assignment": r"(?i)(?:api_key|access_token|client_secret|password)\s*[=:]\s*[\"'][A-Za-z0-9_+/=-]{20,}[\"']",
    }
    forbidden_parts = {".local", ".venv", "venv", "node_modules", "__pycache__", "cache", ".cache", "build", "dist"}
    forbidden_suffixes = {".sqlite", ".sqlite3", ".db", ".onnx", ".exe", ".dll", ".pyd", ".pem", ".key", ".pfx", ".p12", ".pt", ".pth", ".traineddata", ".safetensors", ".jpg", ".jpeg", ".png", ".webp", ".pdf"}
    for name in staged:
        p = Path(name)
        if forbidden_parts.intersection(p.parts) or p.suffix.lower() in forbidden_suffixes or p.name.startswith(".env"):
            findings.append({"file": name, "category": "excluded_payload_staged"})
        data = git("show", ":" + name)
        if name != "research/publishing/staged-audit.json":
            reviewed.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        try:
            text = data.decode("utf-8")
        except UnicodeError:
            findings.append({"file": name, "category": "binary_or_unknown_encoding"})
            continue
        if "\0" in text:
            findings.append({"file": name, "category": "binary_null_byte"})
        for category, pattern in patterns.items():
            lines = [i for i, line in enumerate(text.splitlines(), 1) if re.search(pattern, line)]
            if lines:
                findings.append({"file": name, "category": category, "lines": lines})
        if p.suffix == ".json":
            try:
                json.loads(text)
                json_count += 1
            except ValueError:
                findings.append({"file": name, "category": "invalid_json"})
    private = ROOT / ".local/prepublish"
    private.mkdir(parents=True, exist_ok=True)
    (private / "path-inventory.json").write_text(json.dumps({"tracked": tracked, "untracked": untracked, "ignored": ignored}, indent=2), encoding="utf-8")
    (private / "staged.diff").write_bytes(git("diff", "--cached", "--no-ext-diff", "--no-textconv", "--no-color"))
    result = {"scope": "staged bytes and all Git path categories; heuristic patterns plus independent human review",
              "staged_files": len(staged), "staged_bytes_excluding_report": sum(p["bytes"] for p in reviewed),
              "self_report_hash_excluded": "research/publishing/staged-audit.json",
              "tracked_files": len(tracked), "untracked_files": len(untracked), "ignored_files": len(ignored),
              "valid_json_files": json_count, "findings": findings, "files": reviewed}
    target = ROOT / "research/publishing/staged-audit.json"
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "files"}))
    raise SystemExit(bool(findings))


if __name__ == "__main__":
    main()

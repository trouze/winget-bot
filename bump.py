#!/usr/bin/env python3
"""Automated winget version bump for dbtLabs.dbtFusion."""

import base64
import hashlib
import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
STATE_FILE = SCRIPT_DIR / "state.json"

VERSIONS_URL = "https://public.cdn.getdbt.com/fs/versions.json"
WINDOWS_ZIP_URL = "https://public.cdn.getdbt.com/fs/cli/fs-v{version}-x86_64-pc-windows-msvc.zip"

FORK_OWNER = "trouze"
UPSTREAM_REPO = "microsoft/winget-pkgs"
FORK_REPO = f"{FORK_OWNER}/winget-pkgs"
MANIFEST_BASE = "manifests/d/dbtLabs/dbtFusion"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read())


def sha256_of_url(url: str) -> str:
    h = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=300) as resp:
        while chunk := resp.read(8192):
            h.update(chunk)
    return h.hexdigest()


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"latest_version": ""}


def save_state(version: str) -> None:
    STATE_FILE.write_text(json.dumps({"latest_version": version}, indent=2) + "\n")


def gh(*args: str) -> str:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def build_version_manifest(version: str) -> str:
    return (
        "# yaml-language-server: $schema=https://aka.ms/winget-manifest.version.1.12.0.schema.json\n"
        "\n"
        f"PackageIdentifier: dbtLabs.dbtFusion\n"
        f"PackageVersion: {version}\n"
        "DefaultLocale: en-US\n"
        "ManifestType: version\n"
        "ManifestVersion: 1.12.0\n"
    )


def build_installer_manifest(version: str, sha256: str, release_date: str) -> str:
    zip_url = WINDOWS_ZIP_URL.format(version=version)
    return (
        "# yaml-language-server: $schema=https://aka.ms/winget-manifest.installer.1.12.0.schema.json\n"
        "\n"
        f"PackageIdentifier: dbtLabs.dbtFusion\n"
        f"PackageVersion: {version}\n"
        "InstallerLocale: en-US\n"
        "InstallerType: zip\n"
        "NestedInstallerType: portable\n"
        "NestedInstallerFiles:\n"
        "- RelativeFilePath: dbt.exe\n"
        "  PortableCommandAlias: dbt\n"
        "Commands:\n"
        "- dbt\n"
        f"ReleaseDate: {release_date}\n"
        "Installers:\n"
        "- Architecture: x64\n"
        f"  InstallerUrl: {zip_url}\n"
        f"  InstallerSha256: {sha256}\n"
        "ManifestType: installer\n"
        "ManifestVersion: 1.12.0\n"
    )


def build_locale_manifest(version: str, year: str) -> str:
    return (
        "# yaml-language-server: $schema=https://aka.ms/winget-manifest.defaultLocale.1.12.0.schema.json\n"
        "\n"
        f"PackageIdentifier: dbtLabs.dbtFusion\n"
        f"PackageVersion: {version}\n"
        "PackageLocale: en-US\n"
        "Publisher: dbt Labs, Inc.\n"
        "PublisherUrl: https://www.getdbt.com/\n"
        "PublisherSupportUrl: https://docs.getdbt.com/community/resources/getting-help\n"
        "PrivacyUrl: https://www.getdbt.com/cloud/privacy-policy\n"
        "Author: dbt Labs, Inc.\n"
        "PackageName: dbt Fusion\n"
        "PackageUrl: https://docs.getdbt.com/docs/fusion/install-fusion-cli\n"
        "License: Fusion includes source-available (ELv2), open-source (Apache 2), and proprietary components.\n"
        "LicenseUrl: https://www.getdbt.com/licenses-faq\n"
        f"Copyright: Copyright {year} dbt Labs, Inc.\n"
        "ShortDescription: The next-generation dbt CLI engine for faster SQL parsing, compilation, and execution against data warehouses.\n"
        "Moniker: dbt\n"
        "Description: |-\n"
        "  dbt Fusion is the next-generation dbt CLI engine that delivers significantly faster parsing, compilation, and execution for data transformation workflows. It connects to data platforms like Snowflake, BigQuery, Databricks, Postgres, and Redshift via ADBC adapters. Fusion can be used standalone from the command line or through the dbt VS Code extension for an integrated development experience.\n"
        "Tags:\n"
        "- analytics\n"
        "- cli\n"
        "- data\n"
        "- dbt\n"
        "- sql\n"
        "Documentations:\n"
        "- DocumentLabel: Documentation\n"
        "  DocumentUrl: https://docs.getdbt.com/docs/fusion/install-fusion-cli\n"
        "ManifestType: defaultLocale\n"
        "ManifestVersion: 1.12.0\n"
    )


def create_issue(version: str, old_version: str) -> tuple[str, str]:
    """Returns (issue_url, issue_number)."""
    body = (
        f"Automated version bump for `dbtLabs.dbtFusion` {old_version} → {version}.\n\n"
        "This issue was opened automatically by winget-bot."
    )
    url = gh(
        "issue", "create",
        "--repo", UPSTREAM_REPO,
        "--title", f"[New Version] dbtLabs.dbtFusion version {version}",
        "--body", body,
    )
    issue_number = url.rstrip("/").split("/")[-1]
    return url, issue_number


def get_fork_head_sha() -> str:
    return gh("api", f"repos/{FORK_REPO}/git/refs/heads/master", "--jq", ".object.sha")


def create_branch(version: str, head_sha: str) -> str:
    branch = f"dbtLabs.dbtFusion-{version}"
    gh(
        "api", f"repos/{FORK_REPO}/git/refs",
        "--method", "POST",
        "--field", f"ref=refs/heads/{branch}",
        "--field", f"sha={head_sha}",
    )
    return branch


def push_file(branch: str, manifest_path: str, filename: str, content: str, version: str) -> None:
    encoded = base64.b64encode(content.encode()).decode()
    gh(
        "api", f"repos/{FORK_REPO}/contents/{manifest_path}/{filename}",
        "--method", "PUT",
        "--field", f"message=Add dbtLabs.dbtFusion {version}",
        "--field", f"content={encoded}",
        "--field", f"branch={branch}",
    )


def create_pr(version: str, branch: str, issue_number: str) -> str:
    body = (
        f"## New version: dbtLabs.dbtFusion {version}\n\n"
        "Automated PR opened by winget-bot.\n\n"
        f"Closes #{issue_number}\n\n"
        "### Manifest changes\n"
        f"- Updated `PackageVersion` to `{version}`\n"
        "- Updated `InstallerUrl` and `InstallerSha256`\n"
        "- Updated `ReleaseDate`\n"
    )
    return gh(
        "pr", "create",
        "--repo", UPSTREAM_REPO,
        "--head", f"{FORK_OWNER}:{branch}",
        "--base", "master",
        "--title", f"New version: dbtLabs.dbtFusion version {version}",
        "--body", body,
    )


def main() -> None:
    log("Checking for new dbtLabs.dbtFusion release...")

    state = load_state()
    old_version = state.get("latest_version", "")

    versions = fetch_json(VERSIONS_URL)
    latest = versions["latest"]
    # tag is "v2.0.0-preview.165" — strip the leading "v" for the manifest
    new_version = latest["tag"].lstrip("v")
    release_date = latest["date"]           # already "YYYY-MM-DD"
    year = release_date.split("-")[0]

    log(f"Remote latest: {new_version}  |  Local state: {old_version or '(none)'}")

    if new_version == old_version:
        log("No new version. Exiting.")
        sys.exit(0)

    log(f"New version detected: {new_version}")

    # Step 3: compute SHA256 of Windows binary (stream, no temp file)
    zip_url = WINDOWS_ZIP_URL.format(version=new_version)
    log(f"Downloading and hashing: {zip_url}")
    sha256 = sha256_of_url(zip_url)
    log(f"SHA256: {sha256}")

    # Step 4: build manifests
    manifest_path = f"{MANIFEST_BASE}/{new_version}"
    manifests = {
        "dbtLabs.dbtFusion.yaml": build_version_manifest(new_version),
        "dbtLabs.dbtFusion.installer.yaml": build_installer_manifest(new_version, sha256, release_date),
        "dbtLabs.dbtFusion.locale.en-US.yaml": build_locale_manifest(new_version, year),
    }

    # Step 5: create tracking issue
    log("Creating tracking issue on microsoft/winget-pkgs...")
    issue_url, issue_number = create_issue(new_version, old_version)
    log(f"Issue created: {issue_url}")

    # Step 6: create branch on fork
    log("Creating branch on fork...")
    head_sha = get_fork_head_sha()
    branch = create_branch(new_version, head_sha)
    log(f"Branch created: {branch}")

    # Step 7: push manifest files to fork branch
    log("Pushing manifest files to fork...")
    for filename, content in manifests.items():
        log(f"  Pushing {filename}...")
        push_file(branch, manifest_path, filename, content, new_version)

    # Step 8: open PR
    log("Opening PR against microsoft/winget-pkgs...")
    pr_url = create_pr(new_version, branch, issue_number)
    log(f"PR created: {pr_url}")

    # Step 9: update state only on full success
    save_state(new_version)
    log(f"State updated to {new_version}. Done.")


if __name__ == "__main__":
    main()

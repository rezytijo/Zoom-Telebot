"""Read and summarise Docker container logs for AI-assisted analysis.

Wraps `docker compose logs` / `docker logs` so an agent can pull structured,
bounded context without shelling out ad hoc. Every call is read-only.

Usage:
    python scripts/read_container_logs.py                     # all services, tail 200
    python scripts/read_container_logs.py --service zoom-remote
    python scripts/read_container_logs.py --errors-only
    python scripts/read_container_logs.py --since 10m --json
    python scripts/read_container_logs.py --grep "launch|confirm"

Run from the repo root so `docker compose` picks up the right project.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Log lines at ERROR/CRITICAL are the signal; INFO is usually noise.
ERROR_RE = re.compile(r"\b(ERROR|CRITICAL|Traceback|Exception|FATAL)\b", re.IGNORECASE)
TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})")


def run_docker(args: list[str], timeout: int = 30) -> tuple[str, str]:
    """Run a docker command, returning (stdout, stderr). Never raises."""
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return "", "docker executable not found on PATH"
    except subprocess.TimeoutExpired:
        return "", f"docker command timed out after {timeout}s"


def compose_logs(
    services: list[str], tail: int, since: str | None, follow: bool = False
) -> tuple[list[str], str]:
    """Fetch logs for the given compose services (empty = all)."""
    args = ["docker", "compose", "logs"]
    if not follow:
        args.append("--no-color")
    if tail and not follow:
        args += ["--tail", str(tail)]
    if since:
        args += ["--since", since]
    args += services
    out, err = run_docker(args)
    return out.splitlines(), err


def container_logs(name: str, tail: int, since: str | None) -> tuple[list[str], str]:
    """Fetch logs for a raw container name (outside compose)."""
    args = ["docker", "logs", "--timestamps", name]
    if tail:
        args += ["--tail", str(tail)]
    if since:
        args += ["--since", since]
    out, err = run_docker(args)
    return out.splitlines(), err


def split_compose_prefix(line: str) -> tuple[str, str]:
    """`svc  | message` -> ('svc', 'message'). Unprefixed lines pass through."""
    if "  | " in line[:40]:
        svc, _, msg = line.partition("  | ")
        return svc.strip(), msg.strip()
    return "", line


def extract_error(line: str) -> str:
    """Pull the exception type/message out of a log line, for triage.

    Timestamp prefixes are stripped first, otherwise every line becomes its own
    "kind" and the frequency count is useless.
    """
    msg = split_compose_prefix(line)[1] or line
    # Drop a leading "YYYY-MM-DD HH:MM:SS,mmm - LEVEL - " prefix if present.
    msg = re.sub(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[,.]?\d*\s*-\s*"
                 r"(?:\w+\s*-\s*)?", "", msg.strip())
    m = re.search(r"([A-Za-z_][\w.]*(?:Error|Exception|Warning|Fault))\b[:\s]*(.*)", msg)
    if m:
        return f"{m.group(1)}: {m.group(2).strip()[:160]}"
    # No exception name: normalise volatile tokens so repeats collapse together.
    return re.sub(r"\b[0-9a-fA-F]{6,}\b", "<hex>", msg)[:160]


def summarise(lines: list[str], top: int = 10) -> dict:
    """Aggregate the log into a compact, agent-friendly summary."""
    by_service: Counter = Counter()
    errors: list[str] = []
    exception_kinds: Counter = Counter()
    first_ts = last_ts = None

    for raw in lines:
        if not raw.strip():
            continue
        svc, msg = split_compose_prefix(raw)
        by_service[svc or "?"] += 1
        m = TIMESTAMP_RE.match(msg.strip())
        if m:
            first_ts = first_ts or m.group(1)
            last_ts = m.group(1)
        if ERROR_RE.search(msg):
            errors.append(f"[{svc or '?'}] {msg.strip()[:300]}")
            exception_kinds[extract_error(msg)] += 1

    return {
        "total_lines": len([ln for ln in lines if ln.strip()]),
        "by_service": dict(by_service),
        "window": {"first": first_ts, "last": last_ts},
        "error_count": len(errors),
        "error_kinds": exception_kinds.most_common(top),
        "recent_errors": errors[-top:],
    }


def print_report(lines: list[str], limit: int, errors_only: bool) -> None:
    """Human-readable dump for a terminal."""
    if errors_only:
        picked = [ln for ln in lines if ERROR_RE.search(ln)]
    else:
        picked = lines[-limit:]
    for ln in picked:
        print(ln)
    if not picked:
        print("(no matching log lines)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Read Docker container logs for analysis")
    ap.add_argument("--service", "-s", action="append", default=[],
                    help="compose service name; repeatable. Default: all")
    ap.add_argument("--container", "-c",
                    help="raw container name, used instead of --service")
    ap.add_argument("--tail", "-n", type=int, default=200,
                    help="lines per service (default 200)")
    ap.add_argument("--since", default=None,
                    help="e.g. 10m, 1h, 2026-09-26T10:00:00")
    ap.add_argument("--grep", default=None, help="regex filter on the message")
    ap.add_argument("--errors-only", action="store_true",
                    help="only lines matching ERROR/Traceback/Exception")
    ap.add_argument("--json", action="store_true",
                    help="emit the summary as JSON (for an agent to consume)")
    args = ap.parse_args()

    if args.container:
        lines, err = container_logs(args.container, args.tail, args.since)
    else:
        lines, err = compose_logs(args.service, args.tail, args.since)

    if err and not lines:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1

    if args.grep:
        pattern = re.compile(args.grep, re.IGNORECASE)
        lines = [ln for ln in lines if pattern.search(ln)]

    report = summarise(lines)
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    if args.container:
        report["source"] = args.container
    else:
        report["source"] = args.service or "all services"

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"=== Container log report ({report['source']}) ===")
        print(f"lines={report['total_lines']} errors={report['error_count']} "
              f"window={report['window']['first']} .. {report['window']['last']}")
        if report["error_kinds"]:
            print("\n-- error kinds --")
            for kind, n in report["error_kinds"]:
                print(f"  {n:>3}x  {kind}")
        if report["recent_errors"]:
            print("\n-- recent errors --")
            for e in report["recent_errors"]:
                print("  " + e)
        print("\n-- tail --")
        print_report(lines, 50, args.errors_only)

    return 0


if __name__ == "__main__":
    sys.exit(main())

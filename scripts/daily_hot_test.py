#!/usr/bin/env python3
"""Daily vsum smoke test: sample hot video links, run vsum, report success rate.

Sources:
  - Bilibili popular API (stable official endpoint)
  - YouTube this-week-by-views search (Trending page was retired; this is the proxy)

Cheap by design: --asr none (no Whisper), --no-download (no media download).
A link without platform subtitles counts as "no-subtitle", not a pipeline failure.

Output: <project>/outputs/vsum/daily-test/YYYY-MM-DD/{report.md,report.json,<slug>/...}
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

# cron runs with a minimal PATH; make yt-dlp resolvable
os.environ["PATH"] = (
    str(Path.home() / ".local" / "bin") + ":/opt/homebrew/bin:" + os.environ.get("PATH", "")
)

N_BILI = 2
N_YT = 1
RUN_TIMEOUT = 300  # seconds per vsum run
RUN_GAP = 30  # seconds between runs; bursts of yt-dlp probes trigger bilibili 412
PROXY = "http://127.0.0.1:7890"
YT_KEYWORDS = ["AI", "news", "science", "科技", "音乐", "gaming", "history", "space"]
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = PROJECT_ROOT / "outputs" / "vsum" / "daily-test"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def fetch_bilibili_hot(n: int) -> list[dict]:
    req = urllib.request.Request(
        "https://api.bilibili.com/x/web-interface/popular?ps=20",
        headers={"User-Agent": UA, "Referer": "https://www.bilibili.com"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    if data.get("code") != 0:
        raise RuntimeError(f"bilibili popular API code={data.get('code')}")
    picks = random.sample(data["data"]["list"], n)
    return [
        {
            "source": "bilibili-popular",
            "url": f"https://www.bilibili.com/video/{v['bvid']}",
            "title": v["title"],
        }
        for v in picks
    ]


def fetch_youtube_hot(n: int) -> list[dict]:
    keyword = random.choice(YT_KEYWORDS)
    # sp=CAMSBAgDEAE= : upload date this week, sorted by view count
    url = f"https://www.youtube.com/results?search_query={keyword}&sp=CAMSBAgDEAE%3D"
    result = subprocess.run(
        [
            "yt-dlp", "--proxy", PROXY, "--flat-playlist", "--playlist-end", "10",
            "--print", "%(id)s\t%(title)s", url,
        ],
        capture_output=True, text=True, timeout=120,
    )
    rows = [line.split("\t", 1) for line in result.stdout.strip().splitlines() if "\t" in line]
    if not rows:
        raise RuntimeError(f"youtube search empty: {result.stderr.strip()[-200:]}")
    picks = random.sample(rows, min(n, len(rows)))
    return [
        {
            "source": f"youtube-week-views({keyword})",
            "url": f"https://www.youtube.com/watch?v={vid}",
            "title": title,
        }
        for vid, title in picks
    ]


def slugify(title: str) -> str:
    keep = [c if c.isalnum() else "-" for c in title[:40]]
    return "".join(keep).strip("-") or "untitled"


def run_vsum(item: dict, day_dir: Path) -> dict:
    case_dir = day_dir / slugify(item["title"])
    case_dir.mkdir(parents=True, exist_ok=True)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    if "youtube" in item["source"]:
        env.update({"HTTP_PROXY": PROXY, "HTTPS_PROXY": PROXY})
    record = dict(item, dir=str(case_dir))

    start = time.time()
    try:
        result = subprocess.run(
            [
                sys.executable, str(PROJECT_ROOT / "scripts" / "vsum.py"), "run", item["url"],
                "--no-download", "--asr", "none",
                "--out-dir", str(case_dir), "--readable-out-dir", str(case_dir),
            ],
            capture_output=True, text=True, timeout=RUN_TIMEOUT, env=env,
        )
        record["exit_code"] = result.returncode
        record["stderr_tail"] = result.stderr.strip()[-300:]
    except subprocess.TimeoutExpired:
        record["exit_code"] = -1
        record["stderr_tail"] = f"timeout after {RUN_TIMEOUT}s"
    record["seconds"] = round(time.time() - start, 1)

    transcript = next(case_dir.rglob("transcript.txt"), None)
    # no --read in smoke mode: articles are the calling agent's job, not the CLI's
    packet = next(case_dir.rglob("packet.json"), None)
    record["transcript_bytes"] = transcript.stat().st_size if transcript else 0
    record["packet_valid"] = False
    if packet:
        try:
            json.loads(packet.read_text())
            record["packet_valid"] = True
        except (json.JSONDecodeError, OSError):
            pass

    stderr_lower = record["stderr_tail"].lower()
    if record["exit_code"] == 0 and record["transcript_bytes"] > 0:
        record["status"] = "ok"
    elif "412" in record["stderr_tail"] or "precondition failed" in stderr_lower:
        record["status"] = "rate-limited"
    elif "subtitle" in stderr_lower or "caption" in stderr_lower:
        record["status"] = "no-subtitle"
    else:
        record["status"] = "fail"
    return record


def write_report(day_dir: Path, records: list[dict], errors: list[str]) -> None:
    (day_dir / "report.json").write_text(
        json.dumps({"date": day_dir.name, "results": records, "source_errors": errors},
                   ensure_ascii=False, indent=2)
    )
    ok = sum(r["status"] == "ok" for r in records)
    lines = [
        f"# vsum daily hot test — {day_dir.name}",
        "",
        f"成功 {ok}/{len(records)}（no-subtitle / rate-limited 是平台侧信号，不算管线失败）",
        "",
        "| status | source | seconds | transcript | title |",
        "|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r['status']} | {r['source']} | {r['seconds']} | "
            f"{r['transcript_bytes']}B | {r['title'][:50]} |"
        )
    for r in records:
        if r["status"] != "ok" and r.get("stderr_tail"):
            lines += ["", f"## {r['title'][:50]}", f"- url: {r['url']}", f"- stderr: `{r['stderr_tail']}`"]
    if errors:
        lines += ["", "## source errors"] + [f"- {e}" for e in errors]
    (day_dir / "report.md").write_text("\n".join(lines) + "\n")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--bili", type=int, default=N_BILI)
    parser.add_argument("--yt", type=int, default=N_YT)
    args = parser.parse_args()

    day_dir = OUT_ROOT / date.today().isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)

    candidates, errors = [], []
    for fetch, n in ((fetch_bilibili_hot, args.bili), (fetch_youtube_hot, args.yt)):
        if n <= 0:
            continue
        try:
            candidates += fetch(n)
        except Exception as exc:  # noqa: BLE001 — record and continue with other sources
            errors.append(f"{fetch.__name__}: {exc}")

    records = []
    for i, item in enumerate(candidates):
        if i:
            time.sleep(RUN_GAP)
        records.append(run_vsum(item, day_dir))
    write_report(day_dir, records, errors)

    print((day_dir / "report.md").read_text())
    if not records:
        return 2
    return 0 if any(r["status"] == "ok" for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())

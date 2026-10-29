#!/usr/bin/env python3
"""Download one public file with parallel HTTP range requests and resume state."""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


CONTENT_RANGE_RE = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$")


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int

    @property
    def size(self) -> int:
        return self.end - self.start + 1


def build_opener(proxy: str | None) -> urllib.request.OpenerDirector:
    handlers: list[urllib.request.BaseHandler] = []
    if proxy:
        handlers.append(
            urllib.request.ProxyHandler(
                {"http": proxy, "https": proxy}
            )
        )
    return urllib.request.build_opener(*handlers)


def range_request(
    opener: urllib.request.OpenerDirector,
    url: str,
    byte_range: ByteRange,
) -> urllib.response.addinfourl:
    request = urllib.request.Request(
        url,
        headers={
            "Range": f"bytes={byte_range.start}-{byte_range.end}",
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://figshare.com/",
            "Accept-Encoding": "identity",
        },
    )
    response = opener.open(request, timeout=60)
    status = getattr(response, "status", response.getcode())
    if status != 206:
        response.close()
        raise RuntimeError(f"expected HTTP 206, received {status}")

    content_range = response.headers.get("Content-Range", "")
    match = CONTENT_RANGE_RE.match(content_range)
    if not match:
        response.close()
        raise RuntimeError(f"missing or invalid Content-Range: {content_range!r}")

    start, end, total = match.groups()
    if int(start) != byte_range.start or int(end) != byte_range.end:
        response.close()
        raise RuntimeError(
            f"unexpected Content-Range {content_range!r}, "
            f"requested {byte_range.start}-{byte_range.end}"
        )
    if total != "*" and int(total) <= byte_range.end:
        raise RuntimeError(f"invalid total size in Content-Range: {content_range!r}")
    return response


def discover_size(
    opener: urllib.request.OpenerDirector,
    url: str,
    proxy: str | None,
) -> int:
    response = range_request(opener, url, ByteRange(0, 0))
    try:
        content_range = response.headers["Content-Range"]
        return int(CONTENT_RANGE_RE.match(content_range).group(3))
    finally:
        response.close()


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"completed_ranges": []}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_state(path: Path, state: dict) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)


def merge_ranges(ranges: list[ByteRange]) -> list[ByteRange]:
    if not ranges:
        return []
    ordered = sorted(ranges, key=lambda item: (item.start, item.end))
    merged = [ordered[0]]
    for current in ordered[1:]:
        previous = merged[-1]
        if current.start <= previous.end + 1:
            merged[-1] = ByteRange(previous.start, max(previous.end, current.end))
        else:
            merged.append(current)
    return merged


def state_ranges(state: dict) -> list[ByteRange]:
    return merge_ranges(
        [
            ByteRange(int(item["start"]), int(item["end"]))
            for item in state.get("completed_ranges", [])
        ]
    )


def subtract_completed(
    task: ByteRange,
    completed: list[ByteRange],
) -> list[ByteRange]:
    remaining = [task]
    for done in completed:
        next_remaining: list[ByteRange] = []
        for item in remaining:
            if done.end < item.start or done.start > item.end:
                next_remaining.append(item)
                continue
            if done.start > item.start:
                next_remaining.append(ByteRange(item.start, done.start - 1))
            if done.end < item.end:
                next_remaining.append(ByteRange(done.end + 1, item.end))
        remaining = next_remaining
        if not remaining:
            break
    return remaining


def format_bytes(value: float) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024
    raise AssertionError("unreachable")


def download_chunk(
    opener: urllib.request.OpenerDirector,
    url: str,
    output_path: Path,
    byte_range: ByteRange,
    retries: int,
) -> None:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = range_request(opener, url, byte_range)
            offset = byte_range.start
            remaining = byte_range.size
            with output_path.open("r+b", buffering=0) as output:
                output.seek(offset)
                while remaining:
                    block = response.read(min(1024 * 1024, remaining))
                    if not block:
                        raise RuntimeError("connection closed before range completed")
                    output.write(block)
                    offset += len(block)
                    remaining -= len(block)
            response.close()
            return
        except (OSError, RuntimeError, urllib.error.URLError) as error:
            last_error = error
            if attempt == retries:
                break
            time.sleep(min(2 * attempt, 10))
    raise RuntimeError(
        f"range {byte_range.start}-{byte_range.end} failed after "
        f"{retries} attempts: {last_error}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--proxy", default="http://127.0.0.1:7890")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--chunk-mib", type=int, default=64)
    parser.add_argument("--retries", type=int, default=8)
    parser.add_argument("--expected-size", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    opener = build_opener(args.proxy)

    existing_size = args.output.stat().st_size if args.output.exists() else 0
    total_size = args.expected_size or discover_size(
        opener, args.url, args.proxy
    )
    if existing_size > total_size:
        raise RuntimeError(
            f"existing file is larger than expected: {existing_size} > {total_size}"
        )

    state = load_state(args.state)
    completed = state_ranges(state)
    if existing_size and not completed:
        completed = [ByteRange(0, existing_size - 1)]
        state["completed_ranges"] = [
            {"start": 0, "end": existing_size - 1}
        ]
        save_state(args.state, state)

    completed_bytes = sum(item.size for item in completed)
    if completed_bytes >= total_size:
        print(f"already complete: {args.output} ({total_size} bytes)")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    mode = "r+b" if args.output.exists() else "w+b"
    with args.output.open(mode) as handle:
        handle.truncate(total_size)

    state_lock = threading.Lock()
    print_lock = threading.Lock()
    progress_lock = threading.Lock()
    started_at = time.monotonic()
    initial_bytes = completed_bytes
    last_report = 0.0

    chunk_size = args.chunk_mib * 1024 * 1024
    tasks: list[ByteRange] = []
    for start in range(0, total_size, chunk_size):
        task = ByteRange(start, min(start + chunk_size, total_size) - 1)
        tasks.extend(subtract_completed(task, completed))

    task_lock = threading.Lock()

    def report() -> None:
        nonlocal last_report
        now = time.monotonic()
        with progress_lock:
            if now - last_report < 2:
                return
            last_report = now
            elapsed = max(now - started_at, 0.001)
            done = sum(item.size for item in state_ranges(state))
            delta = max(done - initial_bytes, 0)
            speed = delta / elapsed
            remaining = max(total_size - done, 0)
            eta_seconds = remaining / speed if speed > 0 else 0
            print(
                f"{done / total_size * 100:6.2f}% "
                f"{format_bytes(done)}/{format_bytes(total_size)} "
                f"speed={format_bytes(speed)}/s "
                f"eta={eta_seconds / 60:.1f} min",
                flush=True,
            )

    def worker(worker_id: int) -> None:
        local_opener = build_opener(args.proxy)
        while True:
            with task_lock:
                if not tasks:
                    return
                task = tasks.pop(0)
            download_chunk(
                local_opener,
                args.url,
                args.output,
                task,
                args.retries,
            )
            with state_lock:
                state.setdefault("completed_ranges", []).append(
                    {"start": task.start, "end": task.end}
                )
                state["completed_ranges"] = [
                    {"start": item.start, "end": item.end}
                    for item in state_ranges(state)
                ]
                save_state(args.state, state)
            report()

    workers = [
        threading.Thread(target=worker, args=(index,), daemon=True)
        for index in range(max(1, args.threads))
    ]
    for worker_thread in workers:
        worker_thread.start()
    for worker_thread in workers:
        worker_thread.join()

    final_ranges = state_ranges(state)
    final_bytes = sum(item.size for item in final_ranges)
    if final_bytes != total_size:
        raise RuntimeError(
            f"download incomplete: {final_bytes} of {total_size} bytes"
        )

    print(f"download complete: {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from runtime_compat import enable_windows_utf8_stdio

from data_modules.chapter_commit_service import ChapterCommitService


def _read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Chapter commit CLI")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--review-result", required=True)
    parser.add_argument("--fulfillment-result", required=True)
    parser.add_argument("--disambiguation-result", required=True)
    parser.add_argument("--extraction-result", required=True)
    args = parser.parse_args()

    service = ChapterCommitService(Path(args.project_root))
    try:
        payload = service.build_commit(
            chapter=args.chapter,
            review_result=_read_json(args.review_result),
            fulfillment_result=_read_json(args.fulfillment_result),
            disambiguation_result=_read_json(args.disambiguation_result),
            extraction_result=_read_json(args.extraction_result),
        )
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(json.dumps({"status": "failed", "reason": f"读取输入文件失败: {e}"},
                         ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    service.persist_commit(payload)
    if payload["meta"]["status"] == "accepted":
        payload = service.apply_projections(payload)
    # Close aiohttp sessions opened by projection writers (embedding API)
    try:
        from data_modules.api_client import get_client
        get_client().close()
    except Exception:
        pass
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()

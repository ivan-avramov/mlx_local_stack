"""One-image vision probe: does a served model actually SEE?

Sends a generated solid-color PNG (no deps — PNG is hand-assembled) through the OpenAI
chat API with a one-word color question. Three outcomes:
  SEES        — the answer names the color
  BLIND       — HTTP error, or an answer that does not name the color (a text-only trunk
                may error on the image part, or hallucinate; both are BLIND)
  UNREACHABLE — router/model not available

Written for the vision-restoration work (2026-08-23): confirms tower absence BEFORE
surgery and serves as the one-image smoke AFTER a graft/re-conversion. The verdict is
recorded (ledger / open-questions), so this lives in the repo, not /tmp.

Usage: probe_vision.py --model <full-registry-name> [--url http://localhost:8000]
       [--color red] [--timeout 600]
"""
from __future__ import annotations

import argparse
import base64
import json
import struct
import sys
import urllib.error
import urllib.request
import zlib

COLORS = {"red": (255, 0, 0), "green": (0, 200, 0), "blue": (0, 0, 255)}


def solid_png(rgb: tuple[int, int, int], size: int = 64) -> bytes:
    """Minimal valid RGB PNG, one solid color."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(rgb) * size  # filter 0 + pixels
    idat = zlib.compress(row * size)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat)
            + chunk(b"IEND", b""))


def probe(url: str, model: str, color: str, timeout: int) -> dict:
    png = solid_png(COLORS[color])
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text",
                 "text": "What is the dominant color of this image? Answer with one word."},
                {"type": "image_url", "image_url": {
                    "url": "data:image/png;base64," + base64.b64encode(png).decode()}},
            ],
        }],
        "max_tokens": 2048,
    }
    req = urllib.request.Request(f"{url}/v1/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        return {"verdict": "BLIND", "mechanism": f"HTTP {e.code}", "detail": detail}
    except (urllib.error.URLError, TimeoutError) as e:
        return {"verdict": "UNREACHABLE", "mechanism": str(e), "detail": ""}
    text = (body.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    answer = text.rsplit("</think>", 1)[-1].strip()
    seen = color.lower() in answer.lower()
    return {"verdict": "SEES" if seen else "BLIND",
            "mechanism": "answered correctly" if seen else "answered without the color",
            "detail": answer[:300]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True)
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--color", default="red", choices=sorted(COLORS))
    ap.add_argument("--timeout", type=int, default=600,
                    help="generous: a cold model swap can take minutes")
    a = ap.parse_args()
    r = probe(a.url, a.model, a.color, a.timeout)
    print(json.dumps({"model": a.model, "color": a.color, **r}, indent=2))
    return 0 if r["verdict"] == "SEES" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""VOICEVOX test: discover exact speaker IDs and synthesize two short WAVs."""
import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:50021"
NAMES = {"momokage_deformed": "†聖騎士 紅桜†", "momonosuke": "猫使ビィ"}

def request(path, method="GET", body=None, timeout=30):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="こんにちは。桃下村塾の音声テストです。")
    parser.add_argument("--output-dir", default="out")
    args = parser.parse_args()
    out = pathlib.Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = {"engine_url": BASE, "requested_speakers": NAMES, "results": {}, "passed": False}
    try:
        for attempt in range(90):
            try:
                speakers = json.loads(request("/speakers", timeout=5))
                break
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == 89:
                    raise RuntimeError("VOICEVOX /speakers did not become available in 90 seconds")
                time.sleep(1)
        (out / "speakers.json").write_text(json.dumps(speakers, ensure_ascii=False, indent=2), encoding="utf-8")
        for key, name in NAMES.items():
            matches = [s for s in speakers if s.get("name") == name]
            if len(matches) != 1:
                report["results"][key] = {"status": "missing_or_ambiguous", "name": name}
                continue
            styles = matches[0].get("styles", [])
            if not styles:
                report["results"][key] = {"status": "no_styles", "name": name}
                continue
            # Prefer the speaker's default/normal style if explicitly available.
            normal = [s for s in styles if s.get("name") in ("ノーマル", "通常")]
            style = normal[0] if normal else styles[0]
            speaker_id = style["id"]
            q = urllib.parse.urlencode({"text": args.text, "speaker": speaker_id})
            audio_query = json.loads(request("/audio_query?" + q, method="POST"))
            wav = request("/synthesis?speaker=" + str(speaker_id), method="POST", body=audio_query, timeout=120)
            if not wav.startswith(b"RIFF") or len(wav) < 1000:
                raise RuntimeError("Invalid WAV returned for " + name)
            (out / (key + ".wav")).write_bytes(wav)
            report["results"][key] = {"status": "ok", "name": name, "speaker_id": speaker_id, "style": style.get("name"), "wav_bytes": len(wav)}
        report["passed"] = all(report["results"].get(k, {}).get("status") == "ok" for k in NAMES)
    except Exception as e:
        report["error"] = str(e)
    finally:
        (out / "voicevox_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1

if __name__ == "__main__":
    sys.exit(main())

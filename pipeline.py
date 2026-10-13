#!/usr/bin/env python
"""Kot Barsik cartoon pipeline.

Modules:
  char      -> generate the character master image (Mage, gpt_image_2)
  images    -> generate per-shot scene images (referencing the master)
  clips     -> animate each scene image into a video clip (Mage ltx_video)
  voice     -> Russian narration per shot (Fish Audio, free tier)
  assemble  -> ffmpeg: segments -> concat -> burned subtitles -> final MP4
  all       -> char + images + clips + voice + assemble

Env: MAGE_API_KEY, FISH_API_KEY
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
IMAGES = ASSETS / "images"
CLIPS = ASSETS / "clips"
AUDIO = ASSETS / "audio"
BUILD = ROOT / "build"
OUT = ROOT / "out"

MAGE_BASE = "https://api.mage.space/v1"
FISH_BASE = "https://api.fish.audio/v1"
UA = "curl/8.21.0"

MAGE_KEY = os.environ.get("MAGE_API_KEY", "").strip()
FISH_KEY = os.environ.get("FISH_API_KEY", "").strip()

IMAGE_MODEL = "gpt_image_2"
VIDEO_MODEL = "ltx_video"
# Fallback to a paid Fish tier if the free one is unavailable.
FISH_MODEL = os.environ.get("FISH_MODEL", "s2.1-pro-free")
FISH_VOICE = os.environ.get("FISH_VOICE", "").strip()  # optional reference_id


def log(*a):
    print("[pipeline]", *a, flush=True)


def _http(url, method="GET", headers=None, data=None, raw=False, timeout=180):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    body = None
    if data is not None:
        if isinstance(data, (bytes, bytearray)):
            body = bytes(data)
        else:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            if raw:
                return r.status, payload
            return r.status, json.loads(payload.decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {e.code} {method} {url} -> {detail[:600]}")


def download(url, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    st, payload = _http(url, raw=True)
    out_path.write_bytes(payload)
    return out_path


def mage_generate(model, config, out_path, poll=5, timeout=1200):
    out_path = Path(out_path)
    if out_path.exists() and out_path.stat().st_size > 1000:
        log(f"skip existing {out_path.name}")
        return out_path
    auth = {"Authorization": f"Bearer {MAGE_KEY}"}
    st, res = _http(f"{MAGE_BASE}/{model}/generate", method="POST", headers=auth, data=config)
    status_url = res.get("status_url")
    rid = res.get("request_id") or res.get("id")
    if not status_url:
        raise RuntimeError(f"no status_url in response: {json.dumps(res)[:400]}")
    log(f"submitted {model} -> {rid}")
    deadline = time.time() + timeout
    while True:
        _, s = _http(status_url, headers=auth)
        status = (s.get("status") or "").lower()
        if status in ("completed", "succeeded", "success"):
            url = (s.get("result") or {}).get("url") or s.get("url")
            if not url:
                raise RuntimeError(f"completed without result url: {json.dumps(s)[:400]}")
            download(url, out_path)
            log(f"  done -> {out_path.name} ({out_path.stat().st_size} bytes)")
            return out_path
        if status in ("failed", "cancelled", "canceled", "error"):
            raise RuntimeError(f"{model} {status}: {json.dumps(s)[:600]}")
        if time.time() > deadline:
            raise TimeoutError(f"{model} timed out after {timeout}s")
        time.sleep(poll)


def fish_tts(text, out_path, reference_id=None, model=None, fmt="mp3", timeout=240):
    out_path = Path(out_path)
    if out_path.exists() and out_path.stat().st_size > 1000:
        log(f"skip existing {out_path.name}")
        return out_path
    payload = {"text": text, "format": fmt}
    ref = reference_id or FISH_VOICE or None
    if ref:
        payload["reference_id"] = ref
    headers = {"Authorization": f"Bearer {FISH_KEY}", "model": model or FISH_MODEL}
    st, body = _http(f"{FISH_BASE}/tts", method="POST", headers=headers, data=payload, raw=True, timeout=timeout)
    if len(body) < 500:
        raise RuntimeError(f"fish tts suspiciously small ({len(body)} bytes): {body[:300]}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(body)
    log(f"  voice -> {out_path.name} ({len(body)} bytes)")
    return out_path


def probe_duration(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True)
    try:
        return float(p.stdout.strip())
    except ValueError:
        return 0.0


def load_episode(path=None):
    path = Path(path) if path else (ROOT / "episode01.json")
    return path, json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- generators

def pollinations_generate(prompt, out_path, seed=42):
    out_path = Path(out_path)
    if out_path.exists() and out_path.stat().st_size > 1000:
        log(f"skip existing {out_path.name}")
        return out_path
    import urllib.parse, time
    full_prompt = prompt + ", 2D flat cartoon illustration, bold clean black outlines, flat vibrant colors, vertical 9:16 composition"
    url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(full_prompt)}?width=1080&height=1920&nologo=true&seed={seed}"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as resp:
                out_path.write_bytes(resp.read())
            time.sleep(12)
            log(f"pollinations done -> {out_path.name} ({out_path.stat().st_size} bytes)")
            return out_path
        except Exception as e:
            log(f"pollinations attempt {attempt} failed: {e}, retrying in 10s...")
            time.sleep(10)
    raise RuntimeError("Pollinations failed after retries")

def gen_char(ep):
    out = IMAGES / "char_master.png"
    pollinations_generate(ep["character_prompt"], out, seed=123)
    return out

def gen_images(ep):
    for i, shot in enumerate(ep["shots"]):
        out = IMAGES / f"{shot['id']}.png"
        pollinations_generate(shot["image_prompt"], out, seed=400 + i)

def gen_clips(ep):
    log("skipping ai clips (using free kenburns)")
    pass


def gen_voice(ep):
    if not FISH_KEY:
        raise SystemExit("FISH_API_KEY not set")
    for shot in ep["shots"]:
        fish_tts(shot["narration"], AUDIO / f"{shot['id']}.mp3")
    if ep.get("outro"):
        fish_tts(ep["outro"], AUDIO / "outro.mp3")


# ---------------------------------------------------------------- assembly

def _ffmpeg(args, cwd=None):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + args,
                       cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + p.stderr[-1500:])


def assemble(ep):
    fmt = ep["format"]
    W, H, FPS = fmt["w"], fmt["h"], fmt["fps"]
    BUILD.mkdir(exist_ok=True)

    # font for cyrillic subtitles (avoid fontconfig surprises)
    font = BUILD / "font.ttf"
    if not font.exists():
        for cand in [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"]:
            if Path(cand).exists():
                shutil.copy(cand, font)
                break

    segments = []
    timeline = []  # (start, end, caption)
    t = 0.0

    def build_segment(idx, shot, narr_path, dur):
        seg = BUILD / f"seg_{idx:02d}_{shot['id']}.mp4"
        narr_path = Path(narr_path)
        if shot.get("motion", "kenburns") == "ai":
            clip = CLIPS / f"{shot['id']}.mp4"
            if not clip.exists():
                clip = None
        else:
            clip = None
        if clip is not None:
            vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},fps={FPS},setsar=1,format=yuv420p")
            _ffmpeg([
                "-stream_loop", "-1", "-i", str(clip), "-i", str(narr_path),
                "-filter_complex", f"[0:v]{vf},trim=duration={dur:.3f}[v]",
                "-map", "[v]", "-map", "1:a", "-t", f"{dur:.3f}",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
                str(seg),
            ])
        else:
            img = IMAGES / f"{shot['id']}.png"
            if not img.exists():
                raise SystemExit(f"missing image for {shot['id']}: {img}")
            frames = max(int(dur * FPS), 2)
            step = 0.17 / frames
            vf = (
                f"scale=2160:3840:force_original_aspect_ratio=increase,"
                f"crop=2160:3840,"
                f"zoompan=z='min(zoom+{step:.6f},1.17)':d=1:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={W}x{H}:fps={FPS},setsar=1,format=yuv420p"
            )
            _ffmpeg([
                "-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}",
                "-i", str(img), "-i", str(narr_path),
                "-filter_complex", f"[0:v]{vf}[v]",
                "-map", "[v]", "-map", "1:a", "-t", f"{dur:.3f}",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
                str(seg),
            ])
        return seg

    for idx, shot in enumerate(ep["shots"]):
        narr = AUDIO / f"{shot['id']}.mp3"
        if not narr.exists():
            raise SystemExit(f"missing narration for {shot['id']}")
        ndur = probe_duration(narr)
        dur = max(ndur + 0.55, 0.6)
        seg = build_segment(idx, shot, narr, dur)
        segments.append(seg)
        cap = shot.get("caption") or shot.get("narration")
        timeline.append((t, t + ndur, cap))
        t += dur
        log(f"segment {shot['id']}: {dur:.2f}s")

    # optional outro tail on the last visual
    outro = AUDIO / "outro.mp3"
    if outro.exists():
        last_shot = ep["shots"][-1]
        odur = probe_duration(outro)
        seg = build_segment(len(ep["shots"]), last_shot, outro, odur + 0.5)
        timeline.append((t, t + odur, ep["outro"]))
        segments.append(seg)
        t += odur + 0.5

    # concat
    lst = BUILD / "concat.txt"
    lst.write_text("".join(f"file '{s.name}'\n" for s in segments), encoding="utf-8")
    joined = BUILD / "joined.mp4"
    _ffmpeg(["-f", "concat", "-safe", "0", "-i", "concat.txt",
             "-c", "copy", joined.name], cwd=BUILD)

    # subtitles via drawtext + textfile (robust for cyrillic)
    filters = []
    for i, (a, b, cap) in enumerate(timeline):
        txt = BUILD / f"cap_{i}.txt"
        txt.write_text(cap, encoding="utf-8")
        filters.append(
            f"drawtext=fontfile=font.ttf:textfile=cap_{i}.txt:"
            f"fontcolor=white:fontsize=52:line_spacing=8:"
            f"borderw=5:bordercolor=black@0.85:"
            f"box=0:x=(w-text_w)/2:y=h-420:"
            f"enable='between(t,{a:.2f},{b:.2f})'"
        )
    if ep.get("hook"):
        (BUILD / "hook.txt").write_text(ep["hook"], encoding="utf-8")
        filters.append(
            "drawtext=fontfile=font.ttf:textfile=hook.txt:"
            "fontcolor=0xFFE24B:fontsize=72:borderw=6:bordercolor=black@0.9:"
            "x=(w-text_w)/2:y=150:enable='lt(t,4)'"
        )
    OUT.mkdir(exist_ok=True)
    final = OUT / f"episode{ep['episode']:02d}.mp4"
    _ffmpeg([
        "-i", joined.name,
        "-vf", ",".join(filters),
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        final.name if final.parent == BUILD else str(final),
    ], cwd=BUILD)
    log(f"FINAL -> {final} ({final.stat().st_size} bytes, {t:.1f}s)")
    return final


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    ep_path = sys.argv[2] if len(sys.argv) > 2 else None
    _, ep = load_episode(ep_path)
    if cmd in ("char", "all"):
        gen_char(ep)
    if cmd in ("images", "all"):
        gen_images(ep)
    if cmd in ("clips", "all"):
        gen_clips(ep)
    if cmd in ("voice", "all"):
        gen_voice(ep)
    if cmd in ("assemble", "all"):
        assemble(ep)


if __name__ == "__main__":
    main()

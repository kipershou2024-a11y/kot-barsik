import json
import os
import subprocess
from pathlib import Path
import pipeline
import yt_upload

ROOT = Path(__file__).resolve().parent

IDEAS = [
    {
        "episode": 3,
        "title": "Барсик сдаёт на права",
        "hook": "БАРСИК СДАЁТ НА ПРАВА",
        "shots": [
            {
                "id": "ep3_s1",
                "image_source": "assets/images/char_master.png",
                "narration": "Вчера Барсик записался в автошколу. Инспектор был в шоке.",
                "caption": "Барсик в автошколе"
            },
            {
                "id": "ep3_s2",
                "image_source": "assets/images/char_master.png",
                "narration": "Сдавал площадку три раза. Сбил все конусы, но сдал теорию по мурчанию.",
                "caption": "Сбил все конусы"
            },
            {
                "id": "ep3_s3",
                "image_source": "assets/images/char_master.png",
                "narration": "Теперь у него официальные права. В графе особые отметки — любит рыбу.",
                "caption": "Официальные права"
            },
            {
                "id": "ep3_s4",
                "image_source": "assets/images/char_master.png",
                "narration": "Берегитесь дороги. Барсик за рулем и он спешит к миске.",
                "caption": "Берегитесь дороги!"
            }
        ],
        "outro": "Подпишись — завтра Барсик оформляет ипотеку."
    }
]

def main():
    out_dir = Path("out")
    out_dir.mkdir(exist_ok=True)
    ep = IDEAS[0]
    ep["format"] = {"w": 1080, "h": 1920, "fps": 30}
    ep["character"] = "Barsik"
    
    import shutil
    for shot in ep["shots"]:
        src = Path(shot["image_source"])
        dst = pipeline.IMAGES / f"{shot['id']}.png"
        shutil.copy(src, dst)
        
    print(f"Generating Episode {ep['episode']}: {ep['title']}")
    pipeline.gen_voice(ep)
    
    fmt = ep["format"]
    W, H, FPS = fmt["w"], fmt["h"], fmt["fps"]
    pipeline.BUILD.mkdir(exist_ok=True)
    
    font = pipeline.BUILD / "font.ttf"
    if not font.exists():
        for cand in [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"]:
            if Path(cand).exists():
                shutil.copy(cand, font)
                break

    segments = []
    timeline = []
    t = 0.0
    for idx, shot in enumerate(ep["shots"]):
        narr = pipeline.AUDIO / f"{shot['id']}.mp3"
        ndur = pipeline.probe_duration(narr)
        dur = max(ndur + 0.55, 0.6)
        seg = pipeline.BUILD / f"seg_ep3_{idx}.mp4"
        img = pipeline.IMAGES / f"{shot['id']}.png"
        
        frames = max(int(dur * FPS), 2)
        step = 0.17 / frames
        vf = (
            f"scale=2160:3840:force_original_aspect_ratio=increase,"
            f"crop=2160:3840,"
            f"zoompan=z='min(zoom+{step:.6f},1.17)':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={W}x{H}:fps={FPS},setsar=1,format=yuv420p"
        )
        pipeline._ffmpeg([
            "-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}",
            "-i", str(img), "-i", str(narr),
            "-filter_complex", f"[0:v]{vf}[v]",
            "-map", "[v]", "-map", "1:a", "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
            str(seg),
        ])
        segments.append(seg)
        cap = shot.get("caption") or shot.get("narration")
        timeline.append((t, t + ndur, cap))
        t += dur

    outro = pipeline.AUDIO / "outro.mp3"
    if outro.exists():
        last_shot = ep["shots"][-1]
        odur = pipeline.probe_duration(outro)
        img = pipeline.IMAGES / f"{last_shot['id']}.png"
        seg = pipeline.BUILD / "seg_ep3_outro.mp4"
        frames = max(int((odur + 0.5) * FPS), 2)
        step = 0.17 / frames
        vf = (
            f"scale=2160:3840:force_original_aspect_ratio=increase,"
            f"crop=2160:3840,"
            f"zoompan=z='min(zoom+{step:.6f},1.17)':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={W}x{H}:fps={FPS},setsar=1,format=yuv420p"
        )
        pipeline._ffmpeg([
            "-loop", "1", "-framerate", str(FPS), "-t", f"{odur + 0.5:.3f}",
            "-i", str(img), "-i", str(outro),
            "-filter_complex", f"[0:v]{vf}[v]",
            "-map", "[v]", "-map", "1:a", "-t", f"{odur + 0.5:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
            str(seg),
        ])
        timeline.append((t, t + odur, ep["outro"]))
        segments.append(seg)

    lst = pipeline.BUILD / "concat3.txt"
    lst.write_text("".join(f"file '{s.name}'\n" for s in segments), encoding="utf-8")
    joined = pipeline.BUILD / "joined3.mp4"
    pipeline._ffmpeg(["-f", "concat", "-safe", "0", "-i", "concat3.txt", "-c", "copy", joined.name], cwd=pipeline.BUILD)

    filters = []
    for i, (a, b, cap) in enumerate(timeline):
        txt = pipeline.BUILD / f"cap3_{i}.txt"
        txt.write_text(cap, encoding="utf-8")
        filters.append(
            f"drawtext=fontfile=font.ttf:textfile=cap3_{i}.txt:"
            f"fontcolor=white:fontsize=52:line_spacing=8:"
            f"borderw=5:bordercolor=black@0.85:"
            f"box=0:x=(w-text_w)/2:y=h-420:"
            f"enable='between(t,{a:.2f},{b:.2f})'"
        )
    if ep.get("hook"):
        (pipeline.BUILD / "hook3.txt").write_text(ep["hook"], encoding="utf-8")
        filters.append(
            "drawtext=fontfile=font.ttf:textfile=hook3.txt:"
            "fontcolor=0xFFE24B:fontsize=72:borderw=6:bordercolor=black@0.9:"
            "x=(w-text_w)/2:y=150:enable='lt(t,4)'"
        )
    final_mp4 = ROOT / "out" / f"episode03.mp4"
    pipeline._ffmpeg([
        "-i", joined.name,
        "-vf", ",".join(filters),
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(final_mp4),
    ], cwd=pipeline.BUILD)
    
    thumb = Path("build/auto_thumb3.jpg")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "5", "-i", str(final_mp4),
        "-frames:v", "1", "-vf", "scale=720:1280", str(thumb)
    ])
    
    if Path("yt_token.json").exists():
        title = f"{ep['title']} 🐱 #shorts #кот #мультик"
        desc = f"Новые приключения кота Барсика! Подписывайся на канал! #shorts #котбарсик #мультик #юмор #котики"
        tags = "shorts,кот барсик,мультик про кота,котики,смешной кот,юмор"
        vid = yt_upload.upload_video(str(final_mp4), title, desc, tags.split(","), 23, str(thumb), "public")
        print(f"Uploaded Episode 3 successfully: https://youtu.be/{vid}")

if __name__ == "__main__":
    main()

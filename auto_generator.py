import json
import os
from pathlib import Path
import pipeline
import yt_upload

IDEAS = [
    {
        "episode": 3,
        "title": "Барсик сдаёт на права",
        "hook": "БАРСИК СДАЁТ НА ПРАВА",
        "shots": [
            {
                "id": "s1",
                "image_prompt": "Barsik the chunky orange tabby cat wearing a tiny driver cap, sitting behind the steering wheel of a car, looking deadpan and serious at the road. Modern 2D flat cartoon illustration, bold clean outlines, vertical 9:16.",
                "video_prompt": "none",
                "narration": "Вчера Барсик записался в автошколу. Инспектор был в шоке.",
                "caption": "Барсик в автошколе"
            },
            {
                "id": "s2",
                "image_prompt": "Barsik the chunky orange tabby cat failing parallel parking, hitting three traffic cones while looking smug. Modern 2D flat cartoon illustration, bold clean outlines, vertical 9:16.",
                "video_prompt": "none",
                "narration": "Сдавал площадку три раза. Сбил все конусы, но сдал теорию по мурчанию.",
                "caption": "Сбил все конусы"
            },
            {
                "id": "s3",
                "image_prompt": "Barsik holding a driver license showing a cat paw print instead of photo, looking extremely proud in a car. Modern 2D flat cartoon illustration, bold clean outlines, vertical 9:16.",
                "video_prompt": "none",
                "narration": "Теперь у него официальные права. В графе 'особые отметки' — 'любит рыбу'.",
                "caption": "Официальные права"
            },
            {
                "id": "s4",
                "image_prompt": "Barsik driving a red sports car at high speed, wind blowing his whiskers, pedestrians running away. Modern 2D flat cartoon illustration, bold clean outlines, vertical 9:16.",
                "video_prompt": "none",
                "narration": "Берегитесь дороги. Барсик за рулем и он спешит к миске.",
                "caption": "Берегитесь дороги!"
            }
        ],
        "outro": "Подпишись — завтра Барсик оформляет ипотеку."
    },
    {
        "episode": 4,
        "title": "Барсик завёл Tinder",
        "hook": "БАРСИК В TINDER",
        "shots": [
            {
                "id": "s1",
                "image_prompt": "Barsik the chunky orange tabby cat swiping left and right on a smartphone screen showing cat profiles, looking very picky. Modern 2D flat cartoon illustration, bold clean outlines, vertical 9:16.",
                "video_prompt": "none",
                "narration": "Ночью Барсик украл телефон и завел аккаунт в Тиндере.",
                "caption": "Барсик в Тиндере"
            },
            {
                "id": "s2",
                "image_prompt": "Smartphone screen showing Barsik's bio: 'Chunky, wealthy, owns 3 boxes, looking for a rich cat with fish'. Modern 2D flat cartoon illustration, bold clean outlines, vertical 9:16.",
                "video_prompt": "none",
                "narration": "В описании указал: 'Красив, толст, владею тремя коробками, ищу спонсора с креветками'.",
                "caption": "Ищу спонсора с креветками"
            },
            {
                "id": "s3",
                "image_prompt": "Barsik's phone buzzing with thousands of match notifications, cat looking overwhelmed and smug. Modern 2D flat cartoon illustration, bold clean outlines, vertical 9:16.",
                "video_prompt": "none",
                "narration": "За пять минут — сто матчей. Соседский мейн-кун уже прислал предложение руки и сердца.",
                "caption": "100 матчей за 5 минут"
            },
            {
                "id": "s4",
                "image_prompt": "Barsik deleting the app and going back to sleep in a cardboard box, peaceful expression. Modern 2D flat cartoon illustration, bold clean outlines, vertical 9:16.",
                "video_prompt": "none",
                "narration": "Но он удалил приложение. Слишком много сообщений, а спать хочется больше.",
                "caption": "Сон важнее любви"
            }
        ],
        "outro": "Подпишись — завтра Барсик захватывает робот-пылесос."
    }
]

def main():
    # Pick next episode based on file count or simple rotation
    out_dir = Path("out")
    out_dir.mkdir(exist_ok=True)
    existing = list(out_dir.glob("episode*.mp4"))
    idx = len(existing) % len(IDEAS)
    ep = IDEAS[idx]
    
    ep_file = Path("current_episode.json")
    ep_file.write_text(json.dumps(ep, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"Generating Episode {ep['episode']}: {ep['title']}")
    pipeline.gen_char(ep)
    pipeline.gen_images(ep)
    pipeline.gen_clips(ep)
    pipeline.gen_voice(ep)
    final_mp4 = pipeline.assemble(ep)
    
    # Thumbnail
    thumb = Path("build/auto_thumb.jpg")
    import subprocess
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "5", "-i", str(final_mp4),
        "-frames:v", "1", "-vf", "scale=720:1280", str(thumb)
    ])
    
    # Upload to YouTube if token exists
    if Path("yt_token.json").exists():
        title = f"{ep['title']} 🐱 #shorts #кот #мультик"
        desc = f"Новые приключения кота Барсика! Подписывайся на канал! #shorts #котбарсик #мультик #юмор #котики"
        tags = "shorts,кот барсик,мультик про кота,котики,смешной кот,юмор"
        vid = yt_upload.upload_video(str(final_mp4), title, desc, tags.split(","), 23, str(thumb), "public")
        print(f"Uploaded successfully: https://youtu.be/{vid}")
    else:
        print("yt_token.json not found, skipping upload (local dry run).")

if __name__ == "__main__":
    main()

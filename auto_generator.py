#!/usr/bin/env python
"""Auto-pilot: pick the next Barsik episode, generate it in the Ep1/2 cartoon
style (free CPU diffusion + Fish voice + ffmpeg), and upload to YouTube.

Env:
  FISH_API_KEY   required for voice
  IMAGE_BACKEND  'local' (default here) | 'pollinations' | 'hf'
  DRY_RUN=1      only write the episode JSON, skip images/voice/upload
"""
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

import pipeline
import yt_upload

ROOT = Path(__file__).resolve().parent

CHARACTER = ("Barsik, a chunky orange tabby cat with a white muzzle, white chest "
             "and white front paws, big round amber eyes, a small notch in his "
             "left ear, permanently grumpy deadpan expression")
STYLE = ("Modern 2D flat cartoon illustration, bold clean black outlines, "
         "flat vibrant colors, vertical 9:16 composition")

# Compact episode queue. image_prompt is built automatically from `scene`.
EPISODES = [
    {
        "episode": 4,
        "title": "Барсик открыл свой бизнес",
        "hook": "БАРСИК ОТКРЫЛ СВОЙ БИЗНЕС",
        "outro": "Подпишись — узнаешь, куда Барсик вложил прибыль.",
        "shots": [
            {"scene": "sitting behind a cardboard box desk like a shop owner, a handmade sign reading FISH, proud deadpan face",
             "narration": "Барсик решил, что работать на меня — невыгодно. И открыл свой бизнес. Магазин рыбы.",
             "caption": "Свой бизнес"},
            {"scene": "standing proudly next to a small pile of stuffed toy fish and a cardboard cash register",
             "narration": "Товар он позаимствовал из моего холодильника. Назвал это стартовым капиталом.",
             "caption": "Стартовый капитал"},
            {"scene": "a cartoon mouse customer at the counter paying with a shiny coin, Barsik taking the coin with one paw",
             "narration": "Первый клиент пришёл через час. Соседский мышонок. Купил рыбу за монетку.",
             "caption": "Первый клиент"},
            {"scene": "surrounded by many cartoon mouse customers, looking overwhelmed and annoyed, scattered fish toys",
             "narration": "К вечеру очередь была до кухни. Барсик устал и поднял цены в два раза.",
             "caption": "Очередь до кухни"},
            {"scene": "relaxing on a soft cushion on top of a pile of shiny coins, sunglasses on, smug",
             "narration": "Теперь он бизнесмен. Отдыхает на подушке из монет и не здоровается со мной.",
             "caption": "Бизнесмен"},
            {"scene": "looking smug and unrepentant, holding a single shiny coin up, dramatic spotlight",
             "narration": "И ни о чём не жалеет. Прибыль, говорит, вложил. Только в рыбу. В себя.",
             "caption": "Ни о чём не жалеет"}
        ]
    },
    {
        "episode": 5,
        "title": "Барсик сел на диету",
        "hook": "БАРСИК СЕЛ НА ДИЕТУ",
        "outro": "Подпишись — узнаешь, кто съел диетический корм.",
        "shots": [
            {"scene": "staring in horror at a tiny bowl with a single green leaf in it, deadpan offended face",
             "narration": "Ветеринар сказал Барсику похудеть. Барсик сказал, что подумает. Два дня.",
             "caption": "Надо похудеть"},
            {"scene": "pushing a full plate of sausages off a table with one paw while looking innocent",
             "narration": "Начал он с лёгкого. Убрал из рациона всё вкусное. То есть мою еду со стола.",
             "caption": "Убрал вкусное"},
            {"scene": "doing cat yoga stretching poses on a rug, a fitness chart on the wall, determined grumpy face",
             "narration": "Потом записался на фитнес. Каждое утро потягушки и бег за лазерной точкой.",
             "caption": "Записался на фитнес"},
            {"scene": "standing on a bathroom scale looking shocked and outraged, tail puffed up",
             "narration": "Через неделю он встал на весы. И обвинил в результате весы. И меня. И кота с пятого этажа.",
             "caption": "Весы врут"},
            {"scene": "secretly eating a sausage under a table at night, guilty wide eyes, dark room",
             "narration": "А ночью я поймал его возле холодильника. С сосиской. Двенадцатой за вечер.",
             "caption": "Пойман с сосиской"},
            {"scene": "satisfied, licking lips, sitting on the scale which still shows the same number, smug",
             "narration": "Диета, в общем, не задалась. Но он ни о чём не жалеет. И не собирается.",
             "caption": "Ни о чём не жалеет"}
        ]
    },
    {
        "episode": 6,
        "title": "Барсик и мой телефон",
        "hook": "ЧТО БАРСИК ЗАКАЗАЛ С МОЕГО ТЕЛЕФОНА",
        "outro": "Подпишись — узнаешь, кому Барсик написал сообщение.",
        "shots": [
            {"scene": "sitting on a phone lying on the floor, both front paws tapping the screen, focused devious face",
             "narration": "Однажды я оставил телефон на диване. На пять минут. Барсик успел многое.",
             "caption": "Телефон на диване"},
            {"scene": "a cartoon online shop screen filled with fish, toys and cat beds, Barsik drooling slightly",
             "narration": "Он открыл магазин зоотоваров и набрал корзину на девять тысяч. Из чистого любопытства.",
             "caption": "Корзина на 9 000"},
            {"scene": "holding the phone with a paw, typing a message, sly grin, chat bubbles floating",
             "narration": "Потом написал моей маме. Что я, цитата, очень скучаю и хочу приехать на выходные.",
             "caption": "Сообщение маме"},
            {"scene": "sitting smug next to a phone showing a big map with a route, tiny suitcase beside him",
             "narration": "Мама приехала на выходные в тот же вечер. С чемоданом и с подарками. Для него.",
             "caption": "Мама приехала"},
            {"scene": "cutting a phone screen with a claw while a confused cartoon delivery courier cat stands at the door holding boxes",
             "narration": "А ещё заказ на девять тысяч привезли. Пять коробок. Курьер тоже был кот. У них получилась дружба.",
             "caption": "Курьер тоже кот"},
            {"scene": "lying on a mountain of new toys and boxes, smirking, one paw on the phone, dramatic light",
             "narration": "И он ни о чём не жалеет. Теперь телефон я прячу. Под подушкой. Он и там находит.",
             "caption": "Ни о чём не жалеет"}
        ]
    }
]


def build_episode(spec):
    ep = {
        "series": "Кот Барсик",
        "episode": spec["episode"],
        "title": spec["title"],
        "format": {"w": 1080, "h": 1920, "fps": 30},
        "hook": spec["hook"],
        "character": CHARACTER,
        "character_prompt": f"Full-body 2D cartoon character sheet of {CHARACTER}. "
                            f"Modern flat cartoon illustration, bold clean black outlines, "
                            f"flat vibrant colors, plain light mint background, vertical 9:16 composition.",
        "image_style": STYLE,
        "shots": [
            {
                "id": f"e{spec['episode']}s{i + 1}",
                "image_prompt": f"{CHARACTER}, {s['scene']}. {STYLE}",
                "narration": s["narration"],
                "caption": s["caption"],
            }
            for i, s in enumerate(spec["shots"])
        ],
        "outro": spec["outro"],
    }
    return ep


def pick_episode():
    now = datetime.datetime.utcnow()
    slot = 0 if now.hour < 14 else 1
    idx = (now.toordinal() * 2 + slot) % len(EPISODES)
    return EPISODES[idx]


def main():
    spec = pick_episode()
    ep = build_episode(spec)
    ep_path = ROOT / "episode_auto.json"
    ep_path.write_text(json.dumps(ep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[auto] selected episode {ep['episode']}: {ep['title']}")

    if os.environ.get("DRY_RUN"):
        print("[auto] DRY_RUN -> wrote", ep_path.name, "and stopping")
        return

    pipeline.gen_images(ep)
    pipeline.gen_voice(ep)
    final = pipeline.assemble(ep)

    thumb = pipeline.BUILD / "auto_thumb.jpg"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "5",
        "-i", str(final), "-frames:v", "1", "-vf", "scale=720:1280", str(thumb)
    ])

    if (ROOT / "yt_token.json").exists():
        title = f"{ep['title']} 🐱 #shorts #кот #мультик"
        desc = ("Новые приключения кота Барсика! Подписывайся. "
                "#shorts #котбарсик #мультик #юмор #котики")
        tags = "shorts,кот барсик,мультик про кота,котики,смешной кот,юмор".split(",")
        vid = yt_upload.upload_video(str(final), title, desc, tags, 23, str(thumb), "public")
        print(f"[auto] uploaded -> https://youtu.be/{vid}")

    return ep


if __name__ == "__main__":
    main()

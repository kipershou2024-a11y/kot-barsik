#!/usr/bin/env python
"""Batch-prepare Barsik episodes and upload one per day.

Commands:
  make <N>     generate episode N -> queue/EPNN.mp4 (+ EPNN.json metadata)
  batch        generate every episode in EPISODES that is not queued yet
  upload       upload the next queued episode (lowest number) and dequeue it
  (no args)    same as upload   (used by the daily GitHub Action)

Env:
  FISH_API_KEY   required for make/batch
  IMAGE_BACKEND  'local' (default here) | 'pollinations' | 'hf'
  DRY_RUN=1      show what would happen without generating/uploading
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pipeline
import yt_upload

ROOT = Path(__file__).resolve().parent
QUEUE = ROOT / "queue"

CHARACTER = ("Barsik, a chunky orange tabby cat with a white muzzle, white chest "
             "and white front paws, big round amber eyes, a small notch in his "
             "left ear, permanently grumpy deadpan expression")
STYLE = ("Modern 2D flat cartoon illustration, bold clean black outlines, "
         "flat vibrant colors, vertical 9:16 composition")

TAGS = "shorts,кот барсик,мультик про кота,котики,смешной кот,юмор,кот"

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
        "episode": 7,
        "title": "Барсик пошёл в спортзал",
        "hook": "БАРСИК ЗАПИСАЛСЯ В КАЧАЛКУ",
        "outro": "Подпишись — узнаешь, сколько Барсик поднял на самом деле.",
        "shots": [
            {"scene": "standing in front of a gym entrance sign with a tiny gym bag, determined grumpy face",
             "narration": "Барсик решил, что пора стать сильным. И записался в качалку. Вместе со мной.",
             "caption": "В качалку"},
            {"scene": "wearing a tiny cartoon tank top, lifting a small pink dumbbell with both paws, straining",
             "narration": "Первый подход. Гантель два килограмма. Барсик держал её минуту и очень собой гордился.",
             "caption": "Гантель 2 кг"},
            {"scene": "running on a treadmill with tongue out, funny tired face",
             "narration": "Потом беговая дорожка. Барсик бежал тридцать секунд и объявил перерыв на обед. На два часа.",
             "caption": "Беговая дорожка"},
            {"scene": "sitting on a bench staring at a muscular cartoon cat flexing nearby, unimpressed",
             "narration": "Рядом качался здоровый кот. Барсик сказал, что мышцы — не главное. Главное — харизма.",
             "caption": "Мышцы не главное"},
            {"scene": "sleeping on a yoga mat in the middle of the gym, other cats stepping around him",
             "narration": "Тренировку Барсик закончил сном на коврике. Все ходили вокруг него на цыпочках.",
             "caption": "Сон на коврике"},
            {"scene": "smug, holding a protein shake, one arm raised like a winner",
             "narration": "И ни о чём не жалеет. Говорит, качалка — это его. Особенно диван рядом с ней.",
             "caption": "Ни о чём не жалеет"}
        ]
    },
    {
        "episode": 8,
        "title": "Барсик приготовил ужин",
        "hook": "БАРСИК ПРИГОТОВИЛ МНЕ УЖИН",
        "outro": "Подпишись — узнаешь, что Барсик варил на самом деле.",
        "shots": [
            {"scene": "standing on a kitchen table wearing a small chef hat and apron, proud deadpan face",
             "narration": "Однажды Барсик решил, что я плохо питаюсь. И взял готовку на себя.",
             "caption": "Повар Барсик"},
            {"scene": "a huge mess in the kitchen, flour everywhere, Barsik in the middle holding a whisk",
             "narration": "Начал он с муки. Половина муки оказалась на Барсике. Половина — на кухне.",
             "caption": "Полкухни в муке"},
            {"scene": "stirring a smoking pot with a wooden spoon, alarmed surprised face",
             "narration": "Потом что-то варил. Что именно — не признался. Но запах был очень смелый.",
             "caption": "Смелый запах"},
            {"scene": "a plate with a single burnt sausage cut into fancy shapes, garnished with one leaf",
             "narration": "В итоге на тарелке оказалась одна подгоревшая сосиска. Нарезанная красиво. С листиком.",
             "caption": "Сосиска с листиком"},
            {"scene": "sitting next to a human at the table watching him eat, expectant proud face",
             "narration": "Он сел напротив и смотрел, как я это ем. Отказаться было страшно.",
             "caption": "Смотрит, как я ем"},
            {"scene": "eating a big piece of fish contentedly while a human holds an empty plate, smug",
             "narration": "И ни о чём не жалуется. Правда, сам он ужинал рыбой. Из моего холодильника. Опять.",
             "caption": "Ни о чём не жалеет"}
        ]
    },
    {
        "episode": 9,
        "title": "Барсик привёл друга",
        "hook": "БАРСИК ПРИВЁЛ ДОМОЙ ДРУГА",
        "outro": "Подпишись — узнаешь, вернётся ли серый друг.",
        "shots": [
            {"scene": "standing at a front door with a scruffy grey cartoon stray cat beside him, both flat expressions",
             "narration": "Барсик как-то пришёл домой не один. С другом. Друг был серый, лохматый и очень довольный.",
             "caption": "Привёл друга"},
            {"scene": "two cats sitting on a sofa side by side staring at a human, a snack bowl between them",
             "narration": "Он сказал, что это его новый лучший друг. И что теперь они всё делают вместе. Включая мою еду.",
             "caption": "Лучший друг"},
            {"scene": "Barsik looking jealous while the grey cat gets petted by a human hand",
             "narration": "Но через час все поглаживания достались другу. И Барсик начал ревновать. Тихо. И опасно.",
             "caption": "Ревность"},
            {"scene": "two cats sitting with backs turned to each other, pouting, arms crossed",
             "narration": "К вечеру они поссорились. Из-за места на диване. И из-за моей коленки.",
             "caption": "Поссорились"},
            {"scene": "night, the grey cat quietly leaving through a window, Barsik watching smug from the doorway",
             "narration": "Друг обиделся и ушёл в окно. Барсик помахал ему лапкой. Довольный.",
             "caption": "Ушёл в окно"},
            {"scene": "Barsik alone, stretched out across the whole sofa, smug",
             "narration": "И ни о чём не жалеет. Диван снова только его. Дружба, говорит, это такое.",
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


def _spec(n):
    for s in EPISODES:
        if s["episode"] == n:
            return s
    raise SystemExit(f"no episode {n} defined (have {[s['episode'] for s in EPISODES]})")


def _desc(ep):
    return (f"Новые приключения кота Барсика: {ep['title']}! "
            f"Подписывайся, дальше ещё смешнее.\n\n#shorts #котбарсик #мультик #юмор #котики")


def make_one(n):
    ep = build_episode(_spec(n))
    QUEUE.mkdir(exist_ok=True)
    mp4 = QUEUE / f"EP{n:02d}.mp4"
    meta = QUEUE / f"EP{n:02d}.json"
    if mp4.exists():
        print(f"[auto] EP{n:02d} already queued, skip")
        return mp4
    if os.environ.get("DRY_RUN"):
        print(f"[auto] DRY_RUN: would generate EP{n:02d} {ep['title']}")
        return mp4
    print(f"[auto] generating EP{n:02d} '{ep['title']}' ...", flush=True)
    pipeline.gen_images(ep)
    pipeline.gen_voice(ep)
    final = pipeline.assemble(ep)
    shutil.copy(final, mp4)
    meta.write_text(json.dumps({
        "episode": n, "title": ep["title"], "desc": _desc(ep),
        "tags": TAGS.split(","), "hook": ep["hook"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[auto] queued -> {mp4.name} ({mp4.stat().st_size} bytes)")
    return mp4


def cmd_batch():
    for spec in EPISODES:
        make_one(spec["episode"])


def _thumb_from(mp4):
    pipeline.BUILD.mkdir(exist_ok=True)
    thumb = pipeline.BUILD / "auto_thumb.jpg"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "5",
        "-i", str(mp4), "-frames:v", "1", "-vf", "scale=720:1280", str(thumb)
    ])
    return thumb if thumb.exists() else None


def cmd_upload():
    QUEUE.mkdir(exist_ok=True)
    files = sorted(QUEUE.glob("EP*.mp4"))
    if not files:
        print("[auto] queue empty - nothing to upload")
        return None
    mp4 = files[0]
    meta_path = mp4.with_suffix(".json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    ep_n = meta.get("episode")
    title = meta.get("title") or mp4.stem
    title = f"{title} 🐱 #shorts #кот #мультик"
    desc = meta.get("desc") or _desc({"title": title})
    tags = meta.get("tags") or TAGS.split(",")

    if os.environ.get("DRY_RUN"):
        print(f"[auto] DRY_RUN: would upload {mp4.name} as '{title}'")
        return None

    thumb = _thumb_from(mp4)
    if not (ROOT / "yt_token.json").exists():
        raise SystemExit("yt_token.json missing (restore from secret)")
    vid = yt_upload.upload_video(str(mp4), title, desc, tags, 23,
                                 str(thumb) if thumb else None, "public")
    print(f"[auto] uploaded EP{ep_n} -> https://youtu.be/{vid}")
    mp4.unlink()
    if meta_path.exists():
        meta_path.unlink()
    print(f"[auto] dequeued {mp4.name}; {len(sorted(QUEUE.glob('EP*.mp4')))} left")
    return vid


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "upload"
    if cmd == "make":
        if len(sys.argv) < 3:
            raise SystemExit("usage: auto_generator.py make <episodeNumber>")
        make_one(int(sys.argv[2]))
    elif cmd == "batch":
        cmd_batch()
    elif cmd == "upload":
        cmd_upload()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()

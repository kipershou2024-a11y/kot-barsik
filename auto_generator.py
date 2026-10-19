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
UPLOADED_PATH = QUEUE / "uploaded.json"

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
    },
    {
        "episode": 10,
        "title": "Барсик против пылесоса",
        "hook": "БАРСИК ПРОТИВ ПЫЛЕСОСА",
        "outro": "Подпишись — узнаешь, кто победил в финале.",
        "shots": [
            {"scene": "standing frozen with wide eyes and fur on end, staring at a cartoon vacuum cleaner",
             "narration": "У Барсика есть один заклятый враг. Не собака. Не вода. Пылесос.",
             "caption": "Заклятый враг"},
            {"scene": "hiding behind a sofa peeking nervously at a vacuum cleaner",
             "narration": "Каждую уборку он прячется. Как будто пылесос пришёл именно за ним.",
             "caption": "Прячется"},
            {"scene": "perched crammed on top of the very highest wardrobe shelf, scared",
             "narration": "Однажды он забрался на самый верх шкафа. А пылесос остался внизу. Гудеть.",
             "caption": "На верх шкафа"},
            {"scene": "hissing at the vacuum cleaner from a safe distance, back arched",
             "narration": "Потом решил атаковать. Шипел. На расстоянии. Три метра.",
             "caption": "Шипит издалека"},
            {"scene": "riding on top of the vacuum cleaner while a human pushes it, surprised delighted face",
             "narration": "А потом... поехал на нём. И знаете что? Ему понравилось.",
             "caption": "А потом поехал"},
            {"scene": "sitting proudly on the parked vacuum cleaner, smug",
             "narration": "И ни о чём не жалеет. Теперь просит катать его каждый день. Вместо уборки.",
             "caption": "Ни о чём не жалеет"}
        ]
    },
    {
        "episode": 11,
        "title": "Барсик будит меня в 4 утра",
        "hook": "БАРСИК БУДИТ МЕНЯ В 4 УТРА",
        "outro": "Подпишись — узнаешь, во сколько Барсик ложится спать.",
        "shots": [
            {"scene": "sitting on a sleeping human's chest at night, staring, a wall clock shows four o'clock",
             "narration": "У Барсика есть будильник. Это его лапы. И моя грудная клетка. В четыре утра.",
             "caption": "4 утра"},
            {"scene": "meowing loudly right next to a sleeping person in the dark, mouth wide open",
             "narration": "Сначала он мяукает. Один раз. Потом второй. Потом так, будто его режут. Спойлер: не режут.",
             "caption": "Мяу"},
            {"scene": "casually knocking a glass off a nightstand in the dark, dramatic",
             "narration": "Если не встаю, он роняет со стола что-нибудь. Что-нибудь. Что подороже.",
             "caption": "Роняет со стола"},
            {"scene": "sitting innocently on the kitchen floor next to a completely full food bowl",
             "narration": "Я встаю. Включаю свет. И что я вижу? Полную миску еды. Полную.",
             "caption": "Миска полная"},
            {"scene": "eating calmly at night while a tired human stands nearby, smug",
             "narration": "Он просто хотел компании. И чтобы я постоял рядом. Полчаса. В четыре утра.",
             "caption": "Хотел компании"},
            {"scene": "sleeping peacefully curled on a bed in bright daylight while a tired human works",
             "narration": "Днём он спит. Я — на работе. И ни о чём не жалеет.",
             "caption": "Ни о чём не жалеет"}
        ]
    },
    {
        "episode": 12,
        "title": "Барсик и коробка",
        "hook": "БАРСИК И КОРОБКА",
        "outro": "Подпишись — узнаешь, что будет, когда коробок станет десять.",
        "shots": [
            {"scene": "surrounded by expensive cat toys, ignoring them all, staring at an empty cardboard box",
             "narration": "Я купил Барсику кучу дорогих игрушек. Он выбрал коробку.",
             "caption": "Выбрал коробку"},
            {"scene": "squeezing into a too-small cardboard box, half hanging out, determined",
             "narration": "Коробка была явно мала. Барсика это не остановило.",
             "caption": "Коробка мала"},
            {"scene": "sitting triumphantly inside the box with only head showing, smug",
             "narration": "Он сидел в ней весь день. Как будто это был трон.",
             "caption": "Как трон"},
            {"scene": "a bigger box appears and Barsik immediately moves into it",
             "narration": "Я принёс коробку побольше. Он переехал. Мгновенно.",
             "caption": "Переехал"},
            {"scene": "several stacked boxes with Barsik sitting in the top one like a castle",
             "narration": "Так у него появился многоэтажный дом. Из коробок. С видом на кухню.",
             "caption": "Дом из коробок"},
            {"scene": "chewing the corner of a cardboard box, satisfied, sitting inside it, smug",
             "narration": "И ни о чём не жалеет. Игрушки, говорит, для слабаков. Коробка — это жизнь.",
             "caption": "Ни о чём не жалеет"}
        ]
    },
    {
        "episode": 13,
        "title": "Барсик сел за работу",
        "hook": "БАРСИК СЕЛ ЗА РАБОТУ",
        "outro": "Подпишись — узнаешь, какую должность Барсик себе придумал.",
        "shots": [
            {"scene": "sitting on a desk chair in front of a laptop, serious face, tiny glasses",
             "narration": "Барсик решил, что мне нужна помощь. На удалёнке. И сел за мой ноутбук.",
             "caption": "Сел за работу"},
            {"scene": "walking across a keyboard while random letters appear on the screen",
             "narration": "Сначала он прошёлся по клавиатуре. Получилось сообщение. Начальнику. Из двадцати символов.",
             "caption": "Прошёлся по клавиатуре"},
            {"scene": "staring intensely at a screen full of graphs, one paw on the computer mouse",
             "narration": "Потом посмотрел на графики. Сказал, что тут всё неправильно. И я почти согласен.",
             "caption": "Графики неправильные"},
            {"scene": "lying on top of a warm laptop blocking the screen, sleepy",
             "narration": "К обеду он улёгся прямо на ноутбук. Ноутбук тёплый. Это главное.",
             "caption": "Лёг на ноутбук"},
            {"scene": "a video meeting on screen with many confused cat faces, Barsik's tail in the camera",
             "narration": "Во время созвона в кадре появился его хвост. Встреча была посвящена коту. Не работе.",
             "caption": "Хвост в кадре"},
            {"scene": "sitting on the closed laptop with a coffee mug beside, smug",
             "narration": "И ни о чём не жалеет. Теперь он мой начальник. И требует рыбу как зарплату.",
             "caption": "Ни о чём не жалеет"}
        ]
    },
    {
        "episode": 14,
        "title": "Барсик не любит купаться",
        "hook": "БАРСИК НЕ ЛЮБИТ КУПАТЬСЯ",
        "outro": "Подпишись — узнаешь, во что Барсик верит после купания.",
        "shots": [
            {"scene": "standing at the sight of a bathtub full of water, horrified wide eyes",
             "narration": "Есть три вещи, которых Барсик боится. Пылесос. Понедельник. И вода.",
             "caption": "Боится воды"},
            {"scene": "hiding under a bed in the dark with only glowing eyes visible, a bathtub in the background",
             "narration": "Узнав о купании, он спрятался под кроватью. На три часа.",
             "caption": "Под кроватью"},
            {"scene": "held by a human over the bathtub with all legs spread out like a starfish, distressed",
             "narration": "Когда его всё-таки поймали, он раздвинул лапы. Как морская звезда. Чтобы не влез.",
             "caption": "Как морская звезда"},
            {"scene": "in the water with a betrayed face and wet fur",
             "narration": "В воде он сделал вид, что это конец. Прощание было долгим. Купание длилось пять минут.",
             "caption": "Всё кончено"},
            {"scene": "wrapped in a towel, grumpy, drying off",
             "narration": "Потом он сох. Два часа. В моей любимой простыне. С видом победителя.",
             "caption": "Сох в простыне"},
            {"scene": "freshly clean and fluffy, ignoring a human, smug on a couch",
             "narration": "И ни о чём не жалеет. Чистый кот. И мокрый диван. Но он доволен.",
             "caption": "Ни о чём не жалеет"}
        ]
    },
    {
        "episode": 15,
        "title": "Барсик против дождя",
        "hook": "БАРСИК НЕ ВЫХОДИТ НА УЛИЦУ",
        "outro": "Подпишись — узнаешь, как Барсик выгулял дождь.",
        "shots": [
            {"scene": "standing at an open front door looking at heavy rain outside, stepping back",
             "narration": "Утром я вывел Барсика на прогулку. Дождь. Он всё понял уже на пороге.",
             "caption": "Дождь?"},
            {"scene": "sitting firmly in the middle of a doorway refusing to move, a leash offered, arms crossed",
             "narration": "Он сел посреди двери и остановился. Методом отказа. На час.",
             "caption": "Отказался"},
            {"scene": "peering out of a foggy window at puddles, sad bored face",
             "narration": "В итоге гулял у окна. Смотрел на лужи. Как на телевизор.",
             "caption": "Смотрит на лужи"},
            {"scene": "holding his own tiny umbrella while a human holds a big one, offended face",
             "narration": "Я принёс зонт. Барсик обиделся. Свой зонт он принёл сам.",
             "caption": "Свой зонт"},
            {"scene": "outside in the rain, only paws wet, ears flattened, hating it",
             "narration": "На улице он продержался три минуты. И за них успел мокнуть, испачкаться и оценить погоду.",
             "caption": "Три минуты"},
            {"scene": "sleeping on a warm radiator at home, dry and smug",
             "narration": "Дома он высох на батарее. И ни о чём не жалеет. Прогулки, говорит, это для дождя.",
             "caption": "Ни о чём не жалеет"}
        ]
    },
    {
        "episode": 16,
        "title": "Барсик принимает гостей",
        "hook": "КАК БАРСИК ПРИНИМАЕТ ГОСТЕЙ",
        "outro": "Подпишись — узнаешь, кто остаётся ночевать у Барсика.",
        "shots": [
            {"scene": "at the front door greeting two cartoon cat guests with a very serious face",
             "narration": "К нам пришли гости. Барсик встретил их у двери. Как администратор.",
             "caption": "Встретил гостей"},
            {"scene": "leading the guests into the living room, paw extended showing them seats",
             "narration": "Провёл в гостиную. Показал кресла. Приготовил для каждого — и исчез на час.",
             "caption": "Провёл в гостиную"},
            {"scene": "a table full of food bowls for the guests, Barsik proudly looking at the spread",
             "narration": "Накрыл стол. То есть вынес всю мою еду. Удивительно много еды было.",
             "caption": "Накрыл стол"},
            {"scene": "sitting on the lap of a human guest being fed, while the host human watches annoyed",
             "narration": "Сел на колени к моему другу. Выбрал его из всех. Теперь друг — его лучший друг.",
             "caption": "Выбрал друга"},
            {"scene": "showing a guest the view from the window, paw pointing outside",
             "narration": "Потом показал вид из окна. Каждому. По очереди. По часу.",
             "caption": "Вид из окна"},
            {"scene": "alone and content after the guests left, smug on the sofa",
             "narration": "Гости ушли. Барсик доволен. Устроил приём, дождался комплиментов и спит.",
             "caption": "Ни о чём не жалеет"}
        ]
    },
    {
        "episode": 17,
        "title": "Барсик идёт к ветеринару",
        "hook": "БАРСИК ИДЁТ К ВЕТЕРИНАРУ",
        "outro": "Подпишись — узнаешь, какой диагноз поставил врач.",
        "shots": [
            {"scene": "sitting calmly inside a cat carrier at home, a human carrying it, serious face",
             "narration": "Первый признак: Барсик понял, куда мы едем. Второй: он успокоился. Это тревожнее всего.",
             "caption": "Он всё понял"},
            {"scene": "inside a carrier in a car looking out the window, stone-cold expression",
             "narration": "В машине он молчал. Молчал настырно. Как подозреваемый в машине.",
             "caption": "Молчал"},
            {"scene": "at the vet clinic sitting in a corner trying to be invisible, other animals around",
             "narration": "В клинике понюхал всё. Потом сел в углу и стал невидимым.",
             "caption": "Стал невидимым"},
            {"scene": "on the vet's table being weighed, shocked outraged face, a scale display",
             "narration": "Весы показали на два килограмма больше. Барсик потребовал повторного взвешивания.",
             "caption": "Весы врут"},
            {"scene": "a cartoon vet with a stethoscope while Barsik lies still and calm",
             "narration": "Врач сказал: здоров, просто толстый. Барсик оценил комплимент и уснул ему на столе.",
             "caption": "Здоров, просто толстый"},
            {"scene": "back home sleeping in a cardboard box, ignoring a human",
             "narration": "Дома он отменил поездки навсегда. И ни о чём не жалеет. Врач, говорит, доволен.",
             "caption": "Ни о чём не жалеет"}
        ]
    },
    {
        "episode": 18,
        "title": "Барсик и птица у окна",
        "hook": "БАРСИК И ПТИЦА У ОКНА",
        "outro": "Подпишись — узнаешь, вернулась ли птица.",
        "shots": [
            {"scene": "sitting right at a window staring outside with an intense deadpan face",
             "narration": "У нас есть птица. Стая птиц. И зритель — Барсик. Кресло у окна больше его не волнует.",
             "caption": "Главная птица"},
            {"scene": "paw pressed against the glass trying to touch a bird outside",
             "narration": "Птица за стеклом. Он за стеклом. Они почти договорились.",
             "caption": "Через стекло"},
            {"scene": "knocked over a flower pot in excitement by the window, dirt everywhere",
             "narration": "Он так радовался, что снёс цветок. Цветок стоял на подоконнике много лет.",
             "caption": "Снёс цветок"},
            {"scene": "waiting patiently by the closed window, a wall clock shows hours passed",
             "narration": "Вечером он всё ещё ждал. Четыре часа. Птица не вернулась. Он — да.",
             "caption": "Ждёт четвёртый час"},
            {"scene": "looking up at a distant bird high in the sky through the window, serious",
             "narration": "Потом увидел её в небе. Завиделся. Даже не мурлыкнул — слишком серьёзно.",
             "caption": "Завиделся"},
            {"scene": "sleeping in front of the window, tired but satisfied",
             "narration": "И ни о чём не жалеет. Серьёзная работа. Надо ведь за кем-то наблюдать.",
             "caption": "Ни о чём не жалеет"}
        ]
    },
    {
        "episode": 19,
        "title": "Барсик увидел себя в зеркале",
        "hook": "БАРСИК УВИДЕЛ ДРУГОГО КОТА",
        "outro": "Подпишись — узнаешь, кто победил в финале.",
        "shots": [
            {"scene": "standing in front of a mirror staring at his own reflection, shocked face",
             "narration": "Однажды Барсик увидел в зеркале другого кота. Этот кот оказался им самим. Он не поверил.",
             "caption": "Другой кот"},
            {"scene": "hissing at his own reflection in the mirror, back arched",
             "narration": "Сначала он зашипел на него. Потом попытался напугать. Потом немного попал в зеркало носом.",
             "caption": "Ушипел"},
            {"scene": "walking around behind a mirror searching for the cat, confused",
             "narration": "Он обошёл зеркало сзади. Кота там не было. Кот остался спереди. Это его смутило.",
             "caption": "Обошёл сзади"},
            {"scene": "trying to play with his own reflected paw touching the mirror",
             "narration": "Потом предложил играть. Лапой. Лапа согласилась. Сет согласился.",
             "caption": "Предложил играть"},
            {"scene": "pressing his face against the mirror, nose to nose with his own reflection",
             "narration": "И вот они нос к носу. Долго. Один и тот же. Зеркало такого не ожидало.",
             "caption": "Нос к носу"},
            {"scene": "sitting with his back turned to the mirror, smug, ignoring the reflection",
             "narration": "И ни о чём не жалеет. Врагу больше не верит. Игнорирует его. На всю жизнь.",
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


def _uploaded():
    if UPLOADED_PATH.exists():
        try:
            return set(json.loads(UPLOADED_PATH.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def _mark_uploaded(n):
    done = _uploaded()
    done.add(int(n))
    UPLOADED_PATH.parent.mkdir(exist_ok=True)
    UPLOADED_PATH.write_text(json.dumps(sorted(done), indent=2), encoding="utf-8")


def make_one(n):
    ep = build_episode(_spec(n))
    QUEUE.mkdir(exist_ok=True)
    mp4 = QUEUE / f"EP{n:02d}.mp4"
    meta = QUEUE / f"EP{n:02d}.json"
    if n in _uploaded():
        print(f"[auto] EP{n:02d} already uploaded, skip")
        return mp4
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
    if ep_n:
        _mark_uploaded(ep_n)
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

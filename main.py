import os
import asyncio
import openai
import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.filters import CommandStart
from dotenv import load_dotenv
from aiogram import Router
import aiohttp
import xml.etree.ElementTree as ET
from deep_translator import GoogleTranslator

from states import Survey
from db import db

load_dotenv()

TOKEN = os.getenv("TOKEN")
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
OPEN_AI_CHAT_KEY = os.getenv("OPEN_AI_CHAT_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

user_surveys = {}

questions = [
    "Как вас зовут?",
    "Сколько вам лет?",
    "Какой ваш любимый школьный предмет?",
    "Какой ваш любимый цвет?",
    "Какой ваш любимый фильм?",
    "Какое ваше хобби?",
    "Какое ваше любимое животное?",
]

async def survey_text_handler(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Сколько вам лет")
    await state.set_state(Survey.age)


async def survey_age_handler(message: Message, state: FSMContext):
    await state.update_data(age=message.text)
    await message.answer("Какое ваше хобби?")
    await state.set_state(Survey.hobby)


async def survey_hobby_handler(message: Message, state: FSMContext):
    user_id = await db.check_user(message.chat.id)
    data = await state.get_data()
    name = data.get("name")
    age = data.get("age")
    hobby = message.text
    await message.answer(
        f"CONGRATS {name}!\n You are {age} years old!\n Your hobby is {hobby}"
    )
    await db.add_survey_results(user_id['id'], name, age, hobby)
    await state.clear()

async def main_survey_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == Survey.name:
        await survey_text_handler(message, state)
    elif current_state == Survey.age:
        await survey_age_handler(message, state)
    elif current_state == Survey.hobby:
        await survey_hobby_handler(message, state)


#Список фильмов

movies = """1. Инцепшн (2010)

2. Форрест Гамп (1994)

3. Тёмный рыцарь (2008)

4. Форрест Гамп (1994)

5. Список Шиндлера (1993)

6. Властелин колец: Братство кольца (2001)

7. Начало (2010)

8. Матрица (1999)

9. Титаник (1997)

10. Гладиатор (2000)
... [остальной список фильмов] ..."""

async def create_pool():
    return await asyncpg.create_pool(
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT')
    )

#Погода

async def get_weather():
    url = f"https://api.openweathermap.org/data/2.5/weather?q=Бишкек&appid={WEATHER_API_KEY}&units=metric"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                type_ = data["weather"][0]["main"]
                temp_c = data["main"]["temp"]
                feels_like = data["main"]["feels_like"]
                city = data["name"]
                return f"Погода в городе {city}: {type_}\nТемпература: {temp_c}°C\nЧувствуется как: {feels_like}°C"
            else:
                return "Произошла ошибка при получении данных о погоде"

#Курс валют

async def get_currency_rates():
    url = "https://www.nbkr.kg/XML/daily.xml"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                xml_data = await response.text()
                root = ET.fromstring(xml_data)
                rates = {}
                for currency in root.findall('Currency'):
                    iso_code = currency.get('ISOCode')
                    value_element = currency.find('Value')
                    if iso_code and value_element is not None:
                        rate = value_element.text
                        rates[iso_code] = rate

                usd = rates.get("USD", "Нет данных")
                eur = rates.get("EUR", "Нет данных")
                rub = rates.get("RUB", "Нет данных")
                kzt = rates.get("KZT", "Нет данных")
                cny = rates.get("CNY", "Нет данных")

                return (f"💰 Официальные курсы валют в Кыргызстане:\n"
                        f"🇺🇸 USD: {usd} KGS\n"
                        f"🇪🇺 EUR: {eur} KGS\n"
                        f"🇷🇺 RUB: {rub} KGS\n"
                        f"🇰🇿 KZT: {kzt} KGS\n"
                        f"🇨🇳 CNY: {cny} KGS")
            else:
                return f"Ошибка при запросе данных: {response.status}"

#Шутка

async def get_joke():
    url = "https://v2.jokeapi.dev/joke/Any"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                if data["type"] == "single":
                    joke = data["joke"]
                else:
                    joke = f"{data['setup']}\n{data['delivery']}"
                translated_joke = GoogleTranslator(source="auto", target="ru").translate(joke)
                return translated_joke
            else:
                return "Ошибка при получении шутки 😢"


#Клавиатуры

reply_menu = types.ReplyKeyboardMarkup(
    keyboard=[
        [
            types.KeyboardButton(text='💡 Картинка'),
            types.KeyboardButton(text='🏞 Погода'),
        ],
        [
            types.KeyboardButton(text='💡 Курс валют'),
            types.KeyboardButton(text='🏞 Список фильмов'),
        ],
        [
            types.KeyboardButton(text='💡 Шутка'),
            types.KeyboardButton(text='🏞 Пройти опрос'),
        ],
        [
            types.KeyboardButton(text='💡 Чат с ИИ')
        ]
    ],
    resize_keyboard=True,
)

inline_image = types.InlineKeyboardMarkup(
    inline_keyboard=[
        [types.InlineKeyboardButton(text='Бокс🥊', callback_data='boxing')],
        [types.InlineKeyboardButton(text='Футбол⚽️', callback_data='football')],
        [types.InlineKeyboardButton(text='Баскетбол🏀', callback_data='basketball')]
    ]
)

@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        f"Привет {message.from_user.first_name or message.from_user.username}, выберите из меню",
        reply_markup=reply_menu
    )

@dp.message()
async def text_handler(message: Message):
    chat_id = message.chat.id

    if chat_id in user_surveys:
        await survey_handler(message)
        return

    if message.text == "💡 Картинка":
        await message.answer('Какую картинку вы хотите?', reply_markup=inline_image)
    elif message.text == "🏞 Погода":
        weather = await get_weather()
        await message.answer(weather)
    elif message.text == '💡 Курс валют':
        course = await get_currency_rates()
        await message.answer(course)
    elif message.text == '🏞 Список фильмов':
        await message.answer(movies)
    elif message.text == '💡 Шутка':
        joke = await get_joke()
        await message.answer(joke)
    elif message.text == '🏞 Пройти опрос':
        await start_survey(message)
    elif message.text == '💡 Чат с ИИ':
        await message.answer('Задавайте любой вопрос, на который вам ответит ИИ.')
    else:
        await chat_with_ai(message)

async def start_survey(message: types.Message, questions=None):
    chat_id = message.chat.id
    user_surveys[chat_id] = {'answers': []}
    await message.answer(questions[0])

async def survey_handler(message: types.Message):
    chat_id = message.chat.id

    if chat_id in user_surveys:
        user_surveys[chat_id]['answers'].append(message.text)
        q_index = len(user_surveys[chat_id]['answers'])

        if q_index < len(questions):
            await message.answer(questions[q_index])
        else:
            pool = dp['db']
            async with pool.acquire() as conn:
                await conn.execute(
                    'INSERT INTO surveys (user_id, answers) VALUES ($1, $2)',
                    message.from_user.id,
                    user_surveys[chat_id]['answers']
                )
            await message.answer("Спасибо за участие в опросе!")
            del user_surveys[chat_id]


@dp.callback_query()
async def callback_query_handler(call: types.CallbackQuery):
    if call.data == "boxing":
        await call.message.answer_photo('https://img.championat.com/news/big/i/b/belal-muhammad-dzhek-della-maddalena_17469420721967068446.jpg')
    elif call.data == 'football':
        await call.message.answer_photo('https://upload.wikimedia.org/wikipedia/commons/thumb/4/42/Football_in_Bloomington%2C_Indiana%2C_1995.jpg/1200px-Football_in_Bloomington%2C_Indiana%2C_1995.jpg')
    elif call.data == 'basketball':
        await call.message.answer_photo('https://storage.yandexcloud.net/s3-metaratings-storage/upload/sprint.editor/791/7911b2cff1661ddf323e07b355e42a1a.jpg')

async def chat_with_ai(message: Message):
    try:
        client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPEN_AI_CHAT_KEY,
        )

        completion = client.chat.completions.create(
            model="nousresearch/deephermes-3-mistral-24b-preview:free",
            messages=[
                {
                    "role": "user",
                    "content": message.text
                }
            ]
        )
        r = completion.choices[0].message.content
        await message.answer(r)
    except Exception as e:
        print(f"Error in chat_with_ai: {e}")
        await message.answer("Произошла ошибка при общении с ИИ.")

async def main():
    try:
        pool = await create_pool()
        dp['db'] = pool
        print("Starting bot...")
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Error in main: {e}")
    finally:
        await bot.session.close()
        if 'db' in dp:
            await dp['db'].close()

if __name__ == '__main__':
    print("loading...")
    asyncio.run(main())
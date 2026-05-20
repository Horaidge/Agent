"""Reply Keyboard: меню данных пользователя (история, изображения)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    InputMediaPhoto,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from services.telegram_reply_keyboards import (
    MAIN_MENU_BUTTON_TEXT,
    main_reply_keyboard,
)
from services.user_data_service import UserDataService

router = Router(name="user_menu")

BTN_MENU = MAIN_MENU_BUTTON_TEXT
BTN_BACK = "◀️ Назад"
BTN_MY_DATA = "👤 Мои данные"
BTN_CLEAR_HISTORY = "🗑 Очистить историю"
BTN_CLEAR_ALL_DATA = "🧹 Очистить мои данные"
BTN_MY_IMAGES = "🖼 Мои изображения"
BTN_DELETE_AVATAR = "🧍 Удалить аватар"
BTN_DELETE_IMAGES = "🗑 Удалить все изображения"
BTN_DELETE_VIDEOS = "🎬 Удалить видео"
BTN_CONFIRM_CLEAR_HISTORY = "✅ Да, очистить историю"
BTN_CONFIRM_CLEAR_ALL_DATA = "✅ Да, очистить мои данные"
BTN_CONFIRM_DELETE_IMAGES = "✅ Да, удалить изображения"
BTN_CONFIRM_DELETE_AVATAR = "✅ Да, удалить аватар"
BTN_CONFIRM_DELETE_VIDEOS = "✅ Да, удалить видео"
BTN_CANCEL = "❌ Отмена"


def _main_kb() -> ReplyKeyboardMarkup:
    return main_reply_keyboard()


def _data_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_MY_DATA)],
            [KeyboardButton(text=BTN_CLEAR_HISTORY)],
            [KeyboardButton(text=BTN_MY_IMAGES)],
            [KeyboardButton(text=BTN_DELETE_AVATAR)],
            [KeyboardButton(text=BTN_DELETE_IMAGES)],
            [KeyboardButton(text=BTN_DELETE_VIDEOS)],
            [KeyboardButton(text=BTN_CLEAR_ALL_DATA)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def _confirm_history_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CONFIRM_CLEAR_HISTORY)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def _confirm_images_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CONFIRM_DELETE_IMAGES)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def _confirm_avatar_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CONFIRM_DELETE_AVATAR)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def _confirm_videos_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CONFIRM_DELETE_VIDEOS)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def _confirm_clear_all_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CONFIRM_CLEAR_ALL_DATA)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


_WELCOME = (
    "Привет! Я бот Dream Viz.\n\n"
    "Снизу кнопка **«Меню»** — там можно очистить историю диалога в базе бота, "
    "посмотреть сохранённые картинки из чата или удалить их.\n\n"
    "Если клавиатура пропала, отправьте команду /start."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        _WELCOME,
        reply_markup=main_reply_keyboard(),
        parse_mode="Markdown",
    )


@router.message(F.text == BTN_MENU)
async def open_menu(message: Message) -> None:
    await message.answer(
        "Выберите действие:",
        reply_markup=_data_kb(),
    )


@router.message(F.text == BTN_BACK)
async def menu_back(message: Message) -> None:
    await message.answer("Главное меню.", reply_markup=_main_kb())


@router.message(F.text == BTN_CLEAR_HISTORY)
async def ask_clear_history(message: Message) -> None:
    await message.answer(
        "Удалить **сохранённую историю** с ботом в нашей базе?\n"
        "(сообщения в самом Telegram не исчезнут — при необходимости удалите чат вручную в приложении)\n\n"
        "Нажмите подтверждение ниже.",
        reply_markup=_confirm_history_kb(),
        parse_mode="Markdown",
    )


@router.message(F.text == BTN_MY_DATA)
async def show_my_data_overview(message: Message, user_data_service: UserDataService) -> None:
    uid = message.from_user.id if message.from_user else 0
    ov = await user_data_service.get_user_overview(uid)
    avatar = "есть" if ov["avatar_exists"] else "нет"
    avatar_created = ov.get("avatar_created_at")
    avatar_line = f"Аватар: {avatar}"
    if avatar_created:
        avatar_line += f" (создан: {avatar_created})"
    await message.answer(
        "Мои данные:\n"
        f"• {avatar_line}\n"
        f"• Изображения: {ov['images_count']}\n"
        f"• Видео: {ov['videos_count']}\n"
        f"• Персонажи (actors): {ov['actors_count']}\n"
        f"• Окружения: {ov['environments_count']}\n"
        f"• Снов сгенерировано: {ov['dream_runs_count']}\n"
        f"• Сообщений: {ov['messages_count']}",
        reply_markup=_data_kb(),
    )


@router.message(F.text == BTN_CONFIRM_CLEAR_HISTORY)
async def do_clear_history(message: Message, user_data_service: UserDataService) -> None:
    uid = message.from_user.id if message.from_user else 0
    stats = await user_data_service.clear_bot_history(uid)
    await message.answer(
        "Готово. История в базе бота очищена.\n"
        f"• сообщения: {stats['inbound_messages']}\n"
        f"• реплики чата: {stats['conversation_messages']}\n"
        f"• вызовы модели: {stats['model_calls']}\n"
        f"• tool: {stats['tool_calls']}\n"
        f"• события логов: {stats['observability_events']}",
        reply_markup=_data_kb(),
    )


@router.message(F.text == BTN_MY_IMAGES)
async def show_my_images(message: Message, user_data_service: UserDataService) -> None:
    uid = message.from_user.id if message.from_user else 0
    rows = await user_data_service.list_generated_images(uid, limit=20)
    if not rows:
        await message.answer(
            "Пока нет сохранённых изображений из этого чата.",
            reply_markup=_data_kb(),
        )
        return

    await message.answer(
        f"Сохранённых картинок: **{len(rows)}** (показываю до 10 последних).",
        parse_mode="Markdown",
        reply_markup=_data_kb(),
    )

    http_rows = [r for r in rows if _is_http_url(r.get("image_url"))]
    if not http_rows:
        lines = []
        for i, r in enumerate(rows[:15], start=1):
            pr = (r.get("prompt") or "")[:120]
            lines.append(f"{i}. {pr}…" if pr else f"{i}. (без URL превью)")
        await message.answer("\n".join(lines), reply_markup=_data_kb())
        return

    chunk = http_rows[:10]
    media: list[InputMediaPhoto] = []
    for i, r in enumerate(chunk):
        url = str(r.get("image_url"))
        cap = None
        if i == 0:
            pr = (r.get("prompt") or "")[:900]
            cap = pr if pr else None
        media.append(InputMediaPhoto(media=url, caption=cap))

    try:
        await message.answer_media_group(media)
    except Exception:
        await message.answer(
            "Не удалось показать превью по ссылкам. Список промптов:\n"
            + "\n".join(
                f"• {(r.get('prompt') or '')[:200]}" for r in rows[:10]
            ),
            reply_markup=_data_kb(),
        )
        return

    if len(http_rows) > 10:
        await message.answer(
            f"…и ещё {len(http_rows) - 10} (не поместились в один альбом).",
            reply_markup=_data_kb(),
        )


def _is_http_url(u: object) -> bool:
    s = str(u or "").strip()
    return s.startswith("https://") or s.startswith("http://")


@router.message(F.text == BTN_DELETE_IMAGES)
async def ask_delete_images(message: Message) -> None:
    await message.answer(
        "Удалить **все** сохранённые сгенерированные изображения из базы бота?\n"
        "Это не трогает фото в Telegram и dream-ассеты персонажа.\n\n"
        "Подтвердите ниже.",
        reply_markup=_confirm_images_kb(),
        parse_mode="Markdown",
    )


@router.message(F.text == BTN_DELETE_AVATAR)
async def ask_delete_avatar(message: Message) -> None:
    await message.answer(
        "Удалить сохранённый аватар (главного персонажа)?\n"
        "Это сбросит identity state, и pipeline снова спросит, как вы выглядите.",
        reply_markup=_confirm_avatar_kb(),
    )


@router.message(F.text == BTN_DELETE_VIDEOS)
async def ask_delete_videos(message: Message) -> None:
    await message.answer(
        "Удалить все видео (scene + final) и video jobs для вашего пользователя?",
        reply_markup=_confirm_videos_kb(),
    )


@router.message(F.text == BTN_CLEAR_ALL_DATA)
async def ask_clear_all_data(message: Message) -> None:
    await message.answer(
        "Полностью очистить ваши данные в системе?\n"
        "(история, аватар/actors, изображения, видео, pipeline runs)",
        reply_markup=_confirm_clear_all_kb(),
    )


@router.message(F.text == BTN_CONFIRM_DELETE_IMAGES)
async def do_delete_images(message: Message, user_data_service: UserDataService) -> None:
    uid = message.from_user.id if message.from_user else 0
    n = await user_data_service.delete_all_generated_images(uid)
    await message.answer(
        f"Готово. Удалено записей об изображениях: **{n}**.",
        parse_mode="Markdown",
        reply_markup=_data_kb(),
    )


@router.message(F.text == BTN_CONFIRM_DELETE_AVATAR)
async def do_delete_avatar(message: Message, user_data_service: UserDataService) -> None:
    uid = message.from_user.id if message.from_user else 0
    stats = await user_data_service.delete_avatar(uid)
    await message.answer(
        "Готово. Аватар удалён.\n"
        f"• удалено avatar assets: {stats['avatar_assets_deleted']}",
        reply_markup=_data_kb(),
    )


@router.message(F.text == BTN_CONFIRM_DELETE_VIDEOS)
async def do_delete_videos(message: Message, user_data_service: UserDataService) -> None:
    uid = message.from_user.id if message.from_user else 0
    stats = await user_data_service.delete_videos(uid)
    await message.answer(
        "Готово. Видео удалены.\n"
        f"• final videos: {stats['story_videos']}\n"
        f"• scene videos: {stats['scene_videos']}\n"
        f"• video jobs: {stats['video_jobs']}",
        reply_markup=_data_kb(),
    )


@router.message(F.text == BTN_CONFIRM_CLEAR_ALL_DATA)
async def do_clear_all_data(message: Message, user_data_service: UserDataService) -> None:
    uid = message.from_user.id if message.from_user else 0
    stats = await user_data_service.clear_all_user_data(uid)
    await message.answer(
        "Готово. Ваши данные очищены.\n"
        f"• сообщения: {stats['inbound_messages']}\n"
        f"• conversation: {stats['conversation_messages']}\n"
        f"• model/tool: {stats['model_calls']}/{stats['tool_calls']}\n"
        f"• observability: {stats['observability_events']}\n"
        f"• assets/profile: {stats['dream_assets']}/{stats['user_profiles']}\n"
        f"• images/frames: {stats['generated_images']}/{stats['generated_frames']}\n"
        f"• scene/final videos: {stats['scene_videos']}/{stats['story_videos']}\n"
        f"• runs/scenes/jobs: {stats['dream_runs']}/{stats['dream_scenes']}/{stats['video_jobs']}",
        reply_markup=_data_kb(),
    )


@router.message(F.text == BTN_CANCEL)
async def cancel_confirm(message: Message) -> None:
    await message.answer("Отменено.", reply_markup=_data_kb())

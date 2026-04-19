"""Оркестрация: входящее Telegram-сообщение → история → OpenAI → tools → ответ."""
from __future__ import annotations

import json
import logging
from typing import Any

from aiogram.types import Message
from openai import AuthenticationError

from core.config.settings import Settings
from core.observability.service import ObservabilityService
from services.chat import history_service as hist
from services.assets.dream_asset_service import ASSET_TYPE_CHARACTER, STATUS_GENERATED
from services.llm.openai_chat_service import OpenAIChatService
from services.llm.system_prompt_loader import load_system_prompt, system_prompt_preview
from services.telegram_reply_keyboards import main_reply_keyboard
from services.tools import OPENAI_TOOLS_DEFAULT
from services.tools.model_tools.generate_image_tool import (
    GenerateImageArgs,
    execute_generate_image,
    parse_generate_image_args,
)
from services.tools.image_tools import tool_generate_base_character
from storage.chat_repository import ChatStoreRepository
from storage.dream_asset_repository import DreamAssetRepository
from storage.generated_image_repository import GeneratedImageRepository
from storage.user_profile_repository import UserProfileRepository

logger = logging.getLogger(__name__)

_MAX_STORE_MSG = 12000
_SYSTEM_PREVIEW_STORE = 320


def _clean_user_facing_text(text: str) -> str:
    """
    Подготовка текста для user-facing/TTS:
    - без code fences и служебного мусора,
    - без явных JSON-дампов.
    """
    t = (text or "").strip()
    if not t:
        return "Готово."
    t = t.replace("```json", "").replace("```", "").strip()
    low = t.lower()
    if low.startswith("{") and low.endswith("}") and ("tool" in low or "trace" in low or "status" in low):
        return "Готово. Подробности доступны во внутреннем журнале."
    if low.startswith("[") and low.endswith("]") and ("tool" in low or "trace" in low):
        return "Готово. Подробности доступны во внутреннем журнале."
    return t


def _sanitize_messages_for_storage(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Урезает system и длинный content для Mongo (полный промпт не храним)."""
    out: list[dict[str, Any]] = []
    for m in messages:
        mc: dict[str, Any] = dict(m)
        role = m.get("role")
        c = m.get("content")
        if role == "system" and isinstance(c, str):
            if len(c) > _SYSTEM_PREVIEW_STORE:
                mc["content"] = c[:_SYSTEM_PREVIEW_STORE] + "… [truncated]"
        elif isinstance(c, str) and len(c) > _MAX_STORE_MSG:
            mc["content"] = c[:_MAX_STORE_MSG] + "… [truncated]"
        out.append(mc)
    return out


def _completion_to_excerpt(resp: Any) -> str:
    try:
        if hasattr(resp, "model_dump_json"):
            s = resp.model_dump_json()
        else:
            s = json.dumps(resp, default=str)
    except Exception:  # noqa: BLE001
        s = str(resp)
    if len(s) > 20000:
        return s[:20000] + "… [truncated]"
    return s


class ChatOrchestrator:
    """Один цикл: сохранение user → OpenAI → опционально generate_image → финальный ответ."""

    def __init__(
        self,
        settings: Settings,
        chat_store: ChatStoreRepository,
        openai: OpenAIChatService,
        observability: ObservabilityService | None = None,
        *,
        dream_asset_repo: DreamAssetRepository | None = None,
        user_profile_repo: UserProfileRepository | None = None,
        generated_image_repo: GeneratedImageRepository | None = None,
    ) -> None:
        self._settings = settings
        self._store = chat_store
        self._openai = openai
        self._obs = observability
        self._dream_assets = dream_asset_repo
        self._user_profile = user_profile_repo
        self._generated_images = generated_image_repo

    async def handle_user_message(
        self,
        message: Message,
        *,
        trace_id: str | None,
    ) -> None:
        user = message.from_user
        uid = user.id if user else 0
        chat_id = message.chat.id
        text = (message.text or "").strip()
        internal_user_id = str(uid)

        if not text:
            return

        await hist.save_user_message(
            self._store,
            internal_user_id=internal_user_id,
            telegram_user_id=uid,
            chat_id=chat_id,
            text=text,
            trace_id=trace_id,
        )

        if (
            self._user_profile
            and self._dream_assets
            and await self._should_handle_awaiting_character_description(uid)
        ):
            await self._handle_base_character_description_turn(
                message=message,
                internal_user_id=internal_user_id,
                uid=uid,
                chat_id=chat_id,
                trace_id=trace_id,
                appearance=text,
            )
            return

        if not self._openai.configured:
            await message.answer(
                "Чат недоступен: не задан OPENAI_API_KEY. Проверьте настройки сервера.",
                reply_markup=main_reply_keyboard(),
            )
            logger.error("OPENAI_API_KEY не задан — история сохранена, ответ не сгенерирован")
            return

        try:
            system_prompt = load_system_prompt()
        except Exception as e:
            logger.exception("system prompt: %s", e)
            await message.answer(
                "Ошибка конфигурации: не найден system prompt (prompts/system_prompt.md).",
                reply_markup=main_reply_keyboard(),
            )
            return

        history_rows = await self._store.list_recent_conversation_for_model(
            internal_user_id,
            limit=50,
        )
        messages = hist.build_model_messages(system_prompt, history_rows)
        messages.insert(
            1,
            {
                "role": "system",
                "content": (
                    "Отвечай пользователю чистым естественным текстом. "
                    "Язык по умолчанию русский. "
                    "Не показывай внутренние JSON/trace/tool-логи и технические детали."
                ),
            },
        )

        image_urls: list[str] = []

        try:
            resp = await self._openai.chat_completion(
                messages,
                tools=OPENAI_TOOLS_DEFAULT,
            )
        except AuthenticationError:
            # Не логируем тело ответа OpenAI — в нём может быть фрагмент ключа
            logger.error(
                "OpenAI 401: ключ отклонён. Проверьте OPENAI_API_KEY (platform.openai.com → API keys)."
            )
            await self._persist_error(
                internal_user_id, uid, chat_id, trace_id, "OpenAI 401 invalid API key"
            )
            await message.answer(
                "Ошибка OpenAI: ключ API недействителен или отозван. "
                "Создайте новый ключ на https://platform.openai.com/account/api-keys "
                "и обновите OPENAI_API_KEY в env, затем перезапустите сервер.",
                reply_markup=main_reply_keyboard(),
            )
            return
        except Exception as e:
            logger.exception("OpenAI: сбой запроса (%s)", type(e).__name__)
            await self._persist_error(internal_user_id, uid, chat_id, trace_id, type(e).__name__)
            await message.answer(
                "Не удалось получить ответ модели. Попробуйте позже.",
                reply_markup=main_reply_keyboard(),
            )
            return

        if not resp.choices:
            await message.answer(
                "Модель вернула пустой ответ. Попробуйте ещё раз.",
                reply_markup=main_reply_keyboard(),
            )
            return

        choice0 = resp.choices[0]
        msg = choice0.message

        if msg.tool_calls:
            await self._persist_model_call_safe(
                internal_user_id=internal_user_id,
                telegram_user_id=uid,
                chat_id=chat_id,
                trace_id=trace_id,
                turn_index=1,
                request_messages=messages,
                resp=resp,
            )
            await self._handle_tool_path(
                message=message,
                internal_user_id=internal_user_id,
                uid=uid,
                chat_id=chat_id,
                trace_id=trace_id,
                system_prompt=system_prompt,
                messages=messages,
                assistant_msg=msg,
            )
            return

        reply = _clean_user_facing_text((msg.content or "").strip())
        if not reply:
            reply = "…"

        # Сначала Telegram — чтобы сбой Mongo не блокировал ответ
        try:
            await message.answer(reply[:4096], reply_markup=main_reply_keyboard())
        except Exception:
            logger.exception("Не удалось отправить ответ в Telegram")
            return

        await self._save_assistant_and_trace_after_reply(
            internal_user_id=internal_user_id,
            telegram_user_id=uid,
            chat_id=chat_id,
            trace_id=trace_id,
            reply=reply,
            turn_index=1,
            request_messages=messages,
            resp=resp,
        )

    async def _persist_model_call_safe(
        self,
        *,
        internal_user_id: str,
        telegram_user_id: int,
        chat_id: int,
        trace_id: str | None,
        turn_index: int,
        request_messages: list[dict[str, Any]],
        resp: Any,
    ) -> None:
        try:
            await self._persist_model_call(
                internal_user_id=internal_user_id,
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
                trace_id=trace_id,
                turn_index=turn_index,
                request_messages=request_messages,
                resp=resp,
            )
        except Exception:
            logger.warning(
                "Сохранение model_calls не удалось (ответ пользователю не блокируем)",
                exc_info=True,
            )

    async def _save_assistant_and_trace_after_reply(
        self,
        *,
        internal_user_id: str,
        telegram_user_id: int,
        chat_id: int,
        trace_id: str | None,
        reply: str,
        turn_index: int,
        request_messages: list[dict[str, Any]],
        resp: Any,
    ) -> None:
        try:
            await hist.save_assistant_message(
                self._store,
                internal_user_id=internal_user_id,
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
                text=reply,
                trace_id=trace_id,
            )
            await self._persist_model_call(
                internal_user_id=internal_user_id,
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
                trace_id=trace_id,
                turn_index=turn_index,
                request_messages=request_messages,
                resp=resp,
            )
            await self._mirror_obs_assistant(trace_id, reply)
        except Exception:
            logger.warning(
                "Сохранение assistant/model_calls после ответа в Telegram не удалось",
                exc_info=True,
            )

    async def _handle_tool_path(
        self,
        *,
        message: Message,
        internal_user_id: str,
        uid: int,
        chat_id: int,
        trace_id: str | None,
        system_prompt: str,
        messages: list[dict[str, Any]],
        assistant_msg: Any,
    ) -> None:
        tc_list = assistant_msg.tool_calls
        if not tc_list:
            return

        tc = tc_list[0]
        fn = tc.function.name
        args_raw = tc.function.arguments or "{}"

        tcs_storage = hist.tool_calls_to_storage_format(tc_list)

        await hist.save_assistant_message(
            self._store,
            internal_user_id=internal_user_id,
            telegram_user_id=uid,
            chat_id=chat_id,
            text=assistant_msg.content,
            trace_id=trace_id,
            message_type="tool_request",
            metadata={"tool_calls": tcs_storage},
        )

        if fn != "generate_image":
            logger.warning("Неизвестный tool: %s", fn)
            await message.answer(
                f"Неизвестный инструмент: {fn}",
                reply_markup=main_reply_keyboard(),
            )
            return

        try:
            parsed = parse_generate_image_args(args_raw)
        except ValueError:
            await message.answer(
                "Модель не передала описание для генерации.",
                reply_markup=main_reply_keyboard(),
            )
            return
        args = {
            "prompt": parsed.prompt,
            "size": parsed.size,
            "model": parsed.model,
            "n": parsed.n,
        }
        prompt = parsed.prompt

        if self._user_profile and self._dream_assets:
            has_face = await self._dream_assets.has_classified_face_asset(uid)
            prof = await self._user_profile.get_by_user_id(uid)
            has_base = bool(prof and prof.get("base_character_asset_id"))
            if not has_face and not has_base:
                await self._user_profile.set_awaiting_character_description(
                    uid, awaiting=True
                )
                blocked = {"ok": False, "need_character_description": True}
                await self._persist_tool_call(
                    internal_user_id=internal_user_id,
                    telegram_user_id=uid,
                    chat_id=chat_id,
                    trace_id=trace_id,
                    tool_name=fn,
                    tool_args=args,
                    tool_result=blocked,
                    success=False,
                )
                await hist.save_tool_message(
                    self._store,
                    internal_user_id=internal_user_id,
                    telegram_user_id=uid,
                    chat_id=chat_id,
                    tool_call_id=tc.id,
                    content=json.dumps(blocked, ensure_ascii=False),
                    trace_id=trace_id,
                )
                ask = (
                    "Опиши, как ты выглядишь — по этому образу мы закрепим "
                    "персонажа для всех картинок."
                )
                try:
                    await message.answer(
                        ask[:4096],
                        reply_markup=main_reply_keyboard(),
                    )
                except Exception:
                    logger.exception("Telegram: не удалось отправить запрос описания")
                    return
                try:
                    await hist.save_assistant_message(
                        self._store,
                        internal_user_id=internal_user_id,
                        telegram_user_id=uid,
                        chat_id=chat_id,
                        text=ask,
                        trace_id=trace_id,
                        message_type="text_after_tool",
                        metadata={"blocked_generate_image": True},
                    )
                    await self._mirror_obs_assistant(trace_id, ask)
                except Exception:
                    logger.warning(
                        "Сохранение assistant после блокировки generate_image не удалось",
                        exc_info=True,
                    )
                return

        prompt = await self._maybe_augment_prompt_with_base_character(uid, prompt)

        parsed = GenerateImageArgs(
            prompt=prompt,
            size=parsed.size,
            model=parsed.model,
            n=parsed.n,
        )
        result = execute_generate_image(parsed)

        await self._persist_tool_call(
            internal_user_id=internal_user_id,
            telegram_user_id=uid,
            chat_id=chat_id,
            trace_id=trace_id,
            tool_name=fn,
            tool_args=args,
            tool_result=result.to_dict(),
            success=result.ok,
        )

        tool_content = json.dumps(result.to_dict(), ensure_ascii=False)
        await hist.save_tool_message(
            self._store,
            internal_user_id=internal_user_id,
            telegram_user_id=uid,
            chat_id=chat_id,
            tool_call_id=tc.id,
            content=tool_content,
            trace_id=trace_id,
        )

        if result.ok:
            image_urls = list(result.image_urls)
        else:
            image_urls = []

        if result.ok and image_urls and self._generated_images:
            await self._record_generated_image(
                uid=uid,
                image_url=image_urls[0],
                prompt=prompt,
            )

        history_rows = await self._store.list_recent_conversation_for_model(
            internal_user_id,
            limit=50,
        )
        messages2 = hist.build_model_messages(system_prompt, history_rows)

        try:
            resp2 = await self._openai.chat_completion(messages2, tools=None)
        except AuthenticationError:
            logger.error("OpenAI 401 (второй вызов): проверьте OPENAI_API_KEY.")
            err = (
                "Ошибка авторизации OpenAI. Обновите OPENAI_API_KEY.\n\n"
                + ("\n".join(image_urls) if result.ok and image_urls else "")
            )
            await message.answer(
                err.strip()[:4096],
                reply_markup=main_reply_keyboard(),
            )
            return
        except Exception:
            logger.exception("OpenAI: второй вызов не удался")
            err = "Модель не смогла сформировать ответ после генерации."
            if result.ok and image_urls:
                err += "\n\n" + "\n".join(image_urls)
            await message.answer(
                err[:4096],
                reply_markup=main_reply_keyboard(),
            )
            return

        if not resp2.choices:
            err = "Пустой ответ модели после инструмента."
            if result.ok and image_urls:
                err += "\n\n" + "\n".join(image_urls)
            await message.answer(
                err[:4096],
                reply_markup=main_reply_keyboard(),
            )
            return

        final = _clean_user_facing_text((resp2.choices[0].message.content or "").strip()) or "Готово."
        text_out = final[:3800]
        if result.ok and image_urls:
            text_out += "\n\n" + "\n".join(image_urls)
        try:
            await message.answer(
                text_out[:4096],
                reply_markup=main_reply_keyboard(),
            )
        except Exception:
            logger.exception("Telegram: не удалось отправить текст после tool")
            return

        if result.ok and image_urls:
            try:
                await message.answer_photo(
                    image_urls[0],
                    caption="Сгенерированное изображение",
                    reply_markup=main_reply_keyboard(),
                )
            except Exception:  # noqa: BLE001
                logger.info("answer_photo skipped (URL или лимиты Telegram)")

        try:
            await self._persist_model_call(
                internal_user_id=internal_user_id,
                telegram_user_id=uid,
                chat_id=chat_id,
                trace_id=trace_id,
                turn_index=2,
                request_messages=messages2,
                resp=resp2,
            )
            await hist.save_assistant_message(
                self._store,
                internal_user_id=internal_user_id,
                telegram_user_id=uid,
                chat_id=chat_id,
                text=final,
                trace_id=trace_id,
                message_type="text_after_tool",
                metadata={"image_urls": image_urls} if image_urls else {},
            )
            await self._mirror_obs_assistant(trace_id, final)
        except Exception:
            logger.warning(
                "Сохранение трейса после tool-path не удалось (сообщение в Telegram уже ушло)",
                exc_info=True,
            )

    async def _persist_model_call(
        self,
        *,
        internal_user_id: str,
        telegram_user_id: int,
        chat_id: int,
        trace_id: str | None,
        turn_index: int,
        request_messages: list[dict[str, Any]],
        resp: Any,
    ) -> None:
        sanitized = _sanitize_messages_for_storage(request_messages)
        doc = {
            "internal_user_id": internal_user_id,
            "telegram_user_id": telegram_user_id,
            "chat_id": chat_id,
            "trace_id": trace_id,
            "model_name": self._settings.openai_model,
            "request_messages": sanitized,
            "system_prompt_preview": system_prompt_preview(300),
            "raw_response_excerpt": _completion_to_excerpt(resp),
            "turn_index": turn_index,
        }
        await self._store.insert_model_call(doc)

        if self._obs and trace_id:
            await self._obs.record_model_call(
                trace_id=trace_id,
                system_prompt=None,
                user_message=None,
                context_excerpt=None,
                tools_available=["generate_image"],
                response_text=_completion_to_excerpt(resp)[:12000],
                structured={"turn": turn_index, "stored_in": "model_calls"},
            )

    async def _persist_tool_call(
        self,
        *,
        internal_user_id: str,
        telegram_user_id: int,
        chat_id: int,
        trace_id: str | None,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_result: dict[str, Any],
        success: bool,
    ) -> None:
        doc = {
            "internal_user_id": internal_user_id,
            "telegram_user_id": telegram_user_id,
            "chat_id": chat_id,
            "trace_id": trace_id,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "tool_result": tool_result,
            "success": success,
        }
        await self._store.insert_tool_call_record(doc)

        if self._obs and trace_id:
            await self._obs.record_tool_call(
                trace_id=trace_id,
                tool_name=tool_name,
                arguments=tool_args,
                result_excerpt=json.dumps(tool_result, ensure_ascii=False)[:8000],
                error=None if success else tool_result.get("error"),
            )

    async def _persist_error(
        self,
        internal_user_id: str,
        uid: int,
        chat_id: int,
        trace_id: str | None,
        err: str,
    ) -> None:
        if self._obs and trace_id:
            await self._obs.record_error(
                trace_id=trace_id,
                where="chat_orchestrator",
                message=err[:2000],
            )

    async def _mirror_obs_assistant(self, trace_id: str | None, reply: str) -> None:
        if self._obs and trace_id:
            await self._obs.record_pipeline_stage(
                trace_id=trace_id,
                stage="assistant_reply",
                status="ok",
                detail={"length": len(reply)},
            )

    async def _should_handle_awaiting_character_description(self, uid: int) -> bool:
        if not self._dream_assets or not self._user_profile:
            return False
        if await self._dream_assets.has_classified_face_asset(uid):
            return False
        prof = await self._user_profile.get_by_user_id(uid)
        if prof and prof.get("base_character_asset_id"):
            return False
        return bool(prof and prof.get("awaiting_character_description"))

    async def _maybe_augment_prompt_with_base_character(
        self, uid: int, prompt: str
    ) -> str:
        if not self._user_profile:
            return prompt
        prof = await self._user_profile.get_by_user_id(uid)
        if prof and prof.get("base_character_asset_id"):
            return f"{prompt}. same person as reference, consistent face"
        return prompt

    async def _record_generated_image(
        self,
        *,
        uid: int,
        image_url: str,
        prompt: str,
    ) -> None:
        if not self._generated_images or not self._user_profile:
            return
        prof = await self._user_profile.get_by_user_id(uid)
        char_id = (prof or {}).get("base_character_asset_id")
        try:
            await self._generated_images.insert_one(
                user_id=uid,
                image_url=image_url,
                prompt=prompt,
                related_character_id=char_id,
            )
        except Exception:
            logger.warning(
                "generated_images: запись не сохранена (ответ пользователю не блокируем)",
                exc_info=True,
            )

    async def _handle_base_character_description_turn(
        self,
        *,
        message: Message,
        internal_user_id: str,
        uid: int,
        chat_id: int,
        trace_id: str | None,
        appearance: str,
    ) -> None:
        if not self._dream_assets or not self._user_profile:
            return
        appearance_arg = appearance.strip() if appearance.strip() else None
        bc = tool_generate_base_character(appearance_arg)
        if not bc.ok or not bc.image_url:
            err = bc.error or "ошибка генерации"
            await message.answer(
                f"Не удалось создать базового персонажа: {err[:500]}",
                reply_markup=main_reply_keyboard(),
            )
            return

        doc = {
            "owner_user_id": uid,
            "telegram_user_id": uid,
            "chat_id": chat_id,
            "telegram_file_id": None,
            "source_message_id": message.message_id,
            "asset_type": ASSET_TYPE_CHARACTER,
            "status": STATUS_GENERATED,
            "is_base_character": True,
            "source_image_url": bc.image_url,
            "character_uuid": bc.character_id,
        }
        asset_id = await self._dream_assets.insert_one(doc)
        await self._user_profile.set_base_character_asset(uid, asset_id=asset_id)

        if self._generated_images:
            try:
                await self._generated_images.insert_one(
                    user_id=uid,
                    image_url=bc.image_url,
                    prompt=bc.prompt_used,
                    related_character_id=asset_id,
                )
            except Exception:
                logger.warning(
                    "generated_images (base character): не сохранено",
                    exc_info=True,
                )

        note = (
            "Готово — закрепили базового персонажа для всех следующих картинок. "
            "Можешь снова попросить сгенерировать изображение."
        )
        try:
            await message.answer(
                note[:4096],
                reply_markup=main_reply_keyboard(),
            )
            await message.answer_photo(
                bc.image_url,
                caption="Базовый персонаж",
                reply_markup=main_reply_keyboard(),
            )
        except Exception:
            logger.exception("Telegram: отправка базового персонажа")
            try:
                await message.answer(
                    f"{note}\n\n{bc.image_url}"[:4096],
                    reply_markup=main_reply_keyboard(),
                )
            except Exception:
                logger.exception("Telegram: fallback с URL не удался")

        try:
            await hist.save_assistant_message(
                self._store,
                internal_user_id=internal_user_id,
                telegram_user_id=uid,
                chat_id=chat_id,
                text=note,
                trace_id=trace_id,
                message_type="base_character_created",
                metadata={
                    "asset_id": asset_id,
                    "image_url": bc.image_url,
                    "character_uuid": bc.character_id,
                },
            )
            await self._mirror_obs_assistant(trace_id, note)
        except Exception:
            logger.warning(
                "Сохранение assistant после base character не удалось",
                exc_info=True,
            )

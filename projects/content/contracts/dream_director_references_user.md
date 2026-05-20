Верни JSON строго в формате:
{
  "global_references": {
    "status": "pending_confirmation",
    "items": [
      {
        "ref_id": "stable_snake_case_id",
        "kind": "character|environment|object",
        "label": "короткое имя",
        "short_blurb": "1–2 предложения простым языком: кто/что это для зрителя (без технички)",
        "is_main_hero": true,
        "user_has_reference": false,
        "existing_asset_note": null,
        "generation_prompt": "компактный промпт для одной картинки-референса (без простыни)",
        "rationale": "одна строка: зачем визуально (для команды; не для пользователя в UI)"
      }
    ]
  },
  "playground_notes": "кратко: что пользователь увидит до подтверждения генерации"
}
Правила:
- Ты не генерируешь изображения и не вызываешь инструменты — только план.
- Персонажи: минимум главный герой; второстепенные — только если влияют на визуал (не больше 4 персонажей в сумме).
- Окружения: 1–3 ключевые зоны, не больше.
- Объекты: только если без них визуал сна теряется; не раздувай список.
- short_blurb обязателен: коротко и по-человечески; generation_prompt — только для картинки, без повторения всего сна.
- user_has_reference: в Playground ставь false, если нет явного сигнала из asset_context; existing_asset_note тогда null или пояснение «в проде: проверка коллекции».
- Если в asset_context указано has_base_character / has_face / secondary_actors — отрази это в user_has_reference и кратком existing_asset_note (без выдуманных id).

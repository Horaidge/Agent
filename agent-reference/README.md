# Agent Reference (out of runtime)

Эта папка хранит справочные артефакты для настройки агента (LLM prompt/tool config).

Важно:
- папка НЕ импортируется в `src/*`;
- это НЕ runtime-код фронтенда;
- изменения здесь нужны для согласования контрактов и поведения инструмента на стороне агента.

Содержимое:
- `tool-contracts/show_video.schema.json` — JSON schema аргументов инструмента `show_video`.
- `video-catalog.json` — словарь доступных видео (`Agent1..Agent4`) с короткими описаниями и ключами для `videoKey`.

Рекомендация для агента:
- при вызове `show_video` всегда передавать `videoKey` из `video-catalog.json`;
- не использовать свободный текст вместо `videoKey`;
- опционально передавать `title`, `reason`, `startSeconds`.

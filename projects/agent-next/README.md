# agent-next

Frontend-проект на Next.js для AI-native интерфейса: лендинг + агентный виджет + изолированный voice-экран + базовая админ-зона.

README написан как быстрый онбординг для LLM/инженера: что где лежит, как идет поток данных и где смотреть дебаг.

## Что это за проект

- Основа: `Next.js App Router` + `React` + `TypeScript`.
- Состояние runtime: `zustand` (`src/shared/voice-store.ts`).
- Voice runtime: `@vapi-ai/web` через `VoiceController` (`src/orchestration/voice-controller.ts`).
- UI-слой агента: `AgentWidget` (`src/components/agent/agent-widget.tsx`) и адаптер `VapiAgentWidget`.
- Анимации: `framer-motion`.
- Архитектурные проверки зависимостей: `dependency-cruiser`.

## Главные маршруты

- `/` — публичный сайт (landing + зона агента).
- `/voice` — отдельный рабочий VAPI-экран (не смешан с лендингом).
- `/admin` — mock-админка (без реального backend на этом этапе).
- `/login` — placeholder входа.
- `/deps` — визуализация зависимостей проекта.

## Быстрый запуск

```bash
pnpm install
pnpm dev
```

Сервер поднимается на `http://localhost:3100`.

### Переменные окружения

Минимум для VAPI:

- `NEXT_PUBLIC_VAPI_PUBLIC_KEY`
- `NEXT_PUBLIC_VAPI_ASSISTANT_ID`

Без них виджет покажет понятную ошибку окружения, но проект продолжит запускаться.

## Архитектура (кратко)

### 1) UI-слой

- `src/components/landing/*` — секции лендинга.
- `src/components/agent/*` — переиспользуемый агентный модуль (сфера, чат, сообщения, тулзы, видео, дебаг).
- `src/components/admin/*` — mock-компоненты админки.
- `src/components/ui/*` — базовые UI-элементы.
- `src/components/animations/*` — анимационные примитивы.

### 2) Runtime-слой агента

- `src/orchestration/use-voice-session.ts` — React-hook API для UI.
- `src/orchestration/voice-controller.ts` — подписки на VAPI-события, lifecycle звонка, отправка текста.
- `src/shared/vapi-guards.ts` — парсинг transcript/tool-call из сырого VAPI message payload.

### 3) Debug/observability

- Клиентские debug-события хранятся в store и показываются в UI.
- Сырые события (raw JSON) батчами отправляются на сервер через `src/shared/debug-ingest-client.ts`.
- API ingest: `POST /api/debug-ingest` (`src/app/api/debug-ingest/route.ts`).
- Серверный файл лога: `reports/debug-sessions.ndjson`.

## Поток данных (VAPI)

1. UI вызывает `start()` из `useVoiceSession`.
2. `VoiceController` поднимает звонок через `@vapi-ai/web`.
3. События (`message`, `speech-update`, `video`, `error`, и т.д.) попадают в `voice-controller`.
4. Нормализованные данные пишутся в `zustand` store:
   - `transcriptMessages`
   - `toolEvents`
   - `debugEvents`
   - `remoteVideoTrack`
5. `VapiAgentWidget` маппит store -> `AgentWidget` runtime props.
6. `AgentWidget` рендерит сферу, чат, timeline тулов, live video.

## Видео и tool-calls

- Frontend ожидает tool-call события VAPI и показывает их в `AgentToolRenderer`.
- Live video трек обрабатывается через событие `vapi.on("video", ...)` и рендерится в `AgentLiveVideo`.
- Для детальной диагностики всегда доступен raw поток в `reports/debug-sessions.ndjson`.

## Визуализация зависимостей

Команды:

```bash
pnpm depcruise
pnpm depcruise:json
pnpm depcruise:dot
pnpm depcruise:text
pnpm depcruise:mermaid
pnpm depcruise:html
```

Где смотреть:

- UI-страница: `/deps`
- Файлы отчетов: `reports/dependency-cruiser-*`
- Правила изоляции слоев: `.dependency-cruiser.cjs`

## Важные ограничения этапа

- Здесь нет реализации backend/RAG/авторизации/загрузки файлов как бизнес-логики.
- `AgentWidget` — UI-оболочка над существующим VAPI runtime, а не отдельный новый агентный backend.
- `/voice` остается отдельным рабочим экраном для прямого voice-флоу.

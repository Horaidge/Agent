# Интеграция VAPI с фронтендом (DZEN.ai)

Документ описывает, **как подключается VAPI** к веб-клиенту, **какие данные нужны** и **как их безопасно передавать** в Next.js / Docker. Актуальные примеры кода см. в [официальной документации VAPI](https://docs.vapi.ai/).

---

## 1. Роль VAPI в проекте

**VAPI** — платформа голосовых и текстовых AI-ассистентов. На фронтенде обычно используется один из вариантов:

| Подход | Когда использовать |
|--------|-------------------|
| **Web SDK** (`@vapi-ai/web`) | Свой UI (чат справа, кнопки микрофона), полный контроль |
| **Готовый Web Widget** | Быстрая вставка виджета без кастомной вёрстки |
| **React SDK** (`@vapi-ai/client-sdk-react`) | Готовый React-компонент виджета |

В demo-лендинге логично держать **одну точку входа** (правый чат-виджет) и не дублировать голос в hero/CTA без необходимости.

---

## 2. Переменные окружения (что за что отвечает)

В проекте секреты лежат в `config/.env` (для backend и при необходимости копируются во frontend на этапе сборки). **Имена** переменных, которые связаны с VAPI и смежными сервисами:

| Переменная | Назначение |
|------------|------------|
| `VAPI_API_KEY` | Ключ API VAPI. Часто используется на **сервере** (backend, server actions). **Не вшивайте приватный ключ в публичный клиентский бандл.** |
| `PUBLIC_API_KEYS` | Публичный ключ(и) из [VAPI Dashboard](https://dashboard.vapi.ai/) — **именно такой ключ допустим на фронтенде** для Web SDK / виджета (с ограничениями по домену в настройках VAPI). |
| `assistant_ID` | UUID ассистента в VAPI — передаётся в `start()` или в пропсы виджета. |

Дополнительно в том же файле могут быть ключи OpenAI, Supabase и т.д. — они **не** являются частью VAPI Web SDK, но могут использоваться backend при оркестрации.

**Важно:** не коммитьте реальные значения `.env` в git. Для документации используйте `.env.example` с пустыми значениями.

---

## 3. Что нужно на фронтенде (минимум)

1. **Публичный API-ключ VAPI** (`PUBLIC_API_KEYS` в вашем конфиге — это и есть ключ для клиента, если вы так его назвали в dashboard).
2. **ID ассистента** (`assistant_ID`) — из раздела Assistants в VAPI.
3. **Пакет** для браузера, например:
   ```bash
   pnpm add @vapi-ai/web
   ```
   При необходимости готовый React-виджет:
   ```bash
   pnpm add @vapi-ai/client-sdk-react
   ```

---

## 4. Next.js: как пробросить ключи в клиент

Переменные с префиксом `NEXT_PUBLIC_` попадают в клиентский бандл. Пример:

```env
# frontend/.env.local (или build-args в Docker)
NEXT_PUBLIC_VAPI_PUBLIC_KEY=ваш_публичный_ключ
NEXT_PUBLIC_VAPI_ASSISTANT_ID=uuid-ассистента
```

В коде:

```ts
const publicKey = process.env.NEXT_PUBLIC_VAPI_PUBLIC_KEY!
const assistantId = process.env.NEXT_PUBLIC_VAPI_ASSISTANT_ID!
```

**Приватный** `VAPI_API_KEY` в `NEXT_PUBLIC_*` **не** указывайте — он предназначен для серверных вызовов API VAPI.

Текущий `docker-compose.yml` для сервиса `frontend` задаёт только `NEXT_PUBLIC_API_URL`. Чтобы VAPI работал в контейнере, добавьте в `environment` (или в build `ARG` + `ENV` в Dockerfile на этапе `pnpm build`) переменные `NEXT_PUBLIC_VAPI_*` с публичными значениями.

---

## 5. Web SDK (`@vapi-ai/web`) — типовой поток

Официальный quickstart: [Web calls | Vapi](https://docs.vapi.ai/quickstart/web).

Упрощённый пример (клиентский компонент React):

```tsx
"use client"

import Vapi from "@vapi-ai/web"
import { useEffect, useRef } from "react"

const publicKey = process.env.NEXT_PUBLIC_VAPI_PUBLIC_KEY!
const assistantId = process.env.NEXT_PUBLIC_VAPI_ASSISTANT_ID!

export function useVapiVoice() {
  const vapiRef = useRef<InstanceType<typeof Vapi> | null>(null)

  useEffect(() => {
    vapiRef.current = new Vapi(publicKey)
    const vapi = vapiRef.current

    vapi.on("call-start", () => { /* звонок начался */ })
    vapi.on("call-end", () => { /* звонок завершён */ })
    vapi.on("message", (msg) => {
      // транскрипты, события — см. типы в SDK
      if (msg.type === "transcript") {
        // role, transcript
      }
    })

    return () => {
      vapi.stop()
    }
  }, [])

  return {
    start: () => vapiRef.current?.start(assistantId),
    stop: () => vapiRef.current?.stop(),
  }
}
```

Методы и события могут отличаться по версии SDK — ориентируйтесь на [релизы @vapi-ai/web](https://www.npmjs.com/package/@vapi-ai/web) и документацию.

---

## 6. Готовый Web Widget

Если не нужен полностью кастомный UI, см. [Web widget | Vapi](https://docs.vapi.ai/chat/web-widget): встраивание через скрипт или React-компонент с `publicKey`, `assistantId`, режимом `chat` / `voice` / `hybrid`.

---

## 7. Связь с `config/.env` и Docker

- **Backend** в этом репозитории подключается к `config/.env` (`env_file` в compose) и может хранить `VAPI_API_KEY` для серверных запросов.
- **Frontend** в образе Next.js **не** читает `config/.env` автоматически — нужно либо:
  - продублировать публичные переменные в `frontend/.env.local` / build-args, либо
  - передавать их в `docker-compose.yml` в секции `frontend.environment` как `NEXT_PUBLIC_*`.

Исторически в образе `david_frontend` в зависимостях встречался пакет `@vapi-ai/web`; в текущем дереве исходников проверьте `package.json` и при необходимости добавьте зависимость снова.

---

## 8. Безопасность

1. На сайте в продакшене используйте **только публичный** ключ VAPI для браузера и ограничьте домены в настройках VAPI.
2. `VAPI_API_KEY` (приватный) — только сервер, CI-секреты, не клиент.
3. Не логируйте ключи и полные транскрипты с PII в консоль в production.

---

## 9. Полезные ссылки

- [Quickstart: Web](https://docs.vapi.ai/quickstart/web)
- [Web Widget](https://docs.vapi.ai/chat/web-widget)
- [Client-side Tools (Web SDK)](https://docs.vapi.ai/tools/client-side-websdk)
- [Dashboard VAPI](https://dashboard.vapi.ai/)

---

## 10. Краткий чеклист внедрения на этом проекте

1. Создать ассистента в VAPI, скопировать **Assistant ID**.
2. Создать **Public API key** в dashboard (для фронта).
3. Добавить `NEXT_PUBLIC_VAPI_PUBLIC_KEY` и `NEXT_PUBLIC_VAPI_ASSISTANT_ID` в окружение сборки frontend.
4. Установить `@vapi-ai/web` (и при необходимости `@vapi-ai/client-sdk-react`).
5. В клиентском компоненте (например, правый чат-виджет) инициализировать SDK и вызывать `start(assistantId)` с кнопки микрофона; текст — через события `message` или API чата согласно выбранному режиму.
6. Пересобрать образ frontend и перезапустить контейнер.

Если нужен единый сценарий с кнопкой на лендинге («Открыть чат»), можно диспатчить кастомное событие (например, `dzen-open-chat`), на которое подписан виджет — так CTA не дублирует логику VAPI в нескольких местах.

-- RAG: чанки с эмбеддингами для Telegram-бота (Supabase / Postgres + pgvector).
-- Выполни в Supabase: SQL Editor → New query → вставить → Run.
-- Размерность 1536 соответствует OpenAI text-embedding-3-small (рекомендуется для RAG).

create extension if not exists vector;

create table if not exists public.telegram_rag_chunks (
    id uuid primary key default gen_random_uuid(),
    source text,
    content text not null,
    embedding vector(1536),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

comment on table public.telegram_rag_chunks is 'RAG: текстовые чанки и векторы для мини Telegram-бота';

-- Поиск по косинусному расстоянию (для нормализованных эмбеддингов OpenAI — удобно).
create index if not exists telegram_rag_chunks_embedding_hnsw
    on public.telegram_rag_chunks
    using hnsw (embedding vector_cosine_ops);

create index if not exists telegram_rag_chunks_created_at_idx
    on public.telegram_rag_chunks (created_at desc);

alter table public.telegram_rag_chunks enable row level security;

-- Чтение/запись только через service_role (ключ бэкенда). Анонимный ключ без политик — таблица недоступна.
drop policy if exists "Service role full access to telegram_rag_chunks" on public.telegram_rag_chunks;
create policy "Service role full access to telegram_rag_chunks"
    on public.telegram_rag_chunks
    for all
    using (auth.role() = 'service_role')
    with check (auth.role() = 'service_role');

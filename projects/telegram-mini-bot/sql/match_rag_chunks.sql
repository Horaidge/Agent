-- Поиск чанков по косинусному расстоянию (pgvector).
-- Выполни в Supabase → SQL один раз, после таблицы telegram_rag_chunks.

create or replace function public.match_telegram_rag_chunks(
    query_embedding vector(1536),
    match_count int default 10
)
returns table (
    id uuid,
    content text,
    source text,
    metadata jsonb,
    similarity float
)
language sql
stable
parallel safe
as $$
    select
        t.id,
        t.content,
        t.source,
        t.metadata,
        (1 - (t.embedding <=> query_embedding))::float as similarity
    from public.telegram_rag_chunks t
    where t.embedding is not null
    order by t.embedding <=> query_embedding
    limit greatest(1, least(match_count, 50));
$$;

comment on function public.match_telegram_rag_chunks is 'RAG: top-K по вектору (cosine distance)';

grant execute on function public.match_telegram_rag_chunks(vector(1536), int) to service_role;

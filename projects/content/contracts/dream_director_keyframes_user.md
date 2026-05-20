Верни JSON строго в формате:
{
  "key_frames": {
    "status": "pending_confirmation",
    "items": [
      {
        "frame_index": 1,
        "short_label": "короткий заголовок кадра",
        "moment_description": "что происходит прямо сейчас (одно действие или состояние)",
        "subjects_in_frame": ["кто в кадре"],
        "environment": "окружение / зона",
        "visual_focus": "главный визуальный акцент",
        "hero_state": "состояние героя (эмоция, поза, направление взгляда)",
        "uses_reference_ids": ["ref_id из global_references"],
        "image_prompt": "готовый промпт для генерации одного изображения этого кадра",
        "scene_boundary": "new_scene|continues_previous",
        "continues_from_frame_index": null,
        "source_scene_indices": [1, 2],
        "video_bridge_prompt": "краткая подсказка для будущего i2v между этим и следующим кадром или пустая строка"
      }
    ]
  },
  "video_plan": {
    "status": "pending_confirmation",
    "segments": [
      {
        "from_frame_index": 1,
        "to_frame_index": 2,
        "link_note": "как два кадра склеиваются визуально / по смыслу"
      }
    ],
    "scene_flow": [
      {
        "frame_index": 1,
        "narrative_role": "new_scene|continuation",
        "note": "связь с сценарием сценариста"
      }
    ]
  },
  "playground_notes": "кратко: что будет сгенерировано после подтверждения"
}
Правила:
- Не дублируй сценариста построчно: выдай полную цепочку визуальных моментов — столько кадров, сколько нужно, чтобы передать все существенные изменения, действия и повороты сна (без искусственного сжатия).
- Один кадр = одно действие или одно устойчивое состояние.
- continues_from_frame_index: номер предыдущего key frame, если scene_boundary=continues_previous.
- video_plan.segments: какие пары кадров пойдут в связку видео (не обязательно все подряд).
- ref_id в uses_reference_ids должны совпадать с планом global_references.

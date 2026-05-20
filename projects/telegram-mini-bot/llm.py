"""Обратная совместимость: ChatAgent перенесён в agent.py."""
from __future__ import annotations

from agent import AgentReply, ChatAgent

__all__ = ["AgentReply", "ChatAgent"]

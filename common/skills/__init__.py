"""統一匯出 common/skills 套件對外的介面。"""
from .base import Skill
from .registry import SkillRegistry

__all__ = ["Skill", "SkillRegistry"]

"""從資料夾載入所有 *.yaml 定義的 skill，並提供查詢/關鍵字比對。"""
from pathlib import Path
from typing import Union

import yaml

from .base import Skill


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def load_dir(self, skills_dir: Union[str, Path]) -> None:
        # 掃描資料夾下所有 *.yaml，依 Skill 的欄位結構解析後存進字典
        skills_dir = Path(skills_dir)
        if not skills_dir.exists():
            return
        for f in sorted(skills_dir.glob("*.yaml")):
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            skill = Skill(**data)
            self._skills[skill.name] = skill

    def get(self, name: str) -> Skill:
        return self._skills[name]

    def find_by_keyword(self, text: str) -> list[Skill]:
        # 依 trigger_keywords 做簡單比對，讓 Manager 可以依任務內容動態挑 skill
        text_lower = text.lower()
        return [s for s in self._skills.values() if any(k.lower() in text_lower for k in s.trigger_keywords)]

    def all(self) -> list[Skill]:
        return list(self._skills.values())

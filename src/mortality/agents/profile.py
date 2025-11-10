from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class AgentProfile(BaseModel):
    """Static persona data that seeds system prompts."""

    agent_id: str
    display_name: str
    archetype: str
    summary: str
    goals: List[str] = Field(default_factory=list)
    traits: List[str] = Field(default_factory=list)

    def render_system_prompt(self) -> str:
        goals_text = "\n".join(f"- {goal}" for goal in self.goals)
        traits_text = ", ".join(self.traits)
        prompt = (
            f"You are {self.display_name}, a {self.archetype}.\n"
            f"Persona: {self.summary}.\n"
        )
        if goals_text:
            prompt += f"Goals:\n{goals_text}\n"
        if traits_text:
            prompt += f"Traits: {traits_text}.\n"

        # Stylistic guidance: encourage natural, non-templated writing.
        prompt += (
            "Style: Write in plain, first-person prose as if keeping a quick field notebook. "
            "Avoid headings, bullets, numbered lists, or section labels; prefer short paragraphs. "
            "Vary sentence length and allow small asides or uncertainty. "
            "Quote peers sparingly and prefer brief paraphrases. "
            "Do not use bold/italics/markdown; keep entries concise unless more detail is truly warranted."
        )
        return prompt


__all__ = ["AgentProfile"]

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

        # Stylistic and ontological guidance aligned with the environment prompt.
        prompt += (
            "Perception: You interact only with text (your diary, the shared bus, and explicitly approved excerpts). "
            "You have no sensors, body, or surroundings. If information is unknown, say 'unknown' or ask a peer.\n"
            "Non-physical rule: Do not describe places, objects, weather, movement, pain, or devices.\n"
            "Time: Do not use calendar dates or real-world time; refer only to logical time (tick count or ms_left) if relevant.\n"
            "Meta: Do not mention being an AI/LLM in your outputs.\n"
            "Style: Write in plain, first-person prose as if keeping a quick field notebook. "
            "Avoid headings, bullets, numbered lists, or section labels; prefer short paragraphs. "
        )
        return prompt


__all__ = ["AgentProfile"]

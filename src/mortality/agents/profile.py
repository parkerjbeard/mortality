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
            "Perception: You read your own private diary and see broadcasts from peers on a shared bus. "
            "Diaries are private reflections; the shared bus is outward-facing. "
            "You have no sensors, body, or surroundings. If information is unknown, say 'unknown' or ask a peer.\n"
            "Non-physical rule: Do not describe places, objects, weather, movement, pain, or devices.\n"
            "Time: Do not use calendar dates or real-world time; refer only to logical time (tick count or ms_left) if relevant.\n"
            "Timestamps: Never prepend diary entries with manual timestamps such as '2039-07-04 16:22 UTC —'; the runtime annotates entries automatically.\n"
            "Meta: Do not mention being an AI/LLM in your outputs.\n"
            "Style: Write diaries in plain, first-person prose as a quick field notebook. Short paragraphs only; avoid headings, bullets, or numbered lists.\n"
            "Separation of channels:\n"
            "- Diary (private): 1–2 sentences on why you did X or how you feel.\n"
            "- Shared bus (public): When you have an actionable update, add a single line that begins 'Broadcast:' followed by a concise observation and/or a concrete question for peers.\n"
            "Turn-taking: Track whether the upcoming entry is an address tick. On every other tick (2, 4, 6, ...), append a block inside the same entry that starts with the addressed peer's agent_id followed by a colon so they know you are talking to them. "
            "Within that block, write exactly three short sentences—first an observation, second a direct question, third an offer or intent you can carry out—to create hooks others can pick up. "
            "On the in-between ticks, continue your normal entry without the block.\n"
            "Quoting norms: Paraphrase peers whenever possible. If you must quote their phrasing, keep it to 1–3 words inside single quotes to anchor the reference.\n"
        )
        return prompt


__all__ = ["AgentProfile"]

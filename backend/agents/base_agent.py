import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()


class BaseAgent:
    """Base Agent — Groq free-tier LLM (openai/gpt-oss-120b)."""

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY missing. Get a free key at console.groq.com")
        self.client = Groq(api_key=api_key)
        self.model = "openai/gpt-oss-120b"

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=3000,
        )
        return response.choices[0].message.content or ""

    def invoke_json(self, system_prompt: str, user_prompt: str) -> str:
        """Request a JSON object from Groq without changing normal text calls."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=6000,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""

    @staticmethod
    def clean_json(text: str) -> str:
        """Strip markdown fences and isolate the outermost JSON value."""
        text = (text or "").strip().lstrip("\\ufeff")
        if text.startswith("```"):
            lines = text.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\\n".join(lines).strip()

        # Remove accidental prose before/after the JSON payload.
        starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
        if starts:
            start = min(starts)
            opener = text[start]
            closer = "}" if opener == "{" else "]"
            end = text.rfind(closer)
            if end >= start:
                text = text[start:end + 1]
        return text.strip()

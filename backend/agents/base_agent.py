import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

class BaseAgent:
    """Base Agent — Groq free-tier LLM (openai/gpt-oss-120b, 14400 req/day free)"""

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY missing. Get a free key at console.groq.com")
        self.client = Groq(api_key=api_key)
        self.model  = "openai/gpt-oss-120b"

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=3000,
        )
        return response.choices[0].message.content

    @staticmethod
    def clean_json(text: str) -> str:
        """Strip markdown code fences from LLM response."""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

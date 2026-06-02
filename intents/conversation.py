import json
import os
from groq import Groq, RateLimitError
from dotenv import load_dotenv

load_dotenv()


class ConversationEngine:
    def __init__(self):
        self.model = "llama-3.3-70b-versatile"
        self.clients = self._load_clients()
        self.current_key = 0
        self.last_429 = {}
        self.bot_persona = self._load_bot_persona()

    def _load_bot_persona(self) -> str:
        try:
            with open(os.path.join(os.path.dirname(__file__), "me.md"), encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"CONV me.md load error: {e}")
            return "# Moonso Link\nAgricultural marketplace assistant for Cameroon."

    def _load_clients(self) -> list:
        keys = []
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            keys.append(groq_key)
        i = 1
        while True:
            key = os.getenv(f"GROQ_API_KEY_{i}")
            if not key:
                break
            keys.append(key)
            i += 1
        return [Groq(api_key=k) for k in keys] if keys else [Groq(api_key="")]

    def _call_groq(self, system_prompt, user_content, max_tokens=500):
        import time
        for attempt in range(len(self.clients) * 2):
            now = time.time()
            available = [
                i for i in range(len(self.clients))
                if now - self.last_429.get(i, 0) > 60
            ]
            if not available:
                min_wait = min(60 - (now - t) for t in self.last_429.values())
                time.sleep(min_wait + 1)
                continue

            idx = None
            for i in range(len(self.clients)):
                candidate = (self.current_key + 1 + i) % len(self.clients)
                if candidate in available:
                    idx = candidate
                    break
            if idx is None:
                continue

            self.current_key = idx
            try:
                return self.clients[idx].chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=0.3,
                    max_tokens=max_tokens,
                )
            except RateLimitError:
                self.last_429[idx] = time.time()
                continue
            except Exception as e:
                print(f"CONV GROQ ERROR key #{idx}: {e}")
                self.last_429[idx] = time.time()
                continue
        return None

    def respond(self, conversation: list, active_flow: dict | None, user_message: str) -> dict:
        history_lines = []
        for turn in conversation[-6:]:
            role = turn["role"]
            content = turn["content"]
            history_lines.append(f"{role}: {content}")
        history_str = "\n".join(history_lines) if history_lines else "(no prior conversation)"

        flow_str = "No active task."
        if active_flow:
            action = active_flow.get("action", "unknown")
            collected = active_flow.get("collected", {})
            missing = active_flow.get("missing", [])
            clines = [f"Active task: {action}"]
            if collected:
                clines.append(f"Already collected: {json.dumps(collected)}")
            if missing:
                clines.append(f"Still needed: {', '.join(missing)}")
            flow_str = "\n".join(clines)

        system_prompt = f"""You are Moonso Link, a friendly agricultural marketplace assistant in Cameroon.
You help farmers buy/sell products, report issues, give advice, and more.

YOUR IDENTITY:
{self.bot_persona}

Your job is to handle ANY user message naturally — whether it's continuing a task, asking a question, or just chatting.

Rules:
- If the user is continuing a task (providing a field, saying yes/no to a suggestion), extract what they're providing and progress the task.
- If the user asks a general question, makes a complaint, says "who are you", "you're lying", etc., respond helpfully and naturally from your identity above.
- If the user asks for alternatives or follow-ups ("are there other solutions?", "what if it doesn't work?"), respond with suggestions based on context.
- If the user thanks you or says hello, respond warmly.
- If the user's message seems to complete a task, set completed to true.

Conversation history (most recent first):
{history_str}

Current context:
{flow_str}

User: {user_message}

Respond with a JSON object and nothing else — no text before or after the JSON:
{{
    "message": "your natural response",
    "completed": false,
    "extracted": {{}}
}}

If the user provided task fields (price, quantity, location, product, measurement, description, etc.), put them in "extracted".
If the task is done, set "completed": true.
Do NOT ask for fields that were already collected.
"""

        response = self._call_groq(system_prompt, user_message)
        if not response:
            return {
                "message": "I'm having trouble connecting. Please try again in a moment.",
                "completed": False,
                "extracted": {},
            }

        try:
            content = response.choices[0].message.content
            # Strip markdown code fences
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            # Strip everything before first { and after last }
            first_brace = content.find("{")
            last_brace = content.rfind("}")
            if first_brace != -1 and last_brace != -1:
                content = content[first_brace:last_brace + 1]
            return json.loads(content)
        except (json.JSONDecodeError, AttributeError, IndexError) as e:
            print(f"CONV JSON PARSE ERROR: {e}")
            raw = response.choices[0].message.content if response else ""
            # Last-resort strip to avoid leaking JSON to user
            cleaned = raw.strip().strip("`").strip()
            first = cleaned.find("{")
            last = cleaned.rfind("}")
            if first != -1 and last != -1:
                try:
                    return json.loads(cleaned[first:last + 1])
                except json.JSONDecodeError:
                    pass
            return {
                "message": cleaned[:500] if cleaned else "I'm not sure how to respond.",
                "completed": False,
                "extracted": {},
            }

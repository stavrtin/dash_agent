# test_ollama.py
from openai import OpenAI
from prompts import SYSTEM_PROMPT

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
    timeout=300.0,
)

print("Шаг 1: короткий запрос...")
resp = client.chat.completions.create(
    model="qwen3:8b",
    messages=[{"role": "user", "content": "Скажи привет"}],
    max_tokens=50,
)
print("OK:", resp.choices[0].message.content)

print()
print("Шаг 2: длинный запрос с SYSTEM_PROMPT...")
long_system = "Ты — ассистент. " * 500   # ~5 KB текста
resp = client.chat.completions.create(
    model="qwen3:8b",
    messages=[
        {"role": "system", "content": long_system},
        {"role": "user", "content": "Скажи привет"},
    ],
    max_tokens=50,
)
print("OK:", resp.choices[0].message.content)

print()
print("Шаг 3: настоящий SYSTEM_PROMPT из prompts.py...")
resp = client.chat.completions.create(
    model="qwen3:8b",
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Скажи привет"},
    ],
    max_tokens=200,
)
print("OK:", resp.choices[0].message.content[:200])
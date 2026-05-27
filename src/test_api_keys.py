import os
from dotenv import load_dotenv

load_dotenv()

openai_key = os.getenv("OPENAI_API_KEY")
anthropic_key = os.getenv("ANTHROPIC_API_KEY")

print("OpenAI key loaded:", openai_key is not None)
print("Anthropic key loaded:", anthropic_key is not None)
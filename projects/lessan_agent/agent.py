import logging
import os
try:
    import openai
except ImportError:
    openai = None
from utils import setup_logging, sanitize_input
from config import load_config

class Agent:
    def __init__(self):
        self.config = load_config()
        self.logger = setup_logging(
            level=self.config.get("log_level", logging.INFO),
            log_file=self.config.get("log_file")
        )
        self.logger.info("Agent initialized.")
        if openai is not None:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                self.logger.warning("OPENAI_API_KEY environment variable not set.")
            else:
                openai.api_key = api_key
        else:
            self.logger.warning("OpenAI module not available. AI features will be disabled.")

    def generate_response(self, prompt: str) -> str:
        if openai is None:
            self.logger.error("OpenAI module not installed. Cannot generate response.")
            return "Sorry, the AI backend is not available. Please install the OpenAI package."
        try:
            response = openai.Completion.create(
                engine=self.config.get("model", "gpt-4"),
                prompt=prompt,
                max_tokens=self.config.get("max_tokens", 2000),
                temperature=self.config.get("temperature", 0.7),
                n=1,
                stop=None,
            )
            return response.choices[0].text.strip()
        except Exception as e:
            self.logger.error(f"Failed to generate response: {e}")
            return "Sorry, I encountered an error while processing your request."

    def process_input(self, user_input: str) -> str:
        cleaned = sanitize_input(user_input)
        if not cleaned:
            self.logger.debug("Received empty input after sanitization.")
            return "I didn't receive any input."
        self.logger.debug(f"Processing sanitized input: {cleaned}")
        return self.generate_response(cleaned)

if __name__ == "__main__":
    # Simple interactive test when run directly
    agent = Agent()
    print("Lessan Agent test mode. Type 'exit' to quit.")
    while True:
        user = input("You: ")
        if user.lower() in ("exit", "quit"):
            break
        print("Agent:", agent.process_input(user))
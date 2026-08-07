import logging
import sys
from utils import setup_logging, sanitize_input
from config import load_config
from agent import Agent

def main():
    config = load_config()
    logger = setup_logging(
        level=config.get("log_level", logging.INFO),
        log_file=config.get("log_file")
    )
    logger.info("Starting Lessan agent...")
    try:
        agent = Agent(
            model=config.get("model", "gpt-4"),
            temperature=config.get("temperature", 0.7),
            max_tokens=config.get("max_tokens", 2000),
        )
    except Exception as e:
        logger.exception("Failed to initialize Agent: %s", e)
        sys.exit(1)

    print("Lessan agent REPL. Type 'exit' or 'quit' to stop.")
    while True:
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break

        cleaned = sanitize_input(user_input)
        if not cleaned:
            continue
        if cleaned.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        try:
            response = agent.process_input(cleaned)
            print(f"Agent: {response}")
        except Exception as e:
            logger.exception("Error processing input: %s", e)
            print("Sorry, an error occurred while processing your request.")

    logger.info("Lessan agent stopped.")

if __name__ == "__main__":
    main()
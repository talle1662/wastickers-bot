"""Start the bot:  python run.py

The __main__ guard matters on Windows: the conversion process pool spawns fresh
interpreters that re-import this file, and without it they would each try to
start another bot.
"""

from src.main import main

if __name__ == "__main__":
    main()

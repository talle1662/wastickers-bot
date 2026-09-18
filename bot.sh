#!/usr/bin/env sh
# Opens the control console for the bot.
cd "$(dirname "$0")" || exit 1
exec python3 console.py

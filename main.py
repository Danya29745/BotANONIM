"""
Entry point — initializes DB then launches the bot.
Run: python main.py
"""
import database as db
import bot as bot_module
import asyncio

if __name__ == "__main__":
    db.init_db()
    asyncio.run(bot_module.main())

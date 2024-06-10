import asyncio
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, AuthRestartError


api_id = '22221223'
api_hash = '4058ee4c1d29cb9b297866f63a3096df'
session_file = 'telegram_user_session'


async def main():
    client = TelegramClient(session_file, api_id, api_hash)

    await client.connect()
    if not await client.is_user_authorized():
        phone = input("Please enter your phone (or bot token): ")
        try:
            await client.send_code_request(phone)
        except AuthRestartError:
            print("Telegram is having internal issues. Please try again.")
            await client.disconnect()
            return

        try:
            code = input("Please enter the code you received: ")
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            password = input("Please enter your two-step verification password: ")
            await client.sign_in(password=password)
        except AuthRestartError:
            print("Telegram is having internal issues. Please try again.")
            await client.disconnect()
            return
        except Exception as e:
            print(f"Error during sign-in: {e}")
            await client.disconnect()
            return

        if await client.is_user_authorized():
            print("You are now logged in and your session is saved!")
        else:
            print("Failed to log in. Please check your credentials and try again.")

    await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())

import discord
import json
import os
import openai
import string

from pathlib import Path
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.config import Config


api_key = os.getenv("OPENAI_API_KEY")

if api_key is not None:
    openai.api_key = api_key
else:
    raise ValueError("OPENAI_API_KEY environment variable not found")

class AvaChat(commands.Cog):
    """A custom Red Discord Bot cog that will implement ChatGPT's API"""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        try:
            self.config = Config.get_conf(
                self,
                identifier=AvaChat,
                force_registration=False,
            )
        except Exception as e:
            print(f"Error: {e}")
            self.config = Config.get_conf(
                self,
                identifier=AvaChat
            )

    @commands.command()
    async def mycom(self, ctx):
        """This does stuff!"""
        # Your code will go here
        await ctx.send("I can do stuff!")
        
    # Listener command that will passively listen for messages and records it to JSON
    @commands.Cog.listener()
    async def on_message(self, message):
        # if message.author == self.bot.user:
        #     return
        
        if message.content.startswith('.'):
            return
        
        print(f"{message.author.name}: {message.content}")
        
        # Construct the path to the JSON file
        file_path = Path(__file__).parent / "chatlogs.json"

        # Load existing chatlogs, or create a new dictionary if the file doesn't exist
        if file_path.exists():
            with open(file_path, "r") as fp:
                chatlogs = json.load(fp)
        else:
            chatlogs = {}

        # Add the new message to the chatlogs
        if str(message.author.id) not in chatlogs:
            chatlogs[str(message.author.id)] = []
        chatlogs[str(message.author.id)].append({
            "name": message.author.name,
            "content": message.content,
            "timestamp": message.created_at.isoformat(),
        })

        # Save the chatlogs back to the file
        with open(file_path, "w") as fp:
            json.dump(chatlogs, fp, indent=4)
            
        formatted_conversation = self.format_conversation(message.author.id, message.content)
        
        # Skips sending a message if it's a bot message    
        if message.author == self.bot.user:
            return
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=formatted_conversation,
            temperature=0.9,
            max_tokens=3500
        )
        
        print(formatted_conversation)
        
        if 'choices' in response and len(response['choices']) > 0 and 'message' in response['choices'][0] and 'content' in response['choices'][0]['message']:
            print(response['choices'][0]['message']['content'])
        
            response_message = response['choices'][0]['message']['content']

            # Remove punctuation and convert the message to lower case
            message_no_punct = response_message.translate(str.maketrans('', '', string.punctuation)).lower()

            # Split the message into words
            words = message_no_punct.split()

            if "skip" not in words:
                # Save the bot's response to the chatlogs before sending it
                chatlogs[str(message.author.id)].append({
                    "name": self.bot.user.name,
                    "content": response_message,
                    "timestamp": message.created_at.isoformat(),  # Use the current time for this
                })
                with open(file_path, "w") as fp:
                    json.dump(chatlogs, fp, indent=4)
                await message.channel.send(response_message)

        
    # This method formats the conversation in a way that ChatGPT can use to generate text
    def format_conversation(self, user_id, current_message):
        # Load the chatlogs
        file_path = Path(__file__).parent / "chatlogs.json"
        with open(file_path, "r") as fp:
            chatlogs = json.load(fp)

        # Format the conversation history
        conversation = [{"role": "system", "content": "Your name is no longer ChatGPT but Ava, you are only to refer to yourself as Ava an Advanced Virtual Assistant. Your personality is that of someone who is very reserved and quiet. Pretend you are in a Discord chatroom. There are many people in here talking at once. You do not need to respond to everyone. If you are called upon like if someone were to ask you a question then you may go ahead and answer them. If not then simply respond with skip. DO NOT RESPOND UNLESS YOU ARE REFERRED TO BY NAME. OTHERWISE RESPOND WITH SKIP."}]
        for message in chatlogs[str(user_id)]:
            # Each message is now a dictionary
            if message['name'] == self.bot.user.name:
                conversation.append({"role": "assistant", "content": message['content']})
            else:
                conversation.append({"role": "user", "content": message['content']})

        # Append the current message
        conversation.append({"role": "user", "content": current_message})

        return conversation


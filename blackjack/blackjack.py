
import discord
from discord.ext import commands
from random import randint

import aiohttp

from imgurpython import ImgurClient

from .utils.dataIO import dataIO
from .utils import checks

from PIL import Image,ImageDraw,ImageDraw2

import os
import asyncio
import sys

class Blackjack:

    def __init__(self, bot):

        self.bot = bot
        self.sttg_file_path = "data/blackjack/settings.json"
        self.settings = dataIO.load_json("data/blackjack/settings.json")

        self.game_state = "null"
        self.timer = 0
        self.players = {}

        self.deck = {}

        for suit in ["hearts", "diamonds", "clubs", "spades"]:
            self.deck[suit] = {}
            for i in range(2, 11):
                self.deck[suit][i] = {}
                self.deck[suit][i]["rank"] = str(i)
                self.deck[suit][i]["value"] = i

            self.deck[suit][1] = {}
            self.deck[suit][1]["rank"] = "ace"
            self.deck[suit][1]["value"] = 11

            self.deck[suit][11] = {}
            self.deck[suit][11]["rank"] = "jack"
            self.deck[suit][11]["value"] = 10

            self.deck[suit][12] = {}
            self.deck[suit][12]["rank"] = "queen"
            self.deck[suit][12]["value"] = 10

            self.deck[suit][13] = {}
            self.deck[suit][13]["rank"] = "king"
            self.deck[suit][13]["value"] = 10


    @commands.group(pass_context=True,no_pm=True,name="blackjack", aliases=["bj"])
    async def _blackjack(self, ctx):
        """Play some blackjack"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)

    @_blackjack.command(pass_context=True, no_pm=True)
    async def start(self, ctx):
        """Start a game of blackjack"""
        if self.game_state == "null":
            self.game_state = "pregame"
            await self.blackjack_game(ctx)
        else:
            await self.bot.say("A blackjack game is already in progress!")

    @_blackjack.command(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_server=True)
    async def stop(self, ctx):
        """Stop the current game of blackjack (no refunds)"""

        if self.game_state == "null":
            await self.bot.say("There is no game currently running")
        else:
            self.game_state = "null"
            await self.bot.say("**Blackjack has been stopped**")


    @_blackjack.command(pass_context=True, no_pm=True)
    async def bet(self, ctx, bet: int):
        """Join the game of blackjack with your opening bet"""
        player = ctx.message.author

        if self.bot.get_cog('Economy').bank.can_spend(player, bet) and self.game_state == "pregame":
            if bet < self.settings["BLACKJACK_MIN"] or (bet > self.settings["BLACKJACK_MAX"] and self.settings["BLACKJACK_MAX_ENABLED"]):
                await self.bot.say("{0}, bet must be between {1} and {2}.".format(player.name, self.settings["BLACKJACK_MIN"], self.settings["BLACKJACK_MAX"]))
            else:
                em = discord.Embed(title = '', description = '', colour= 0x95270e)
                em.set_author(name = player.name, icon_url = player.avatar_url)

                if not (player in self.players.keys()):
                    em.add_field(name = 'Bet Placed', value = '{0}'.format(bet))
                    self.bot.get_cog('Economy').bank.withdraw_credits(player, bet)

                else:
                    em.add_field(name = 'Bet Placed', value = '{0}'.format(bet))
                    self.bot.get_cog('Economy').bank.deposit_credits(player, bet)
                    self.bot.get_cog('Economy').bank.withdraw_credits(player, bet)

                self.players[player] = {}
                self.players[player]["curr_hand"] = 0
                self.players[player]["hand"] = {}
                self.players[player]["hand"][0] = {}
                self.players[player]["hand"][0]["card"] = {}
                self.players[player]["hand"][0]["ranks"] = []
                self.players[player]["hand"][0]["bet"] = bet
                self.players[player]["hand"][0]["standing"] = False
                self.players[player]["hand"][0]["blackjack"] = False

                em.add_field(name = 'Current Balance', value = '{0}'.format(self.bot.get_cog('Economy').bank.get_balance(player)))
                await self.bot.send_message(ctx.message.channel, embed = em)

        elif self.game_state == "null":
            await self.bot.say("There is currently no game running, type `r!!blackjack start` to begin one")

        elif self.game_state != "pregame" and self.game_state != "null":
            await self.bot.say("There is currently a game in progress, wait for the next game")

        elif not self.bot.get_cog('Economy').bank.can_spend(player, bet):
            await self.bot.say("{0}, you need an account with enough funds to play blackjack".format(player.name))

    @commands.command(pass_context=True, no_pm=True, name="bet")
    async def _clean_bet(self,ctx,bt: int):
        await ctx.invoke(self.bet, bt)

    @_blackjack.command(pass_context=True, no_pm=True)
    async def hit(self, ctx):
        """Hit and draw another card"""
        player = ctx.message.author

        card = await self.draw_card(player)
        curr_hand = self.players[player]["curr_hand"]
        ranks = self.players[player]["hand"][curr_hand]["ranks"]
        count = await self.count_hand(player, curr_hand)

        if self.game_state == "game" and self.players[player]["hand"][curr_hand]["standing"] == False:

            if count > 21 and len(self.players[player]["hand"]) == self.players[player]["curr_hand"] + 1:
                mesg = "{0} has **busted**!".format(player.name)
                self.players[player]["hand"][curr_hand]["standing"] = True

            elif count > 21 and len(self.players[player]["hand"]) > self.players[player]["curr_hand"] + 1:
                mesg = "{0} has **busted** on their current hand! Moving on to next split hand!".format(player.name)
                self.players[player]["curr_hand"] += 1
                self.players[player]["hand"][curr_hand]["standing"] = True

            elif "ace" in ranks:
                mesg = "{0} has hit and drawn a {1}, totaling their hand to {2} ({3})".format(player.name, card, str(count), str(count - 10))

            else:
                mesg = "{0} has hit and drawn a {1}, totaling their hand to {2}".format(player.name, card, count)

            if self.settings["BLACKJACK_IMAGES_ENABLED"]:
                await self.show_hand(player, curr_hand, ctx.message, mesg)

        elif self.game_state != "game":
            await self.bot.say("{0}, you cannot hit right now".format(player.name))

        elif self.players[player]["hand"][curr_hand]["standing"]:
            await self.bot.say("{0}, you are standing and cannot hit".format(player.name))


    @commands.command(pass_context=True, no_pm=True, name="hit")
    async def _clean_hit(self,ctx):
        await ctx.invoke(self.hit)


    @_blackjack.command(pass_context=True, no_pm=True, name="stand", aliases=["stay"])
    async def stand(self, ctx):
        """Finishing drawing and stand with your current cards"""
        player = ctx.message.author
        curr_hand = self.players[player]["curr_hand"]
        if self.game_state == "game" and not self.players[player]["hand"][curr_hand]["standing"]:
            count = await self.count_hand(player, self.players[player]["curr_hand"])

            if len(self.players[player]["hand"]) == self.players[player]["curr_hand"] + 1:
                await self.bot.say("{0} has stood with a hand totaling to {1}".format(player.name, str(count)))

            else:
                await self.bot.say("{0} has stood with a hand totaling to {1}. Moving on to next split hand!".format(player.name, str(count)))
                self.players[player]["curr_hand"] += 1

            self.players[player]["hand"][curr_hand]["standing"] = True

        elif self.game_state != "game":
            await self.bot.say("{0}, you cannot stand right now".format(player.name))

        elif self.players[player]["hand"][curr_hand]["standing"]:
            await self.bot.say("{0}, you are already standing".format(player.name))


    @commands.command(pass_context=True, no_pm=True, name="stand", aliases=["stay"])
    async def _clean_stand(self,ctx):
        await ctx.invoke(self.stand)

    @_blackjack.command(pass_context=True, no_pm=True)
    async def double(self, ctx):
        """Double your original bet and draw one last card"""
        player = ctx.message.author
        curr_hand = self.players[player]["curr_hand"]
        bet = self.players[player]["hand"][curr_hand]["bet"]

        if self.bot.get_cog('Economy').bank.can_spend(player, bet) and not self.players[player]["hand"][curr_hand]["standing"] and self.game_state == "game":

            mesg = await self.bot.say("{0} has doubled down, totaling their bet to {1}".format(player.name, self.players[player]["hand"][curr_hand]["bet"]))

            self.players[player]["hand"][curr_hand]["bet"] += bet
            self.bot.get_cog('Economy').bank.withdraw_credits(player, bet)

            card = await self.draw_card(player)
            count = await self.count_hand(player, self.players[player]["curr_hand"])

            if count > 21 and len(self.players[player]["hand"]) == self.players[player]["curr_hand"] + 1:
                mesg = "{0} has **busted**!".format(player.name)
                self.players[player]["hand"][curr_hand]["standing"] = True

            elif count > 21 and len(self.players[player]["hand"]) > self.players[player]["curr_hand"] + 1:
                mesg = "{0} has **busted**! Moving on to next split hand!".format(player.name)
                self.players[player]["curr_hand"] += 1
                self.players[player]["hand"][curr_hand]["standing"] = True

            elif count < 21 and len(self.players[player]["hand"]) == self.players[player]["curr_hand"] + 1:
                mesg = "{0} has doubled and drawn a {1}, totaling their hand to {2}".format(player.name, card, count)
                self.players[player]["hand"][curr_hand]["standing"] = True

            elif count < 21 and len(self.players[player]["hand"]) > self.players[player]["curr_hand"] + 1:
                mesg = "{0} has doubled and drawn a {1}, totaling their hand to {2}. Moving on to next split hand!".format(player.name, card, count)
                self.players[player]["curr_hand"] += 1
                self.players[player]["hand"][curr_hand]["standing"] = True

            if self.settings["BLACKJACK_IMAGES_ENABLED"]:
                await self.show_hand(player, curr_hand, ctx.message, mesg)

        elif self.game_state != "game":
            await self.bot.say("{0}, you cannot double down right now!".format(player.name))

        elif self.players[player]["hand"][curr_hand]["standing"]:
            await self.bot.say("{0}, you are standing and cannot double!".format(player.name))

        elif not self.bot.get_cog('Economy').bank.can_spend(player, bet):
            await self.bot.say("{0}, you do not have enough money to double down!".format(player.name))

    @commands.command(pass_context=True, no_pm=True, name="double")
    async def _clean_double(self,ctx):
        await ctx.invoke(self.double)

    @_blackjack.command(pass_context=True, no_pm=True)
    async def split(self, ctx):
        """Split your hand into two seperate hands if you have two cards of the same rank"""
        player = ctx.message.author

        curr_hand = self.players[player]["curr_hand"]
        cards = self.players[player]["hand"][curr_hand]["card"]

        if (cards[0]["value"] == 11 and cards[1]["value"] == 1) or (cards[0]["value"] == 1 and cards[1]["value"] == 11): #reset aces to orginal value
            cards[0]["value"] = 11
            cards[0]["rank"] = "ace"

            cards[1]["value"] = 11
            cards[1]["rank"] = "ace"

        if cards[0]["value"] == cards[1]["value"] and len(cards) == 2 and self.game_state == "game" and not self.players[player]["hand"][curr_hand]["standing"]:
            await self.bot.say( "{0} has split their {1}'s! Play through your first hand and stand to begin your next!".format(player.name, cards[0]["value"]))
            hand_index = len(self.players[player]["hand"])

            self.players[player]["hand"][hand_index] = {}
            self.players[player]["hand"][hand_index]["card"] = {}
            self.players[player]["hand"][hand_index]["ranks"] = []
            self.players[player]["hand"][hand_index]["bet"] = self.players[player]["hand"][curr_hand]["bet"]
            self.players[player]["hand"][hand_index]["standing"] = False
            self.players[player]["hand"][hand_index]["blackjack"] = False

            self.players[player]["hand"][hand_index]["card"][0] = cards[1]
            del cards[1]

            if self.settings["BLACKJACK_IMAGES_ENABLED"]:
                await self.show_hand(player, curr_hand, ctx.message)

        elif self.game_state != "game":
            await self.bot.say("{0}, you cannot split right now!".format(player.name))

        elif self.players[player]["hand"][curr_hand]["standing"]:
            await self.bot.say("{0}, you are standing and cannot split!".format(player.name))

        elif len(cards) != 2:
            await self.bot.say("{0}, you may only split with two cards!".format(player.name))

        elif cards[0]["value"] != cards[1]["value"]:
            await self.bot.say("{0}, you may only split with two cards of the same value!".format(player.name))


    @commands.command(pass_context=True, no_pm=True, name="split")
    async def _clean_split(self,ctx):
        await ctx.invoke(self.split)

    async def blackjack_game(self, ctx):
        while self.game_state != "null":
            if self.game_state == "pregame":
                self.players = {}
                self.timer = 0
                asdf = await self.bot.say(":moneybag::hearts:             `Blackjack started!`              :diamonds::moneybag:\n:moneybag:`Place your bets now to join the round!`:moneybag:")
                await asyncio.sleep(self.settings["BLACKJACK_PRE_GAME_TIME"])

            if self.game_state == "pregame":
                if len(self.players) == 0:
                    await self.bot.say("No bets made, aborting game!")
                    self.game_state = "null"
                else:
                    self.game_state = "drawing"

            if self.game_state == "drawing":
                for player in self.players:

                    card1 = await self.draw_card(player)
                    card2 = await self.draw_card(player)

                    curr_hand = self.players[player]["curr_hand"]
                    ranks = self.players[player]["hand"][curr_hand]["ranks"]
                    count = await self.count_hand(player, curr_hand)

                    if "ace" in ranks and ("jack" in ranks or "queen" in ranks or "king" in ranks):

                        desc = "{0} has a **blackjack**!".format(player.name)
                        self.players[player]["hand"][curr_hand]["blackjack"] = True
                        self.players[player]["hand"][curr_hand]["standing"] = True

                    elif "ace" in ranks:
                        desc = "{0} has drawn a {1} and a {2}, totaling to {3} ({4})!".format(player.name, card1, card2, str(count), str(count-10))

                    else:
                        desc = "{0} has drawn a {1} and a {2}, totaling to {3}!".format(player.name, card1, card2, str(count))

                    if self.settings["BLACKJACK_IMAGES_ENABLED"]:
                            await self.show_hand(player, curr_hand, ctx.message, desc)

                    await asyncio.sleep(1)

                self.players[self.bot] = {}
                self.players[self.bot]["curr_hand"] = 0
                self.players[self.bot]["hand"] = {}
                self.players[self.bot]["hand"][0] = {}
                self.players[self.bot]["hand"][0]["card"] = {}
                self.players[self.bot]["hand"][0]["ranks"] = []

                card = await self.draw_card(self.bot)

                desc = "**The dealer has drawn a {0}!**".format(card)

                if self.settings["BLACKJACK_IMAGES_ENABLED"]:
                    await self.show_hand(self.bot, curr_hand, asdf, desc)

                self.game_state = "game"

            if self.game_state == "game":
                all_stood = True
                for player in self.players:
                    for hand in self.players[player]["hand"]:
                        if player != self.bot and not self.players[player]["hand"][hand]["standing"]:
                            all_stood = False

                if self.timer < self.settings["BLACKJACK_GAME_TIME"] and not all_stood:
                    self.timer += 1
                    await asyncio.sleep(1)
                elif all_stood or self.timer >= self.settings["BLACKJACK_GAME_TIME"]:
                    self.game_state = "endgame"

            if self.game_state == "endgame":

                card = await self.draw_card(self.bot)
                dealer_count = await self.count_hand(self.bot, 0)
                ranks = self.players[self.bot]["hand"][0]["ranks"]
                blackjack = False

                if "ace" in ranks and ("jack" in ranks or "queen" in ranks or "king" in ranks) and len(self.players[self.bot]["hand"][curr_hand]["ranks"]) == 2:
                    blackjack = True

                if dealer_count <= 21 and not blackjack: #if dealer has a normal hand, no bust

                    if "ace" in ranks and dealer_count < 17:
                        desc = "**The dealer has drawn a {0}, totaling his hand to {1} ({2})!**".format(card, str(dealer_count), str(dealer_count - 10))
                    else:
                        desc = "**The dealer has drawn a {0}, totaling his hand to {1}!**".format(card, str(dealer_count))

                    if self.settings["BLACKJACK_IMAGES_ENABLED"]:
                        await self.show_hand(self.bot, curr_hand, ctx.message, desc)

                await asyncio.sleep(1)

                if blackjack: #if dealer has blackjack

                    await self.bot.say("**The dealer has a blackjack!**")

                    for player in self.players:
                        if player != self.bot:
                            for hand in self.players[player]["hand"]:
                                if self.players[player]["hand"][hand]["blackjack"]:
                                    self.bot.get_cog('Economy').bank.deposit_credits(player, self.players[player]["hand"][hand]["bet"])
                                    desc = "{0} ties dealer and pushes!".format(player.name)

                                    if self.settings["BLACKJACK_IMAGES_ENABLED"]:
                                        await self.show_hand(player, curr_hand, ctx.message, desc)

                                else:
                                    desc = "{0} loses with a score of {1}".format(player.name, str(count))

                                    if self.settings["BLACKJACK_IMAGES_ENABLED"]:
                                        await self.show_hand(player, curr_hand, ctx.message, desc)


                    self.game_state = "pregame"
                    await asyncio.sleep(3)

                elif dealer_count > 21: #if dealer busts

                    await self.bot.say("**The dealer has busted!**")
                    for player in self.players:
                        if player != self.bot:
                            for hand in self.players[player]["hand"]:
                                count = await self.count_hand(player, hand)
                                if self.players[player]["hand"][hand]["blackjack"]:
                                    self.bot.get_cog('Economy').bank.deposit_credits(player, self.players[player]["hand"][hand]["bet"] * 2.5)
                                    desc = "{0} beats dealer with a blackjack and wins **{2}**!".format(player.name, str(count), self.players[player]["hand"][hand]["bet"] * 1.5)
                                elif count <= 21:
                                    self.bot.get_cog('Economy').bank.deposit_credits(player, self.players[player]["hand"][hand]["bet"] * 2)
                                    desc = "{0} doesn't bust with a score of {1} and wins **{2}**!".format(player.name, str(count), self.players[player]["hand"][hand]["bet"])
                                else:
                                    desc = "{0} busted and wins nothing".format(player.name)

                    if self.settings["BLACKJACK_IMAGES_ENABLED"]:
                        await self.show_hand(player, curr_hand, ctx.message, desc)

                    self.game_state = "pregame"
                    await asyncio.sleep(3)

                elif dealer_count >= 17: #if dealer stands

                    await self.bot.say("**The dealer stands at {0}!**".format(dealer_count))
                    for player in self.players:
                        if player != self.bot:
                            for hand in self.players[player]["hand"]:
                                count = await self.count_hand(player, hand)
                                if self.players[player]["hand"][hand]["blackjack"]:
                                    self.bot.get_cog('Economy').bank.deposit_credits(player, self.players[player]["hand"][hand]["bet"] * 2.5)
                                    await self.bot.say("{0} beats dealer with a blackjack and wins **{2}**!".format(player.name, str(count), self.players[player]["hand"][hand]["bet"] * 1.5))
                                elif count > 21:
                                    await self.bot.say("{0} busted and wins nothing".format(player.name))
                                elif count > dealer_count:
                                    self.bot.get_cog('Economy').bank.deposit_credits(player, self.players[player]["hand"][hand]["bet"] * 2)
                                    await self.bot.say("{0} beats dealer with a score of {1} and wins **{2}**!".format(player.name, str(count), self.players[player]["hand"][hand]["bet"]))
                                elif count == dealer_count:
                                    self.bot.get_cog('Economy').bank.deposit_credits(player, self.players[player]["hand"][hand]["bet"])
                                    await self.bot.say("{0} ties dealer and pushes!".format(player.name))
                                else:
                                    await self.bot.say("{0} loses with a score of {1}".format(player.name, str(count)))

                    self.game_state = "pregame"
                    await asyncio.sleep(3)

                if self.game_state == "pregame":
                    for player in self.players:
                        if player != self.bot:
                            em = discord.Embed(title = '', description = '', colour= 0x95270e)
                            em.set_author(name = player.name, icon_url = player.avatar_url)
                            em.add_field(name = 'Current Balance', value = '{0}'.format(self.bot.get_cog('Economy').bank.get_balance(player)))
                            await self.bot.send_message(ctx.message.channel, embed = em)
                            #await self.bot.say("{0} now has a balance of: {1}".format(player.name, self.bot.get_cog('Economy').bank.get_balance(player)))

    async def draw_card(self, player):
        suit = randint(1, 4)
        num = randint(1, 13)

        if suit == 1:
            suit = "hearts"
        elif suit == 2:
            suit = "diamonds"
        elif suit == 3:
            suit = "clubs"
        elif suit == 4:
            suit = "spades"

        rank = self.deck[suit][num]["rank"]

        curr_hand = self.players[player]["curr_hand"]
        card_index = len(self.players[player]["hand"][curr_hand]["card"])

        self.players[player]["hand"][curr_hand]["card"][card_index] = {}
        self.players[player]["hand"][curr_hand]["card"][card_index]["suit"] = suit
        self.players[player]["hand"][curr_hand]["card"][card_index]["rank"] = rank
        self.players[player]["hand"][curr_hand]["card"][card_index]["value"] = self.deck[suit][num]["value"]
        self.players[player]["hand"][curr_hand]["ranks"].append(rank)

        await self.count_hand(player, curr_hand) #to change ace names and values in the "ranks" table, don't actually need the count


        if rank == "small_ace":
            rank = "ace"

        return rank + " of " + suit

    async def count_hand(self, player, curr_hand):
        count = 0
        cards = self.players[player]["hand"][curr_hand]["card"]

        for card in cards:
            count += cards[card]["value"]

        for card in cards:
            if count > 21:
                if cards[card]["value"] == 11:
                    cards[card]["value"] = 1
                    cards[card]["rank"] = "small_ace"
                    count -= 10

                    self.players[player]["hand"][curr_hand]["ranks"] = []
                    for card in self.players[player]["hand"][curr_hand]["card"]:
                        self.players[player]["hand"][curr_hand]["ranks"].append(self.players[player]["hand"][curr_hand]["card"][card]["rank"])
                    break
        return count

    async def show_hand(self,player,curr_hand, message, desc:str=None, firstDeal:bool=None):
        cards = self.players[player]["hand"][curr_hand]["card"]
        box1 = (0,0,56,82)
        box2 = (0,0,112,82)
        count = 0

        cRank = ""
        cSuit = ""

        hand = Image.open("data/blackjack/hand/{}_cards.png".format(len(cards)))
        for card in cards:
            cRank = cards[card]["rank"]
            if cRank == "small_ace":
                cRank = "ace"
            cSuit = cards[card]["suit"]
            crd = Image.open("data/blackjack/playing_cards/{}_of_{}.png".format(cRank,cSuit))
            if len(cards) is 1:
                hand.paste(crd, (56,0,112,82))
            else:
                hand.paste(crd, (56*count,0,(56*count)+56,82))
            count += 1
            if player is self.bot:
                hand.save("data/blackjack/hand/{}_hand.png".format("dealer"))
            else:
                hand.save("data/blackjack/hand/{}_hand.png".format(player.name))
            crd.close()
        hand.close()
        imgurclient = ImgurClient("1fd3ef04daf8cab", "f963e574e8e3c17993c933af4f0522e1dc01e230")
        if player is self.bot:
            pic = imgurclient.upload_from_path("data/blackjack/hand/{}_hand.png".format("dealer"))
            em = discord.Embed(title = '', description = desc, colour = 0x002e20 )
            em.set_image(url=pic['link'])
            em.set_author(name='The Dealer')
            await self.bot.send_message(message.channel, embed = em)
        else:
            pic = imgurclient.upload_from_path("data/blackjack/hand/{}_hand.png".format(player.name))
            em = discord.Embed(title = '', description = desc, colour = 0x95270e )
            em.set_image(url=pic['link'])
            em.set_author(name= '{}'.format(player.name), icon_url= player.avatar_url)
            await self.bot.send_message(message.channel, embed = em)

    # async def delete_messages(self, ctx):
    #     server = ctx.message.server
    #     user = ctx.message.server.me
    #     message = ctx.message
    #     if x.author.id == user.id:
    #         await self.bot.delete_message(x)
    #     await self.bot.delete_message(cmdmsg)


    @commands.group(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_server=True)
    async def blackjackset(self, ctx):
        """Changes blackjack settings"""
        if ctx.invoked_subcommand is None:
            msg = "```"
            for k, v in self.settings.items():
                msg += str(k) + ": " + str(v) + "\n"
            msg += "\nType {}help blackjackset to see the list of commands.```".format(ctx.prefix)
            await self.bot.say(msg)


    @blackjackset.command()
    async def blackjackmin(self, bet : int):
        """Minimum blackjack bet"""
        self.settings["BLACKJACK_MIN"] = bet
        await self.bot.say("Minimum bet is now " + str(bet) + " credits.")
        dataIO.save_json(self.sttg_file_path, self.settings)

    @blackjackset.command()
    async def blackjackmax(self, bet : int):
        """Maximum blackjack bet"""
        self.settings["BLACKJACK_MAX"] = bet
        await self.bot.say("Maximum bet is now " + str(bet) + " credits.")
        dataIO.save_json(self.sttg_file_path, self.settings)

    @blackjackset.command()
    async def blackjackmaxtoggle(self):
        """Toggle the use of a maximum blackjack bet"""
        self.settings["BLACKJACK_MAX_ENABLED"] = not self.settings["BLACKJACK_MAX_ENABLED"]
        if self.settings["BLACKJACK_MAX_ENABLED"]:
            await self.bot.say("Maximum bet is now enabled.")
        else:
            await self.bot.say("Maximum bet is now disabled.")
        dataIO.save_json(self.sttg_file_path, self.settings)

    @blackjackset.command()
    async def blackjackpretime(self, time : int):
        """Set the pregame time for players to bet"""
        self.settings["BLACKJACK_PRE_GAME_TIME"] = time
        await self.bot.say("Blackjack pre-game time is now " + str(time))
        dataIO.save_json(self.sttg_file_path, self.settings)

    @blackjackset.command()
    async def blackjacktime(self, time : int):
        """Set the maximum game time given to hit"""
        self.settings["BLACKJACK_GAME_TIME"] = time
        await self.bot.say("Blackjack maximum game time is now " + str(time))
        dataIO.save_json(self.sttg_file_path, self.settings)

    @blackjackset.command()
    async def blackjackimagestoggle(self):
        """Toggle the use of card images"""
        self.settings["BLACKJACK_IMAGES_ENABLED"] = not self.settings["BLACKJACK_IMAGES_ENABLED"]
        if self.settings["BLACKJACK_IMAGES_ENABLED"]:
            await self.bot.say("Card images are now enabled.")
        else:
            await self.bot.say("Card images are now disabled.")
        dataIO.save_json(self.sttg_file_path, self.settings)

    @blackjackset.command()
    async def paydaytime(self, seconds : int):
        """Seconds between each payday"""
        self.settings["PAYDAY_TIME"] = seconds
        await self.bot.say("Value modified. At least " + str(seconds) + " seconds must pass between each payday.")
        dataIO.save_json(self.sttg_file_path, self.settings)

    @blackjackset.command()
    async def paydaycredits(self, credits : int):
        """Credits earned each payday"""
        self.settings["PAYDAY_CREDITS"] = credits
        await self.bot.say("Every payday will now give " + str(credits) + " credits.")



def check_folders():
    if not os.path.exists("data/blackjack"):
        print("Making a blackjack folder...")
        os.makedirs("data/blackjack")

def check_files():
    settings = {
        "BLACKJACK_MIN" : 10,
        "BLACKJACK_MAX" : 5000,
        "BLACKJACK_MAX_ENABLED" : False,
        "BLACKJACK_GAME_TIME" : 60,
        "BLACKJACK_PRE_GAME_TIME" : 15,
        "BLACKJACK_IMAGES_ENABLED" : True
    }

    f = "data/blackjack/settings.json"
    if not dataIO.is_valid_json(f):
        print("Creating default blackjack's settings.json...")
        dataIO.save_json(f,settings)

def setup(bot):
    check_folders()
    check_files()
    global ImgurClient
    try:
        from imgurpython import ImgurClient
    except:
        raise RuntimeError("imgurpython is not installed. Do 'pip3 install imgurpython' to use this cog.")
    bot.add_cog(Blackjack(bot))
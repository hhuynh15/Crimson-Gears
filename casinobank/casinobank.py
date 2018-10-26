import discord
from discord.ext import commands
from cogs.utils.dataIO import dataIO
from collections import namedtuple, defaultdict
from datetime import datetime
from random import randint
from copy import deepcopy
from .utils import checks
from __main__ import send_cmd_help
import os
import time
import logging
import io

default_settings = {"PAYDAY_TIME" : 86400, "PAYDAY_CREDITS" : 500}


class BankError(Exception):
    pass


class AccountAlreadyExists(BankError):
    pass


class NoAccount(BankError):
    pass


class InsufficientBalance(BankError):
    pass


class NegativeValue(BankError):
    pass


class SameSenderAndReceiver(BankError):
    pass


class Bank:
    def __init__(self, bot, file_path):
        self.accounts = dataIO.load_json(file_path)
        self.bot = bot

    def create_account(self, user, *, initial_balance=0):
        server = user.server
        if not self.account_exists(user):
            if server.id not in self.accounts:
                self.accounts[server.id] = {}
            if user.id in self.accounts:  # Legacy account
                balance = self.accounts[user.id]["balance"]
            else:
                balance = initial_balance
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            account = {"name" : user.name,
                       "balance" : balance,
                       "created_at" : timestamp
                       }
            self.accounts[server.id][user.id] = account
            self._save_bank()
            return self.get_account(user)
        else:
            raise AccountAlreadyExists()

    def account_exists(self, user):
        try:
            self._get_account(user)
        except NoAccount:
            return False
        return True

    def withdraw_credits(self, user, amount):
        server = user.server

        if amount < 0:
            raise NegativeValue()

        account = self._get_account(user)
        if account["balance"] >= amount:
            account["balance"] -= amount
            self.accounts[server.id][user.id] = account
            self._save_bank()
        else:
            raise InsufficientBalance()

    def deposit_credits(self, user, amount):
        server = user.server
        if amount < 0:
            raise NegativeValue()
        account = self._get_account(user)
        account["balance"] += amount
        self.accounts[server.id][user.id] = account
        self._save_bank()

    def set_credits(self, user, amount):
        server = user.server
        if amount < 0:
            raise NegativeValue()
        account = self._get_account(user)
        account["balance"] = amount
        self.accounts[server.id][user.id] = account
        self._save_bank()

    def transfer_credits(self, sender, receiver, amount):
        if amount < 0:
            raise NegativeValue()
        if sender is receiver:
            raise SameSenderAndReceiver()
        if self.account_exists(sender) and self.account_exists(receiver):
            sender_acc = self._get_account(sender)
            if sender_acc["balance"] < amount:
                raise InsufficientBalance()
            self.withdraw_credits(sender, amount)
            self.deposit_credits(receiver, amount)
        else:
            raise NoAccount()

    def can_spend(self, user, amount):
        account = self._get_account(user)
        if account["balance"] >= amount:
            return True
        else:
            return False

    def wipe_bank(self, server):
        self.accounts[server.id] = {}
        self._save_bank()

    def get_server_accounts(self, server):
        if server.id in self.accounts:
            raw_server_accounts = deepcopy(self.accounts[server.id])
            accounts = []
            for k, v in raw_server_accounts.items():
                v["id"] = k
                v["server"] = server
                acc = self._create_account_obj(v)
                accounts.append(acc)
            return accounts
        else:
            return []

    def get_all_accounts(self):
        accounts = []
        for server_id, v in self.accounts.items():
            server = self.bot.get_server(server_id)
            if server is None:  # Servers that have since been left will be ignored
                continue      # Same for users_id from the old bank format
            raw_server_accounts = deepcopy(self.accounts[server.id])
            for k, v in raw_server_accounts.items():
                v["id"] = k
                v["server"] = server
                acc = self._create_account_obj(v)
                accounts.append(acc)
        return accounts

    def get_balance(self, user):
        account = self._get_account(user)
        return account["balance"]

    def get_account(self, user):
        acc = self._get_account(user)
        acc["id"] = user.id
        acc["server"] = user.server
        return self._create_account_obj(acc)

    def _create_account_obj(self, account):
        account["member"] = account["server"].get_member(account["id"])
        account["created_at"] = datetime.strptime(account["created_at"],
                                                  "%Y-%m-%d %H:%M:%S")
        Account = namedtuple("Account", "id name balance "
                                        "created_at server member")
        return Account(**account)

    def _save_bank(self):
        dataIO.save_json("data/economy/bank.json", self.accounts)

    def _get_account(self, user):
        server = user.server
        try:
            return deepcopy(self.accounts[server.id][user.id])
        except KeyError:
            raise NoAccount()


class Economy:
    """Economy
    Get rich and have fun with imaginary currency!"""

    def __init__(self, bot):
        global default_settings
        self.bot = bot
        self.bank = Bank(bot, "data/economy/bank.json")
        self.file_path = "data/economy/settings.json"
        self.settings = dataIO.load_json(self.file_path)
        if "PAYDAY_TIME" in self.settings:  # old format
            default_settings = self.settings
            self.settings = {}
        self.settings = defaultdict(lambda: default_settings, self.settings)
        self.payday_register = defaultdict(dict)
        self.slot_register = defaultdict(dict)

    @commands.group(name="bank", pass_context=True)
    async def _bank(self, ctx):
        """Bank operations"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @_bank.command(pass_context=True, no_pm=True)
    async def register(self, ctx):
        """Registers an account at the bank"""
        user = ctx.message.author
        try:
            account = self.bank.create_account(user)
            await self.bot.say("{}\n```css\nAccount opened. Current balance: {}\n"
                               "Remember to periodically type {}payday to get free credits.\n```".format(user.mention,
                                                                                                         account.balance,ctx.prefix))
            await ctx.invoke(self.payday)
        except AccountAlreadyExists:
            await self.bot.say("{}\n```css\nYou already have an account at the bank.\n```".format(user.mention))

    @commands.command(pass_context=True,no_pm=True, name="register")
    async def _register(self,ctx):
        """Registers an account at the bank"""
        await ctx.invoke(self.register)

    @_bank.command(pass_context=True)
    async def balance(self, ctx, user : discord.Member=None):
        """Shows balance of user.
        Defaults to yours."""
        if not user:
            user = ctx.message.author
            try:
                await self.bot.say("{}\n```css\nYour balance is: {}\n```".format(user.mention, self.bank.get_balance(user)))
            except NoAccount:
                await ctx.invoke(self.register)
        else:
            try:
                await self.bot.say("```css\n{}'s balance is {}```".format(user.name, self.bank.get_balance(user)))
            except NoAccount:
                await self.bot.say("```css\n{} does not have an account registered with the bank.\n```".format(user.name))

    @commands.command(pass_context=True, no_pm=True,name="balance")
    async def _balance(self,ctx, user : discord.Member=None):
        """Shows balance of user.
        Defaults to yours."""
        if not user:
            await ctx.invoke(self.balance)
        else:
            await ctx.invoke(self.balance, user)

    @_bank.command(pass_context=True)
    async def transfer(self, ctx, user : discord.Member, sum : int):
        """Transfer credits to other users."""
        author = ctx.message.author
        try:
            self.bank.transfer_credits(author, user, sum)
            logger.info("{}({}) transferred {} credits to {}({})".format(
                author.name, author.id, sum, user.name, user.id))
            await self.bot.say("```css\n{} credits have been transferred to {}'s account.\n```".format(sum, user.name))
        except NegativeValue:
            await self.bot.say("```css\nYou need to transfer at least 1 credit.\n```")
        except SameSenderAndReceiver:
            await self.bot.say("```css\nYou can't transfer credits to yourself.\n```")
        except InsufficientBalance:
            await self.bot.say("```css\nYou don't have that sum in your bank account.\n```")
        except NoAccount:
            self.bank.withdraw_credits(author,sum)
            await ctx.invoke(self._set,user,sum)

    @commands.command(pass_context=True,no_pm=True,name="transfer")
    async def _transfer(self,ctx,user:discord.Member,sum:int):
        """Transfers credits to other users."""
        if not user:
            await ctx.invoke(self.transfer)
        else:
            await ctx.invoke(self.transfer,user,sum)

    @_bank.command(name="set", pass_context=True, hidden=True)
    @checks.is_owner()
    async def _set(self, ctx, user : discord.Member, sum : int):
        """Sets credits of user's bank account.
        Owner use only."""
        author = ctx.message.author
        try:
            self.bank.set_credits(user, sum)
            logger.info("{}({}) set {} credits to {} ({})".format(author.name, author.id, str(sum), user.name, user.id))
            await self.bot.say("```css\n{}'s credits have been set to {}.\n```".format(user.name, str(sum)))
        except NoAccount:
            self.bank.create_account(user)
            self.bank.set_credits(user, sum)
            balance = self.bank.get_balance(user)
            await self.bot.say("```css\n{} had no existing account so new account opened with balance: {}\n```".format(user.name,
                                                                                                                       str(balance)))

    @_bank.command(name="wipe", pass_context=True, hidden=True)
    @checks.is_owner()
    async def wipe(self,ctx):
        """Wipes all bank account information stored on this server.
        Owner use only."""
        self.bank.wipe_bank(ctx.message.server)
        await self.bot.say("```css\nWipe successful.\n```")

    @_bank.command(pass_context=True,no_pm=True,name="activity",hidden=True)
    @checks.is_owner()
    async def activity(self,ctx,num:int=10):
        """Returns recent bank activity information."""
        log_file_path = "data/economy/economy.log"
        log_file = open(log_file_path, "r", encoding="utf-8")
        count = 0
        ls = "Activity log (descending time order)\n" \
             "==============================================================================\n"
        for line in reversed(log_file.readlines()):
            ls += "{}. {}\n".format(count+1, line)
            count += 1
            if count >= num:
                break
        log_file.close()
        await self.bot.say("```css\n{}\n```".format(ls))

    @commands.command(pass_context=True, no_pm=True)
    async def payday(self, ctx):
        """Get some free credits"""
        author = ctx.message.author
        server = author.server
        id = author.id
        if self.bank.account_exists(author):
            if id in self.payday_register[server.id]:
                seconds = abs(self.payday_register[server.id][id] - int(time.perf_counter()))
                if seconds  >= self.settings[server.id]["PAYDAY_TIME"]:
                    self.bank.deposit_credits(author, self.settings[server.id]["PAYDAY_CREDITS"])
                    self.payday_register[server.id][id] = int(time.perf_counter())
                    await self.bot.say("```css\n{}, {} credits have been added to your account!\n```".format(author.name, str(self.settings[server.id]["PAYDAY_CREDITS"])))
                else:
                    await self.bot.say("{}\n```css\nToo soon. For your next payday you have to wait {}.\n```".format(author.mention, self.display_time(self.settings[server.id]["PAYDAY_TIME"] - seconds)))
            else:
                self.payday_register[server.id][id] = int(time.perf_counter())
                self.bank.deposit_credits(author, self.settings[server.id]["PAYDAY_CREDITS"])
                await self.bot.say("```css\n{}, {} credits have been added to your account!\n```".format(author.name, str(self.settings[server.id]["PAYDAY_CREDITS"])))
        else:
            await self.bot.say("{}\n```css\nYou need an account to receive credits. Type '{}bank register' to open one.\n```".format(author.mention, ctx.prefix))

    @commands.group(pass_context=True)
    async def leaderboard(self, ctx):
        """Server / global leaderboard
        Defaults to server"""
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self._server_leaderboard)

    @leaderboard.command(name="server", pass_context=True)
    async def _server_leaderboard(self, ctx, top : int=10):
        """Prints out the server's leaderboard
        Defaults to top 10"""
        server = ctx.message.server
        if top < 1:
            top = 10
        bank_sorted = sorted(self.bank.get_server_accounts(server),
                             key=lambda x: x.balance, reverse=True)
        if len(bank_sorted) < top:
            top = len(bank_sorted)
        topten = bank_sorted[:top]
        highscore = ""
        place = 1
        for acc in topten:
            highscore += str(place).ljust(len(str(top))+1)
            highscore += (acc.name+" ").ljust(23-len(str(acc.balance)))
            highscore += str(acc.balance) + "\n"
            place += 1
        if highscore:
            if len(highscore) < 1985:
                await self.bot.say("```py\n"+highscore+"```")
            else:
                await self.bot.say("```css\nThe leaderboard is too big to be displayed. Try with a lower <top> parameter.\n```")
        else:
            await self.bot.say("```css\nThere are no accounts in the bank.\n```")


    @leaderboard.command(name="global")
    @checks.is_owner()
    async def _global_leaderboard(self, top : int=10):
        """Prints out the global leaderboard
        Defaults to top 10"""
        if top < 1:
            top = 10
        bank_sorted = sorted(self.bank.get_all_accounts(),
                             key=lambda x: x.balance, reverse=True)
        unique_accounts = []
        for acc in bank_sorted:
            if not self.already_in_list(unique_accounts, acc):
                unique_accounts.append(acc)
        if len(unique_accounts) < top:
            top = len(unique_accounts)
        topten = unique_accounts[:top]
        highscore = ""
        place = 1
        for acc in topten:
            highscore += str(place).ljust(len(str(top))+1)
            highscore += ("{} |{}| ".format(acc.name, acc.server.name)).ljust(23-len(str(acc.balance)))
            highscore += str(acc.balance) + "\n"
            place += 1
        if highscore:
            if len(highscore) < 1985:
                await self.bot.say("```py\n"+highscore+"```")
            else:
                await self.bot.say("```css\nThe leaderboard is too big to be displayed. Try with a lower <top> parameter.\n```")
        else:
            await self.bot.say("```css\nThere are no accounts in the bank.\n```")

    def already_in_list(self, accounts, user):
        for acc in accounts:
            if user.id == acc.id:
                return True
        return False

    @commands.group(pass_context=True, no_pm=True)
    @checks.is_owner()
    async def economyset(self, ctx):
        """Changes economy module settings"""
        server = ctx.message.server
        settings = self.settings[server.id]
        if ctx.invoked_subcommand is None:
            msg = "```"
            for k, v in settings.items():
                msg += "{}: {}\n".format(k, v)
            msg += "```"
            await send_cmd_help(ctx)
            await self.bot.say(msg)


    @economyset.command(pass_context=True)
    async def paydaytime(self, ctx, seconds : int):
        """Seconds between each payday"""
        server = ctx.message.server
        self.settings[server.id]["PAYDAY_TIME"] = seconds
        await self.bot.say("```css\nValue modified. At least " + self.display_time(seconds) + " must pass between each payday.\n```")
        dataIO.save_json(self.file_path, self.settings)

    @economyset.command(pass_context=True)
    async def paydaycredits(self, ctx, credits : int):
        """Credits earned each payday"""
        server = ctx.message.server
        self.settings[server.id]["PAYDAY_CREDITS"] = credits
        await self.bot.say("```css\nEvery payday will now give " + str(credits) + " credits.\n```")
        dataIO.save_json(self.file_path, self.settings)

    def display_time(self, seconds, granularity=2):
        intervals = (
            ('weeks', 604800),
            ('days', 86400),
            ('hours', 3600),
            ('minutes', 60),
            ('seconds', 1),
        )

        result = []

        for name, count in intervals:
            value = seconds // count
            if value:
                seconds -= value * count
                if value == 1:
                    name = name.rstrip('s')
                result.append("{} {}".format(value, name))
        return ', '.join(result[:granularity])


def check_folders():
    if not os.path.exists("data/economy"):
        print("Creating data/economy folder...")
        os.makedirs("data/economy")


def check_files():

    f = "data/economy/settings.json"
    if not dataIO.is_valid_json(f):
        print("Creating default economy's settings.json...")
        dataIO.save_json(f, {})

    f = "data/economy/bank.json"
    if not dataIO.is_valid_json(f):
        print("Creating empty bank.json...")
        dataIO.save_json(f, {})


def setup(bot):
    global logger
    check_folders()
    check_files()
    logger = logging.getLogger("red.economy")
    if logger.level == 0:  # Prevents the logger from being loaded again in case of module reload
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(filename='data/economy/economy.log', encoding='utf-8', mode='a')
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt="[%d/%m/%Y %H:%M]"))
        logger.addHandler(handler)
    bot.add_cog(Economy(bot))
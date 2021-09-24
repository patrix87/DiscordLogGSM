import os
import time
import urllib
import asyncio
import requests
import subprocess
from datetime import datetime

# discord
import discord
from discord.ext import tasks

# discordgsm
from bin import *
from servers import Servers, ServerCache
from settings import Settings

# [HEROKU] get and load servers json from SERVERS_JSON env directly
servers_json = os.getenv('SERVERS_JSON')
if servers_json and servers_json.strip():
    with open('configs/servers.json', 'w') as file:
        file.write(servers_json)

# [HEROKU] Check bot token and servers.json valid before start
if 'DGSM_TOKEN' in os.environ:
    invite_link = subprocess.run(['python3', 'getbotinvitelink.py'], stdout=subprocess.PIPE, shell=False).stdout.decode('utf8')
    if 'https://discord.com/api/oauth2/authorize?client_id=' not in invite_link:
        while True:
            time.sleep(1)
    with open('configs/servers.json', 'r') as file:
        try:
            Servers().get()
        except Exception as e:
            print(e)
            while True:
                time.sleep(1)

# env values
VERSION = '1.8.3'
SETTINGS = Settings.get()
DGSM_TOKEN = os.getenv('DGSM_TOKEN', SETTINGS['token'])
DGSM_PREFIX = os.getenv("DGSM_PREFIX", SETTINGS.get('prefix', '!'))
ROLE_ID = os.getenv('ROLE_ID', SETTINGS.get('role_id', '123'))
CUSTOM_IMAGE_URL = os.getenv('CUSTOM_IMAGE_URL', SETTINGS.get('image_url', ''))
REFRESH_RATE = int(os.getenv('REFRESH_RATE', SETTINGS['refreshrate'])) if int(os.getenv('REFRESH_RATE', SETTINGS['refreshrate'])) > 5 else 5
PRESENCE_TYPE = int(os.getenv('PRESENCE_TYPE', SETTINGS.get('presence_type', 3)))
PRESENCE_RATE = int(os.getenv('PRESENCE_RATE', SETTINGS.get('presence_rate', 5))) if int(os.getenv('PRESENCE_RATE', SETTINGS.get('presence_rate', 5))) > 1 else 1

FIELD_STATUS = os.getenv("FIELD_STATUS", SETTINGS["fieldname"]["status"])
FIELD_TITLE = os.getenv("FIELD_STATUS", SETTINGS["fieldname"]["status"])
FIELD_LOCK = os.getenv("FIELD_STATUS", SETTINGS["fieldname"]["status"])
FIELD_PASSWORD = os.getenv("FIELD_STATUS", SETTINGS["fieldname"]["status"])
FIELD_MAP = os.getenv("FIELD_STATUS", SETTINGS["fieldname"]["status"])
FIELD_MAP = os.getenv("FIELD_STATUS", SETTINGS["fieldname"]["status"])
FIELD_ADDRESS = os.getenv("FIELD_ADDRESS", SETTINGS["fieldname"]["address"])
FIELD_PORT = os.getenv("FIELD_PORT", SETTINGS["fieldname"]["port"])
FIELD_GAME = os.getenv("FIELD_GAME", SETTINGS["fieldname"]["game"])
FIELD_CURRENTMAP = os.getenv("FIELD_CURRENTMAP", SETTINGS["fieldname"]["currentmap"])
FIELD_PLAYERS = os.getenv("FIELD_PLAYERS", SETTINGS["fieldname"]["players"])
FIELD_COUNTRY = os.getenv("FIELD_COUNTRY", SETTINGS["fieldname"]["country"])

class DiscordGSM():
    def __init__(self, bot):
        print('\n----------------')
        print('Github: \thttps://github.com/DiscordGSM/DiscordGSM')
        print('Discord:\thttps://discord.gg/Cg4Au9T')
        print('----------------\n')

        self.bot = bot
        self.servers = Servers()
        self.server_list = self.servers.get()
        self.messages = []
        self.message_error_count = self.current_display_server = 0

    def start(self):
        self.print_to_console(f'Starting DiscordGSM v{VERSION}...')
        self.query_servers.start()    

    def cancel(self):
        self.query_servers.cancel()
        self.print_servers.cancel()
        self.presense_load.cancel()

    async def on_ready(self):
        # set username and avatar
        icon_file_name = 'images/discordgsm' + ('DGSM_TOKEN' in os.environ and '-heroku' or '') + '.png'
        with open(icon_file_name, 'rb') as file:
            try:
                await bot.user.edit(username='DiscordGSM', avatar=file.read())
            except:
                pass

        # print info to console
        print('\n----------------')
        print(f'Logged in as:\t{bot.user.name}')
        print(f'Robot ID:\t{bot.user.id}')
        app_info = await bot.application_info()
        print(f'Owner ID:\t{app_info.owner.id} ({app_info.owner.name})')
        print('----------------\n')

        self.print_presense_hint()
        self.presense_load.start()

        await self.set_channels_permissions()
        self.print_to_console(f'Query server and send discord embed every {REFRESH_RATE} seconds...')
        await self.refresh_discord_embed()
        self.print_servers.start()

    # query the servers
    @tasks.loop(seconds=REFRESH_RATE)
    async def query_servers(self):
        server_count = self.servers.query()
        self.print_to_console(f'{server_count} servers queried')

    # pre-query servers before ready
    @query_servers.before_loop
    async def before_query_servers(self):
        self.print_to_console('Pre-Query servers...')
        server_count = self.servers.query()
        self.print_to_console(f'{server_count} servers queried')
        await self.bot.wait_until_ready()
        await self.on_ready()
    
    # send messages to discord
    @tasks.loop(seconds=REFRESH_RATE)
    async def print_servers(self):
        if self.message_error_count < 20:
            updated_count = 0
            for i in range(len(self.server_list)):
                try:
                    await self.messages[i].edit(content=('frontMessage' in self.server_list[i] and self.server_list[i]['frontMessage'].strip()) and self.server_list[i]['frontMessage'] or None, embed=self.get_embed(self.server_list[i]))
                    updated_count += 1
                except:
                    self.message_error_count += 1
                    self.print_to_console(f'ERROR: message {i} fail to edit, message deleted or no permission. Server: {self.server_list[i]["addr"]}:{self.server_list[i]["port"]}')

            self.print_to_console(f'{updated_count} messages updated')
        else:
            self.message_error_count = 0
            self.print_to_console(f'Message ERROR reached, refreshing...')
            await self.refresh_discord_embed()
    
    # refresh discord presense
    @tasks.loop(minutes=PRESENCE_RATE)
    async def presense_load(self):
        # 1 = display number of servers, 2 = display total players/total maxplayers, 3 = display each server one by one every 10 minutes
        if len(self.server_list) == 0:
            activity_text = f'Command: {DGSM_PREFIX}dgsm'
        if PRESENCE_TYPE <= 1:
            activity_text = f'{len(self.server_list)} game servers'
        elif PRESENCE_TYPE == 2:
            total_activeplayers = total_maxplayers = 0
            for server in self.server_list:
                server_cache = ServerCache(server['addr'], server['port'])
                data = server_cache.get_data()
                if data and server_cache.get_status() == 'Online':
                    total_activeplayers += int(data['players'])
                    total_maxplayers += int(data['maxplayers'])
                  
            activity_text = f'{total_activeplayers}/{total_maxplayers} active players' if total_maxplayers > 0 else '0 players' 
        elif PRESENCE_TYPE >= 3:
            if self.current_display_server >= len(self.server_list):
                self.current_display_server = 0

            server_cache = ServerCache(self.server_list[self.current_display_server]['addr'], self.server_list[self.current_display_server]['port'])
            data = server_cache.get_data()
            if data and server_cache.get_status() == 'Online':
                activity_text = f'{data["players"]}/{data["maxplayers"]} on {data["name"]}' if int(data["maxplayers"]) > 0 else '0 players'
            else:
                activity_text = None

            self.current_display_server += 1

        if activity_text != None:
            await bot.change_presence(status=discord.Status.online, activity=discord.Activity(name=activity_text, type=3))
            self.print_to_console(f'Discord presence updated | {activity_text}')

    # set channels permissions before sending new messages
    async def set_channels_permissions(self):
        channels = [server['channel'] for server in self.server_list]
        channels = list(set(channels))  # remove duplicated channels
        for channel in channels:
            try:
                await bot.get_channel(channel).set_permissions(bot.user, read_messages=True, send_messages=True, reason='Display servers embed')
                self.print_to_console(f'Channel: {channel} | Permissions: read_messages, send_messages | Permissions set successfully')
            except:
                self.print_to_console(f'Channel: {channel} | Permissions: read_messages, send_messages | ERROR: Permissions fail to set')

    # remove old discord embed and send new discord embed
    async def refresh_discord_embed(self):
        # refresh servers.json cache
        self.servers = Servers()
        self.server_list = self.servers.get()

        # remove old discord embed
        channels = [server['channel'] for server in self.server_list]
        channels = list(set(channels)) # remove duplicated channels
        for channel in channels:
            await bot.get_channel(channel).purge(check=lambda m: m.author==bot.user)
        
        # send new discord embed
        self.messages = [await bot.get_channel(s['channel']).send(content=('frontMessage' in s and s['frontMessage'].strip()) and s['frontMessage'] or None, embed=self.get_embed(s)) for s in self.server_list]
    
    def print_to_console(self, value):
        print(datetime.now().strftime('%Y-%m-%d %H:%M:%S: ') + value)

    # 1 = display number of servers, 2 = display total players/total maxplayers, 3 = display each server one by one every 10 minutes
    def print_presense_hint(self):
        if PRESENCE_TYPE <= 1:
            hints = 'number of servers'
        elif PRESENCE_TYPE == 2:
            hints = 'total players/total maxplayers'
        elif PRESENCE_TYPE >= 3:
            hints = f'each server one by one every {PRESENCE_RATE} minutes'
        self.print_to_console(f'Presence update type: {PRESENCE_TYPE} | Display {hints}')

    # get game server discord embed
    def get_embed(self, server):
        # load server cache
        server_cache = ServerCache(server['addr'], server['port'])

        # load server data
        data = server_cache.get_data()

        if data:
            # load server status Online/Offline
            status = server_cache.get_status()

            emoji = (status == 'Online') and ':green_circle:' or ':red_circle:'

            if status == 'Online':
                if int(data['maxplayers']) <= int(data['players']):
                    color = discord.Color.from_rgb(240, 71, 71) # red
                elif int(data['maxplayers']) <= int(data['players']) * 2:
                    color = discord.Color.from_rgb(250, 166, 26) # yellew
                else:
                    color = discord.Color.from_rgb(67, 181, 129) # green
                    try:
                        if 'color' in server:
                            h = server['color'].lstrip('#')
                            rgb = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
                            color = discord.Color.from_rgb(rgb[0], rgb[1], rgb[2])
                    except Exception as e:
                        self.print_to_console(e)
            else:
                color = discord.Color.from_rgb(32, 34, 37) # dark

            title = (data['password'] and ':lock: ' or '') + f'`{data["name"]}`'
            custom = ('custom' in server) and server['custom'] or None
            if custom and custom.strip():
                embed = discord.Embed(title=title, description=custom, color=color)
            elif server['type'] == 'SourceQuery' and not custom:
                embed = discord.Embed(title=title, description=f'Connect: steam://connect/{data["addr"]}:{server["port"]}', color=color)
            else:
                embed = discord.Embed(title=title, color=color)

            embed.add_field(name=FIELD_STATUS, value=f'{emoji} **{status}**', inline=True)
            embed.add_field(name=f'{FIELD_ADDRESS}:{FIELD_PORT}', value=f'`{data["addr"]}:{data["port"]}`', inline=True)
 
            flag_emoji = ('country' in server) and (':flag_' + server['country'].lower() + f': {server["country"]}') or ':united_nations: Unknown'
            embed.add_field(name=FIELD_COUNTRY, value=flag_emoji, inline=True)
            if len(data['game']) > 0:
                embed.add_field(name=FIELD_GAME, value=data['game'], inline=True)
            if len(data['map']) > 0:
                embed.add_field(name=FIELD_CURRENTMAP, value=data['map'], inline=True)

            if status == 'Online':
                value = str(data['players']) # example: 20/32
                if int(data['bots']) > 0: value += f' ({data["bots"]})' # example: 20 (2)/32
            else:
                value = '0' # example: 0/32

            embed.add_field(name=FIELD_PLAYERS, value=f'{value}/{data["maxplayers"]}', inline=True)

            if 'image_url' in server:
                image_url = str(server['image_url'])
            else:
                image_url = (CUSTOM_IMAGE_URL and CUSTOM_IMAGE_URL.strip()) and CUSTOM_IMAGE_URL or f'https://github.com/DiscordGSM/Map-Thumbnails/raw/master/{urllib.parse.quote(data["game"])}'
                image_url += f'/{urllib.parse.quote(data["map"])}.jpg'

            embed.set_thumbnail(url=image_url)
        else:
            # server fail to query
            color = discord.Color.from_rgb(240, 71, 71) # red
            embed = discord.Embed(title='ERROR', description=f'{FIELD_STATUS}: :warning: **Fail to query**', color=color)
            embed.add_field(name=f'{FIELD_ADDRESS}:{FIELD_PORT}', value=f'{server["addr"]}:{server["port"]}', inline=True)
        
        embed.set_footer(text=f'DiscordGSM v{VERSION} | 📺Game Server Monitor | Last update: ' + datetime.now().strftime('%a, %Y-%m-%d %I:%M:%S%p'), icon_url='https://github.com/DiscordGSM/DiscordGSM/raw/master/images/discordgsm.png')
        
        return embed

    def get_server_list(self):
        return self.server_list

bot = discord.Client()

discordgsm = DiscordGSM(bot)
discordgsm.start()

bot.run(DGSM_TOKEN)

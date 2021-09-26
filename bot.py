import os
import time
import urllib
from datetime import datetime

# discord
import discord
from discord.ext import tasks

# discordgsm
from servers import Servers, ServerCache

# load env
import os
from dotenv import load_dotenv
load_dotenv()

VERSION = '2.0.0'
# Get Env
PREFIX=os.getenv("DGSM_PREFIX")
ROLEID=os.getenv("DGSM_ROLEID")
CUSTOM_IMAGE_URL=os.getenv("DGSM_CUSTOM_IMAGE_URL")
REFRESH_RATE=int(os.getenv("DGSM_REFRESH_RATE"))
PRESENCE_TYPE=int(os.getenv("DGSM_PRESENCE_TYPE"))
PRESENCE_RATE=int(os.getenv("DGSM_PRESENCE_RATE"))
FIELD_STATUS=os.getenv("DGSM_FIELD_STATUS")
FIELD_ADDRESS=os.getenv("DGSM_FIELD_ADDRESS")
FIELD_PORT=os.getenv("DGSM_FIELD_PORT")
FIELD_GAME=os.getenv("DGSM_FIELD_GAME")
FIELD_CURRENTMAP=os.getenv("DGSM_FIELD_CURRENTMAP")
FIELD_PLAYERS=os.getenv("DGSM_FIELD_PLAYERS")
FIELD_COUNTRY=os.getenv("DGSM_FIELD_COUNTRY")
FIELD_LASTUPDATE=os.getenv("DGSM_FIELD_LASTUPDATE")

class DiscordGSM():
    def __init__(self, client):

        self.client = client
        self.servers = Servers()
        self.server_list = self.servers.get()
        self.messages = []
        #number of failed attempt to post.
        self.message_error_count = self.current_display_server = 0

    def start(self):
        self.print_to_console(f'Starting DiscordGSM v{VERSION}...')
        self.query_servers.start()    

    def cancel(self):
        self.query_servers.cancel()
        self.print_servers.cancel()
        self.presense_load.cancel()

    async def on_ready(self):
        # print info to console
        print('\n----------------')
        print(f'Logged in as:\t{client.user.name}')
        print(f'Client ID:\t{client.user.id}')
        app_info = await client.application_info()
        print(f'Owner ID:\t{app_info.owner.id} ({app_info.owner.name})')
        print('----------------\n')

        #Print presence type and rate to console
        self.print_presense_hint()
        #Update bot presence
        self.presense_load.start()

        self.print_to_console(f'Query server and send discord embed every {REFRESH_RATE} seconds...')
        #async refresh embed messages
        await self.refresh_discord_embed()
        #Start main update loop.
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
        await self.client.wait_until_ready()
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
            activity_text = f'Command: {PREFIX}dgsm'
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
            await client.change_presence(status=discord.Status.online, activity=discord.Activity(name=activity_text, type=3))
            self.print_to_console(f'Discord presence updated | {activity_text}')

    # remove old discord embed and send new discord embed
    async def refresh_discord_embed(self):
        # refresh servers.json cache
        self.servers = Servers()
        self.server_list = self.servers.get()

        # remove old discord embed
        channels = [server['channel'] for server in self.server_list]
        channels = list(set(channels)) # remove duplicated channels
        for channel in channels:
            await client.get_channel(channel).purge(check=lambda m: m.author==client.user)
        
        # send new discord embed
        self.messages = [await client.get_channel(s['channel']).send(content=('frontMessage' in s and s['frontMessage'].strip()) and s['frontMessage'] or None, embed=self.get_embed(s)) for s in self.server_list]
    
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
                    color = discord.Color.from_rgb(250, 166, 26) # yellow
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
            
            title = ('title' in server) and server['title'] or (data['password'] and ':lock: ' or '') + f'`{data["name"]}`'
            # if custom is in server and server['custom'] exist use server['custom'] or use None
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
        
        embed.set_footer(text=f'{FIELD_LASTUPDATE}: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        return embed

    def get_server_list(self):
        return self.server_list

client = discord.Client()

discordgsm = DiscordGSM(client)
discordgsm.start()

client.run(os.getenv("DGSM_TOKEN"))

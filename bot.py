import os
import time
import urllib
import asyncio
import sys
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

VERSION = "2.0.0"
# Get Env
PREFIX=os.getenv("DGSM_PREFIX")
ROLEID=os.getenv("DGSM_ROLEID")
CUSTOM_IMAGE_URL=os.getenv("DGSM_CUSTOM_IMAGE_URL")
REFRESH_RATE=int(os.getenv("DGSM_REFRESH_RATE"))
PRESENCE_TYPE=int(os.getenv("DGSM_PRESENCE_TYPE"))
PRESENCE_RATE=int(os.getenv("DGSM_PRESENCE_RATE"))
SEND_DELAY=int(os.getenv("DGSM_SEND_DELAY"))
FIELD_NAME=os.getenv("DGSM_FIELD_NAME")
FIELD_STATUS=os.getenv("DGSM_FIELD_STATUS")
FIELD_ADDRESS=os.getenv("DGSM_FIELD_ADDRESS")
FIELD_PORT=os.getenv("DGSM_FIELD_PORT")
FIELD_GAME=os.getenv("DGSM_FIELD_GAME")
FIELD_CURRENTMAP=os.getenv("DGSM_FIELD_CURRENTMAP")
FIELD_PLAYERS=os.getenv("DGSM_FIELD_PLAYERS")
FIELD_COUNTRY=os.getenv("DGSM_FIELD_COUNTRY")
FIELD_LASTUPDATE=os.getenv("DGSM_FIELD_LASTUPDATE")
FIELD_CUSTOM=os.getenv("DGSM_FIELD_CUSTOM")
FIELD_PASSWORD=os.getenv("DGSM_FIELD_PASSWORD")
FIELD_ONLINE=os.getenv("DGSM_FIELD_ONLINE")
FIELD_OFFLINE=os.getenv("DGSM_FIELD_OFFLINE")
FIELD_UNKNOWN=os.getenv("DGSM_FIELD_UNKNOWN")
SPACER=u"\u200B"

class DiscordGSM():
    def __init__(self, client):

        self.client = client
        self.servers = Servers()
        self.server_list = self.servers.get()
        #number of failed attempt to post.
        self.message_error_count = self.current_display_server = 0

    def start(self):
        self.print_to_console(f'Starting DiscordGSM v{VERSION}...')
        #Query Servers
        self.query_servers.start()

    def cancel(self):
        self.query_servers.cancel()
        self.update_servers.cancel()
        self.presence_load.cancel()

    async def on_ready(self):
        # print info to console
        print("\n----------------")
        print(f'Logged in as:\t{client.user.name}')
        print(f'Client ID:\t{client.user.id}')
        app_info = await client.application_info()
        print(f'Owner ID:\t{app_info.owner.id} ({app_info.owner.name})')
        print("----------------\n")

        #Update bot presence
        self.presence_load.start()

        self.print_to_console(f'Query server and send discord embed every {REFRESH_RATE} minutes...')
        #async refresh embed messages
        await self.repost_servers()
        #Wait one full loop then Start main update loop.
        await asyncio.sleep(REFRESH_RATE*60)
        self.update_servers.start()

    def print_to_console(self, value):
        print(datetime.now().strftime("%Y-%m-%d %H:%M:%S: ") + value)

    # query the servers
    @tasks.loop(minutes=REFRESH_RATE)
    async def query_servers(self):
        self.servers.refresh()
        self.server_list = self.servers.get()
        server_count = self.servers.query()
        self.print_to_console(f'{server_count} servers queried')

    # pre-query servers before ready
    @query_servers.before_loop
    async def before_query_servers(self):
        self.print_to_console("Pre-Query servers...")
        server_count = self.servers.query()
        self.print_to_console(f'{server_count} servers queried')
        await client.wait_until_ready()
        await self.on_ready()
    
    # send messages to discord
    @tasks.loop(minutes=REFRESH_RATE)
    async def update_servers(self):
        if self.message_error_count < 20:
            updated_count = 0
            for i in range(len(self.server_list)):
                try:
                    await self.messages[i].edit(embed=self.get_embed(self.server_list[i]))
                    updated_count += 1
                except:
                    self.message_error_count += 1
                    self.print_to_console(f'ERROR: message {i} failed to edit, message deleted or no permission. Server: {self.server_list[i]["address"]}:{self.server_list[i]["port"]}')
                finally:
                    await asyncio.sleep(SEND_DELAY)
       
            self.print_to_console(f'{updated_count} messages updated')
        else:
            self.message_error_count = 0
            self.print_to_console(f'Message ERROR reached, refreshing...')
            await self.repost_servers()

    # remove old discord embed and send new discord embed
    async def repost_servers(self):
        # refresh servers.json cache
        self.servers = Servers()
        self.server_list = self.servers.get()
        self.messages = []
        repost_count = 0
        # remove old discord embed
        channels = [server["channel"] for server in self.server_list]
        channels = list(set(channels)) # remove duplicated channels
        for channel in channels:
            try:
                await client.get_channel(channel).purge(check=lambda m: m.author==client.user)
            except:
                self.print_to_console(f'ERROR: Unable to delete messages.')
            finally:
                await asyncio.sleep(SEND_DELAY)

        # send new discord embed
        for s in self.server_list:
            try:
                message = await client.get_channel(s["channel"]).send(embed=self.get_embed(s))
                self.messages.append(message)
                repost_count += 1
            except:
                self.message_error_count += 1
                self.print_to_console(f'ERROR: message fail to send, no permission. Server: {s["address"]}:{s["port"]}')
            finally:
                await asyncio.sleep(SEND_DELAY)

        self.print_to_console(f'{repost_count} messages reposted')
    
    # refresh discord presence
    @tasks.loop(minutes=PRESENCE_RATE)
    async def presence_load(self):
        # 1 = display number of servers, 2 = display total players/total maxplayers, 3 = display each server one by one every 10 minutes
        if len(self.server_list) == 0:
            activity_text = f'Command: {PREFIX}dgsm'
        if PRESENCE_TYPE <= 1:
            activity_text = f'{len(self.servers.get_distinct_servers())} game servers'
        elif PRESENCE_TYPE == 2:
            total_activeplayers = total_maxplayers = 0
            for server in self.server_list:
                server_cache = ServerCache(server["address"], server["port"])
                data = server_cache.get_data()
                if data and server_cache.get_status() == "Online":
                    total_activeplayers += int(data["players"])
                    total_maxplayers += int(data["maxplayers"])
                  
            activity_text = f'{total_activeplayers}/{total_maxplayers} active players' if total_maxplayers > 0 else "0 players" 
        elif PRESENCE_TYPE >= 3:
            if self.current_display_server >= len(self.server_list):
                self.current_display_server = 0

            server_cache = ServerCache(self.server_list[self.current_display_server]["address"], self.server_list[self.current_display_server]["port"])
            data = server_cache.get_data()
            if data and server_cache.get_status() == "Online":
                activity_text = f'{data["players"]}/{data["maxplayers"]} on {data["name"]}' if int(data["maxplayers"]) > 0 else "0 players"
            else:
                activity_text = None

            self.current_display_server += 1

        if activity_text != None:
            try:
                await client.change_presence(status=discord.Status.online, activity=discord.Activity(name=activity_text, type=3))
                self.print_to_console(f'Discord presence updated | {activity_text}')
            except:
                self.print_to_console(f'ERROR: Unable to update presence.')

    def get_value(dataset, field, default = None):
        if type(dataset) != dict and field not in dataset and dataset[field] is None and dataset[field] == "": 
            return default
        return dataset[field]

    # get game server discord embed
    def get_embed(self, server):
        # load server cache
        server_cache = ServerCache(server["address"], server["port"])
        # load server data
        data = server_cache.get_data()

        #
        #   [LOCK] Title or Game                                       [ Thumbnail ]
        #                                                              [   Image   ]    
        #   Description (FIELD_CUSTOM)  
        #   
        #   FIELD_STATUS            FIELD_NAME                  EMPTY_FIELD
        #   [icon] Status           Hostname or Title or Game   Empty Char.
        #
        #   FIELD_PLAYERS           FIELD_ADDRESS               FIELD_PASSWORD
        #   Number of players       server adresse:port         The password or Empty Field.
        #
        #   FIELD_COUNTRY           FIELD_CURRENTMAP
        #   [Country Flag] or Empty   Current Map
        #
        #   [Footer thumbnail] | Bot name + Version | Long name | Last update Time *(used as spacer to strech embed)
        #

        # Parsing Data
        if "locked" in server and type(server["locked"]) == bool:
            lock = server["locked"]
        elif "password" in data and type(data["locked"]) == bool:
            lock = data["locked"]
        else:
            lock = False

        title = self.get_value(server, "title") or self.get_value(data, "game") or self.get_value(server, "game")
        if lock:
            title = f':lock: {title.capitalize()}'
        else:
            title = f':unlock: {title.capitalize()}'
        
        description = self.get_value(server, "custom") or SPACER
        
        if server_cache.get_status() == "Online":
            status = f':green_circle: **{FIELD_ONLINE}**'
        elif server_cache.get_status() == "Offline":
            status = f':red_circle: **{FIELD_OFFLINE}**'
        else:
            status = f':yellow_circle: **{FIELD_UNKNOWN}**'

        hostname = self.get_value(server, "hostname") or self.get_value(data, "name") or SPACER

        players = self.get_value(data, "players", "?")

        bots = self.get_value(data, "bots")

        players_string = f'{players}({bots})' if bots is not None and bots > 0 else f'{players}'

        maxplayers = self.get_value(data, "maxplayers") or self.get_value(server, "maxplayers") or "?"
        
        port = self.get_value(data, "port")
        address = self.get_value(server, "public_address") or self.get_value(data, "address") and port and f'{data["address"]}:{port}' or SPACER

        password = self.get_value(server, "password")

        country = self.get_value(server, "country")

        map = self.get_value(server, "map") or self.get_value(data, "map")

        image_url = self.get_value(server, "image_url")

        # Color : if offline = Black, if full = red, if half = yellow, if less = green, if defined = defined.
        if server_cache.get_status() == "Online" and players != "?" and maxplayers != "??":
            if players >= maxplayers:
                color = discord.Color.from_rgb(240, 71, 71) # red
            elif players >= maxplayers / 2:
                color = discord.Color.from_rgb(250, 166, 26) # yellow
            else:
                color = discord.Color.from_rgb(67, 181, 129) # green
        else:
            color = discord.Color.from_rgb(0, 0, 0) # black
        # color is defined
        try:
            if "color" in server:
                h = server["color"].lstrip("#")
                rgb = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
                color = discord.Color.from_rgb(rgb[0], rgb[1], rgb[2])
        except:
            pass

        # Build embed

        embed = discord.Embed(title=title, description=description, color=color)
        embed.add_field(name=FIELD_STATUS, value=status, inline=True)
        embed.add_field(name=FIELD_NAME, value=hostname, inline=True)
        embed.add_field(name=SPACER, value=SPACER, inline=True)
        embed.add_field(name=FIELD_PLAYERS, value=players_string, inline=True)
        embed.add_field(name=FIELD_ADDRESS, value=address, inline=True)
        if password is None:
            embed.add_field(name=SPACER, value=SPACER, inline=True)
        else:
            embed.add_field(name=FIELD_PASSWORD, value=password, inline=True)
        if not country:
            embed.add_field(name=SPACER, value=SPACER, inline=True)
        else:
            embed.add_field(name=FIELD_PASSWORD, value=f':flag_{country.lower()}:', inline=True)
        if map:
            embed.add_field(name=FIELD_CURRENTMAP, value=map, inline=True)

        if image_url:
            embed.set_thumbnail(url=image_url)

        embed.set_footer(text=f'DiscordGSM v{VERSION} | Game Server Monitor | {FIELD_LASTUPDATE}: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}                   {SPACER}', icon_url=CUSTOM_IMAGE_URL)
        
        return embed

client = discord.Client()

discordgsm = DiscordGSM(client)
discordgsm.start()

client.run(os.getenv("DGSM_TOKEN"))

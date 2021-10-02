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

VERSION = "1.0.L"
# Get Env
PREFIX = os.getenv("DGSM_PREFIX")
ROLEID = os.getenv("DGSM_ROLEID")
CUSTOM_IMAGE_URL = os.getenv("DGSM_CUSTOM_IMAGE_URL")
REFRESH_RATE = int(os.getenv("DGSM_REFRESH_RATE"))
PRESENCE_TYPE = int(os.getenv("DGSM_PRESENCE_TYPE"))
PRESENCE_RATE = int(os.getenv("DGSM_PRESENCE_RATE"))
SEND_DELAY = int(os.getenv("DGSM_SEND_DELAY"))
ERROR_TRESHOLD = int(os.getenv("DGSM_ERROR_TRESHOLD"))
FIELD_NAME = os.getenv("DGSM_FIELD_NAME")
FIELD_STATUS = os.getenv("DGSM_FIELD_STATUS")
FIELD_ADDRESS = os.getenv("DGSM_FIELD_ADDRESS")
FIELD_PORT = os.getenv("DGSM_FIELD_PORT")
FIELD_GAME = os.getenv("DGSM_FIELD_GAME")
FIELD_CURRENTMAP = os.getenv("DGSM_FIELD_CURRENTMAP")
FIELD_PLAYERS = os.getenv("DGSM_FIELD_PLAYERS")
FIELD_COUNTRY = os.getenv("DGSM_FIELD_COUNTRY")
FIELD_LASTUPDATE = os.getenv("DGSM_FIELD_LASTUPDATE")
FIELD_CUSTOM = os.getenv("DGSM_FIELD_CUSTOM")
FIELD_PASSWORD = os.getenv("DGSM_FIELD_PASSWORD")
FIELD_ONLINE = os.getenv("DGSM_FIELD_ONLINE")
FIELD_OFFLINE = os.getenv("DGSM_FIELD_OFFLINE")
FIELD_UNKNOWN = os.getenv("DGSM_FIELD_UNKNOWN")
SPACER=u"\u200B"

class DiscordGSM():
    def __init__(self, client):

        self.client = client
        self.servers = Servers()
        self.server_list = self.servers.get()
        self.message_error_count = self.current_display_server = 0

    def start(self):
        self.print_to_console(f'Starting DiscordGSM v.{VERSION}...')
        self.query_servers.start()
        
    def cancel(self):
        self.query_servers.cancel()
        self.update_messages.cancel()
        self.presence_load.cancel()

        
    async def on_ready(self):
        # print info to console
        print("\n----------------")
        print(f'Logged in as:\t{client.user.name}')
        print(f'Client ID:\t{client.user.id}')
        app_info = await client.application_info()
        print(f'Owner ID:\t{app_info.owner.id} ({app_info.owner.name})')
        print("----------------\n")
        
        self.print_to_console(f'Querying servers and updating messages every {REFRESH_RATE} minutes...')  
        
        self.presence_load.start()
        self.update_messages.start()


    def print_to_console(self, value):
        print(datetime.now().strftime("%Y-%m-%d %H:%M:%S: ") + value)

    async def try_get_message_to_update(self, server):
        try:
            message = await client.get_channel(server["channel"]).fetch_message(server["message_id"])
            #TODO: Missing logic to see if message has been deleted on the server?
            return message
        except Exception as e:
            self.print_to_console(f'ERROR: fetch_message failed for server {server} \n{e}')
            return None
        finally:
            await asyncio.sleep(SEND_DELAY)

    # query the servers
    @tasks.loop(minutes=REFRESH_RATE)
    async def query_servers(self):
        self.server_list = self.servers.refresh()
        server_count = self.servers.query()
        self.print_to_console(f'{server_count} servers queried')

    # pre-query servers before ready
    @query_servers.before_loop
    async def before_query_servers(self):
        self.print_to_console("Pre-Query servers...")
        server_count = self.servers.query()
        self.print_to_console(f'{server_count} servers pre-queried')
        await client.wait_until_ready()
        await self.on_ready()

    @tasks.loop(minutes=REFRESH_RATE)
    async def update_messages(self):
        # Force refresh every update_messages loop for quick info modification
        self.server_list = self.servers.refresh()
        self.messages = [await self.try_get_message_to_update(server) for server in self.server_list]

        if self.message_error_count < ERROR_TRESHOLD:
            updated_count = 0
            for server in self.server_list:
                try:
                    # TODO: Something one line -> not working (m for m in self.messages if m.id == server["message_id"])
                    for m in self.messages:
                        if m.id == server["message_id"]:
                            message = m
                            break

                    await message.edit(embed=self.get_embed(server))
                    updated_count += 1
                except Exception as e:
                    self.message_error_count += 1
                    self.print_to_console(f'ERROR: Server: {server["address"]}:{server["port"]} failed to edit. \n{e}')
                finally:
                    await asyncio.sleep(SEND_DELAY)
       
            self.print_to_console(f'{updated_count} messages updated')
        else:
            self.message_error_count = 0
            self.print_to_console(f'Message ERROR reached, refreshing...')
            await self.repost_messages()

    # remove old discord embed and send new discord embed
    async def repost_messages(self):
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
            except Exception as e:
                self.print_to_console(f'ERROR: Unable to delete messages.\n{e}')
            finally:
                await asyncio.sleep(SEND_DELAY)

        # send new discord embed
        for s in self.server_list:
            try:
                message = await client.get_channel(s["channel"]).send(embed=self.get_embed(s))
                self.messages.append(message)
                s["message_id"] = message.id
                repost_count += 1
            except Exception as e:
                self.message_error_count += 1
                self.print_to_console(f'ERROR: message fail to send, no permission. Server: {s["address"]}:{s["port"]}\n{e}')
            finally:
                self.servers.update_server_file(self.server_list)
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
            except Exception as e:
                self.print_to_console(f'ERROR: Unable to update presence.\n{e}')

    def get_value(self, dataset, field, default = None):
        if type(dataset) != dict or field not in dataset or dataset[field] is None or dataset[field] == "": 
            return default
        return dataset[field]

    def get_embed(self, server):
        server_cache = ServerCache(server["address"], server["port"])
        data = server_cache.get_data()
        cache_status = server_cache.get_status()

        # Evaluate fields
        lock = (server["locked"] if type(self.get_value(server, "locked")) == bool 
            else data["password"] if type(self.get_value(data, "password")) == bool 
            else False)

        title = self.get_value(server, "title") or self.get_value(data, "game") or self.get_value(server, "game")
        title = f':lock: {title}' if lock else  f':unlock: {title}'
        
        description = self.get_value(server, "custom")
        
        status = (f':green_circle: **{FIELD_ONLINE}**' if cache_status == "Online" 
            else f':red_circle: **{FIELD_OFFLINE}**' if cache_status == "Offline" and data is not False 
            else f':yellow_circle: **{FIELD_UNKNOWN}**')

        hostname = self.get_value(server, "hostname") or self.get_value(data, "name") or SPACER
        players_string = self.determinePlayerString(server, data, cache_status)   
        port = self.get_value(data, "port")
        address = self.get_value(server, "public_address") or self.get_value(data, "address") and port and f'{data["address"]}:{port}' or SPACER
        password = self.get_value(server, "password")
        country = self.get_value(server, "country")
        map = None if  self.get_value(server, "map") == False else self.get_value(server, "map") or self.get_value(data, "map")
        image_url = self.get_value(server, "image_url")
        color = self.determineColor(server, data, cache_status)

        # Build embed
        embed = (discord.Embed(title=title, description=description, color=color) if description 
            else discord.Embed(title=title, color=color))

        embed.add_field(name=FIELD_STATUS, value=status, inline=True)
        embed.add_field(name=FIELD_NAME, value=hostname, inline=True)
        embed.add_field(name=SPACER, value=SPACER, inline=True)
        embed.add_field(name=FIELD_PLAYERS, value=players_string, inline=True)
        embed.add_field(name=FIELD_ADDRESS, value=f'`{address}`', inline=True)
 
        if password is None:
            embed.add_field(name=SPACER, value=SPACER, inline=True)
        else:
            embed.add_field(name=FIELD_PASSWORD, value=f'`{password}`', inline=True)

        if country:
            embed.add_field(name=FIELD_COUNTRY, value=f':flag_{country.lower()}:', inline=True)
        if map and not country:
            embed.add_field(name=SPACER, value=SPACER, inline=True)
        if map:
            embed.add_field(name=FIELD_CURRENTMAP, value=map, inline=True)
        if map or country:
            embed.add_field(name=SPACER, value=SPACER, inline=True)
        if image_url:
            embed.set_thumbnail(url=image_url)

        embed.set_footer(text=f'DiscordGSM v.{VERSION} | Game Server Monitor | {FIELD_LASTUPDATE}: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}{SPACER}', icon_url=CUSTOM_IMAGE_URL)
        
        return embed
        

    def determineColor(self, server, data, cache_status):
        players = self.get_value(data, "players", "?")  
        maxplayers = self.get_value(data, "maxplayers") or self.get_value(server, "maxplayers") or "?"

        if cache_status == "Online" and players != "?" and maxplayers != "??":
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

        return color

    def determinePlayerString(self,server, data, cache_status):

        players = self.get_value(data, "players", "?")  
        maxplayers = self.get_value(data, "maxplayers") or self.get_value(server, "maxplayers") or "?"

        bots = self.get_value(data, "bots")

        if cache_status == "Offline": 
            players = 0
            bots = None
        if data is False: 
            players = "?"
            bots = None

        return f'{players}({bots})/{maxplayers}' if bots is not None and bots > 0 else f'{players}/{maxplayers}'

client = discord.Client()

discordgsm = DiscordGSM(client)
discordgsm.start()

client.run(os.getenv("DGSM_TOKEN"))

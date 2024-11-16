import yt_dlp as youtube_dl
import os
import subprocess
from highrise import BaseBot, User, Position
import requests
from concurrent.futures import ThreadPoolExecutor
import asyncio
import json
import shutil

class xenoichi(BaseBot):
    def __init__(self):
        super().__init__()
        self.song_queue = []
        self.currently_playing = False
        self.skip_event = asyncio.Event()
        self.ffmpeg_process = None
        self.currently_playing_title = None
        self.credits = self.load_credits()  # Load credits from file
        self.user_song_count = {}
        self.admins = {'Xenoichi'}
        self.bot_pos = None

    async def on_start(self, session_metadata):
        print("Xenbot is armed and ready!")
        print("Bot is starting... cleaning up any active streams.")

        self.load_loc_data()
        
        await self.stop_existing_stream()

        # Reset currently playing status
        self.currently_playing = False

        await asyncio.sleep(5)

        # Load the saved song queue
        self.load_queue()

        # Check if there are songs to play after loading the queue
        if self.song_queue:
            print("Resuming playback of queued songs...")
            await self.play_next_song()

    def is_admin(self, username):
        return username in self.admins

    async def on_chat(self, user: User, message: str) -> None:

        if message.startswith("/crash"):
            # Check if the user is in the admin list
            if user.username not in self.admins:
                return

            # Allow admins to crash the bot
            await self.highrise.chat("Admin command received. Crashing the bot... 💥")

            # Terminate any active FFmpeg stream process before crashing
            if self.ffmpeg_process:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait()  # Ensure the process is completely stopped
                self.ffmpeg_process = None
                print("Terminated active stream process before crashing.")

            # Raise a RuntimeError to crash the bot intentionally
            raise RuntimeError("Intentional crash triggered by admin")

        elif message.startswith("/setpos"):

            if not self.is_admin(user.username):
                return

            self.bot_pos = await self.get_actual_pos(user.id)
            await self.highrise.chat("Bot position set!")
            await asyncio.sleep(1)
            await self.highrise.teleport(self.highrise.my_id, self.bot_pos)
            await asyncio.sleep(1)
            await self.highrise.teleport(self.highrise.my_id, self.bot_pos)
            self.save_loc_data()

        elif message.startswith('/admin '):
            if not self.is_admin(user.username):
                return
            parts = message.split()
            if len(parts) == 2:
                target_user = parts[1][1:]  # Remove '@' from the username
                if target_user not in self.admins:
                    self.admins.add(target_user)
                    await self.highrise.chat(f"@{target_user} has been added as an admin.")
                else:
                    await self.highrise.chat(f"@{target_user} is already an admin.")
            else:
                await self.highrise.chat("Usage: /admin @<username>")

        elif message.startswith('/deladmin '):
            if not self.is_admin(user.username):
                return
            parts = message.split()
            if len(parts) == 2:
                target_user = parts[1][1:]  # Remove '@' from the username
                if target_user in self.admins:
                    self.admins.remove(target_user)
                    await self.highrise.chat(f"@{target_user} has been removed from the admin list.")
                else:
                    await self.highrise.chat(f"@{target_user} is not an admin.")
            else:
                await self.highrise.chat("Usage: /deladmin @<username>")

        elif message.startswith('/cadmin'):
            if not self.is_admin(user.username):
                await self.highrise.chat("Sorry, you need to be an admin to view the admin list.")
                return
            page_number = 1
            if len(message.split()) > 1:
                try:
                    page_number = int(message.split()[1])
                except ValueError:
                    await self.highrise.chat("Invalid page number.")
                    return
            await self.check_admins(page_number)

        # Credits logic
        elif message.startswith('/ac '):
            if user.username != 'Xenoichi':  # Only allow Xenoichi to add credits
                await self.highrise.chat("Sorry, only @Xenoichi can add credits.")
                return
            
            parts = message.split()
            
            if len(parts) == 3:
                # Extract the username, ensuring it includes the '@' symbol
                target_user = parts[1]
                
                # Remove the '@' symbol if it's there
                if target_user.startswith('@'):
                    target_user = target_user[1:]
                else:
                    await self.highrise.chat("Invalid username format. Please include '@' before the username.")
                    return
                
                try:
                    amount = int(parts[2])
                    await self.add_credits(target_user, amount)
                except ValueError:
                    await self.highrise.chat("Invalid amount. Please provide a valid number for credits.")
            else:
                await self.highrise.chat("Usage: /ac @<username> <credits>")

        elif message.startswith('/cc'):
            await self.check_credits(user.username)

        if message.startswith('/play '):
            song_request = message[len('/play '):].strip()
            
            # Check if the user has already queued 3 songs
            if self.user_song_count.get(user.username, 0) >= 3:
                await self.highrise.chat(f"@{user.username}, you can only queue up to 3 songs. Please wait until one finishes.")
                return

            if await self.has_enough_credits(user.username):
                await self.deduct_credit(user.username)
                # Pass the song request and the user who requested it
                await self.add_to_queue(song_request, user.username)  
            else:
                await self.highrise.chat(f"@{user.username}, you don't have enough credits!")

        elif message.startswith('/skip'):
            await self.skip_song(user)  # Pass user.username to the skip_song method

        elif message.startswith('/q'):
            page_number = 1
            try:
                page_number = int(message.split(' ')[1])
            except (IndexError, ValueError):
                pass
            await self.check_queue(page_number)

        elif message.startswith('/np'):
            await self.now_playing()

    async def check_admins(self, page_number=1):
        admins_per_page = 5  # How many admins per page
        admins_list = list(self.admins)
        total_pages = (len(admins_list) // admins_per_page) + (1 if len(admins_list) % admins_per_page != 0 else 0)
        
        if page_number > total_pages:
            await self.highrise.chat(f"Page {page_number} does not exist. Only {total_pages} pages of admins.")
            return

        start_index = (page_number - 1) * admins_per_page
        end_index = min(start_index + admins_per_page, len(admins_list))
        admins_page = admins_list[start_index:end_index]
        
        # Display the admins on this page with numbers instead of '@'
        admins_message = f"Page {page_number}/{total_pages}:\nAdmins:\n"
        admins_message += "\n".join([f"{index + 1}. {admin}" for index, admin in enumerate(admins_page)])
        await self.highrise.chat(admins_message)

    async def add_credits(self, username, amount):
        """Adds credits to a user."""
        self.credits[username] = self.credits.get(username, 0) + amount
        await self.save_credits()
        await self.highrise.chat(f"Added {amount} credits to @{username}.\n\nCurrent balance: {self.credits[username]}")

    async def check_credits(self, username):
        """Checks the credits of a user."""
        current_credits = self.credits.get(username, 0)
        await self.highrise.chat(f"@{username}, you have {current_credits} credits.")

    async def has_enough_credits(self, username):
        """Checks if a user has enough credits to request a song."""
        return self.credits.get(username, 0) > 0

    async def deduct_credit(self, username):
        """Deducts 1 credit from a user's balance."""
        if username in self.credits and self.credits[username] > 0:
            self.credits[username] -= 1
            await self.save_credits()
            print(f"Credit deducted for {username}. Remaining credits: {self.credits[username]}")

    def load_credits(self):
        """Loads the credits from a file."""
        try:
            with open('credits.json', 'r') as file:
                return json.load(file)
        except FileNotFoundError:
            return {}

    async def save_credits(self):
        """Saves the credits to a file."""
        with open('credits.json', 'w') as file:
            json.dump(self.credits, file)

    async def check_queue(self, page_number=1):
        songs_per_page = 2
        total_songs = len(self.song_queue)
        total_pages = (total_songs + songs_per_page - 1) // songs_per_page

        if total_songs == 0:
            await self.highrise.chat("The queue is currently empty.")
            return

        if page_number < 1 or page_number > total_pages:
            await self.highrise.chat("Invalid page number.")
            return

        queue_message = f"There's {total_songs} song(s) in the queue (Page {page_number}/{total_pages}):\n\n"
        start_index = (page_number - 1) * songs_per_page
        end_index = min(start_index + songs_per_page, total_songs)

        for index, song in enumerate(self.song_queue[start_index:end_index], start=start_index + 1):
            queue_message += f"{index}. '{song['title']}' req by @{song['owner']}\n"

        await self.highrise.chat(queue_message)

        if page_number < total_pages:
            await self.highrise.chat(f"Use '/q {page_number + 1}' to view the next page.")


    async def add_to_queue(self, song_request, owner):
        await self.highrise.chat("Searching song request...")

        # Check if the user already queued 3 songs
        if self.user_song_count.get(owner, 0) >= 3:
            await self.highrise.chat(f"@{owner}, you can only queue a maximum of 3 songs.")
            return
        
        file_path, title = await self.download_youtube_audio(song_request)
        if file_path and title:
            self.song_queue.append({'title': title, 'file_path': file_path, 'owner': owner})

            # Update the song count for the user
            self.user_song_count[owner] = self.user_song_count.get(owner, 0) + 1

            self.save_queue()  # Save the queue after adding a song
            await self.highrise.chat(f"Added to queue: '{title}' \n\nRequested by @{owner}")

            if not self.currently_playing:
                await self.play_next_song()
        else:
            await self.highrise.chat("Could not download the song. Please try again.")

    async def download_youtube_audio(self, song_request):
        """Downloads audio from YouTube and returns the file path and title."""
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': 'downloads/%(id)s.%(ext)s',
                'default_search': 'ytsearch',
                'quiet': True,
                'noplaylist': True,
            }

            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(song_request, download=True)
                if 'entries' in info:
                    info = info['entries'][0]
                
                video_id = info['id']
                title = info['title']
                file_extension = info['ext']
                file_path = f"downloads/{video_id}.{file_extension}"

                print(f"Downloaded: {file_path} with title: {title}")
                return file_path, title
        except Exception as e:
            print(f"Error downloading the song: {e}")
            return None, None

    async def now_playing(self):
        if self.currently_playing_title:
            current_song_owner = self.current_song['owner'] if self.current_song else "Unknown"
            await self.highrise.chat(f"Now playing: '{self.currently_playing_title}'\n\nRequested by @{current_song_owner}")
        else:
            await self.highrise.chat("No song is currently playing.")

    async def play_next_song(self):
        self.skip_event.clear()

        if not self.song_queue:
            self.currently_playing = False
            self.currently_playing_title = None
            await self.highrise.chat("The queue is now empty.")
            return

        next_song = self.song_queue.pop(0)
        self.save_queue()  # Save the queue after removing a song
        self.current_song = next_song
        self.currently_playing = True
        self.currently_playing_title = next_song['title']
        song_title = next_song['title']
        song_owner = next_song['owner']
        file_path = next_song['file_path']

        await self.highrise.chat(f"Processing song. Please wait...\n\nUp Next: '{song_title}'\n\nRequested by @{song_owner}")
        print(f"Playing: {song_title}")

        mp3_file_path = await self.convert_to_mp3(file_path)
        if not mp3_file_path:
            await self.highrise.chat("Error converting song to MP3.")
            self.currently_playing = False
            await self.play_next_song()
            return

        await self.stream_to_radioking(mp3_file_path)

        # Clean up files after playing
        if os.path.exists(mp3_file_path):
            os.remove(mp3_file_path)
        if os.path.exists(file_path):
            os.remove(file_path)

        self.currently_playing = False
        self.current_song = None

        # After the song finishes, check and play the next one
        if not self.skip_event.is_set():
            # Decrease the song count for the user who requested the song
            self.user_song_count[song_owner] -= 1
            await self.play_next_song()

    async def convert_to_mp3(self, audio_file_path):
        try:
            if audio_file_path.endswith('.mp3'):
                return audio_file_path

            mp3_file_path = audio_file_path.replace(os.path.splitext(audio_file_path)[1], '.mp3')
            subprocess.run([
                'ffmpeg', '-i', audio_file_path,
                '-acodec', 'libmp3lame', '-ab', '192k', '-ar', '44100', '-ac', '2', mp3_file_path
            ], check=True)

            return mp3_file_path
        except Exception as e:
            print(f"Error converting to MP3: {e}")
            return None

    async def stream_to_radioking(self, mp3_file_path):
        with ThreadPoolExecutor() as executor:
            future = executor.submit(self._stream_to_radioking_thread, mp3_file_path)
            await asyncio.get_event_loop().run_in_executor(None, future.result)

    def _stream_to_radioking_thread(self, mp3_file_path):
        try:
            icecast_server = "live.radioking.com"
            icecast_port = 80
            mount_point = "/xenradio"
            username = "Ichiyako_Kissu"
            password = "Xeno021992gamerzx"
            icecast_url = f"icecast://{username}:{password}@{icecast_server}:{icecast_port}{mount_point}"

            # Terminate any existing FFmpeg process before starting a new one
            if self.ffmpeg_process:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait()
                self.ffmpeg_process = None

            command = [
                'ffmpeg', '-re', '-i', mp3_file_path,
                '-f', 'mp3', '-acodec', 'libmp3lame', '-ab', '192k',
                '-ar', '44100', '-ac', '2', '-reconnect', '1', '-reconnect_streamed', '1', 
                '-reconnect_delay_max', '2', icecast_url
            ]

            self.ffmpeg_process = subprocess.Popen(command)
            self.ffmpeg_process.wait()
        except Exception as e:
            print(f"Error streaming to Radioking: {e}")


    async def skip_song(self, user):
        if self.currently_playing:
            if self.is_admin(user.username) or (self.current_song and self.current_song['owner'] == user.username):
                async with asyncio.Lock():  # Ensure only one skip happens at a time
                    # Set the skip event and terminate the ffmpeg process
                    self.skip_event.set()
                    if self.ffmpeg_process:
                        self.ffmpeg_process.terminate()

                    # Deduct the song count for the user who requested the song
                    song_owner = self.current_song['owner']
                    if song_owner in self.user_song_count:
                        self.user_song_count[song_owner] -= 1
                        if self.user_song_count[song_owner] <= 0:
                            del self.user_song_count[song_owner]  # Remove user if they have no queued songs left

                    # Notify that the song was skipped
                    await self.highrise.chat(f"@{user.username} skipped the song.")
                    
                    # Wait before playing the next song to avoid multiple skips firing simultaneously
                    await asyncio.sleep(10)
                    
                    # Play the next song in the queue
                    await self.play_next_song()

            else:
                # Inform the user that only the requester or an admin can skip
                await self.highrise.chat("Only the requester of the song or an admin can skip it.")
        else:
            # Inform the user that no song is playing
            await self.highrise.chat("No song is currently playing to skip.")

    async def stop_existing_stream(self):
        """Check if an active stream is running and stop it if necessary."""
        if self.ffmpeg_process:
            print("Stopping active stream...")
            try:
                self.ffmpeg_process.terminate()
                await asyncio.sleep(1)  # Give it some time to stop gracefully
                if self.ffmpeg_process.poll() is None:
                    self.ffmpeg_process.kill()  # Force kill if not terminated
                print("Stream terminated successfully.")
            except Exception as e:
                print(f"Error while stopping stream: {e}")
            self.ffmpeg_process = None
        else:
            print("No active stream to stop.")

    def save_queue(self):
        """Save the current song queue to a JSON file."""
        try:
            with open('song_queue.json', 'w') as file:
                json.dump(self.song_queue, file)
        except Exception as e:
            print(f"Error saving queue: {e}")

    def load_queue(self):
        """Load the song queue from a JSON file."""
        try:
            with open('song_queue.json', 'r') as file:
                self.song_queue = json.load(file)
                print("Loaded song queue from file.")
        except FileNotFoundError:
            self.song_queue = []
        except Exception as e:
            print(f"Error loading queue: {e}")

    async def get_actual_pos(self, user_id):

        room_users = await self.highrise.get_room_users()
        
        for user, position in room_users.content:
            if user.id == user_id:
                return position

    def save_loc_data(self):

        loc_data = {
            'bot_position': {'x': self.bot_pos.x, 'y': self.bot_pos.y, 'z': self.bot_pos.z} if self.bot_pos else None,
        }

        with open('loc_data.json', 'w') as file:
            json.dump(loc_data, file)

    def load_loc_data(self):

        try:
            with open('loc_data.json', 'r') as file:
                loc_data = json.load(file)
                self.bot_pos = Position(**loc_data.get('bot_position')) if loc_data.get('bot_position') is not None else None
        except FileNotFoundError:
            pass





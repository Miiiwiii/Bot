import yt_dlp as youtube_dl
import os
import subprocess
from highrise import BaseBot, User, Position
from highrise.models import GetMessagesRequest
from concurrent.futures import ThreadPoolExecutor
import asyncio
import json
import random
import string
import time
import glob

class xenoichi(BaseBot):
    def __init__(self):
        super().__init__()

        self.dance = None
        self.current_song = None
        self.song_queue = []
        self.pending_confirmations = {}
        self.currently_playing = False
        self.skip_event = asyncio.Event()
        self.ffmpeg_process = None
        self.currently_playing_title = None
        self.credits = self.load_credits()  # Load credits from file
        self.user_song_count = {}
        self.admins = {'Xenoichi'}
        self.bot_pos = None
        self.ctoggle = False
        self.is_loading = True

    async def on_start(self, session_metadata):

        self.queue = []
        self.currently_playing = False

        await self.highrise.chat("Initialization in progress. Please wait.")
        self.is_loading = True
        print("Xenbot is armed and ready!")
        print("Bot is starting... cleaning up any active streams.")

        self.load_loc_data()
        if self.bot_pos:
            await self.highrise.teleport(self.highrise.my_id, self.bot_pos)

        # Terminate any existing stream before restarting
        await self.stop_existing_stream()
        await asyncio.sleep(5)

        # Reset the skip event
        self.skip_event.clear()
        self.load_queue()
        self.current_song = self.load_current_song()

        # Add the current song back to the queue as the first song
        if self.current_song:
            await self.highrise.chat(f"Replaying song due to disconnection: '{self.current_song['title']}'")
            self.song_queue.insert(0, self.current_song)  # Add it to the front of the queue
            await asyncio.sleep(10)

        # Load the saved song queue
        self.is_loading = False
        await self.highrise.chat("Initialization is complete.")

        # Start playback if there are songs in the queue
        if self.song_queue:
            print("Resuming playback of queued songs...")
            await self.play_next_song()

    def is_admin(self, username):
        return username in self.admins

    async def on_chat(self, user: User, message: str) -> None:

        if message.startswith('/ctoggle') and user.username in self.admins:

            self.ctoggle = not self.ctoggle
            status = "enabled" if self.ctoggle else "disabled"
            await self.highrise.chat(f"Credits requirement has been {status}.")
            self.save_loc_data()

        if message.startswith("/refresh"):
            # Check if the user is in the admin list
            if user.username not in self.admins:
                return

            # Allow admins to crash the bot
            await self.highrise.chat("Refreshing the bot. Please wait.")
            await asyncio.sleep(5)

            # Terminate any active FFmpeg stream process before crashing
            if self.ffmpeg_process:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait()  # Ensure the process is completely stopped
                self.ffmpeg_process = None
                print("Terminated active stream process before crashing.")

            # Raise a RuntimeError to crash the bot intentionally
            raise RuntimeError("Intentional crash triggered by admin")
        
        if message.startswith("/shutdown"):
            # Check if the user is in the admin list
            if user.username not in self.admins:
                return
            
            if self.is_loading:
                await self.highrise.chat("The bot is still initializing. Please wait a moment before using the /shutdown command.")
                return

            # Allow admins to "crash" the bot
            await self.highrise.chat("Initializing shut down.")
            await asyncio.sleep(5)

            # Terminate any active FFmpeg stream process before shutting down
            if self.ffmpeg_process:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait()  # Ensure the process is completely stopped
                self.ffmpeg_process = None
                print("Terminated active stream process before shutting down.")

            # Clear the current song
            self.current_song = None
            self.save_current_song()

            # Optionally, close the bot connection (based on your bot's API/SDK)
            await self.highrise.chat("Shutting down.")
            await asyncio.sleep(2)

            os._exit(0)

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
            if user.username not in self.admins:  # Only allow Xenoichi to add credits
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

        elif message.startswith('/rc '):
            # Remove credits from a user
            if user.username not in self.admins:
                return
            
            parts = message.split()
            
            if len(parts) == 3:
                target_user = parts[1]
                
                # Remove the '@' symbol if it's there
                if target_user.startswith('@'):
                    target_user = target_user[1:]
                else:
                    await self.highrise.chat("Invalid username format. Please include '@' before the username.")
                    return
                
                try:
                    amount = int(parts[2])
                    await self.remove_credits(target_user, amount)
                except ValueError:
                    await self.highrise.chat("Invalid amount. Please provide a valid number for credits.")
            else:
                await self.highrise.chat("Usage: /rc @<username> <credits>")

        elif message.startswith('/cc'):
            await self.check_credits(user.username)

        elif message.startswith('/cac'):

            if user.username not in self.admins:
                return
    
            parts = message.split()

            if len(parts) == 1:
                # No confirmation code provided, generate a new one
                if user.username in self.pending_confirmations:
                    confirmation_code = self.pending_confirmations[user.username]
                    await self.highrise.chat(f"You already have a pending confirmation.\n\n Type '/cac {confirmation_code}' to confirm.")
                    return

                # Generate a new random 5-letter confirmation code
                confirmation_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
                self.pending_confirmations[user.username] = confirmation_code
                await self.highrise.chat(f"Are you sure you want to clear all credits?\n\n Type '/cac {confirmation_code}' to confirm.")

            elif len(parts) == 2:
                # A confirmation code was provided
                confirmation_code = self.pending_confirmations.get(user.username)

                if confirmation_code:
                    provided_code = parts[1]
                    if provided_code == confirmation_code:
                        await self.clear_all_credits()
                        del self.pending_confirmations[user.username]
                    else:
                        await self.highrise.chat("Invalid confirmation code. Please check and try again.")
                else:
                    await self.highrise.chat("You have no pending actions to confirm.")

        elif message.startswith('/play '):

            if self.is_loading:
                await self.highrise.chat("The bot is still initializing. Please wait a moment before using the /play command.")
                return
            
            song_request = message[len('/play '):].strip()

            # Check if the user has already queued 3 songs
            if self.user_song_count.get(user.username, 0) >= 3:
                await self.highrise.chat(f"@{user.username}, you can only queue up to 3 songs. Please wait until one finishes.")
                return

            if self.ctoggle:
                # Get the user's current credits from self.credits
                user_credits = self.credits.get(user.username, 0)  # Default to 0 if the user is not found
                
                if user_credits <= 0:
                    await self.highrise.chat(f"@{user.username}, you need at least 1 credit to queue a song.")
                    return
                
            await self.add_to_queue(song_request, user.username)

        elif message.startswith('/skip'):
            await self.skip_song(user)  # Pass user.username to the skip_song method

        elif message.startswith('/delq'):

            parts = message.split()

            if len(parts) == 1:
                # Call the del_last_song function to delete the user's last song
                await self.del_last_song(user.username)

        elif message.startswith('/clearq') and user.username in self.admins:

            parts = message.split()

            if len(parts) == 1:
                # Call the clear_queue function to remove all songs from the user's queue and delete the files
                await self.clear_queue()

        elif message.startswith('/q'):
            page_number = 1
            try:
                page_number = int(message.split(' ')[1])
            except (IndexError, ValueError):
                pass
            await self.check_queue(page_number)

        elif message.startswith('/np'):
            await self.now_playing()

    async def on_message(self, user_id: str, conversation_id: str, is_new_conversation: bool) -> None:
        # Fetch the latest message in the conversation
        response = await self.highrise.get_messages(conversation_id)
        if isinstance(response, GetMessagesRequest.GetMessagesResponse):
            message = response.messages[0].content  # Get the message content

        # Handle the /play command
        if message.startswith('/play '):

            if self.is_loading:
                await self.highrise.send_message(conversation_id, "The bot is still initializing. Please wait a moment before using the /play command.")
                return

            # Get the username based on user_id
            username = await self.get_user_details(user_id)
            print(f"{username} {message}")

            if not username:
                await self.highrise.chat(conversation_id, "Sorry, I couldn't find your username.")
                return
            
            song_request = message[len('/play '):].strip()

            # Check if the user has already queued 3 songs
            if self.user_song_count.get(username, 0) >= 3:
                await self.highrise.send_message(conversation_id, "You can only queue up to 3 songs. Please wait until one finishes.")
                return

            if self.ctoggle:
                # Check if the user has enough credits
                user_credits = self.credits.get(username, 0)  # Default to 0 if the user is not found
                
                if user_credits <= 0:
                    await self.highrise.send_message(conversation_id, "You need at least 1 credit to queue a song.")
                    return
            
            # Add the song to the queue with the username as the requester
            await self.add_to_queue(song_request, username)
            await self.highrise.send_message(conversation_id, f"@{username}, your song '{song_request}' has been added to the queue!")


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

    async def remove_credits(self, username, amount):
        if username in self.credits:
            self.credits[username] -= amount
            if self.credits[username] < 0:
                self.credits[username] = 0
            await self.save_credits()
            await self.highrise.chat(f"Removed {amount} credits from @{username}.\n\nRemaining balance: {self.credits[username]}")
        else:
            await self.highrise.chat(f"@{username} does not have any credits.")

    async def check_credits(self, username):
        """Checks the credits of a user."""
        current_credits = self.credits.get(username, 0)
        await self.save_credits()
        await self.highrise.chat(f"@{username}, you have {current_credits} credits.")

    async def clear_all_credits(self):
        self.credits = {}
        await self.highrise.chat("All user credits have been cleared.")

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

            # Get the duration, default to 0 if not available
            duration = song.get('duration', 0)

            # Format the duration as MM:SS
            duration_minutes = int(duration // 60)
            duration_seconds = int(duration % 60)
            formatted_duration = f"{duration_minutes}:{duration_seconds:02d}"

            queue_message += f"{index}. '{song['title']}' ({formatted_duration}) req by @{song['owner']}\n"

        await self.highrise.chat(queue_message)

        if page_number < total_pages:
            await self.highrise.chat(f"Use '/q {page_number + 1}' to view the next page.")


    async def add_to_queue(self, song_request, owner):

        await self.highrise.chat("\n🔎 Search in progress.")

        # Check if the user already queued 3 songs
        if self.user_song_count.get(owner, 0) >= 3:
            await self.highrise.chat(f"@{owner}, you can only queue a maximum of 3 songs.")
            return
        
        # Download the song details (file path and title)
        file_path, title, duration = await self.download_youtube_audio(song_request)
        
        if file_path and title and duration:

            # **Check if the song exceeds the duration limit**
            if duration > 12 * 60:  # 12 minutes in seconds
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"Deleted file: {file_path}")
                await self.highrise.chat(f"@{owner}, your request '{title}' exceeds the 12-minute duration limit and cannot be added.")
                return

            # Check if the song is already in the queue (using title as unique identifier)
            if any(song['title'].lower() == title.lower() for song in self.song_queue):
                await self.highrise.chat(f"@{owner}, the song '{title}' is already in the queue.")
                return
            
            # Check if the requested song is the same as the current playing song
            if self.currently_playing_title and self.currently_playing_title.lower() == title.lower():
                await self.highrise.chat(f"@{owner}, the song '{title}' is already playing. Please wait for it to finish.")
                return

            # If not in the queue, add the song
            self.song_queue.append({
                'title': title,
                'file_path': file_path,
                'owner': owner,
                'duration': duration
            })

            # Update the song count for the user
            self.user_song_count[owner] = self.user_song_count.get(owner, 0) + 1

            # Save the queue after adding a song
            self.save_queue()

            duration_minutes = int(duration // 60)
            duration_seconds = int(duration % 60)
            formatted_duration = f"{duration_minutes}:{duration_seconds:02d}"

            await self.highrise.chat(f"\n🎵 Added to queue: '{title}' ({formatted_duration})\n\nRequested by @{owner}")

            if self.ctoggle:
                try:
                    self.credits[owner] -= 1  # Deduct 1 credit
                except Exception as e:
                    print(f"Failed to send whisper to {owner}: {e}")
                finally:
                    await self.save_credits()  # Save the credits to the file

            # If no song is currently playing, start the next song
            if not self.currently_playing_title:
                await self.play_next_song()
        else:
            await self.highrise.chat("Could not download the song. Please try again.")

    async def del_last_song(self, owner):
        # Find the last song that the user added to the queue
        last_song = None
        for song in reversed(self.song_queue):
            if song['owner'] == owner:
                last_song = song
                break

        if last_song:
            # Remove the last song from the queue
            self.song_queue.remove(last_song)
            self.user_song_count[owner] -= 1  # Decrease the user's song count
            await self.highrise.chat(f"@{owner}, your last song: '{last_song['title']}' has been removed from the queue.")

            # Save the updated queue
            self.save_queue()
        else:
            await self.highrise.chat(f"@{owner}, you have no songs in the queue to remove.")

    async def clear_queue(self):
        """Clears all songs from the queue and deletes all downloaded files."""

        # Clear the song queue
        self.song_queue.clear()

        # Reset the song count for all users
        self.user_song_count.clear()

        # Delete all downloaded files in the 'downloads' folder
        downloaded_files = glob.glob('downloads/*')  # This will match all files in the 'downloads' folder
        for file in downloaded_files:
            try:
                os.remove(file)  # Remove the file
                print(f"Deleted file: {file}")
            except Exception as e:
                print(f"Error deleting file {file}: {e}")

        # Optionally, save the empty queue and reset other states as needed
        self.save_queue()

        # Notify the admin that the queue has been cleared and files deleted
        await self.highrise.chat("All songs have been cleared from the queue and all downloaded files have been deleted.")

    async def download_youtube_audio(self, song_request):
        """Downloads audio from YouTube and returns the file path, title, and duration."""
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': 'downloads/%(id)s.%(ext)s',
                'default_search': 'ytsearch',
                'quiet': True,
                'noplaylist': True,
                            'ffmpeg_options': {
                'y': True,  # Automatically overwrite any existing file
                },
            }

            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(song_request, download=True)
                if 'entries' in info:
                    info = info['entries'][0]
                
                video_id = info['id']
                title = info['title']
                duration = info['duration']  # Duration in seconds
                file_extension = info['ext']
                file_path = f"downloads/{video_id}.{file_extension}"

                print(f"Downloaded: {file_path} with title: {title}, duration: {duration} seconds")
                return file_path, title, duration
        except Exception as e:
            print(f"Error downloading the song: {e}")
            return None, None, None

    async def now_playing(self):
        # Check if a song is currently set
        if self.current_song is None:
            await self.highrise.chat("No song is currently playing.")
            return
        
        if self.currently_playing_title:
            current_song = self.current_song
            total_duration = current_song.get('duration', 0)

            # Add 10 seconds to the total duration to account for streaming delay
            adjusted_total_duration = total_duration

            delay_threshold = 20
            elapsed_time = time.time() - self.song_start_time

            if elapsed_time < delay_threshold:
                # Simulate a gradual increase in elapsed time after the delay
                elapsed_time = 0  # Only count up after the delay period ends
            else:
                # Ensure elapsed_time starts counting normally after the delay
                elapsed_time -= delay_threshold

            # Ensure the elapsed time doesn't exceed the song duration
            elapsed_time = min(elapsed_time, adjusted_total_duration)

            # Calculate progress as a percentage
            progress_percentage = (elapsed_time / adjusted_total_duration) * 100
            progress_bar_length = 10  # Total number of segments in the progress bar
            filled_length = int(progress_percentage / (100 / progress_bar_length))  # Determine the filled portion
            progress_bar = '█' * filled_length  # Filled portion of the progress bar
            empty_bar = '▒' * (progress_bar_length - filled_length)  # Empty portion of the progress bar
            progress_bar_display = f"[{progress_bar}{empty_bar}]"

            # Format time as MM:SS
            total_duration_str = f"{int(adjusted_total_duration // 60)}:{int(adjusted_total_duration % 60):02d}"
            elapsed_time_str = f"{int(elapsed_time // 60)}:{int(elapsed_time % 60):02d}"

            # Send the formatted message with progress bar
            await self.highrise.chat(
                f"🎶 Now playing: '{self.currently_playing_title}'\n\n"
                f"{elapsed_time_str} {progress_bar_display} {total_duration_str}\n\n"
                f"Requested by @{current_song['owner']}"
            )
        else:
            await self.highrise.chat("No song is currently playing.")

    async def play_next_song(self):
        # Clear the skip event before starting
        self.skip_event.clear()
        await asyncio.sleep(2)

        if not self.song_queue:
            self.currently_playing = False
            self.currently_playing_title = None
            await self.highrise.chat("The queue is now empty.")
            return

        # Prevent playing if already marked as playing
        if self.currently_playing:
            print("A song is already playing. Aborting start of a new song.")
            return

        next_song = self.song_queue.pop(0)
        self.save_queue()  # Save the queue after removing a song
        self.current_song = next_song
        self.save_current_song()
        self.currently_playing = True
        self.currently_playing_title = next_song['title']
        song_title = next_song['title']
        song_owner = next_song['owner']
        file_path = next_song['file_path']
        self.song_start_time = time.time()

        duration = next_song.get('duration', 0)  # Default to 0 if no duration is provided

        duration_minutes = int(duration // 60)
        duration_seconds = int(duration % 60)
        formatted_duration = f"{duration_minutes}:{duration_seconds:02d}"

        await self.highrise.chat(f"♫⋆｡♪ ₊˚♬\nUp Next: '{song_title}' ({formatted_duration})\n\nRequested by @{song_owner}")
        print(f"Playing: {song_title}")

        mp3_file_path = await self.convert_to_mp3(file_path)
        if not mp3_file_path:
            await self.highrise.chat("Processing. Please wait.")
            # Retry downloading the song
            new_file_path, new_title, new_duration = await self.download_youtube_audio(song_title)
            if new_file_path:
                mp3_file_path = await self.convert_to_mp3(new_file_path)
                if not mp3_file_path:
                    await self.highrise.chat("Retry failed. Skipping to the next song.")
                    self.currently_playing = False
                    await asyncio.sleep(10)
                    await self.play_next_song()
                    return
                else:
                    file_path = new_file_path  # Update file_path to the newly downloaded file
            else:
                await self.highrise.chat("Retry failed. Skipping to the next song.")
                self.currently_playing = False
                await asyncio.sleep(10)
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

        # Only play the next song if the skip event was not set
        if not self.skip_event.is_set():
            # Ensure the user exists in the song count dictionary
            if song_owner not in self.user_song_count:
                self.user_song_count[song_owner] = 0  # Initialize if user is not in the dictionary
            
            # Decrease the song count for the user who requested the song
            self.user_song_count[song_owner] -= 1
            
            await asyncio.sleep(10)
            await self.play_next_song()
        else:
            self.skip_event.clear()  # Reset skip event for the next song


    async def convert_to_mp3(self, audio_file_path):
        try:

            if audio_file_path.endswith('.mp3'):
                return audio_file_path

            mp3_file_path = audio_file_path.replace(os.path.splitext(audio_file_path)[1], '.mp3')

            # Check if the MP3 file already exists before trying to convert
            if os.path.exists(mp3_file_path):
                print(f"MP3 file {mp3_file_path} already exists. Skipping conversion.")
                return mp3_file_path  # Return the existing MP3 file path

            subprocess.run([
                'ffmpeg', '-i', audio_file_path,
                '-acodec', 'libmp3lame', '-ab', '192k', '-ar', '44100', '-ac', '2', mp3_file_path
            ], check=True)

            return mp3_file_path
        except Exception as e:
            print(f"Error converting to MP3: {e}")
            return None

    async def stream_to_radioking(self, mp3_file_path):
        icecast_server = "live.radioking.com"
        icecast_port = 80
        mount_point = "/myradio01"
        username = "Jack_Cole"
        password = "021xenogamerzx992"
        icecast_url = f"icecast://{username}:{password}@{icecast_server}:{icecast_port}{mount_point}"

        with ThreadPoolExecutor() as executor:
            # Use the `_run_ffmpeg` helper inside the executor
            future = executor.submit(self._run_ffmpeg, mp3_file_path, icecast_url)
            await asyncio.get_event_loop().run_in_executor(None, future.result)

    def _run_ffmpeg(self, mp3_file_path, icecast_url):
            
        command = [
            'ffmpeg', '-y', '-re', '-i', mp3_file_path,
            '-f', 'mp3', '-acodec', 'libmp3lame', '-ab', '192k',
            '-ar', '44100', '-ac', '2', '-reconnect', '1', '-reconnect_streamed', '1',
            '-reconnect_delay_max', '2', icecast_url
        ]

        try:
            # Terminate any existing FFmpeg process before starting a new one
            if self.ffmpeg_process:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait()
                self.ffmpeg_process = None

            # Start the FFmpeg process
            self.ffmpeg_process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = self.ffmpeg_process.communicate()

            if self.ffmpeg_process.returncode != 0:
                raise RuntimeError(f"FFmpeg error: {stderr.decode('utf-8')}")

        except Exception as e:
            print(f"Error in FFmpeg process: {e}")

    async def skip_song(self, user):
        if self.currently_playing:
            if self.is_admin(user.username) or (self.current_song and self.current_song['owner'] == user.username):
                async with asyncio.Lock():
                    self.skip_event.set()  # Mark that the song was skipped

                    # Terminate the ffmpeg process if it's running
                    if self.ffmpeg_process:
                        self.ffmpeg_process.terminate()
                        self.ffmpeg_process.wait()
                        self.ffmpeg_process = None

                    song_owner = self.current_song['owner']
                    if song_owner in self.user_song_count:
                        self.user_song_count[song_owner] -= 1
                        if self.user_song_count[song_owner] <= 0:
                            del self.user_song_count[song_owner]

                    await self.highrise.chat(f"@{user.username} skipped the current song.")
                    await asyncio.sleep(10)

                    self.currently_playing = False
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

    async def musicbot_dance(self):
        
        while True:

            try:

                if self.song_queue or self.currently_playing:
                    await self.highrise.send_emote('dance-tiktok11', self.highrise.my_id)
                    await asyncio.sleep(9.5)

                else:
                    await self.highrise.send_emote('emote-hello', self.highrise.my_id)
                    await asyncio.sleep(2.7)

            except Exception as e:
                print(f"Error sending emote: {e}")

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
            'ctoggle': self.ctoggle 
        }

        with open('loc_data.json', 'w') as file:
            json.dump(loc_data, file)

    def load_loc_data(self):

        try:
            with open('loc_data.json', 'r') as file:
                loc_data = json.load(file)
                self.bot_pos = Position(**loc_data.get('bot_position')) if loc_data.get('bot_position') is not None else None
                self.ctoggle = loc_data.get('ctoggle', False)
        except FileNotFoundError:
            pass

    def save_current_song(self):
        with open("current_song.json", "w") as file:
            json.dump(self.current_song, file)

    def load_current_song(self):
        try:
            with open("current_song.json", "r") as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    async def get_user_details(self, user_id: str) -> str:
        # Call the web API to get the user details by user_id
        try:
            response = await self.webapi.get_user(user_id)  # This assumes your API call returns a GetPublicUserResponse object
            if response.user:  # Check if the 'user' attribute exists in the response
                user_data = response.user  # Assuming the response has a 'user' attribute
                return user_data.username  # Return the username (adjust the key as needed)
            else:
                print(f"Error: User data not found in response")
                return None
        except Exception as e:
            print(f"Error fetching user details: {str(e)}")
            return None





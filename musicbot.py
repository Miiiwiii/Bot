
        # Start playback if there are songs in the queue
        if self.song_queue:
            print("Resuming playback of queued songs...")
            await self.play_next_song()

    def is_admin(self, username):
        return username in self.admins

    async def                target_user = parts[1][1:]  # Remove '@' from the username
                if target_user in self.admins:
                    self.admins.remove(target_user)
                    await self.highrise.chat(f"@{target_user} has been removed from the admin list.")
                else:
                    await self.highrise.chat(f"@{target_user} is not an admin.")
            else:
                
                self.pending_confirmations[user.username
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
        admins_message = f"Page {page_number}/{total_pages}:\nAdmins:\
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
            await 
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

            with        song_owner = next_song['owner']
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

        
                    self.currently_playing = False
                    await self.play_next_song()

            else:
                # Inform the user that only the requester or an admin can skip
                await self.highrise.chat("Only the requester of the song or an admin can skip it.")
        else:
            # Inform the user that no song is playing
            await self.highrise.chat("No song is currently playing to skip.")

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





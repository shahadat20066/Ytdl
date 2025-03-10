from flask import Flask, jsonify, render_template, request, redirect, url_for, send_from_directory
import yt_dlp
import os
import signal
import platform
import subprocess
import stat
import requests
import zipfile
import tarfile
import threading
import time

app = Flask(__name__)

# Path to the YouTube cookies file
COOKIES_FILE = 'cookies.txt'

# Directory to store downloaded audio files
AUDIO_DIR = 'audio_files'
os.makedirs(AUDIO_DIR, exist_ok=True)

# Directory to store ffmpeg binaries
FFMPEG_DIR = 'ffmpeg'
os.makedirs(FFMPEG_DIR, exist_ok=True)

# Helper function to format duration in HH:MM:SS
def format_duration(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours:02}:{minutes:02}:{seconds:02}"

# Helper function to format large numbers into k, M, B
def format_number(number):
    if number >= 1_000_000_000:
        return f"{number / 1_000_000_000:.1f}B"
    elif number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    elif number >= 1_000:
        return f"{number / 1_000:.1f}k"
    return str(number)

# Function to download and setup ffmpeg
def setup_ffmpeg():
    system = platform.system()
    machine = platform.machine()

    # Define download URLs for ffmpeg based on the OS
    if system == 'Windows':
        ffmpeg_url = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'
        ffmpeg_zip = os.path.join(FFMPEG_DIR, 'ffmpeg.zip')
        ffmpeg_exe = os.path.join(FFMPEG_DIR, 'ffmpeg-master-latest-win64-gpl', 'bin', 'ffmpeg.exe')
    elif system == 'Linux':
        ffmpeg_url = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz'
        ffmpeg_tar = os.path.join(FFMPEG_DIR, 'ffmpeg.tar.xz')
        ffmpeg_exe = os.path.join(FFMPEG_DIR, 'ffmpeg-master-latest-linux64-gpl', 'bin', 'ffmpeg')
    elif system == 'Darwin':  # macOS
        ffmpeg_url = 'https://evermeet.cx/ffmpeg/ffmpeg-6.0.zip'
        ffmpeg_zip = os.path.join(FFMPEG_DIR, 'ffmpeg.zip')
        ffmpeg_exe = os.path.join(FFMPEG_DIR, 'ffmpeg')
    else:
        raise Exception("Unsupported operating system.")

    # Download ffmpeg if it doesn't exist
    if not os.path.exists(ffmpeg_exe):
        print("Downloading ffmpeg...")
        if system == 'Windows' or system == 'Darwin':
            response = requests.get(ffmpeg_url)
            with open(ffmpeg_zip, 'wb') as f:
                f.write(response.content)
            if system == 'Windows':
                with zipfile.ZipFile(ffmpeg_zip, 'r') as zip_ref:
                    zip_ref.extractall(FFMPEG_DIR)
            else:  # macOS
                with zipfile.ZipFile(ffmpeg_zip, 'r') as zip_ref:
                    zip_ref.extractall(FFMPEG_DIR)
                os.chmod(ffmpeg_exe, stat.S_IRWXU)  # Make ffmpeg executable
        elif system == 'Linux':
            response = requests.get(ffmpeg_url)
            with open(ffmpeg_tar, 'wb') as f:
                f.write(response.content)
            with tarfile.open(ffmpeg_tar, 'r:xz') as tar_ref:
                tar_ref.extractall(FFMPEG_DIR)
            os.chmod(ffmpeg_exe, stat.S_IRWXU)  # Make ffmpeg executable

# Function to delete a file after a delay
def delete_file_after_delay(file_path, delay=120):  # 120 seconds = 2 minutes
    def delete_file():
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Deleted file: {file_path}")
    timer = threading.Timer(delay, delete_file)
    timer.start()

# Function to fetch video details
def get_video_info(video_id, media_type):
    # Options for fetching video or audio
    ydl_opts = {
        'format': 'best[height<=360]' if media_type == 'mp4' else 'bestaudio/best',
        'noplaylist': True,
        'cookiefile': COOKIES_FILE,
        'quiet': True,
        'no_warnings': True,
        'outtmpl': os.path.join(AUDIO_DIR, f'{video_id}.%(ext)s'),  # Save as video ID
    }

    # Add post-processor for MP3 audio with 128k bitrate
    if media_type == 'mp3':
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }]

    try:
        # Fetch video or audio information
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=(media_type == 'mp3'))

        # Extract required fields
        media_info = {
            'title': info.get('title'),
            'channel_name': info.get('uploader'),
            'duration': format_duration(info.get('duration', 0)),
            'views': format_number(info.get('view_count', 0)),
            'media_url': info.get('url'),
        }

        # For MP4, return the video stream URL
        #if media_type == 'mp4':
            #for format in info.get('formats', []):
                #if format.get('height') == 360 and format.get('ext') == 'mp4':
                    #media_info['video_url'] = format.get('url')
                    #break
            #else:
                #raise Exception("360p MP4 format not found.")
        # For MP3, return the local streaming URL
        if media_type == 'mp3':
            media_info['stream_url'] = f'http://localhost:8080/{video_id}'

        return media_info

    except Exception as e:
        raise Exception(f"Error fetching {media_type.upper()} information: {str(e)}")

# Route for fetching 360p MP4 video
@app.route('/id=<video_id>&type=mp4', methods=['GET'])
def video_mp4(video_id):
    try:
        info = get_video_info(video_id, 'mp4')
        return jsonify(info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Route for fetching 128k MP3 audio
@app.route('/id=<video_id>&type=mp3', methods=['GET'])
def audio_mp3(video_id):
    try:
        info = get_video_info(video_id, 'mp3')
        
        # Schedule the audio file for deletion after 2 minutes
        mp3_file = os.path.join(AUDIO_DIR, f'{video_id}.mp3')
        delete_file_after_delay(mp3_file, delay=120)  # 120 seconds = 2 minutes
        
        return jsonify(info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Route to stream the downloaded MP3 audio file
@app.route('/<video_id>', methods=['GET'])
def stream_audio(video_id):
    try:
        # Check if the MP3 file exists
        mp3_file = os.path.join(AUDIO_DIR, f'{video_id}.mp3')
        if not os.path.exists(mp3_file):
            return jsonify({'error': 'Audio file not found'}), 404

        # Stream the MP3 file
        return send_from_directory(AUDIO_DIR, f'{video_id}.mp3', mimetype='audio/mpeg')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Route to display and edit the cookies file and restart the project
@app.route('/changecookie', methods=['GET', 'POST'])
def change_cookie():
    if request.method == 'POST':
        # Get the cookie content from the form
        new_cookies = request.form.get('cookies')
        # Overwrite the cookies.txt file with the new content
        with open(COOKIES_FILE, 'w') as f:
            f.write(new_cookies)

        # Restart the project
        restart_project()

        return redirect(url_for('change_cookie'))

    # Read the current content of cookies.txt
    if os.path.exists(COOKIES_FILE):
        with open(COOKIES_FILE, 'r') as f:
            current_cookies = f.read()
    else:
        current_cookies = ''

    return render_template('changecookie.html', current_cookies=current_cookies)

# Function to restart the project
def restart_project():
    # Restart the current process by sending SIGTERM to the current process
    os.kill(os.getpid(), signal.SIGTERM)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)

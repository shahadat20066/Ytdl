from flask import Flask, jsonify, render_template, request, redirect, url_for
import yt_dlp
import os
import signal

app = Flask(__name__)

# Path to the YouTube cookies file
COOKIES_FILE = 'cookies.txt'

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

# Function to fetch video details and stream URLs using cookies
def get_video_info(video_id):
    ydl_opts_video = {
        'format': 'best[height<=360]',  # 360p or lower for video
        'noplaylist': True,
        'cookiefile': COOKIES_FILE,  # Load cookies from file
    }

    ydl_opts_audio = {
        'format': 'bestaudio/best',  # Best audio available
        'noplaylist': True,
        'cookiefile': COOKIES_FILE,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts_video) as ydl:
            info_video = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)

        with yt_dlp.YoutubeDL(ydl_opts_audio) as ydl:
            info_audio = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)

        video_info = {
            'title': info_video.get('title'),
            'channel': info_video.get('uploader'),
            'duration': format_duration(info_video.get('duration', 0)),
            'views': format_number(info_video.get('view_count', 0)),
            'likes': format_number(info_video.get('like_count', 0)),
            'comments': format_number(info_video.get('comment_count', 0)),
            'id': video_id,
            'link': f'https://youtu.be/{video_id}',
            'video_url': info_video.get('url'),
            'audio_url': info_audio.get('url'),
        }

        return video_info

    except Exception as e:
        raise Exception(f"Error fetching video information: {str(e)}")

# Route for the video information and stream URLs
@app.route('/id=<video_id>', methods=['GET'])
def video_info(video_id):
    try:
        info = get_video_info(video_id)
        return jsonify(info)
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
import yt_dlp
from yt_dlp.utils import DownloadError

ydl = yt_dlp.YoutubeDL()

def get_video_info(url):
    try:
        result = ydl.extract_info(url, download=False)

        if 'entries' in result:
            video = result['entries'][0]  
        else:
            video = result

        infos = ['id', 'title', 'channel', 'view_count', 'like_count',
                 'channel_id', 'duration', 'categories', 'tags']

        def key_name(key):
            return 'video_id' if key == 'id' else key

        return {key_name(key): video.get(key) for key in infos}

    except DownloadError as e:
        print(f"Error downloading video info: {e}")
        return None

#!/usr/bin/env python3
"""
Enhanced YouTube Downloader - Final Version
Supports: Single videos, Playlists, Channels with robust error handling.
Usage: python enhanced_youtube_downloader.py -u <URL> [options]
"""

import argparse
import os
import sys
import time
import re
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional

# --- Dependency Installation Check ---
try:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError, ExtractorError
except ImportError:
    print("❌ Error: yt-dlp is not installed. Please run: pip install yt-dlp")
    sys.exit(1)

try:
    import colorama
    colorama.init(autoreset=True)
except ImportError:
    print("⚠️ Warning: colorama not found. For colored output, run: pip install colorama")
    class DummyColorama:
        def __getattr__(self, name):
            return ''
    colorama = type('Colorama', (), {'Fore': DummyColorama(), 'Style': DummyColorama()})()


# --- Color Formatting ---
class Colors:
    RED = colorama.Fore.RED
    GREEN = colorama.Fore.GREEN
    YELLOW = colorama.Fore.YELLOW
    BLUE = colorama.Fore.BLUE
    CYAN = colorama.Fore.CYAN
    WHITE = colorama.Fore.WHITE
    BOLD = colorama.Style.BRIGHT
    END = colorama.Style.RESET_ALL

C = Colors()

# --- Utility Functions ---
def setup_logging(debug: bool = False):
    """Set up logging configuration."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler('youtube_downloader.log'), logging.StreamHandler()]
    )

def format_size(size_bytes: Optional[int]) -> str:
    """Convert bytes to a human-readable format."""
    if not isinstance(size_bytes, (int, float)) or size_bytes <= 0:
        return "N/A"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    while size >= 1024 and i < len(units) - 1:
        size /= 1024.0
        i += 1
    return f"{size:.1f} {units[i]}"

def format_duration(seconds: Optional[int]) -> str:
    """Convert seconds to a readable hh:mm:ss format."""
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return "N/A"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

# --- Core Classes ---
class EnhancedProgressHook:
    """A more robust progress hook for yt-dlp."""
    def __init__(self):
        self.last_update_time = 0
        self.current_video_info = ""

    def __call__(self, d: Dict):
        status = d.get('status')

        if status == 'downloading':
            current_time = time.time()
            if current_time - self.last_update_time < 0.5:
                return
            self.last_update_time = current_time

            info_dict = d.get('info_dict', {})
            playlist_index = info_dict.get('playlist_index')
            playlist_count = info_dict.get('playlist_count')
            if playlist_index and playlist_count:
                self.current_video_info = f"[{playlist_index}/{playlist_count}] "

            filename = Path(d.get('filename', '...')).name[:40]
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            speed = d.get('speed')

            speed_str = f"{format_size(speed)}/s" if speed else "N/A"
            percent_str = f"{(downloaded / total) * 100:5.1f}%" if total else "---.-%"
            eta_seconds = d.get('eta', 0)
            eta_str = f"ETA: {format_duration(eta_seconds)}" if eta_seconds else ""

            print(
                f"\r{C.CYAN}{self.current_video_info}⬇️  {percent_str} | "
                f"{format_size(downloaded)}/{format_size(total)} @ {speed_str} | "
                f"{eta_str} | {filename}{C.END}",
                end="", flush=True
            )

        elif status == 'finished':
            filename = Path(d.get('info_dict', {}).get('filepath', 'file')).name
            print(f"\n{C.GREEN}✅ {self.current_video_info}Completed: {filename}{C.END}")

        elif status == 'error':
            # This will now be handled by yt-dlp's ignoreerrors flag
            pass

def check_dependencies() -> Dict[str, bool]:
    """Check for required external dependencies like FFmpeg."""
    print(f"{C.BLUE}🔎 Checking for dependencies...{C.END}")
    results = {}
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True, timeout=10)
        results['ffmpeg'] = True
        print(f"{C.GREEN}   - FFmpeg found (required for audio conversion).{C.END}")
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        results['ffmpeg'] = False
        print(f"{C.YELLOW}   - ⚠️ FFmpeg not found. Audio-only downloads (e.g., MP3) will fail.{C.END}")
    return results

def get_content_info(url: str, cookies_from: Optional[str]) -> Optional[Dict]:
    """Extract content information reliably."""
    print(f"{C.BLUE}🔍 Extracting content information...{C.END}")
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
        'extract_flat': 'in_playlist',
        'skip_download': True,
        'ignoreerrors': True,
    }
    if cookies_from:
        ydl_opts['cookiesfrombrowser'] = [cookies_from]
        print(f"{C.CYAN}   - Using cookies from {cookies_from}...{C.END}")

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info or ('entries' in info and not info['entries']):
            raise ExtractorError("No valid videos found at the URL. The content may be private or deleted.")
        return info
    except (ExtractorError, DownloadError) as e:
        print(f"{C.RED}❌ Failed to extract info: {e}{C.END}")
        logging.error(f"ExtractorError for URL '{url}': {e}")
        return None

def display_content_info(info: Dict):
    """Display a summary of the content to be downloaded."""
    content_type = info.get('_type', 'video')
    print(f"\n{C.WHITE}{C.BOLD}📊 Content Information:{C.END}")

    if content_type in ['playlist', 'multi_video']:
        title = info.get('title', 'Unknown Playlist')
        uploader = info.get('uploader', 'Unknown Creator')
        valid_entries = [e for e in info.get('entries', []) if e]
        print(f"   📋 Type:    {C.CYAN}Playlist{C.END}")
        print(f"   📋 Title:   {C.CYAN}{title}{C.END}")
        print(f"   👤 Creator: {C.GREEN}{uploader}{C.END}")
        print(f"   🎬 Videos:  {C.YELLOW}{len(valid_entries)}{C.END}")
    else:
        title = info.get('title', 'Unknown Video')
        uploader = info.get('uploader', 'Unknown Channel')
        duration = info.get('duration', 0)
        print(f"   🎬 Type:     {C.CYAN}Single Video{C.END}")
        print(f"   📺 Title:    {C.CYAN}{title}{C.END}")
        print(f"   👤 Channel:  {C.GREEN}{uploader}{C.END}")
        print(f"   ⏱️ Duration: {C.YELLOW}{format_duration(duration)}{C.END}")

def select_format(has_ffmpeg: bool) -> Optional[str]:
    """Allow the user to select the download format."""
    print(f"\n{C.WHITE}{C.BOLD}⚙️ Select Download Quality:{C.END}")
    options = {
        '1': {'label': "🏆 Best Available Quality (up to 4K/8K, WEBM/MP4)", 'format': 'bestvideo+bestaudio/best'},
        '2': {'label': "💎 Full HD (1080p MP4)", 'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]'},
        '3': {'label': "📱 Good Quality (720p MP4)", 'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]'},
    }
    audio_key = '4'
    if has_ffmpeg:
        options[audio_key] = {'label': "🎵 Audio Only (Best Quality MP3)", 'format': 'bestaudio/best'}

    for key, val in options.items():
        print(f"   [{key}] {val['label']}")

    while True:
        choice = input(f"\n{C.BOLD}Choose an option [1-{len(options)}] or 'q' to quit: {C.END}").strip()
        if choice.lower() in ['q', 'quit']:
            return None
        if choice in options:
            print(f"{C.GREEN}✅ Selected: {options[choice]['label']}{C.END}")
            return options[choice]['format']
        print(f"{C.RED}❌ Invalid choice. Please try again.{C.END}")

def download_content(url: str, format_id: str, output_dir: str, info: Dict, has_ffmpeg: bool, max_downloads: Optional[int], cookies_from: Optional[str]):
    """Handle the download process with robust options."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    content_type = info.get('_type', 'video')
    playlist_title = re.sub(r'[<>:"/\\|?*]', '_', info.get('title', 'YouTube Playlist'))[:60]

    template = (
        str(output_path / playlist_title / '%(playlist_index)03d - %(title)s [%(id)s].%(ext)s')
        if content_type in ['playlist', 'multi_video']
        else str(output_path / '%(title)s [%(id)s].%(ext)s')
    )

    ydl_opts = {
        'outtmpl': template,
        'progress_hooks': [EnhancedProgressHook()],
        'ignoreerrors': True,
        'retries': 10,
        'fragment_retries': 10,
        'socket_timeout': 30,
        'format': format_id,
        'nocheckcertificate': True,
        'no_mtime': True, # Helps prevent filesystem permission errors
    }

    if max_downloads:
        ydl_opts['playlistend'] = max_downloads
    
    if cookies_from:
        ydl_opts['cookiesfrombrowser'] = [cookies_from]

    if format_id == 'bestaudio/best':
        if has_ffmpeg:
            ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
        else:
            print(f"{C.RED}❌ Cannot extract to MP3 without FFmpeg. Aborting.{C.END}")
            return

    print(f"\n{C.GREEN}🚀 Starting download...{C.END}")
    print(f"   📁 Output: {output_path.resolve()}")
    
    start_time = time.time()
    with YoutubeDL(ydl_opts) as ydl:
        result = ydl.download([url])

    elapsed = time.time() - start_time
    print(f"\n{C.GREEN}🎉 All downloads finished!{C.END}")
    print(f"   ⏱️ Total time: {format_duration(int(elapsed))}")
    if result != 0:
        print(f"{C.YELLOW}⚠️ Some videos in the playlist may have been skipped due to errors (like 403 Forbidden).{C.END}")


def main():
    """Main function to parse arguments and orchestrate the download."""
    parser = argparse.ArgumentParser(
        description='🎥 Enhanced YouTube Downloader - Final Version',
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=f"""
{C.BOLD}Examples:{C.END}
  {C.CYAN}Download a playlist interactively:{C.END}
    %(prog)s -u "YOUTUBE_URL"

  {C.CYAN}Download using cookies from Firefox to avoid 403 errors:{C.END}
    %(prog)s -u "YOUTUBE_URL" --cookies-from-browser firefox

  {C.CYAN}Supported browsers for cookies:{C.END}
    brave, chrome, chromium, edge, firefox, opera, safari, vivaldi
"""
    )
    parser.add_argument('-u', '--url', required=True, help='YouTube URL (video, playlist, or channel)')
    parser.add_argument('-o', '--output', default='./YouTube_Downloads', help='Output directory')
    parser.add_argument('--max-downloads', type=int, help='Max number of videos to download from a playlist/channel')
    # NEW: Argument for using cookies
    parser.add_argument('--cookies-from-browser', type=str, help='Name of the browser to load cookies from (e.g., chrome, firefox)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging to file')
    args = parser.parse_args()

    setup_logging(args.debug)
    print(f"{C.BOLD}{C.BLUE}🎥 Welcome to the Enhanced YouTube Downloader{C.END}")
    print(f"{C.BLUE}{'='*50}{C.END}")

    has_ffmpeg = check_dependencies().get('ffmpeg', False)

    info = get_content_info(args.url, args.cookies_from_browser)
    if not info:
        sys.exit(1)

    display_content_info(info)

    format_id = select_format(has_ffmpeg)
    if not format_id:
        print(f"{C.YELLOW}👋 No format selected. Exiting.{C.END}")
        sys.exit(0)

    download_content(args.url, format_id, args.output, info, has_ffmpeg, args.max_downloads, args.cookies_from_browser)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}👋 Download cancelled by user. Goodbye!{C.END}")
        sys.exit(0)
    except Exception as e:
        print(f"{C.RED}❌ A fatal, unexpected error occurred: {e}{C.END}")
        logging.critical(f"Fatal error in main execution: {e}", exc_info=True)
        sys.exit(1)
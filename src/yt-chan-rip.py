#!/usr/bin/env python3
"""
YouTube Channel Audio Ripper
Downloads all videos from a YouTube channel as high-quality MP3 files.
Uses yt-dlp for extraction and ffmpeg for audio conversion.
"""

import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import yt_dlp


# Configuration
DEFAULT_OUTPUT_DIR = "./output"
MAX_CONCURRENT_DOWNLOADS = 4
SCRIPT_DIR = Path(__file__).parent.parent.resolve()
FFMPEG_DIR = SCRIPT_DIR / "ffmpeg"


def derive_channel_dir_name(channel_url: str) -> str:
    """
    Turn a YouTube channel URL into a safe folder name.
    
    Supports @handles, /channel/UC*, /c/custom, /user/name forms and strips
    trailing /videos.
    """
    parsed = urlparse(channel_url)
    path = parsed.path.rstrip('/')
    if path.endswith('/videos'):
        path = path[:-len('/videos')]
    segments = [seg for seg in path.split('/') if seg]
    
    candidate = ""
    if segments:
        if segments[0] in ('channel', 'c', 'user') and len(segments) > 1:
            candidate = segments[1]
        else:
            candidate = segments[-1]
    else:
        candidate = parsed.netloc
    
    if candidate.startswith('@'):
        candidate = candidate[1:]
    
    # Replace disallowed filesystem chars with underscores
    candidate = re.sub(r'[^A-Za-z0-9._-]+', '_', candidate)
    return candidate or "channel"


def get_ffmpeg_location() -> str:
    """Get the path to the ffmpeg directory."""
    import subprocess
    
    # First try the bundled ffmpeg
    ffmpeg_binary = FFMPEG_DIR / "ffmpeg"
    if ffmpeg_binary.exists():
        # Verify it can actually run on this system
        try:
            result = subprocess.run(
                [str(ffmpeg_binary), "-version"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                return str(FFMPEG_DIR.resolve())
        except (subprocess.SubprocessError, OSError):
            pass  # Bundled ffmpeg doesn't work, try system
    
    # Fallback to system ffmpeg (empty string means use system PATH)
    return ""


def get_channel_video_urls(channel_url: str) -> list[dict]:
    """
    Extract all video URLs and metadata from a YouTube channel.
    
    Args:
        channel_url: The YouTube channel URL (e.g., https://www.youtube.com/@channelname)
    
    Returns:
        List of video info dictionaries containing url and title
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'ignoreerrors': True,
    }
    
    # Append /videos to ensure we get the videos tab
    if not channel_url.endswith('/videos'):
        if channel_url.endswith('/'):
            channel_url = channel_url + 'videos'
        else:
            channel_url = channel_url + '/videos'
    
    print(f"[INFO] Fetching video list from: {channel_url}")
    
    videos = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            result = ydl.extract_info(channel_url, download=False)
            if result is None:
                print("[ERROR] Could not extract channel information")
                return []
            
            # Handle channel/playlist entries
            if 'entries' in result:
                for entry in result['entries']:
                    if entry is None:
                        continue
                    # Some entries might be nested (tabs)
                    if 'entries' in entry:
                        for nested_entry in entry['entries']:
                            if nested_entry and 'url' in nested_entry:
                                videos.append({
                                    'url': nested_entry.get('url') or nested_entry.get('webpage_url'),
                                    'title': nested_entry.get('title', 'Unknown'),
                                    'id': nested_entry.get('id', 'unknown')
                                })
                    elif 'url' in entry:
                        videos.append({
                            'url': entry.get('url') or entry.get('webpage_url'),
                            'title': entry.get('title', 'Unknown'),
                            'id': entry.get('id', 'unknown')
                        })
            
            print(f"[INFO] Found {len(videos)} videos")
            
        except Exception as e:
            print(f"[ERROR] Failed to fetch channel videos: {e}")
            return []
    
    return videos


def download_audio(video_info: dict, output_dir: str, ffmpeg_location: str) -> dict:
    """
    Download a single video and convert it to MP3.
    
    Args:
        video_info: Dictionary containing video url, title, and id
        output_dir: Directory to save the MP3 file
        ffmpeg_location: Path to ffmpeg binaries
    
    Returns:
        Dictionary with download status and info
    """
    video_url = video_info['url']
    video_title = video_info['title']
    video_id = video_info['id']
    
    # Build full YouTube URL if only ID is provided
    if not video_url.startswith('http'):
        video_url = f"https://www.youtube.com/watch?v={video_url}"
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'writethumbnail': True,           # download a thumbnail to embed
        'convert_thumbnails': 'jpg',      # ensure common album-art format
        # Only set ffmpeg_location if we have a custom path
        **({'ffmpeg_location': ffmpeg_location} if ffmpeg_location else {}),
        'postprocessors': [
            {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '0',  # 0 = best quality (VBR)
            },
            {
                'key': 'FFmpegMetadata',
                'add_metadata': True,
            },
            {
                'key': 'EmbedThumbnail',
                'already_have_thumbnail': False,
            },
        ],
        'postprocessor_args': {
            'FFmpegExtractAudio': ['-q:a', '0'],  # highest quality VBR for LAME encoder
        },
        'quiet': False,
        'no_warnings': False,
        'ignoreerrors': False,
        'noplaylist': True,
        'retries': 3,
        'fragment_retries': 3,
    }
    
    result = {
        'video_id': video_id,
        'title': video_title,
        'url': video_url,
        'success': False,
        'error': None
    }
    
    try:
        print(f"[DOWNLOADING] {video_title}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        result['success'] = True
        print(f"[SUCCESS] {video_title}")
    except Exception as e:
        result['error'] = str(e)
        print(f"[FAILED] {video_title}: {e}")
    
    return result


def download_channel_audio(
    channel_url: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    max_workers: int = MAX_CONCURRENT_DOWNLOADS,
    limit: Optional[int] = None
) -> dict:
    """
    Download all videos from a YouTube channel as MP3 files.
    
    Args:
        channel_url: YouTube channel URL
        output_dir: Directory to save MP3 files
        max_workers: Maximum number of concurrent downloads
        limit: Optional limit on number of videos to download
    
    Returns:
        Dictionary with download statistics
    """
    # Create output directory scoped to channel
    channel_dir_name = derive_channel_dir_name(channel_url)
    output_path = Path(output_dir) / channel_dir_name
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Get ffmpeg location
    ffmpeg_location = get_ffmpeg_location()
    print(f"[INFO] Using ffmpeg from: {ffmpeg_location if ffmpeg_location else 'system PATH'}")
    print(f"[INFO] Channel folder: {channel_dir_name}")
    print(f"[INFO] Output directory: {output_path.resolve()}")
    
    # Get all video URLs from the channel
    videos = get_channel_video_urls(channel_url)
    
    if not videos:
        print("[ERROR] No videos found in the channel")
        return {'total': 0, 'success': 0, 'failed': 0, 'errors': []}
    
    # Apply limit if specified
    if limit and limit > 0:
        videos = videos[:limit]
        print(f"[INFO] Limited to {limit} videos")
    
    stats = {
        'total': len(videos),
        'success': 0,
        'failed': 0,
        'errors': []
    }
    
    print(f"\n[INFO] Starting download of {len(videos)} videos with {max_workers} concurrent workers\n")
    print("=" * 60)
    
    # Download videos concurrently
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all download tasks
        future_to_video = {
            executor.submit(download_audio, video, str(output_path), ffmpeg_location): video
            for video in videos
        }
        
        # Process completed downloads
        for future in as_completed(future_to_video):
            video = future_to_video[future]
            try:
                result = future.result()
                if result['success']:
                    stats['success'] += 1
                else:
                    stats['failed'] += 1
                    stats['errors'].append({
                        'title': result['title'],
                        'error': result['error']
                    })
            except Exception as e:
                stats['failed'] += 1
                stats['errors'].append({
                    'title': video.get('title', 'Unknown'),
                    'error': str(e)
                })
    
    print("=" * 60)
    print(f"\n[COMPLETE] Downloaded: {stats['success']}/{stats['total']} videos")
    if stats['failed'] > 0:
        print(f"[FAILED] {stats['failed']} videos failed to download")
        for error in stats['errors']:
            print(f"  - {error['title']}: {error['error']}")
    
    return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Download all videos from a YouTube channel as MP3 files.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://www.youtube.com/@channelname
  %(prog)s https://www.youtube.com/@channelname -o ./my_music
  %(prog)s https://www.youtube.com/@channelname -w 8 --limit 10
        """
    )
    
    parser.add_argument(
        'channel_url',
        help='YouTube channel URL (e.g., https://www.youtube.com/@channelname)'
    )
    
    parser.add_argument(
        '-o', '--output',
        default=DEFAULT_OUTPUT_DIR,
        help=f'Output directory for MP3 files (default: {DEFAULT_OUTPUT_DIR})'
    )
    
    parser.add_argument(
        '-w', '--workers',
        type=int,
        default=MAX_CONCURRENT_DOWNLOADS,
        help=f'Number of concurrent downloads (default: {MAX_CONCURRENT_DOWNLOADS})'
    )
    
    parser.add_argument(
        '-l', '--limit',
        type=int,
        default=None,
        help='Limit the number of videos to download (default: all)'
    )
    
    args = parser.parse_args()
    
    # Validate URL
    if not args.channel_url.startswith('https://www.youtube.com/'):
        print("[ERROR] Invalid YouTube URL. Please provide a valid YouTube channel URL.")
        print("Example: https://www.youtube.com/@channelname")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("  YouTube Channel Audio Ripper")
    print("=" * 60)
    print(f"  Channel: {args.channel_url}")
    print(f"  Output:  {args.output}")
    print(f"  Workers: {args.workers}")
    if args.limit:
        print(f"  Limit:   {args.limit} videos")
    print("=" * 60 + "\n")
    
    # Start download
    stats = download_channel_audio(
        channel_url=args.channel_url,
        output_dir=args.output,
        max_workers=args.workers,
        limit=args.limit
    )
    
    # Exit with error code if any downloads failed
    if stats['failed'] > 0:
        sys.exit(1)
    
    sys.exit(0)


if __name__ == '__main__':
    main()

# YouTube Channel Audio Ripper

Download all videos from a YouTube channel as high-quality MP3 files.

## Usage

### Makefile Commands

| Command | Description |
|---------|-------------|
| `make run URL=<url>` | Download all videos as MP3 |
| `make clean` | Remove downloaded files |
| `make help` | Show usage information |

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `URL` | required | YouTube channel URL |
| `WORKERS` | 4 | Number of concurrent downloads |
| `OUTPUT` | ./output | Output directory for MP3 files |
| `LIMIT` | all | Limit number of videos to download |


### Script Options

```
positional arguments:
  channel_url           YouTube channel URL

options:
  -h, --help            show help message
  -o, --output OUTPUT   Output directory (default: ./output)
  -w, --workers N       Concurrent downloads (default: 4)
  -l, --limit N         Limit videos to download
```

## Example Usage

```bash
# Download all videos from a channel as MP3
make run URL=https://www.youtube.com/@channelname

# With custom settings
make run URL=https://www.youtube.com/@channelname WORKERS=8 OUTPUT=./my_music

# Test with limited downloads
make run URL=https://www.youtube.com/@channelname LIMIT=5
```
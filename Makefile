.PHONY: run install test clean help

# Default number of concurrent download workers
WORKERS ?= 4

# Output directory for downloaded MP3 files
OUTPUT ?= ./output

# Optional limit on number of videos to download
LIMIT ?=

help:
	@echo "YouTube Channel Audio Ripper"
	@echo ""
	@echo "Usage:"
	@echo "  make run URL=<youtube_channel_url>    Download all videos as MP3"
	@echo "  make clean                            Remove downloaded files"
	@echo ""
	@echo "Options:"
	@echo "  URL=<url>       YouTube channel URL (required for 'run')"
	@echo "  WORKERS=<n>     Number of concurrent downloads (default: 4)"
	@echo "  OUTPUT=<dir>    Output directory (default: ./output)"
	@echo "  LIMIT=<n>       Limit number of videos to download"
	@echo ""
	@echo "Examples:"
	@echo "  make run URL=https://www.youtube.com/@channelname"
	@echo "  make run URL=https://www.youtube.com/@channelname WORKERS=8"
	@echo "  make run URL=https://www.youtube.com/@channelname LIMIT=10"

run:
ifndef URL
	@echo "Error: URL is required"
	@echo "Usage: make run URL=https://www.youtube.com/@channelname"
	@exit 1
endif
	( [ -d venv ] || python3 -m venv venv; ) && \
	. venv/bin/activate && \
	pip install --upgrade pip -q && \
	pip install -r requirements.txt -q && \
	python ./src/yt-chan-rip.py "$(URL)" -o "$(OUTPUT)" -w $(WORKERS) $(if $(LIMIT),-l $(LIMIT),)

clean:
	rm -rf ./output/*
	@echo "Output directory cleaned"

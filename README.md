# YouTube Shorts Uploader API Server

A Flask-based API server for uploading YouTube Shorts with custom sound overlay support.

## Setup

1. Create a project in the Google Cloud Console
2. Enable the YouTube Data API v3
3. Create OAuth 2.0 credentials
4. Download the credentials and save them in the `config` directory as `{accountname}.json`

## Running with Docker

```bash
docker-compose up --build
```

## API Usage

Upload a Short with the following curl command:

```bash
curl -X POST http://localhost:8048/upload \
  -F "video=@/path/to/video.mp4" \
  -F "description=Your video description" \
  -F "accountname=your_account" \
  -F "sound_name=background.mp3" \
  -F "sound_aud_vol=1.0" \
  -F "hashtags=viral,trending"
```

### Parameters

- `video`: The video file to upload (required)
- `description`: Video description (optional)
- `accountname`: YouTube account name (matches config file name)
- `sound_name`: Background sound file name (optional)
- `sound_aud_vol`: Sound volume multiplier (optional, default: 1.0)
- `hashtags`: Comma-separated hashtags (optional)

### Response

Success:
```json
{
    "success": true,
    "video_id": "VIDEO_ID",
    "url": "https://youtube.com/shorts/VIDEO_ID"
}
```

Error:
```json
{
    "error": "Error message"
}
```

## File Structure

```
├── app/
│   └── main.py
├── config/
│   └── {accountname}.json
├── sounds/
│   └── (your sound files)
├── temp/
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Requirements

- Docker
- YouTube API credentials
- Vertical video format (9:16 aspect ratio)
- Video duration ≤ 60 seconds
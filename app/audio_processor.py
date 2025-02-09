import subprocess
import tempfile
import os
import logging

logger = logging.getLogger(__name__)

class AudioProcessor:
    def __init__(self):
        self.volume_presets = {
            'mix': ('0.5', '0.5'),
            'background': ('0.9', '0.1'),  # Reduced background volume from 0.2 to 0.1
            'main': ('0.2', '0.8')
        }

    def mix_audio(self, video_path, sound_path, volume_type='mix'):
        if volume_type not in self.volume_presets:
            volume_type = 'mix'

        video_vol, sound_vol = self.volume_presets[volume_type]
        
        # Create temporary file with a unique name
        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, f'output_{os.urandom(8).hex()}.mp4')

        # Validate input files first
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        if not os.path.exists(sound_path):
            raise FileNotFoundError(f"Sound file not found: {sound_path}")

        # First, verify the input video file
        try:
            probe_cmd = [
                'ffmpeg', '-v', 'error',
                '-i', video_path,
                '-f', 'null', '-'
            ]
            subprocess.run(probe_cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Invalid input video file: {e.stderr}")
            raise ValueError("The input video file appears to be corrupted or invalid")

        cmd = [
            'ffmpeg',
            '-y',  # Force overwrite
            '-i', video_path,
            '-i', sound_path,
            '-filter_complex',
            f'[0:a]volume={video_vol}[a1];[1:a]volume={sound_vol}[a2];[a1][a2]amix=inputs=2:duration=first[aout]',
            '-map', '0:v',
            '-map', '[aout]',
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-movflags', '+faststart',  # Optimize for web playback
            output_path
        ]

        try:
            process = subprocess.run(cmd, check=True, capture_output=True, text=True)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
            else:
                raise subprocess.CalledProcessError(1, cmd, process.stdout, process.stderr)
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg Error: {e.stderr}")
            if os.path.exists(output_path):
                os.unlink(output_path)
            raise RuntimeError(f"Failed to process video: {e.stderr}")
        except Exception as e:
            logger.error(f"Unexpected error during video processing: {str(e)}")
            if os.path.exists(output_path):
                os.unlink(output_path)
            raise
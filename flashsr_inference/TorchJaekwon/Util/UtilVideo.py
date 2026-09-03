from typing import Literal, Tuple

import os
import subprocess
import numpy as np
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip
try: from pydub import AudioSegment
except: print('pydub is not installed. Please install it using `pip install pydub`')

class UtilVideo:
    @staticmethod
    def extract_audio_from_video(video_path:str,
                                 output_path:str = './tmp/tmp.wav',
                                 ) -> str:
        video = VideoFileClip(video_path)
        audio = video.audio
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        audio.write_audiofile(output_path, codec='pcm_s16le')
        return output_path

    @staticmethod
    def attach_audio_to_video(video_path:str, 
                              audio_path:str, 
                              output_path:str, 
                              fps:int=30, 
                              video_duration_sec:float = None,
                              audio_codec:Literal['aac', 'pcm_s16le', 'pcm_s32le'] = 'aac',
                              ) -> VideoFileClip:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        video_clip = VideoFileClip(video_path).set_fps(fps)
        if video_duration_sec is not None:
            video_clip = video_clip.subclip(0, video_duration_sec)
        video_clip = video_clip.set_audio(AudioFileClip(audio_path))
        video_clip.write_videofile(
            output_path, 
            audio=True, 
            audio_codec = audio_codec,
            fps=fps, 
            verbose=False, 
            logger=None
        )
        return video_clip
    
    @staticmethod
    def attach_audio_to_img(image_path:str,
                            audio_path:str,
                            output_path:str = 'output.mkv',
                            audio_codec:Literal['aac', 'pcm_s16le', 'pcm_s32le'] = 'pcm_s32le',
                            audio_fps:int=44100,
                            video_size:Tuple[int,int]=(1920,1080),
                            module:Literal['moviepy', 'ffmpeg'] = 'moviepy'
                            ):
        if module == 'moviepy':
            import PIL
            PIL.Image.ANTIALIAS = PIL.Image.LANCZOS
            audio = AudioFileClip(audio_path)
            image_clip:ImageClip = ImageClip(image_path).set_duration(audio.duration).resize(newsize=video_size)
            video = image_clip.set_audio(audio)
            video.write_videofile(output_path, 
                                  codec='libx264', 
                                  audio_fps = audio_fps,
                                  audio_codec=audio_codec, 
                                  fps=24)
        elif module == 'ffmpeg':
            subprocess.run([
                'ffmpeg', '-loop', '1', '-i', image_path, '-i', audio_path,
                '-vf', f'scale={video_size[0]}:{video_size[1]}', '-c:v', 'libx264', 
                '-c:a', 'aac', '-shortest', output_path
            ])

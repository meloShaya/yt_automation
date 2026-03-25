import os
import uuid
import subprocess

import requests
import srt_equalizer
import assemblyai as aai

from typing import List
from moviepy.editor import *
from termcolor import colored
from dotenv import load_dotenv
from datetime import timedelta
from moviepy.video.fx.all import crop
from moviepy.video.tools.subtitles import SubtitlesClip

load_dotenv("../.env")

ASSEMBLY_AI_API_KEY = os.getenv("ASSEMBLY_AI_API_KEY")


def save_video(video_url: str, directory: str = "../temp") -> str:
    """
    Saves a video from a given URL and returns the path to the video.

    Args:
        video_url (str): The URL of the video to save.
        directory (str): The path of the temporary directory to save the video to

    Returns:
        str: The path to the saved video.
    """
    video_id = uuid.uuid4()
    video_path = f"{directory}/{video_id}.mp4"
    with open(video_path, "wb") as f:
        f.write(requests.get(video_url).content)

    return video_path


def __generate_subtitles_assemblyai(audio_path: str, voice: str) -> str:
    """
    Generates subtitles from a given audio file and returns the path to the subtitles.

    Args:
        audio_path (str): The path to the audio file to generate subtitles from.

    Returns:
        str: The generated subtitles
    """

    language_mapping = {
        "br": "pt",
        "id": "en", #AssemblyAI doesn't have Indonesian 
        "jp": "ja",
        "kr": "ko",
    }

    if voice in language_mapping:
        lang_code = language_mapping[voice]
    else:
        lang_code = voice

    aai.settings.api_key = ASSEMBLY_AI_API_KEY
    config = aai.TranscriptionConfig(language_code=lang_code)
    transcriber = aai.Transcriber(config=config)
    transcript = transcriber.transcribe(audio_path)
    subtitles = transcript.export_subtitles_srt()

    return subtitles


def __generate_subtitles_locally(sentences: List[str], audio_clips: List[AudioFileClip]) -> str:
    """
    Generates subtitles from a given audio file and returns the path to the subtitles.

    Args:
        sentences (List[str]): all the sentences said out loud in the audio clips
        audio_clips (List[AudioFileClip]): all the individual audio clips which will make up the final audio track
    Returns:
        str: The generated subtitles
    """

    def convert_to_srt_time_format(total_seconds):
        # Convert total seconds to the SRT time format: HH:MM:SS,mmm
        if total_seconds == 0:
            return "0:00:00,0"
        return str(timedelta(seconds=total_seconds)).rstrip('0').replace('.', ',')

    start_time = 0
    subtitles = []

    for i, (sentence, audio_clip) in enumerate(zip(sentences, audio_clips), start=1):
        duration = audio_clip.duration
        end_time = start_time + duration

        # Format: subtitle index, start time --> end time, sentence
        subtitle_entry = f"{i}\n{convert_to_srt_time_format(start_time)} --> {convert_to_srt_time_format(end_time)}\n{sentence}\n"
        subtitles.append(subtitle_entry)

        start_time += duration  # Update start time for the next subtitle

    return "\n".join(subtitles)


def generate_subtitles(audio_path: str, sentences: List[str], audio_clips: List[AudioFileClip], voice: str) -> str:
    """
    Generates subtitles from a given audio file and returns the path to the subtitles.

    Args:
        audio_path (str): The path to the audio file to generate subtitles from.
        sentences (List[str]): all the sentences said out loud in the audio clips
        audio_clips (List[AudioFileClip]): all the individual audio clips which will make up the final audio track

    Returns:
        str: The path to the generated subtitles.
    """

    def equalize_subtitles(srt_path: str, max_chars: int = 10) -> None:
        # Equalize subtitles
        srt_equalizer.equalize_srt_file(srt_path, srt_path, max_chars)

    # Save subtitles
    subtitles_path = f"../subtitles/{uuid.uuid4()}.srt"

    if ASSEMBLY_AI_API_KEY is not None and ASSEMBLY_AI_API_KEY != "":
        print(colored("[+] Creating subtitles using AssemblyAI", "blue"))
        subtitles = __generate_subtitles_assemblyai(audio_path, voice)
    else:
        print(colored("[+] Creating subtitles locally", "blue"))
        subtitles = __generate_subtitles_locally(sentences, audio_clips)
        # print(colored("[-] Local subtitle generation has been disabled for the time being.", "red"))
        # print(colored("[-] Exiting.", "red"))
        # sys.exit(1)

    with open(subtitles_path, "w") as file:
        file.write(subtitles)

    # Equalize subtitles
    equalize_subtitles(subtitles_path)

    print(colored("[+] Subtitles generated.", "green"))

    return subtitles_path


def _process_clip_to_segment(video_path: str, target_duration: float, max_clip_duration: int, threads: int) -> tuple:
    """
    Process a single video clip (crop, resize, trim) and write it to a temp segment file.
    Returns (segment_path, clip_duration). The clip is closed before returning.
    """
    segment_path = f"../temp/seg_{uuid.uuid4()}.mp4"
    clip = VideoFileClip(video_path)
    try:
        clip = clip.without_audio()

        # Trim to target duration
        if target_duration < clip.duration:
            clip = clip.subclip(0, target_duration)

        clip = clip.set_fps(30)

        # Crop to 9:16 aspect ratio
        if round((clip.w / clip.h), 4) < 0.5625:
            clip = crop(clip, width=clip.w, height=round(clip.w / 0.5625),
                        x_center=clip.w / 2, y_center=clip.h / 2)
        else:
            clip = crop(clip, width=round(0.5625 * clip.h), height=clip.h,
                        x_center=clip.w / 2, y_center=clip.h / 2)

        clip = clip.resize((1080, 1920))

        if clip.duration > max_clip_duration:
            clip = clip.subclip(0, max_clip_duration)

        duration = clip.duration
        clip.write_videofile(
            segment_path,
            threads=threads,
            preset="ultrafast",
            logger=None,
        )
    finally:
        clip.close()

    return segment_path, duration


def _ffmpeg_concat(segment_paths: List[str], output_path: str) -> None:
    """
    Concatenate video segments using ffmpeg concat demuxer.
    This streams from disk with near-zero RAM usage and does not re-encode.
    """
    concat_list_path = f"../temp/concat_{uuid.uuid4()}.txt"
    try:
        with open(concat_list_path, "w") as f:
            for seg in segment_paths:
                # ffmpeg concat demuxer requires absolute or properly escaped paths
                abs_path = os.path.abspath(seg)
                f.write(f"file '{abs_path}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(colored(f"[!] ffmpeg concat stderr: {result.stderr[-500:]}", "yellow"))
            raise RuntimeError(f"ffmpeg concat failed (exit {result.returncode})")
    finally:
        if os.path.exists(concat_list_path):
            os.remove(concat_list_path)


def combine_videos(video_paths: List[str], max_duration: int, max_clip_duration: int, threads: int) -> str:
    """
    Combines a list of videos into one video and returns the path to the combined video.

    Uses a memory-efficient approach: each clip is processed individually and written
    to a temp file (only 1 clip in RAM at a time), then joined via ffmpeg concat demuxer
    which streams from disk with near-zero memory usage.

    Args:
        video_paths (List): A list of paths to the videos to combine.
        max_duration (int): The maximum duration of the combined video.
        max_clip_duration (int): The maximum duration of each clip.
        threads (int): The number of threads to use for the video processing.

    Returns:
        str: The path to the combined video.
    """
    video_id = uuid.uuid4()
    combined_video_path = f"../temp/{video_id}.mp4"
    
    # Required duration of each clip
    req_dur = max_duration / len(video_paths)

    print(colored("[+] Combining videos...", "blue"))
    print(colored(f"[+] Each clip will be maximum {req_dur} seconds long.", "blue"))

    segment_files = []
    tot_dur = 0

    try:
        # Process clips one at a time — only 1 clip in RAM at any moment
        while tot_dur < max_duration:
            for video_path in video_paths:
                remaining = max_duration - tot_dur
                if remaining <= 0:
                    break

                target_dur = min(req_dur, remaining)

                print(colored(f"[+] Processing segment {len(segment_files) + 1} ({target_dur:.1f}s)...", "blue"))
                seg_path, actual_dur = _process_clip_to_segment(
                    video_path, target_dur, max_clip_duration, threads
                )
                segment_files.append(seg_path)
                tot_dur += actual_dur

                if tot_dur >= max_duration:
                    break

        # Join all segments via ffmpeg (streams from disk, near-zero RAM)
        print(colored(f"[+] Joining {len(segment_files)} segments...", "blue"))
        _ffmpeg_concat(segment_files, combined_video_path)

    finally:
        # Clean up temp segment files
        for seg in segment_files:
            try:
                if os.path.exists(seg):
                    os.remove(seg)
            except Exception:
                pass

    return combined_video_path


def generate_video(combined_video_path: str, tts_path: str, subtitles_path: str, threads: int, subtitles_position: str,  text_color : str) -> str:
    """
    This function creates the final video, with subtitles and audio.

    Args:
        combined_video_path (str): The path to the combined video.
        tts_path (str): The path to the text-to-speech audio.
        subtitles_path (str): The path to the subtitles.
        threads (int): The number of threads to use for the video processing.
        subtitles_position (str): The position of the subtitles.

    Returns:
        str: The path to the final video.
    """
    # Make a generator that returns a TextClip when called with consecutive
    generator = lambda txt: TextClip(
        txt,
        font="../fonts/bold_font.ttf",
        fontsize=100,
        color=text_color,
        stroke_color="black",
        stroke_width=5,
    )

    # Split the subtitles position into horizontal and vertical
    horizontal_subtitles_position, vertical_subtitles_position = subtitles_position.split(",")

    video_clip = None
    subtitles = None
    result = None
    audio = None

    try:
        # Burn the subtitles into the video
        subtitles = SubtitlesClip(subtitles_path, generator)
        video_clip = VideoFileClip(combined_video_path)
        result = CompositeVideoClip([
            video_clip,
            subtitles.set_pos((horizontal_subtitles_position, vertical_subtitles_position))
        ])

        # Add the audio
        audio = AudioFileClip(tts_path)
        result = result.set_audio(audio)

        result.write_videofile("../temp/output.mp4", threads=threads or 2)
    finally:
        # Close all clips to free memory and file handles
        for clip_obj in [result, subtitles, video_clip, audio]:
            if clip_obj is not None:
                try:
                    clip_obj.close()
                except Exception:
                    pass

    return "output.mp4"

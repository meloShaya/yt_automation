import os
import json
import time
import random
from utils import *
from dotenv import load_dotenv

# Load environment variables
load_dotenv("../.env")
# Check if all required environment variables are set
# This must happen before importing video which uses API keys without checking
check_env_vars()

from gpt import *
from video import *
from search import *
from uuid import uuid4
from tiktokvoice import *
from flask_cors import CORS
from termcolor import colored
from youtube import upload_video
from apiclient.errors import HttpError
from flask import Flask, request, jsonify
from moviepy.config import change_settings



# Set environment variables
SESSION_ID = os.getenv("TIKTOK_SESSION_ID")
openai_api_key = os.getenv("OPENAI_API_KEY")
imagemagick_binary = resolve_imagemagick_binary()
if imagemagick_binary:
    change_settings({"IMAGEMAGICK_BINARY": imagemagick_binary})

# Initialize Flask
app = Flask(__name__)
CORS(app)

# Constants
HOST = "0.0.0.0"
PORT = 8080
AMOUNT_OF_STOCK_VIDEOS = 5
GENERATING = False
JOB_STATE_PATH = "../temp/job_state.json"
TTS_RETRIES = int(os.getenv("TTS_RETRIES", "3"))
TTS_BACKOFF_SECONDS = float(os.getenv("TTS_BACKOFF_SECONDS", "1.5"))


def save_job_state(state: dict) -> None:
    os.makedirs(os.path.dirname(JOB_STATE_PATH), exist_ok=True)
    with open(JOB_STATE_PATH, "w", encoding="utf-8") as file:
        json.dump(state, file, indent=2)


def load_job_state() -> dict | None:
    if not os.path.exists(JOB_STATE_PATH):
        return None
    with open(JOB_STATE_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def _filter_existing_paths(paths: list[str]) -> list[str]:
    return [path for path in paths if path and os.path.exists(path)]


def _attempt_tts(sentence: str, voice: str, output_path: str) -> bool:
    for attempt in range(1, TTS_RETRIES + 1):
        tts(sentence, voice, filename=output_path)
        if os.path.exists(output_path):
            return True
        if attempt < TTS_RETRIES:
            backoff = TTS_BACKOFF_SECONDS * (2 ** (attempt - 1))
            jitter = random.uniform(0, 0.25 * backoff)
            print(colored(f"[!] TTS retry {attempt}/{TTS_RETRIES} in {backoff + jitter:.1f}s", "yellow"))
            time.sleep(backoff + jitter)
    return False


def run_generation(data: dict, resume_state: dict | None = None):
    try:
        # Set global variable
        global GENERATING
        GENERATING = True

        # Clean only on a fresh run
        if resume_state is None:
            clean_dir("../temp/")
            clean_dir("../subtitles/")
        else:
            os.makedirs("../temp", exist_ok=True)
            os.makedirs("../subtitles", exist_ok=True)

        # Parse JSON
        paragraph_number = int(data.get("paragraphNumber", 1))
        ai_model = data.get("aiModel")
        n_threads = data.get("threads")
        subtitles_position = data.get("subtitlesPosition")
        text_color = data.get("color")

        use_music = data.get("useMusic", False)
        automate_youtube_upload = data.get("automateYoutubeUpload", False)
        songs_zip_url = data.get("zipUrl")

        state = resume_state or {
            "stage": "init",
            "request": data,
        }
        save_job_state(state)

        # Download songs
        if use_music:
            if songs_zip_url:
                fetch_songs(songs_zip_url)
            else:
                fetch_songs("https://filebin.net/2avx134kdibc4c3q/drive-download-20240209T180019Z-001.zip")

        # Print little information about the video which is to be generated
        print(colored("[Video to be generated]", "blue"))
        print(colored("   Subject: " + data["videoSubject"], "blue"))
        print(colored("   AI Model: " + ai_model, "blue"))
        print(colored("   Custom Prompt: " + data["customPrompt"], "blue"))

        if not GENERATING:
            return jsonify(
                {
                    "status": "error",
                    "message": "Video generation was cancelled.",
                    "data": [],
                }
            )

        voice = data["voice"]
        voice_prefix = voice[:2]

        if not voice:
            print(colored("[!] No voice was selected. Defaulting to \"en_us_001\"", "yellow"))
            voice = "en_us_001"
            voice_prefix = voice[:2]

        # Generate a script
        script = state.get("script")
        if not script:
            script = generate_script(data["videoSubject"], paragraph_number, ai_model, voice, data["customPrompt"])
            state["script"] = script
            state["stage"] = "script"
            save_job_state(state)

        # Generate search terms
        search_terms = state.get("search_terms")
        if not search_terms:
            search_terms = get_search_terms(
                data["videoSubject"], AMOUNT_OF_STOCK_VIDEOS, script, ai_model
            )
            state["search_terms"] = search_terms
            state["stage"] = "search_terms"
            save_job_state(state)

        # Search for a video of the given search term
        video_urls = state.get("video_urls") or []
        if not video_urls:
            video_urls = []
            it = 15
            min_dur = 10

            for search_term in search_terms:
                if not GENERATING:
                    return jsonify(
                        {
                            "status": "error",
                            "message": "Video generation was cancelled.",
                            "data": [],
                        }
                    )
                found_urls = search_for_stock_videos(
                    search_term, os.getenv("PEXELS_API_KEY"), it, min_dur
                )
                for url in found_urls:
                    if url not in video_urls:
                        video_urls.append(url)
                        break

            state["video_urls"] = video_urls
            state["stage"] = "video_urls"
            save_job_state(state)

        if not video_urls:
            print(colored("[-] No videos found to download.", "red"))
            return jsonify(
                {
                    "status": "error",
                    "message": "No videos found to download.",
                    "data": [],
                }
            )

        # Define video_paths
        video_paths = _filter_existing_paths(state.get("video_paths", []))

        # Let user know
        print(colored(f"[+] Downloading {len(video_urls)} videos...", "blue"))

        if len(video_paths) < len(video_urls):
            for video_url in video_urls:
                if not GENERATING:
                    return jsonify(
                        {
                            "status": "error",
                            "message": "Video generation was cancelled.",
                            "data": [],
                        }
                    )
                try:
                    saved_video_path = save_video(video_url)
                    if saved_video_path not in video_paths:
                        video_paths.append(saved_video_path)
                except Exception:
                    print(colored(f"[-] Could not download video: {video_url}", "red"))

            state["video_paths"] = video_paths
            state["stage"] = "video_paths"
            save_job_state(state)

        # Let user know
        print(colored("[+] Videos downloaded!", "green"))
        print(colored("[+] Script generated!\n", "green"))

        if not GENERATING:
            return jsonify(
                {
                    "status": "error",
                    "message": "Video generation was cancelled.",
                    "data": [],
                }
            )

        # Split script into sentences
        sentences = state.get("sentences")
        if not sentences:
            sentences = script.split(". ")
            sentences = list(filter(lambda x: x != "", sentences))
            state["sentences"] = sentences
            state["stage"] = "sentences"
            save_job_state(state)

        # Generate TTS for every sentence (resume safe)
        tts_paths = state.get("tts_paths")
        if not tts_paths or len(tts_paths) != len(sentences):
            tts_paths = [None] * len(sentences)

        for idx, sentence in enumerate(sentences):
            if not GENERATING:
                return jsonify(
                    {
                        "status": "error",
                        "message": "Video generation was cancelled.",
                        "data": [],
                    }
                )

            existing_path = tts_paths[idx]
            if existing_path and os.path.exists(existing_path):
                continue

            current_tts_path = f"../temp/{uuid4()}.mp3"
            if not _attempt_tts(sentence, voice, current_tts_path):
                state["tts_paths"] = tts_paths
                state["stage"] = "tts"
                save_job_state(state)
                return jsonify(
                    {
                        "status": "error",
                        "message": "TTS failed. Fix the issue and call /api/resume to continue.",
                        "data": [],
                    }
                )

            tts_paths[idx] = current_tts_path
            state["tts_paths"] = tts_paths
            state["stage"] = "tts"
            save_job_state(state)

        # Build audio clips from TTS paths
        paths = []
        for tts_file in tts_paths:
            if not tts_file or not os.path.exists(tts_file):
                return jsonify(
                    {
                        "status": "error",
                        "message": "Missing TTS audio files. Call /api/resume to continue.",
                        "data": [],
                    }
                )
            paths.append(AudioFileClip(tts_file))

        # Combine all TTS files using moviepy
        tts_path = state.get("tts_path")
        if not tts_path or not os.path.exists(tts_path):
            final_audio = concatenate_audioclips(paths)
            tts_path = f"../temp/{uuid4()}.mp3"
            final_audio.write_audiofile(tts_path)
            final_audio.close()
            state["tts_path"] = tts_path
            state["stage"] = "audio"
            save_job_state(state)

        # Close TTS audio clips — they are no longer needed
        for clip in paths:
            try:
                clip.close()
            except Exception:
                pass
        paths.clear()

        subtitles_path = state.get("subtitles_path")
        if subtitles_path and not os.path.exists(subtitles_path):
            subtitles_path = None

        if subtitles_path is None:
            try:
                subtitles_path = generate_subtitles(
                    audio_path=tts_path, sentences=sentences, audio_clips=paths, voice=voice_prefix
                )
            except Exception as e:
                print(colored(f"[-] Error generating subtitles: {e}", "red"))
                subtitles_path = None
            state["subtitles_path"] = subtitles_path
            state["stage"] = "subtitles"
            save_job_state(state)

        # Concatenate videos
        combined_video_path = state.get("combined_video_path")
        if not combined_video_path or not os.path.exists(combined_video_path):
            temp_audio = AudioFileClip(tts_path)
            audio_duration = temp_audio.duration
            temp_audio.close()  # Close immediately — only needed for duration
            combined_video_path = combine_videos(video_paths, audio_duration, 5, n_threads or 2)
            state["combined_video_path"] = combined_video_path
            state["stage"] = "combined_video"
            save_job_state(state)

        # Put everything together
        final_video_path = state.get("final_video_path")
        final_video_disk_path = os.path.join("../temp", final_video_path) if final_video_path else None
        if not final_video_path or not final_video_disk_path or not os.path.exists(final_video_disk_path):
            try:
                final_video_path = generate_video(
                    combined_video_path,
                    tts_path,
                    subtitles_path,
                    n_threads or 2,
                    subtitles_position,
                    text_color or "#FFFF00",
                )
            except Exception as e:
                print(colored(f"[-] Error generating final video: {e}", "red"))
                final_video_path = None
            state["final_video_path"] = final_video_path
            state["stage"] = "final_video"
            save_job_state(state)

        # Define metadata for the video
        title, description, keywords = generate_metadata(data["videoSubject"], script, ai_model)

        print(colored("[-] Metadata for YouTube upload:", "blue"))
        print(colored("   Title: ", "blue"))
        print(colored(f"   {title}", "blue"))
        print(colored("   Description: ", "blue"))
        print(colored(f"   {description}", "blue"))
        print(colored("   Keywords: ", "blue"))
        print(colored(f"  {', '.join(keywords)}", "blue"))

        if automate_youtube_upload:
            client_secrets_file = os.path.abspath("./client_secret.json")
            SKIP_YT_UPLOAD = False
            if not os.path.exists(client_secrets_file):
                SKIP_YT_UPLOAD = True
                print(colored("[-] Client secrets file missing. YouTube upload will be skipped.", "yellow"))
                print(colored("[-] Please download the client_secret.json from Google Cloud Platform and store this inside the /Backend directory.", "red"))

            if not SKIP_YT_UPLOAD:
                video_category_id = "28"
                privacyStatus = "private"
                video_metadata = {
                    'video_path': os.path.abspath(f"../temp/{final_video_path}"),
                    'title': title,
                    'description': description,
                    'category': video_category_id,
                    'keywords': ",".join(keywords),
                    'privacyStatus': privacyStatus,
                }

                try:
                    video_response = upload_video(
                        video_path=video_metadata['video_path'],
                        title=video_metadata['title'],
                        description=video_metadata['description'],
                        category=video_metadata['category'],
                        keywords=video_metadata['keywords'],
                        privacyStatus=video_metadata['privacyStatus'],
                    )
                    print(colored("[+] Video uploaded to YouTube!", "green"))
                    print(colored(f"[+] Video ID: {video_response['id']}", "green"))
                except HttpError as e:
                    print(colored(f"[-] An error occurred while uploading the video: {e}", "red"))

        # If music was selected, overlay the audio on the video (resume safe)
        if use_music and final_video_path and not state.get("music_applied"):
            final_video_disk_path = os.path.join("../temp", final_video_path)
            if os.path.exists(final_video_disk_path):
                song_clip = None
                original_audio = None
                video_clip = None
                try:
                    song_path = choose_random_song()
                    song_clip = AudioFileClip(song_path)
                    original_audio = AudioFileClip(tts_path)
                    original_duration = original_audio.duration
                    song_clip = song_clip.set_duration(original_duration)
                    video_clip = VideoFileClip(final_video_disk_path)
                    comp_audio = CompositeAudioClip([original_audio, song_clip])
                    video_clip = video_clip.set_audio(comp_audio)
                    video_clip = video_clip.set_fps(30)
                    video_clip = video_clip.set_duration(original_duration)
                    video_clip.write_videofile(final_video_disk_path, threads=n_threads or 1)
                    state["music_applied"] = True
                    state["stage"] = "music"
                    save_job_state(state)
                except Exception as e:
                    print(colored(f"[-] Error adding music: {e}", "red"))
                finally:
                    for clip_obj in [video_clip, original_audio, song_clip]:
                        if clip_obj is not None:
                            try:
                                clip_obj.close()
                            except Exception:
                                pass

        # Let user know
        print(colored(f"[+] Video generated: {final_video_path}!", "green"))

        # Stop FFMPEG processes
        if os.name == "nt":
            os.system("taskkill /f /im ffmpeg.exe")
        else:
            os.system("pkill -f ffmpeg")

        GENERATING = False
        state["stage"] = "done"
        save_job_state(state)

        return jsonify(
            {
                "status": "success",
                "message": "Video generated! See MoneyPrinter/output.mp4 for result.",
                "data": final_video_path,
            }
        )
    except Exception as err:
        print(colored(f"[-] Error: {str(err)}", "red"))
        return jsonify(
            {
                "status": "error",
                "message": f"Video generation failed: {str(err)}",
                "data": [],
            }
        )


# Generation Endpoint
@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.get_json()
    return run_generation(data)


@app.route("/api/resume", methods=["POST"])
def resume():
    state = load_job_state()
    if not state or "request" not in state:
        return jsonify(
            {
                "status": "error",
                "message": "No resumable job found.",
                "data": [],
            }
        )
    return run_generation(state["request"], resume_state=state)


@app.route("/api/cancel", methods=["POST"])
def cancel():
    print(colored("[!] Received cancellation request...", "yellow"))

    global GENERATING
    GENERATING = False

    return jsonify({"status": "success", "message": "Cancelled video generation."})


if __name__ == "__main__":

    # Run Flask App
    app.run(debug=True, host=HOST, port=PORT)

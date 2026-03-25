import re
import os
import g4f
import json
import openai
import google.generativeai as genai

from g4f.client import Client
from openai import OpenAI
from termcolor import colored
from dotenv import load_dotenv
from typing import Tuple, List

# Load environment variables
load_dotenv("../.env")

# Set environment variables
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
openai.api_key = OPENAI_API_KEY
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "MoneyPrinter")
OPENROUTER_FREE_MODELS = [
    "openai/gpt-oss-120b:free",
    "openai/gpt-oss-20b:free",
    "arcee-ai/trinity-large-preview:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "qwen3-4b:free",
]

_openrouter_headers = {}
if OPENROUTER_SITE_URL:
    _openrouter_headers["HTTP-Referer"] = OPENROUTER_SITE_URL
if OPENROUTER_APP_NAME:
    _openrouter_headers["X-Title"] = OPENROUTER_APP_NAME

OPENROUTER_CLIENT = None
if OPENROUTER_API_KEY:
    OPENROUTER_CLIENT = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers=_openrouter_headers or None,
    )

GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
genai.configure(api_key=GOOGLE_API_KEY)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _ensure_g4f_cookies_file() -> str:
    """
    Ensure g4f cookies file exists for providers that require it.

    Returns:
        str: Path to the cookies file.
    """
    config_dir = os.path.join(os.path.expanduser("~"), ".config", "g4f")
    cookies_path = os.path.join(config_dir, "cookies")
    if not os.path.exists(cookies_path):
        os.makedirs(config_dir, exist_ok=True)
        with open(cookies_path, "w", encoding="utf-8"):
            pass
        print(
            colored(
                f"[!] g4f cookies file was missing and has been created at {cookies_path}.",
                "yellow",
            )
        )
        print(
            colored(
                "[!] If g4f still fails, add valid cookies for the provider or switch AI model.",
                "yellow",
            )
        )
    return cookies_path


def generate_response(prompt: str, ai_model: str) -> str:
    """
    Generate a script for a video, depending on the subject of the video.

    Args:
        video_subject (str): The subject of the video.
        ai_model (str): The AI model to use for generation.


    Returns:

        str: The response from the AI model.

    """

    if ai_model == 'g4f':
        # Newest G4F Architecture
        _ensure_g4f_cookies_file()
        client = Client()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            provider=g4f.Provider.You, 
            messages=[{"role": "user", "content": prompt}],
        ).choices[0].message.content

    elif ai_model in ["gpt3.5-turbo", "gpt4"]:

        model_name = "gpt-3.5-turbo" if ai_model == "gpt3.5-turbo" else "gpt-4-1106-preview"

        response = openai.chat.completions.create(

            model=model_name,

            messages=[{"role": "user", "content": prompt}],

        ).choices[0].message.content
    elif ai_model in ["gemmini", "gemini"]:
        model = genai.GenerativeModel(GEMINI_MODEL)
        response_model = model.generate_content(prompt)
        response = response_model.text
    elif ai_model == "openrouter":
        if OPENROUTER_CLIENT is None:
            raise ValueError("OPENROUTER_API_KEY is not set.")

        last_error = None
        for model in OPENROUTER_FREE_MODELS:
            try:
                completion = OPENROUTER_CLIENT.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                )
                response = completion.choices[0].message.content
                if response:
                    return response
                raise ValueError("Empty response from model.")
            except Exception as exc:
                last_error = exc
                print(colored(f"[!] OpenRouter model '{model}' failed: {exc}", "yellow"))
                continue

        raise RuntimeError("All OpenRouter models failed.") from last_error

    else:

        raise ValueError("Invalid AI model selected.")

    return response

def generate_script(video_subject: str, paragraph_number: int, ai_model: str, voice: str, customPrompt: str) -> str:

    """
    Generate a script for a video, depending on the subject of the video, the number of paragraphs, and the AI model.



    Args:

        video_subject (str): The subject of the video.

        paragraph_number (int): The number of paragraphs to generate.

        ai_model (str): The AI model to use for generation.



    Returns:

        str: The script for the video.

    """

    # Build prompt
    
    if customPrompt:
        prompt = customPrompt
    else:
        prompt = """

            You are the official script writer for a viral YouTube Shorts channel that delivers soul-touching, poetic expressions of love — the kind that make viewers tear up, tag their person, and save the video forever.

          Generate a perfect 20 to 30-second voiceover script for a romantic poetry Short.

            The script must be raw spoken text ONLY. 
            - paragraphs: (usually 1).
            - Total 50-60 words (perfect for 20 seconds at a soft, emotional pace).
            - Language: (natural, spoken, heartfelt version).

            Signature style (follow 100%):
            - Tone: Deeply romantic, poetic, novel, and soul-stirring. Use beautiful metaphors, gentle rhythm, and original imagery that feels fresh and never cliché. Speak directly to "you" as if whispering to a lover. Make it feel intimate and timeless.
            - Structure that crushes the algorithm:
            • Start with the topic and immediately transform it into something poetic and heart-melting. Turn ordinary words (like "I love you") into something profound and unexpected. 
            - I Repeat, start with the topic and immediately transform it into something poetic and heart-melting. 
            - Never mention the channel, never say "in this Short", never add titles, emojis, or formatting.
            - Make it highly shareable — every script should feel like something people want to send to their partner at 2 a.m.

            Now write the script straight away. Get straight to the point. Only return the raw paragraphs.

            YOU MUST NOT INCLUDE ANY TYPE OF MARKDOWN OR FORMATTING IN THE SCRIPT, NEVER USE A TITLE.
            YOU MUST WRITE THE SCRIPT IN THE LANGUAGE SPECIFIED IN [LANGUAGE].
            ONLY RETURN THE RAW CONTENT OF THE SCRIPT. DO NOT INCLUDE "VOICEOVER", "NARRATOR" OR SIMILAR INDICATORS OF WHAT SHOULD BE SPOKEN AT THE BEGINNING OF EACH PARAGRAPH OR LINE. YOU MUST NOT MENTION THE PROMPT, OR ANYTHING ABOUT THE SCRIPT ITSELF. ALSO, NEVER TALK ABOUT THE AMOUNT OF PARAGRAPHS OR LINES. JUST WRITE THE SCRIPT.

        """

    prompt += f"""
    
    Subject: {video_subject}
    Number of paragraphs: {paragraph_number}
    Language: {voice}

    """

    # Generate script
    response = generate_response(prompt, ai_model)

    print(colored(response, "cyan"))

    # Return the generated script
    if response:
        # Clean the script
        # Remove asterisks, hashes
        response = response.replace("*", "")
        response = response.replace("#", "")

        # Remove markdown syntax
        response = re.sub(r"\[.*\]", "", response)
        response = re.sub(r"\(.*\)", "", response)

        # Split the script into paragraphs
        paragraphs = response.split("\n\n")

        # Select the specified number of paragraphs
        selected_paragraphs = paragraphs[:paragraph_number]

        # Join the selected paragraphs into a single string
        final_script = "\n\n".join(selected_paragraphs)

        # Print to console the number of paragraphs used
        print(colored(f"Number of paragraphs used: {len(selected_paragraphs)}", "green"))

        return final_script
    else:
        print(colored("[-] GPT returned an empty response.", "red"))
        return None


def get_search_terms(video_subject: str, amount: int, script: str, ai_model: str) -> List[str]:
    """
    Generate a JSON-Array of search terms for stock videos,
    depending on the subject of a video.

    Args:
        video_subject (str): The subject of the video.
        amount (int): The amount of search terms to generate.
        script (str): The script of the video.
        ai_model (str): The AI model to use for generation.

    Returns:
        List[str]: The search terms for the video subject.
    """

    # Build prompt
    prompt = f"""
    Generate {amount} search terms for stock videos,
    depending on the subject of a video.
    Subject: {video_subject}

    The search terms are to be returned as
    a JSON-Array of strings.

    Each search term should consist of 1-3 words,
    always add the main subject of the video.
    
    YOU MUST ONLY RETURN THE JSON-ARRAY OF STRINGS.
    YOU MUST NOT RETURN ANYTHING ELSE. 
    YOU MUST NOT RETURN THE SCRIPT.
    
    The search terms must be related to the subject of the video.
    Here is an example of a JSON-Array of strings:
    ["search term 1", "search term 2", "search term 3"]

    For context, here is the full text:
    {script}
    """

    # Generate search terms
    response = generate_response(prompt, ai_model)
    print(response)

    # Parse response into a list of search terms
    search_terms = []
    raw_response = response

    try:
        search_terms = json.loads(response)
        if not isinstance(search_terms, list) or not all(isinstance(term, str) for term in search_terms):
            raise ValueError("Response is not a list of strings.")

    except (json.JSONDecodeError, ValueError):
        print(colored("[*] GPT returned an unformatted response. Attempting to clean...", "yellow"))

        # Try to extract a JSON array block from the original response
        match = re.search(r'\[[\s\S]*\]', raw_response)
        if match:
            try:
                search_terms = json.loads(match.group())
            except json.JSONDecodeError:
                search_terms = []

        # Fallback: extract quoted strings as terms
        if not search_terms:
            extracted_terms = re.findall(r'"([^"]+)"', raw_response)
            if extracted_terms:
                search_terms = extracted_terms
            else:
                print(colored("[-] Could not parse response.", "red"))
                return []


    # Let user know
    print(colored(f"\nGenerated {len(search_terms)} search terms: {', '.join(search_terms)}", "cyan"))

    # Return search terms
    return search_terms


def generate_metadata(video_subject: str, script: str, ai_model: str) -> Tuple[str, str, List[str]]:  
    """  
    Generate metadata for a YouTube video, including the title, description, and keywords.  
  
    Args:  
        video_subject (str): The subject of the video.  
        script (str): The script of the video.  
        ai_model (str): The AI model to use for generation.  
  
    Returns:  
        Tuple[str, str, List[str]]: The title, description, and keywords for the video.  
    """  
  
    # Build prompt for title  
    title_prompt = f"""  
    Generate a catchy and SEO-friendly title for a YouTube shorts video about {video_subject}.  
    """  
  
    # Generate title  
    title = generate_response(title_prompt, ai_model).strip()  
    
    # Build prompt for description  
    description_prompt = f"""  
    Write a brief and engaging description for a YouTube shorts video about {video_subject}.  
    The video is based on the following script:  
    {script}  
    """  
  
    # Generate description  
    description = generate_response(description_prompt, ai_model).strip()  
  
    # Generate keywords  
    keywords = get_search_terms(video_subject, 6, script, ai_model)  

    return title, description, keywords  

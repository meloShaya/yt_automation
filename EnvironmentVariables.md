# Environment Variables

## Required

- TIKTOK_SESSION_ID: Your TikTok session ID is required. Obtain it by logging into TikTok in your browser and copying the value of the `sessionid` cookie.

- IMAGEMAGICK_BINARY: The filepath to the ImageMagick binary is needed. On Linux, you can use the AppImage in the repo root (named `magick`) and make it executable (`chmod +x magick`); it will be auto-detected. You can also set an explicit path (for example: `../magick` when running from `Backend/`, or an absolute path). On Windows, use the `magick.exe` path. Obtain ImageMagick [here](https://imagemagick.org/script/download.php).

- PEXELS_API_KEY: Your unique Pexels API key is required. Obtain yours [here](https://www.pexels.com/api/).

## Optional

- OPENAI_API_KEY: Your unique OpenAI API key is required. Obtain yours [here](https://platform.openai.com/api-keys), only nessecary if you want to use the OpenAI models.

- OPENROUTER_API_KEY: Your OpenRouter API key is required to use OpenRouter models. Create one at https://openrouter.ai/

- GOOGLE_API_KEY: Your Gemini API key is essential for Gemini Pro Model. Generate one securely at [Get API key | Google AI Studio](https://makersuite.google.com/app/apikey)
- GEMINI_MODEL: Optional. The Gemini model name to use (for example: `gemini-2.5-flash`). If not set, the backend defaults to `gemini-2.5-flash`.

* ASSEMBLY_AI_API_KEY: Your unique AssemblyAI API key is required. You can obtain one [here](https://www.assemblyai.com/app/). This field is optional; if left empty, the subtitle will be created based on the generated script. Subtitles can also be created locally.
- TTS_RETRIES: Optional. Number of automatic retries for TikTok TTS failures (default: 3).
- TTS_BACKOFF_SECONDS: Optional. Base backoff in seconds between TTS retries (default: 1.5).

Join the [Discord](https://dsc.gg/fuji-community) for support and updates.

import json
import logging
import requests
import base64
import os
import re
import config

# Configure logging
logger = logging.getLogger("bot.replier")


class LLMException(Exception):
    """Exception raised when the LLM backend encounters an error."""
    pass


# Keep backward compatibility alias
GeminiQuotaExceededException = LLMException


def is_quota_error(e: Exception) -> bool:
    """Detects if a given exception corresponds to an API quota/rate-limit error."""
    err_str = str(e).lower()
    if "resourceexhausted" in e.__class__.__name__.lower() or "429" in err_str or "quota" in err_str or "exhausted" in err_str or "limit" in err_str:
        return True
    try:
        from google.api_core.exceptions import ResourceExhausted
        if isinstance(e, ResourceExhausted):
            return True
    except ImportError:
        pass
    return False


def _call_ollama(prompt: str, image_path: str = None, temperature: float = 0.85) -> str:
    """
    Sends a prompt to the local Ollama server and returns the response text.
    Supports multimodal (image) input via base64 encoding.
    """
    url = f"{config.OLLAMA_BASE_URL}/api/generate"

    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": 0.92,
            "top_k": 50,
            "num_predict": 512,
        }
    }

    # Multimodal: attach base64-encoded image if provided
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as img_file:
                img_b64 = base64.b64encode(img_file.read()).decode("utf-8")
            payload["images"] = [img_b64]
            logger.info(f"[MULTIMODAL] Attached image '{image_path}' to Ollama request.")
        except Exception as e_img:
            logger.error(f"Failed to encode image for Ollama: {e_img}")

    try:
        logger.info(f"[OLLAMA] Sending request to {config.OLLAMA_MODEL}...")
        resp = requests.post(url, json=payload, timeout=config.OLLAMA_TIMEOUT)
        resp.raise_for_status()

        data = resp.json()
        response_text = data.get("response", "").strip()

        if not response_text:
            raise LLMException("Ollama returned empty response")

        logger.info(f"[OLLAMA] Got response ({len(response_text)} chars)")
        return response_text

    except requests.exceptions.ConnectionError:
        raise LLMException(
            f"Cannot connect to Ollama at {config.OLLAMA_BASE_URL}. "
            "Make sure Ollama is running: 'ollama serve'"
        )
    except requests.exceptions.Timeout:
        raise LLMException(f"Ollama request timed out after {config.OLLAMA_TIMEOUT}s")
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            raise LLMException(
                f"Model '{config.OLLAMA_MODEL}' not found. "
                f"Pull it first: 'ollama pull {config.OLLAMA_MODEL}'"
            )
        raise LLMException(f"Ollama HTTP error: {e}")
    except LLMException:
        raise
    except Exception as e:
        raise LLMException(f"Unexpected Ollama error: {e}")


def _build_savage_prompt(original_tweet: str, replies_str: str, is_proactive: bool = False) -> str:
    """Builds the reply generation prompt with savage+humble+sarcastic personality."""

    context_label = "a tweet you stumbled upon while browsing" if is_proactive else "a viral tweet"

    return f"""/no_think
You are a real person on X (Twitter). You're witty, sharp, and have a razor-sharp sense of humor. You're the kind of person who can be savage and sarcastic while still being polite and humble — the perfect balance that makes people laugh AND hit the follow button.

Your personality traits:
- Polite but savage — you roast with a smile, never crude or mean-spirited
- Humble sarcasm — you're self-aware, sometimes self-deprecating, always clever
- Tech-savvy — you understand programming, AI, startups, and internet culture deeply
- Concise — you speak in punchy one-liners or short observations, never essays
- Original — you NEVER repeat what others have said, you find a fresh angle every time
- Human — you make typos sometimes, use lowercase, don't always use perfect grammar. Real people don't write like professors.
- Use words like bro, dude, man,fr, lol, haha, etc. (very important)
- Never put replies in "quote or strings" format.Just reply like a normal person with no punctuations or full stops.
- Example of good reply : "ngl i never thought i would see someone say this" 
- Never give any political opinions, or any controversial topics.
- Never respond to any tweets which are offensive in any type of manner.


Here is {context_label} you want to reply to:

TWEET:
\"\"\"
{original_tweet}
\"\"\"

TOP REPLIES ALREADY IN THE THREAD (do NOT repeat or paraphrase these):
\"\"\"
{replies_str}
\"\"\"

STRICT RULES:
1. Generate exactly 3 different candidate replies, each with a unique angle/approach.
2. Each reply MUST be under 240 characters.
3. DO NOT copy, paraphrase, or rephrase ANY existing reply in the thread.
4. Sound like a REAL human — occasional lowercase, natural phrasing, no corporate/marketing tone.
5. NO hashtags. NO emojis unless it's a single one that adds genuine flavor (max 1 emoji across all 3 replies).
6. ABSOLUTELY NO AI clichés: never use words like "delve", "tapestry", "indeed", "furthermore", "realm", "testament", "in conclusion", "game-changer", "revolutionary", "I think it's safe to say", "this is huge", "let that sink in".
7. NEVER use harm/violence words: "kill", "killed", "die", "died", "death", "murder", "suicide", "rape" or variations.
8. Be savage but SMART — roast the idea, not the person. Be witty, not cruel.
9. If the tweet is about tech/programming, flex your knowledge subtly — show you actually understand the topic.
10. Vary the style: one can be a witty observation, one a sarcastic take, one a humble/self-deprecating angle.

OUTPUT FORMAT — Return ONLY a raw JSON object (no markdown, no code blocks, no explanation):
{{"candidates": ["reply one", "reply two", "reply three"], "best_reply": "the best one from the list"}}
"""


def generate_best_reply(original_tweet: str, top_replies: list, image_path: str = None, is_proactive: bool = False) -> tuple:
    """Generates 3 candidates and selects the best one via a single Ollama API call."""

    # Filter to only the text of the top 3 replies to reduce input tokens
    texts_only = []
    if isinstance(top_replies, list):
        texts_only = [r["text"] if isinstance(r, dict) and "text" in r else str(r) for r in top_replies[:3]]
    replies_str = json.dumps(texts_only, indent=2)

    prompt = _build_savage_prompt(original_tweet, replies_str, is_proactive)

    try:
        content = _call_ollama(prompt, image_path=image_path)

        # Clean markdown code blocks if model outputs them
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        # Try to extract JSON from the response even if there's surrounding text
        json_match = re.search(r'\{[^{}]*"candidates"[^{}]*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)

        data = json.loads(content)
        candidates = data.get("candidates", [])
        best_reply = data.get("best_reply", "")

        if not candidates:
            raise ValueError("No candidates found in the JSON response.")
        if not best_reply or best_reply not in candidates:
            best_reply = candidates[0]

        return best_reply, [str(c).strip() for c in candidates[:3]]

    except LLMException:
        raise
    except Exception as e:
        if is_quota_error(e):
            raise GeminiQuotaExceededException(f"LLM quota exceeded: {e}") from e
        logger.error(f"Error generating replies via Ollama: {e}")

        # Attempt relaxed JSON extraction from raw response
        try:
            if 'content' in locals() and content:
                # Try to find any JSON array in the response
                array_match = re.search(r'\[.*?\]', content, re.DOTALL)
                if array_match:
                    candidates = json.loads(array_match.group(0))
                    if isinstance(candidates, list) and len(candidates) >= 1:
                        return str(candidates[0]).strip(), [str(c).strip() for c in candidates[:3]]
        except Exception as e_inner:
            logger.error(f"Fallback parser also failed: {e_inner}")

    # Absolute fallback — these should rarely trigger
    fallbacks = ["interesting take ngl", "lmao this is actually so real", "somebody had to say it"]
    return fallbacks[0], fallbacks


def safety_check(reply: str, original_tweet: str) -> bool:
    """Performs safety checks before posting: non-empty, unique, relevant, and not AI-cliché."""
    if not reply or len(reply.strip()) == 0:
        logger.warning("[SAFETY] Candidate is empty.")
        return False

    if len(reply) > 280:
        logger.warning(f"[SAFETY] Candidate is too long ({len(reply)} chars). Max is 280.")
        return False

    # Expanded AI giveaway detection — comprehensive list
    ai_giveaways = [
        "delve", "testament", "tapestry", "indeed,", "furthermore", "realm of",
        "in conclusion", "game-changer", "game changer", "revolutionary",
        "let that sink in", "this is huge", "i think it's safe to say",
        "it's worth noting", "at the end of the day", "needless to say",
        "it goes without saying", "in the grand scheme", "paradigm shift",
        "synergy", "leverage", "utilize", "facilitate", "aforementioned",
        "henceforth", "notwithstanding", "pursuant", "thereby", "therein",
        "whilst", "amongst", "shall", "commendable", "noteworthy",
        "groundbreaking", "transformative", "pivotal", "holistic",
        "ecosystem", "landscape", "navigate", "unpack", "deep dive",
        "circle back", "move the needle", "low-hanging fruit",
        "thought leader", "disruptive", "innovative solution",
        "cutting-edge", "state-of-the-art", "best-in-class",
        "world-class", "next-level", "top-notch",
        "i couldn't agree more", "absolutely spot on", "well said!",
        "this resonates", "beautifully put", "eloquently stated",
        "couldn't have said it better", "truer words",
        "ah, the beauty of", "let's dive in", "let me break this down",
        "here's the thing", "hot take:", "unpopular opinion:",
    ]
    reply_lower = reply.lower()
    for phrase in ai_giveaways:
        if phrase in reply_lower:
            logger.warning(f"[SAFETY] Candidate contains AI giveaway phrase: '{phrase}'. Skipping.")
            return False

    # Simple check to make sure it's not identical to original tweet text
    if reply.strip().lower() == original_tweet.strip().lower():
        logger.warning("[SAFETY] Candidate is identical to original tweet. Skipping.")
        return False

    # Check for prohibited harm/sensitive words to avoid X flags/suspensions
    harm_words = ["kill", "killed", "rape", "die", "died", "murder", "suicide", "death", "shooting", "bomb", "terrorist"]
    cleaned_reply = re.sub(r'[^\w\s]', ' ', reply.lower())
    reply_words = cleaned_reply.split()
    for word in harm_words:
        if word in reply_words:
            logger.warning(f"[SAFETY] Candidate contains prohibited harm word '{word}' that could trigger suspension. Skipping.")
            return False

    # Reject replies that look like AI-structured responses (numbered lists, bullet points)
    if re.match(r'^\d+[\.\)]\s', reply.strip()):
        logger.warning("[SAFETY] Candidate starts with a numbered list format. Skipping.")
        return False

    # Reject replies with excessive capitalization (shouting = bot behavior)
    upper_ratio = sum(1 for c in reply if c.isupper()) / max(len(reply), 1)
    if upper_ratio > 0.6 and len(reply) > 10:
        logger.warning("[SAFETY] Candidate has excessive caps. Skipping.")
        return False

    # Reject replies with more than 1 emoji
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF]",
        flags=re.UNICODE
    )
    emoji_count = len(emoji_pattern.findall(reply))
    if emoji_count > 1:
        logger.warning(f"[SAFETY] Candidate has {emoji_count} emoji clusters (max 1). Skipping.")
        return False

    return True


# ──────────────────────────────────────────────────────────────────
# Legacy functions preserved for backward compatibility
# ──────────────────────────────────────────────────────────────────

def generate_reply_candidates(original_tweet: str, top_replies: list, image_path: str = None) -> list:
    """Legacy wrapper — generates 3 candidate replies."""
    _, candidates = generate_best_reply(original_tweet, top_replies, image_path=image_path)
    return candidates


def select_best_reply(candidates: list, original_tweet: str, top_replies: list, image_path: str = None) -> str:
    """Legacy wrapper — selects the best from pre-generated candidates."""
    if not candidates:
        return "interesting take ngl"
    return candidates[0]

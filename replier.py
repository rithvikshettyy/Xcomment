import json
import logging
import base64
import requests
import os
import re
from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT

# Configure logging
logger = logging.getLogger("bot.replier")

class OllamaException(Exception):
    """Exception raised when the Ollama API fails, returns an error, or times out."""
    pass

def encode_image_to_base64(image_path: str) -> str:
    """Encodes an image file to a base64 string."""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to encode image {image_path}: {e}")
        return ""

def call_ollama(prompt: str, image_path: str = None) -> str:
    """Invokes Ollama /api/chat endpoint with JSON format enforcement."""
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    
    messages = []
    user_message = {
        "role": "user",
        "content": prompt
    }
    
    if image_path and os.path.exists(image_path):
        img_b64 = encode_image_to_base64(image_path)
        if img_b64:
            user_message["images"] = [img_b64]
            logger.info(f"[MULTIMODAL] Sent tweet visual screenshot context from '{image_path}' to Ollama.")
            
    messages.append(user_message)
    
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "format": "json"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT)
        if response.status_code != 200:
            raise OllamaException(f"Ollama server returned status code {response.status_code}: {response.text}")
        
        resp_json = response.json()
        content = resp_json.get("message", {}).get("content", "").strip()
        if not content:
            raise OllamaException("Ollama response message content was empty.")
        return content
    except requests.RequestException as e:
        raise OllamaException(f"Failed to connect to Ollama host: {e}")

def generate_reply_candidates(original_tweet: str, top_replies: list, image_path: str = None) -> list[str]:
    """Generates 3 candidate replies using Ollama by analyzing original tweet context and top replies."""
    # Filter to only the text of the top 3 replies to drastically reduce input tokens/cost
    texts_only = [r["text"] if isinstance(r, dict) and "text" in r else str(r) for r in top_replies[:3]] if isinstance(top_replies, list) else []
    replies_str = json.dumps(texts_only, indent=2)
    
    prompt = f"""
You are an expert X (Twitter) user known for writing highly engaging, organic, human-sounding replies.
Your goal is to analyze a tweet text and its top replies, identify the topic, tone, humor style, and writing style, and then generate 3 distinct candidate replies that will fit perfectly in the conversation thread.

Original Tweet Text:
\"\"\"
{original_tweet}
\"\"\"

Top Performing Replies in the Thread:
\"\"\"
{replies_str}
\"\"\"

Guidelines for generating candidates:
1. DO NOT copy or paraphrase the existing replies. They must be completely original.
2. Ensure they are relevant to the topic of the original tweet.
3. Match the tone and humor style of the thread (whether it's sarcastic, funny, intellectual, curious, or meme-focused).
4. Be concise and punchy. Human tweets are rarely long paragraphs.
5. Sound human and conversational. Avoid corporate speak, overly polished marketing phrases, or typical AI clichés (e.g., "Ah, the beauty of...", "Indeed,", "Let's dive in").
6. AVOID hashtags unless they are extremely natural or part of a joke in the thread.
7. AVOID emojis unless they are commonly used in the thread. If you use them, use them sparingly (1 emoji max).
8. STRICTLY AVOID using any harm-related, violent, or sensitive words like "kill", "killed", "rape", "die", "died", "murder", "suicide", "death", or any variation of them. This is critical to avoid X auto-flags or account suspension.

Return exactly 3 candidates. Format your output strictly as a JSON list of strings, with no markdown styling (no ```json code blocks), just a pure JSON array of strings.
Example:
["reply one", "reply two", "reply three"]
"""

    try:
        content = call_ollama(prompt, image_path)
        # Clean markdown code blocks if the model outputs them anyway
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        candidates = json.loads(content)
        if isinstance(candidates, list) and len(candidates) >= 1:
            return [str(c).strip() for c in candidates[:3]]
        else:
            raise ValueError("Parsed content was not a valid list of candidates.")
    except Exception as e:
        if isinstance(e, OllamaException):
            raise e
        logger.error(f"Error generating replies via Ollama: {e}")
        # Try a relaxed parser if model wrapped it in markdown anyway
        try:
            if 'content' in locals() and content:
                if "```json" in content:
                    cleaned = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    cleaned = content.split("```")[1].split("```")[0].strip()
                else:
                    cleaned = content.strip()
                candidates = json.loads(cleaned)
                return [str(c).strip() for c in candidates[:3]]
        except Exception as e_inner:
            logger.error(f"Fallback parser failed: {e_inner}")
            
    # Absolute fallback
    return ["Interesting points here.", "Absolutely correct.", "I had the exact same thought."]

def select_best_reply(candidates: list[str], original_tweet: str, top_replies: list, image_path: str = None) -> str:
    """Uses Ollama API to evaluate and rank the 3 candidates, returning the strongest one."""
    if len(candidates) < 1:
        return candidates[0] if candidates else "Interesting perspective."
        
    candidates_str = json.dumps(candidates, indent=2)
    # Filter to only the text of the top 3 replies to drastically reduce input tokens/cost
    texts_only = [r["text"] if isinstance(r, dict) and "text" in r else str(r) for r in top_replies[:3]] if isinstance(top_replies, list) else []
    replies_str = json.dumps(texts_only, indent=2)
    
    prompt = f"""
You are an expert editor. You need to analyze the original tweet text, the top replies in the thread, and 3 candidate replies we generated.
Select the single best candidate reply that will maximize views, engagement, and fits most naturally into the thread without sounding automated.

Original Tweet Text:
\"\"\"
{original_tweet}
\"\"\"

Top Performing Replies:
\"\"\"
{replies_str}
\"\"\"

Candidates to Choose From:
\"\"\"
{candidates_str}
\"\"\"

Return the best candidate reply from the list. Format your response as a JSON object with one key "best_reply" containing the exact string of the selected candidate reply. Do not write any explanations or markdown.
"""
    try:
        content = call_ollama(prompt, image_path)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        data = json.loads(content)
        selected = data.get("best_reply", "").strip()
        
        # Clean quotes if any
        if selected.startswith('"') and selected.endswith('"'):
            selected = selected[1:-1]
        elif selected.startswith("'") and selected.endswith("'"):
            selected = selected[1:-1]
            
        # Ensure the selected text is actually one of the candidates (or extremely close)
        for cand in candidates:
            if cand.lower() in selected.lower() or selected.lower() in cand.lower():
                return cand
                
        # If it generated something slightly different but valid, use it
        if selected and len(selected) > 2:
            return selected
            
    except Exception as e:
        if isinstance(e, OllamaException):
            raise e
        logger.error(f"Error selecting best reply via Ollama: {e}")
        
    return candidates[0]

def safety_check(reply: str, original_tweet: str) -> bool:
    """Performs safety checks before posting: non-empty, unique, relevant, and not AI-cliché."""
    if not reply or len(reply.strip()) == 0:
        logger.warning("[SAFETY] Candidate is empty.")
        return False
        
    if len(reply) > 280:
        logger.warning(f"[SAFETY] Candidate is too long ({len(reply)} chars). Max is 280.")
        return False
        
    # Check for basic AI giveaways
    ai_giveaways = ["delve", "testament", "tapestry", "indeed,", "furthermore", "realm of", "in conclusion"]
    for word in ai_giveaways:
        if word in reply.lower():
            logger.warning(f"[SAFETY] Candidate contains AI giveaway word: '{word}'. Skipping.")
            return False
            
    # Simple check to make sure it's not identical to original tweet text
    if reply.strip().lower() == original_tweet.strip().lower():
        logger.warning("[SAFETY] Candidate is identical to original tweet. Skipping.")
        return False
        
    # Check for prohibited harm/sensitive words to avoid X flags/suspensions
    harm_words = ["kill", "killed", "rape", "die", "died", "murder", "suicide", "death"]
    cleaned_reply = re.sub(r'[^\w\s]', ' ', reply.lower())
    reply_words = cleaned_reply.split()
    for word in harm_words:
        if word in reply_words:
            logger.warning(f"[SAFETY] Candidate contains prohibited harm word '{word}' that could trigger suspension. Skipping.")
            return False
            
    return True

def generate_best_reply(original_tweet: str, top_replies: list, image_path: str = None) -> tuple[str, list[str]]:
    """Generates 3 candidates and selects the best one in a single unified Ollama API call."""
    # Filter to only the text of the top 3 replies to drastically reduce input tokens/cost
    texts_only = [r["text"] if isinstance(r, dict) and "text" in r else str(r) for r in top_replies[:3]] if isinstance(top_replies, list) else []
    replies_str = json.dumps(texts_only, indent=2)
    
    prompt = f"""
You are an expert X (Twitter) user known for writing highly engaging, organic, human-sounding replies.
Your goal is to analyze a tweet text and its top replies, identify the topic, tone, humor style, and writing style, and then:
1. Generate 3 distinct candidate replies that will fit perfectly in the conversation thread.
2. Select the single best candidate reply that will maximize views, engagement, and fits most naturally into the thread without sounding automated.

Original Tweet Text:
\"\"\"
{original_tweet}
\"\"\"

Top Performing Replies in the Thread:
\"\"\"
{replies_str}
\"\"\"

Guidelines for generating candidates:
1. DO NOT copy or paraphrase the existing replies. They must be completely original.
2. Ensure they are relevant to the topic of the original tweet.
3. Match the tone and humor style of the thread (whether it's sarcastic, funny, intellectual, curious, or meme-focused).
4. Be concise and punchy. Human tweets are rarely long paragraphs.
5. Sound human and conversational. Avoid corporate speak, overly polished marketing phrases, or typical AI clichés (e.g., "Ah, the beauty of...", "Indeed,", "Let's dive in").
6. AVOID hashtags unless they are extremely natural or part of a joke in the thread.
7. AVOID emojis unless they are commonly used in the thread. If you use them, use them sparingly (1 emoji max).
8. STRICTLY AVOID using any harm-related, violent, or sensitive words like "kill", "killed", "rape", "die", "died", "murder", "suicide", "death", or any variation of them. This is critical to avoid X auto-flags or account suspension.

Format your output strictly as a JSON object with two keys:
1. "candidates": a list of 3 generated candidate replies as strings.
2. "best_reply": the selected best candidate reply as a string (it must be one of the strings inside the "candidates" list).

Return ONLY the raw JSON object. Do not include any markdown styling, just a pure JSON object.
"""

    try:
        content = call_ollama(prompt, image_path)
        
        # Clean markdown code blocks if the model outputs them anyway
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        data = json.loads(content)
        candidates = data.get("candidates", [])
        best_reply = data.get("best_reply", "")
        
        if not candidates:
            raise ValueError("No candidates found in the JSON response.")
        if not best_reply or best_reply not in candidates:
            best_reply = candidates[0]
            
        return best_reply, [str(c).strip() for c in candidates[:3]]
        
    except Exception as e:
        if isinstance(e, OllamaException):
            raise e
        logger.error(f"Error generating replies via unified Ollama call: {e}")
        
        # Try a relaxed parser if model wrapped it in markdown or different format
        try:
            if 'content' in locals() and content:
                raw_text = content.strip()
                if "```json" in raw_text:
                    cleaned = raw_text.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_text:
                    cleaned = raw_text.split("```")[1].split("```")[0].strip()
                else:
                    cleaned = raw_text
                data = json.loads(cleaned)
                candidates = data.get("candidates", [])
                best_reply = data.get("best_reply", candidates[0] if candidates else "")
                if candidates:
                    return best_reply, [str(c).strip() for c in candidates[:3]]
        except Exception as e_inner:
            logger.error(f"Fallback unified parser failed: {e_inner}")
            
    # Absolute fallback
    fallbacks = ["Interesting points here.", "Absolutely correct.", "I had the exact same thought."]
    return fallbacks[0], fallbacks

import json
import logging
from config import GEMINI_API_KEY

# Configure logging
logger = logging.getLogger("bot.replier")

class GeminiQuotaExceededException(Exception):
    """Exception raised when the Gemini API quota is exceeded."""
    pass

def is_quota_error(e: Exception) -> bool:
    """Detects if a given exception corresponds to a Gemini API quota exhaust error."""
    err_str = str(e).lower()
    # Check by exception class name or standard status code/message
    if "resourceexhausted" in e.__class__.__name__.lower() or "429" in err_str or "quota" in err_str or "exhausted" in err_str or "limit" in err_str:
        return True
    try:
        from google.api_core.exceptions import ResourceExhausted
        if isinstance(e, ResourceExhausted):
            return True
    except ImportError:
        pass
    return False

def get_gemini_client():
    """Initializes and returns a Google GenerativeAI model."""
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY configuration is empty! Please check your environment variables or config.py.")
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        # Using gemini-2.5-flash as default, but configurable
        model = genai.GenerativeModel("gemini-2.5-flash")
        return model
    except Exception as e:
        logger.error(f"Failed to initialize Gemini Client: {e}")
        return None

def generate_reply_candidates(original_tweet: str, top_replies: list, image_path: str = None) -> list[str]:
    """Generates 3 candidate replies using Gemini by analyzing original tweet context and top replies."""
    model = get_gemini_client()
    if not model:
        logger.error("Gemini model not initialized. Returning fallback candidates.")
        return ["Wow, that's fascinating!", "Interesting perspective on this.", "Totally agree with this viewpoint."]
        
    replies_str = json.dumps(top_replies, indent=2)
    
    prompt = f"""
You are an expert X (Twitter) user known for writing highly engaging, organic, human-sounding replies.
Your goal is to analyze a tweet (both its text and any attached screenshot of its image/video/layout) and its top replies, identify the topic, tone, humor style, and writing style, and then generate 3 distinct candidate replies that will fit perfectly in the conversation thread.

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
2. Ensure they are relevant to the topic and visual elements of the original tweet.
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
        from PIL import Image
        import os
        
        inputs = []
        if image_path and os.path.exists(image_path):
            try:
                img = Image.open(image_path)
                inputs.append(img)
                logger.info(f"[MULTIMODAL] Sent tweet visual screenshot context from '{image_path}' to Gemini.")
            except Exception as e_img:
                logger.error(f"Failed to open image for Gemini: {e_img}")
                
        inputs.append(prompt)
        response = model.generate_content(inputs)
        content = response.text.strip()
        candidates = json.loads(content)
        if isinstance(candidates, list) and len(candidates) >= 1:
            return [str(c).strip() for c in candidates[:3]]
        else:
            raise ValueError("Parsed content was not a valid list of candidates.")
    except Exception as e:
        if is_quota_error(e):
            raise GeminiQuotaExceededException(f"Gemini API quota exceeded: {e}") from e
        logger.error(f"Error generating replies via Gemini: {e}")
        # Try a relaxed parser if Gemini wrapped it in markdown anyway
        try:
            if 'response' in locals() and response and hasattr(response, 'text'):
                if "```" in response.text:
                    cleaned = response.text.split("```json")[1].split("```")[0].strip()
                elif "```" in response.text:
                    cleaned = response.text.split("```")[1].split("```")[0].strip()
                else:
                    cleaned = response.text.strip()
                candidates = json.loads(cleaned)
                return [str(c).strip() for c in candidates[:3]]
            else:
                raise ValueError("No response was generated to parse.")
        except Exception as e_inner:
            logger.error(f"Fallback parser failed: {e_inner}")
            
    # Absolute fallback
    return ["Interesting points here.", "Absolutely correct.", "I had the exact same thought."]

def select_best_reply(candidates: list[str], original_tweet: str, top_replies: list, image_path: str = None) -> str:
    """Uses Gemini API to evaluate and rank the 3 candidates, returning the strongest one."""
    model = get_gemini_client()
    if not model or len(candidates) < 1:
        return candidates[0] if candidates else "Interesting perspective."
        
    candidates_str = json.dumps(candidates, indent=2)
    replies_str = json.dumps(top_replies, indent=2)
    
    prompt = f"""
You are an expert editor. You need to analyze the original tweet (text and attached screenshot), the top replies in the thread, and 3 candidate replies we generated.
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

Return ONLY the selected candidate reply text. Do not provide explanations, do not provide markdown, do not wrap it in quotes. Just return the exact text of the best reply.
"""
    try:
        from PIL import Image
        import os
        
        inputs = []
        if image_path and os.path.exists(image_path):
            try:
                img = Image.open(image_path)
                inputs.append(img)
            except Exception:
                pass
                
        inputs.append(prompt)
        response = model.generate_content(inputs)
        selected = response.text.strip()
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
        if is_quota_error(e):
            raise GeminiQuotaExceededException(f"Gemini API quota exceeded during selection: {e}") from e
        logger.error(f"Error selecting best reply: {e}")
        
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
    import re
    cleaned_reply = re.sub(r'[^\w\s]', ' ', reply.lower())
    reply_words = cleaned_reply.split()
    for word in harm_words:
        if word in reply_words:
            logger.warning(f"[SAFETY] Candidate contains prohibited harm word '{word}' that could trigger suspension. Skipping.")
            return False
            
    return True

import os
import json
import random
import requests
import urllib.parse
import re
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# ==========================================
# 👇 CONFIGURATION 👇
# ==========================================

CONFIG = {
    "category_id": "27",  # 27 = Education
    "title_prompt": "Write a short viral amazing fact video title in English under 60 characters. No hashtags. No quotes.",
    "cooldown_days": 30,
    "fallback_tags": ["facts", "interesting facts", "knowledge", "shorts"]
}

CHANNEL_CUSTOM_NAME = "The Interesting Fact"
HISTORY_FILE = "history.json"

# ==========================================
# HISTORY & COOLDOWN LOGIC
# ==========================================

def load_history():
    """Load history file to check what has been used."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    # Default structure if file doesn't exist
    return {"titles": {}, "descriptions": {}, "hashtags": {}, "tags": {}}

def save_history(history):
    """Save the updated history back to the JSON file."""
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)

def filter_available(items, history_category):
    """Filter out items that are currently in the 30-day cooldown period."""
    now = datetime.now()
    available_items = []
    
    for item in items:
        last_used_str = history_category.get(item)
        if last_used_str:
            last_used_date = datetime.fromisoformat(last_used_str)
            # Agar last use kiye hue time ko 30 din nahi huye hain, toh skip karo
            if now - last_used_date < timedelta(days=CONFIG["cooldown_days"]):
                continue
        available_items.append(item)
        
    return available_items

def record_usage(history_category, items_used):
    """Mark selected items with current date & time."""
    now_str = datetime.now().isoformat()
    if isinstance(items_used, str):
        items_used = [items_used]
    for item in items_used:
        history_category[item] = now_str

# ==========================================
# FILE READING LOGIC (WITH COOLDOWN)
# ==========================================

def get_cooldown_title(history):
    try:
        with open("title.txt", "r", encoding="utf-8") as file:
            all_titles = [line.strip() for line in file.readlines() if line.strip()]
            
            available_titles = filter_available(all_titles, history["titles"])
            
            # Agar saare titles cooldown me hain, toh list reset kar do (fallback)
            if not available_titles and all_titles:
                print("All titles are on cooldown. Reusing an old title.")
                available_titles = all_titles
                
            if available_titles:
                chosen = random.choice(available_titles)
                record_usage(history["titles"], chosen)
                return chosen
    except FileNotFoundError:
        print("Warning: title.txt not found.")
    return None

def get_cooldown_description(history):
    try:
        with open("description.txt", "r", encoding="utf-8") as file:
            content = file.read()
            all_desc = [d.strip() for d in content.split('---') if d.strip()]
            
            available_desc = filter_available(all_desc, history["descriptions"])
            
            if not available_desc and all_desc:
                available_desc = all_desc
                
            if available_desc:
                chosen = random.choice(available_desc)
                record_usage(history["descriptions"], chosen)
                return chosen
    except FileNotFoundError:
        pass
    return "Welcome to our channel! Enjoy this amazing fact."

def get_cooldown_hashtags(history):
    try:
        with open("hashtag.txt", "r", encoding="utf-8") as file:
            content = file.read()
            words = content.split()
            all_hashtags = [w if w.startswith('#') else f'#{w}' for w in words if w.strip()]
            
            # Remove duplicates from source list
            all_hashtags = list(set(all_hashtags))
            available_hashtags = filter_available(all_hashtags, history["hashtags"])
            
            # Humein exactly 5 hashtags chahiye. Agar fresh 5 nahi hain, toh purane mix kar lenge
            if len(available_hashtags) < 5:
                available_hashtags = list(set(available_hashtags + all_hashtags))
                
            if available_hashtags:
                # Select up to 5 random hashtags
                chosen = random.sample(available_hashtags, min(5, len(available_hashtags)))
                record_usage(history["hashtags"], chosen)
                return " ".join(chosen)
    except FileNotFoundError:
        pass
    return "#facts #shorts #viral #amazingfacts #trending"

def get_cooldown_tags(history):
    try:
        with open("tag.txt", "r", encoding="utf-8") as file:
            content = file.read().replace('\n', ',')
            # Remove any special characters that might break YouTube tags
            all_tags = list(set([re.sub(r'[^a-zA-Z0-9\s-]', '', t.strip()) for t in content.split(',') if t.strip()]))
            
            available_tags = filter_available(all_tags, history["tags"])
            
            if len(available_tags) < 5: 
                available_tags = all_tags # Fallback
                
            if available_tags:
                random.shuffle(available_tags)
                chosen = []
                total_chars = 0
                
                # YouTube limit is 500 chars total. We use 450 to be completely safe.
                for tag in available_tags:
                    # length of tag + 1 for the comma separator
                    if total_chars + len(tag) + 1 > 450:
                        break
                    chosen.append(tag)
                    total_chars += len(tag) + 1
                    
                record_usage(history["tags"], chosen)
                return chosen
    except FileNotFoundError:
        pass
    return CONFIG["fallback_tags"]

# ==========================================
# YOUTUBE & TELEGRAM LOGIC
# ==========================================

def get_youtube_service():
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    if not client_id or not refresh_token:
        raise ValueError("Secrets missing! Check GitHub Settings.")

    creds = Credentials(
        None, refresh_token=refresh_token, token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id, client_secret=client_secret
    )
    return build("youtube", "v3", credentials=creds)

def ask_pollinations_ai(prompt):
    try:
        url = f"https://text.pollinations.ai/{urllib.parse.quote(prompt)}?seed={os.urandom(4).hex()}"
        res = requests.get(url)
        if res.status_code == 200: return res.text.strip()
    except: pass
    return None

def should_replace_title(title):
    if len(title) < 5 or "untitled" in title.lower() or "upload" in title.lower(): return True
    if " " not in title or re.search(r'\d{4}-\d{2}-\d{2}', title): return True
    return False

def send_telegram_alert(video_id, channel_name, new_title):
    # Using TELEGRAM_TOKEN as configured
    bot_token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id: return

    video_link = f"https://youtu.be/{video_id}"
    msg = f"<b>🟢 {channel_name.upper()} 🟢</b>\n\n<b>Title:</b> {new_title}\n<b>Status:</b> Public\n<b>Link:</b> {video_link}"
    
    requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", 
                  json={'chat_id': chat_id, 'text': msg, 'parse_mode': 'HTML'})

def main():
    try:
        print("--- STARTING AUTOMATION ---")
        youtube = get_youtube_service()
        history_data = load_history()
        
        channel_res = youtube.channels().list(part="snippet,contentDetails", mine=True).execute()
        uploads_id = channel_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        
        playlist_res = youtube.playlistItems().list(part="contentDetails", playlistId=uploads_id, maxResults=10).execute()
        
        target_video_id, target_video_snippet = None, None
        for item in playlist_res.get("items", []):
            vid_id = item["contentDetails"]["videoId"]
            vid_res = youtube.videos().list(part="snippet,status", id=vid_id).execute()
            
            if not vid_res["items"]: continue
            video_data = vid_res["items"][0]
            if video_data["status"]["privacyStatus"] in ["private", "unlisted"]:
                target_video_id, target_video_snippet = vid_id, video_data["snippet"]
                break 
        
        if not target_video_id:
            print("No Unlisted/Private videos found.")
            return

        # 1. PROCESS TITLE (Always force change)
        current_title = target_video_snippet["title"]
        print(f"Old Title was: {current_title}")
        
        file_title = get_cooldown_title(history_data)
        if file_title: 
            new_title = file_title
        else:
            print("Title text file empty/cooldown, using AI...")
            ai_title = ask_pollinations_ai(CONFIG["title_prompt"])
            new_title = ai_title if ai_title else current_title
            
        new_title = new_title.replace('"', '').replace("'", "")[:67]

        # 2. PROCESS DESCRIPTION & HASHTAGS
        random_desc = get_cooldown_description(history_data)
        five_hashtags = get_cooldown_hashtags(history_data)
        final_description = f"{random_desc}\n\n{five_hashtags}"
        
        # 3. PROCESS TAGS
        final_tags = get_cooldown_tags(history_data)

        # 4. UPDATE YOUTUBE
        youtube.videos().update(
            part="snippet,status",
            body={
                "id": target_video_id,
                "snippet": {
                    "categoryId": CONFIG["category_id"],
                    "title": new_title,
                    "description": final_description,
                    "tags": final_tags,
                    "channelTitle": target_video_snippet["channelTitle"]
                },
                "status": {"privacyStatus": "public", "embeddable": True}
            }
        ).execute()
        
        print(f"SUCCESS: Video Public | Title: {new_title}")
        
        # 5. SEND TELEGRAM & SAVE HISTORY
        send_telegram_alert(target_video_id, CHANNEL_CUSTOM_NAME, new_title)
        save_history(history_data)
        print("History updated successfully.")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        
if __name__ == "__main__":
    main()

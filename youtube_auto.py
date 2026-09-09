import os
import random
import requests
import urllib.parse
import re
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# ==========================================
# 👇 CONFIGURATION FOR FACTS CHANNEL 👇
# ==========================================

CONFIG = {
    # 27 = Education, 22 = People & Blogs
    "category_id": "27",  
    
    # Title AI Prompt (Used only if title is a filename like VID_2024...)
    "title_prompt": "Write a short viral amazing fact video title in English under 60 characters. No hashtags. No quotes. No emoji.",
    
    # SEO Settings
    "seo_hashtags": "#facts #interestingfacts #amazingfacts #knowledge #factsdaily #sciencefacts #worldfacts #didyouknow #factshorts #ytshorts",
    
    # Tags List
    "tags": [
        "facts", "interesting facts", "amazing facts", "knowledge", "facts daily",
        "did you know", "science facts", "world facts", "daily facts", "fact shorts",
        "educational", "learning", "curiosity", "mind blowing facts", "shorts"
    ]
}

CHANNEL_CUSTOM_NAME = "The Interesting Fact"

def get_youtube_service():
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    if not client_id or not refresh_token:
        raise ValueError("Secrets missing! Check GitHub Settings.")

    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret
    )
    return build("youtube", "v3", credentials=creds)

def get_random_description():
    """Reads description.txt and selects one random description block"""
    try:
        with open("description.txt", "r", encoding="utf-8") as file:
            content = file.read()
            # Split using '---' as the separator
            descriptions = [d.strip() for d in content.split('---') if d.strip()]
            if descriptions:
                return random.choice(descriptions)
    except FileNotFoundError:
        print("Warning: description.txt not found. Using default description.")
    
    return "Welcome to our channel! Enjoy this amazing fact."

def ask_pollinations_ai(prompt):
    """Fallback for AI Title generation"""
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://text.pollinations.ai/{encoded_prompt}?seed={os.urandom(4).hex()}"
        response = requests.get(url)
        if response.status_code == 200:
            return response.text.strip()
    except Exception as e:
        print(f"AI Error: {e}")
    return None

def should_replace_title(title):
    if len(title) < 5 or "untitled" in title.lower() or "upload" in title.lower():
        return True
    if " " not in title or re.search(r'\d{4}-\d{2}-\d{2}', title):
        return True
    return False

def send_telegram_alert(video_id, channel_name, new_title):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        return

    video_link = f"https://youtu.be/{video_id}"
    formatted_name = f"<b>🟢 {channel_name.upper()} 🟢</b>"

    message = (
        f"{formatted_name}\n\n"
        f"<b>Title:</b> {new_title}\n"
        f"<b>Status:</b> Uploaded & Public\n"
        f"<b>Link:</b> {video_link}"
    )
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id, 
        'text': message, 
        'parse_mode': 'HTML',
        'disable_web_page_preview': False
    }
    requests.post(url, json=payload)

def main():
    try:
        print(f"--- STARTING AUTOMATION ---")
        youtube = get_youtube_service()
        
        # 1. Connect to Channel & Get Uploads
        channel_response = youtube.channels().list(part="snippet,contentDetails", mine=True).execute()
        uploads_playlist_id = channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        print(f"✅ Connected to Channel")

        # 2. Get Recent Videos
        playlist_response = youtube.playlistItems().list(
            part="contentDetails", playlistId=uploads_playlist_id, maxResults=10
        ).execute()
        
        target_video_id = None
        target_video_snippet = None
        
        # 3. Find Unlisted/Private Video
        for item in playlist_response.get("items", []):
            vid_id = item["contentDetails"]["videoId"]
            vid_response = youtube.videos().list(part="snippet,status", id=vid_id).execute()
            
            if not vid_response["items"]: continue
                
            video_data = vid_response["items"][0]
            privacy = video_data["status"]["privacyStatus"]
            
            if privacy in ["private", "unlisted"]:
                target_video_id = vid_id
                target_video_snippet = video_data["snippet"]
                print(f"Target Found: {vid_id} | Status: {privacy}")
                break 
        
        if not target_video_id:
            print("No Unlisted/Private videos found.")
            return

        vid_id = target_video_id
        snippet = target_video_snippet
        
        # A) TITLE LOGIC
        current_title = snippet["title"]
        new_title = current_title
        
        if should_replace_title(current_title):
            ai_title = ask_pollinations_ai(CONFIG["title_prompt"])
            if ai_title:
                new_title = ai_title.replace('"', '').replace("'", "")
                if len(new_title) > 70: new_title = new_title[:67] + "..."
        
        # B) DESCRIPTION LOGIC (From File)
        print("Selecting random description from file...")
        random_desc = get_random_description()
        final_description = f"{random_desc}\n\n{CONFIG['seo_hashtags']}"
        
        # C) TAGS LOGIC
        final_tags = list(set(CONFIG["tags"]))[:30]

        # UPDATE VIDEO
        update_body = {
            "id": vid_id,
            "snippet": {
                "categoryId": CONFIG["category_id"],
                "title": new_title,
                "description": final_description,
                "tags": final_tags,
                "channelTitle": snippet["channelTitle"]
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
                "embeddable": True,
                "license": "youtube"
            }
        }
        
        youtube.videos().update(part="snippet,status", body=update_body).execute()
        print(f"SUCCESS: Video Public | Title: {new_title}")
        
        send_telegram_alert(vid_id, CHANNEL_CUSTOM_NAME, new_title)

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        
if __name__ == "__main__":
    main()

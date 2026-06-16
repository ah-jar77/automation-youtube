import os
import urllib.parse
import webbrowser
import requests
from dotenv import load_dotenv

# Load env variables
load_dotenv()

CLIENT_ID = os.getenv("SNAP_CLIENT_ID")
CLIENT_SECRET = os.getenv("SNAP_CLIENT_SECRET")

# This must match EXACTLY the Redirect URI registered in your Snapchat Developer App Dashboard
# Defaulting to "https://localhost:8080/callback" as per the guide
REDIRECT_URI = "https://localhost:8080/callback"

def exchange_tokens(code):
    url = "https://accounts.snapchat.com/accounts/oauth2/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI
    }
    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            tokens = response.json()
            access_token = tokens.get("access_token")
            refresh_token = tokens.get("refresh_token")
            print("\n[+] تم الحصول على التوكنات بنجاح!")
            print(f"Access Token: {access_token[:25]}...")
            print(f"Refresh Token: {refresh_token[:25]}...")
            
            update_env_file(access_token, refresh_token)
            
            # Automatically fetch and save the public profile ID
            fetch_and_save_profile_id(access_token)
        else:
            print(f"\n[-] فشل استبدال الكود بالتوكن. الرد من سناب شات: {response.text}")
    except Exception as e:
        print(f"\n[-] حدث خطأ أثناء الاتصال بـ Snapchat: {e}")

def fetch_and_save_profile_id(access_token):
    print("\n[+] جاري جلب حسابات سناب شات العامة المرتبطة...")
    url = "https://businessapi.snapchat.com/v1/me/public_profiles"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(url, headers=headers)
        print(response.status_code)
        print(response.text)
        if response.status_code == 200:
            profiles = response.json().get("public_profiles", [])
            if profiles:
                print("\n[+] تم العثور على الحسابات العامة (Public Profiles):")
                for p in profiles:
                    profile_id = p.get("public_profile", {}).get("id")
                    profile_name = p.get("public_profile", {}).get("profile_name")
                    print(f"   - الاسم: {profile_name} | المعرّف: {profile_id}")
                
                # Automatically save the first profile ID
                first_profile_id = profiles[0].get("public_profile", {}).get("id")
                update_env_profile_id(first_profile_id)
            else:
                print("\n[-] لم يتم العثور على أي حسابات عامة (Public Profiles) مرتبطة بهذا الحساب.")
        else:
            print(f"\n[-] فشل جلب حسابات سناب شات العامة. الرد: {response.text}")
    except Exception as e:
        print(f"\n[-] خطأ أثناء جلب حسابات سناب شات العامة: {e}")

def update_env_file(access_token, refresh_token):
    env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        new_lines = []
        keys_to_update = {
            "SNAP_ACCESS_TOKEN": f'SNAP_ACCESS_TOKEN="{access_token}"\n',
            "SNAP_REFRESH_TOKEN": f'SNAP_REFRESH_TOKEN="{refresh_token}"\n'
        }
        
        for line in lines:
            updated = False
            for key in keys_to_update:
                if line.startswith(f"{key}="):
                    new_lines.append(keys_to_update[key])
                    del keys_to_update[key]
                    updated = True
                    break
            if not updated:
                new_lines.append(line)
        
        for key, val in keys_to_update.items():
            new_lines.append(val)
            
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        print("[+] تم تحديث ملف .env بالتوكنات الجديدة بنجاح! ✅")
    else:
        print("[-] ملف .env غير موجود لحفظ التوكنات.")

def update_env_profile_id(profile_id):
    env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        new_lines = []
        key_to_update = {"SNAP_PROFILE_ID": f'SNAP_PROFILE_ID="{profile_id}"\n'}
        
        for line in lines:
            updated = False
            for key in key_to_update:
                if line.startswith(f"{key}="):
                    new_lines.append(key_to_update[key])
                    del key_to_update[key]
                    updated = True
                    break
            if not updated:
                new_lines.append(line)
        
        for key, val in key_to_update.items():
            new_lines.append(val)
            
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        print(f"[+] تم حفظ SNAP_PROFILE_ID={profile_id} في ملف .env تلقائياً! ✅")
    else:
        print("[-] ملف .env غير موجود لحفظ Profile ID.")

def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("[-] خطأ: الرجاء كتابة SNAP_CLIENT_ID و SNAP_CLIENT_SECRET في ملف .env أولاً.")
        return
        
    # Generate auth URL
    auth_url = (
        "https://accounts.snapchat.com/accounts/oauth2/auth"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        "&response_type=code"
        "&scope=snapchat-marketing-api"
    )
    
    print("\n" + "="*80)
    print("   👻 SNAPCHAT OAUTH LOGIN HELPER (FAIL-PROOF MANUAL METHOD) 👻")
    print("="*80)
    print(f"\n1. سيتم فتح رابط المصادقة التالي في متصفحك الآن:\n\n{auth_url}\n")
    print("2. سجّل دخول في سناب شات واقبل الصلاحيات.")
    print("3. بعد الموافقة، سيتم توجيهك لصفحة localhost (قد تظهر رسالة خطأ بالاتصال، وهذا طبيعي جداً!).")
    print("4. انسخ كود المصادقة من شريط العنوان في المتصفح. الكود هو الجزء الذي بعد code=")
    print("   مثال: إذا كان الرابط في المتصفح هو:")
    print("   https://localhost:8080/callback?code=MySecretCode123")
    print("   فالكود الذي تنسخه هو: MySecretCode123")
    print("\nإذا لم يفتح المتصفح تلقائياً، يمكنك نسخ الرابط أعلاه وفتحه يدوياً.")
    print("="*80)
    
    webbrowser.open(auth_url)
    
    try:
        code = input("\nأدخل الكود (Authorization Code) الذي نسخته هنا ثم اضغط Enter: ").strip()
        if code:
            # If the user pasted the entire redirect URL by mistake, extract the code automatically
            if "?code=" in code:
                try:
                    parsed = urllib.parse.urlparse(code)
                    code = urllib.parse.parse_qs(parsed.query)["code"][0]
                except Exception:
                    pass
            print(f"\n[+] جاري استبدال الكود: {code}...")
            exchange_tokens(code)
        else:
            print("[-] لم يتم إدخال أي كود.")
    except KeyboardInterrupt:
        print("\n[-] تم إلغاء العملية.")

if __name__ == "__main__":
    main()

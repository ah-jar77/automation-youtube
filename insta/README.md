# 🤖 Instagram Reel Bot via Telegram

بوت Telegram ينشر Reels تلقائياً على Instagram مع دعم الجدولة.

---

## 🏗️ المعمارية

```
أنت → ترسل فيديو للبوت
       ↓
   Telegram Bot (Python)
       ↓
   Cloudinary (تخزين مؤقت للفيديو)
       ↓
   Instagram Graph API
       ↓
   ✅ Reel منشور!
```

---

## 📋 المتطلبات

### 1. Telegram Bot Token
- افتح [@BotFather](https://t.me/BotFather)
- أرسل `/newbot` واتبع الخطوات
- احفظ الـ token

### 2. Instagram Graph API
تحتاج:
- حساب Instagram **Business أو Creator**
- صفحة Facebook مربوطة
- تطبيق على [developers.facebook.com](https://developers.facebook.com)

**للحصول على IG_USER_ID و IG_ACCESS_TOKEN:**
1. اذهب لـ [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. اختر تطبيقك
3. أضف الصلاحيات: `instagram_basic`, `instagram_content_publish`
4. احصل على Long-Lived Token (يدوم 60 يوم)
5. لمعرفة IG_USER_ID: `GET /me/accounts` ثم `/PAGE_ID?fields=instagram_business_account`

### 3. Cloudinary (مجاني)
- سجل على [cloudinary.com](https://cloudinary.com)
- من Dashboard احصل على: Cloud Name, API Key, API Secret

---

## 🚀 الرفع على Render

1. ارفع الكود على GitHub
2. اذهب لـ [render.com](https://render.com) → New → Blueprint
3. اربطه بـ repo
4. أضف متغيرات البيئة:

| المتغير | القيمة |
|---------|--------|
| `TELEGRAM_BOT_TOKEN` | token من BotFather |
| `IG_USER_ID` | رقم حساب Instagram |
| `IG_ACCESS_TOKEN` | token من Graph API |
| `CLOUDINARY_CLOUD_NAME` | اسم الـ cloud |
| `CLOUDINARY_API_KEY` | مفتاح Cloudinary |
| `CLOUDINARY_API_SECRET` | سر Cloudinary |
| `INSTAGRAM_CAPTION` | الكابشن الثابت |
| `ALLOWED_USER_IDS` | Telegram IDs مسموح لهم (اختياري) |

---

## 📱 طريقة الاستخدام

```
1. ابعت /start للبوت
2. ابعت أي فيديو MP4
3. اختر "نشر الآن" أو "جدولة لوقت معين"
4. إذا جدولة: اكتب الوقت بصيغة  YYYY-MM-DD HH:MM
5. البوت يرسل إشعار عند النشر
```

**أوامر:**
- `/start` - بداية
- `/jobs` - عرض الجدولات المستقبلية

---

## ⚠️ ملاحظات مهمة

- **حجم الفيديو:** أقصى 1GB (Telegram limit: 2GB, Instagram limit: 1GB)
- **مدة الفيديو:** 3 ثواني إلى 15 دقيقة
- **الصيغة:** MP4 فقط
- **Access Token:** يجب تجديده كل 60 يوم (أو استخدام System User token للـ production)
- **Cloudinary:** تلقائياً يحذف الملفات القديمة في الخطة المجانية

---

## 🔄 تجديد Access Token تلقائياً (اختياري)

أضف هذا في `instagram.py`:

```python
def refresh_token():
    res = requests.get(
        "https://graph.facebook.com/v19.0/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": os.getenv("FB_APP_ID"),
            "client_secret": os.getenv("FB_APP_SECRET"),
            "fb_exchange_token": ACCESS_TOKEN,
        }
    )
    return res.json().get("access_token")
```

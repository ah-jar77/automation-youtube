# Hosting This Bot

This project should not be deployed to Vercel in its current form.

Reason:
- `main.py` runs `app.run_polling()`, which needs an always-on process.
- The bot also downloads video files locally before uploading them.

Use an always-on host instead. The simplest fit for the current code is Railway. Render worker services are also a valid option.

## Railway path

Keep these files in the project root on your machine before deploying:
- `client_secrets.json`
- `youtube_token.pickle`

Set these environment variables in Railway:
- `TELEGRAM_BOT_TOKEN`
- `ALLOWED_USER_ID`
- `YOUTUBE_CLIENT_SECRETS=client_secrets.json`

Deploy from your local machine so the ready token file is included in the image:

```bash
railway login
railway init
railway up
```

Useful follow-up commands:

```bash
railway logs
railway status
```

## Important note

If you deploy from GitHub instead of your local machine, `client_secrets.json` and `youtube_token.pickle` will not be present unless you add them separately.

If you later want a Git-based deploy or Vercel-style secret management, then the auth/token handling should be converted to environment-based secrets. Right now this setup keeps your current auth flow unchanged.

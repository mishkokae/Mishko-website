# Email address maker (Cloudflare Email Routing)

Type a username and get `username@yourdomain`, which forwards to an inbox you already have.

## One-time setup
1. Buy a domain and add it to Cloudflare (free plan is fine).
2. In the Cloudflare dashboard: your domain → **Email** → **Email Routing** → **Enable**.
   Let it add the MX/TXT DNS records it asks for.
3. Create an API token: **My Profile → API Tokens → Create Token → Custom token**, with
   - Zone → Email Routing Rules → Edit
   - Account → Email Routing Addresses → Edit
4. `cp .env.example .env` and fill in the values.

## Use it
```
python3 cf_email.py                         # asks for a username
python3 cf_email.py create alex             # alex@yourdomain -> default inbox
python3 cf_email.py create sam --to sam@example.com
python3 cf_email.py list
python3 cf_email.py delete alex
```

The first time you forward to a new inbox, Cloudflare emails it a verification link that must be clicked.

## Limits
- These addresses **receive** mail only (forwarded to a real inbox). You can't log in to them or send from them.
- Each address needs an existing inbox to forward to.

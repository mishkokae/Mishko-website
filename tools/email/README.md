# Email address maker (Cloudflare Email Routing)

Type a username and get `username@yourdomain`, which forwards to an inbox you already have. Works with several domains.

## One-time setup
1. Add each domain to Cloudflare (free plan is fine) and point the domain's nameservers to Cloudflare.
2. For **each** domain in the Cloudflare dashboard: **Email** → **Email Routing** → **Enable**.
   Let it add the MX/TXT DNS records it asks for.
3. Create one API token: **My Profile → API Tokens → Create Token → Custom token**, with
   - Zone → Zone → Read
   - Zone → Email Routing Rules → Edit
   - Account → Email Routing Addresses → Edit

   Under *Zone Resources* choose "All zones" (or include all your domains).
4. `cp .env.example .env` and fill in the token, your domains and your default inbox.
   Zone and account IDs are looked up automatically.

## Use it
```
python3 cf_email.py                          # asks for username, then which domain
python3 cf_email.py create alex              # alex@<first domain> -> default inbox
python3 cf_email.py create alex@second.com   # choose the domain by typing it
python3 cf_email.py create sam -d third.com --to sam@example.com
python3 cf_email.py list                     # every domain
python3 cf_email.py delete alex@second.com
```

The first time you forward to a new inbox, Cloudflare emails it a verification link that must be clicked.

## Limits
- These addresses **receive** mail only (forwarded to a real inbox). You can't log in to them or send from them.
- Each address needs an existing inbox to forward to.

#!/usr/bin/env python3
"""
Create email addresses on your own domain with Cloudflare Email Routing.

Type a username -> it creates  username@yourdomain  and forwards its mail
to an inbox you already have. No extra installs needed (standard library only).

Usage:
  python3 cf_email.py                      # asks you for a username
  python3 cf_email.py create alex          # alex@yourdomain -> default inbox
  python3 cf_email.py create alex --to friend@example.com
  python3 cf_email.py list
  python3 cf_email.py delete alex

Settings are read from a .env file next to this script (see .env.example).
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"
HERE = os.path.dirname(os.path.abspath(__file__))
USERNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------- settings ----------

def load_env():
    path = os.path.join(HERE, ".env")
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def setting(name, required=True):
    val = os.environ.get(name, "").strip()
    if required and not val:
        sys.exit(f"Missing setting {name}. Add it to {os.path.join(HERE, '.env')} (see .env.example).")
    return val


# ---------- Cloudflare API ----------

def cf(method, path, body=None):
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": "Bearer " + setting("CF_API_TOKEN"),
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            data = json.load(e)
        except Exception:
            sys.exit(f"Cloudflare error {e.code}: {e.reason}")
    if not data.get("success"):
        msgs = "; ".join(err.get("message", str(err)) for err in data.get("errors", [])) or "unknown error"
        sys.exit(f"Cloudflare said: {msgs}")
    return data


def cf_list(path):
    items, page = [], 1
    while True:
        sep = "&" if "?" in path else "?"
        data = cf("GET", f"{path}{sep}page={page}&per_page=50")
        items += data.get("result") or []
        info = data.get("result_info") or {}
        if page >= info.get("total_pages", 1):
            return items
        page += 1


def zone():
    return setting("CF_ZONE_ID")


def account():
    return setting("CF_ACCOUNT_ID")


def domain():
    return setting("CF_DOMAIN").lower().lstrip("@")


def rule_address(rule):
    for m in rule.get("matchers", []):
        if m.get("type") == "literal" and m.get("field") == "to":
            return m.get("value", "").lower()
    return None


def find_rule(address):
    for r in cf_list(f"/zones/{zone()}/email/routing/rules"):
        if rule_address(r) == address:
            return r
    return None


def ensure_destination(email):
    """Destination inboxes must be verified once. Returns True if already verified."""
    for d in cf_list(f"/accounts/{account()}/email/routing/addresses"):
        if d.get("email", "").lower() == email.lower():
            return bool(d.get("verified"))
    cf("POST", f"/accounts/{account()}/email/routing/addresses", {"email": email})
    return False


# ---------- commands ----------

def clean_username(name):
    name = name.strip().lower()
    if "@" in name:
        name = name.split("@", 1)[0]
    if not USERNAME_RE.match(name):
        sys.exit("Usernames can use letters, numbers, dots, dashes and underscores "
                 "(must start and end with a letter or number, max 64 characters).")
    return name


def create(username, to):
    username = clean_username(username)
    to = (to or setting("CF_DEFAULT_DESTINATION")).strip()
    if not EMAIL_RE.match(to):
        sys.exit(f"'{to}' doesn't look like an email address.")
    address = f"{username}@{domain()}"

    if find_rule(address):
        sys.exit(f"{address} already exists.")

    verified = ensure_destination(to)
    cf("POST", f"/zones/{zone()}/email/routing/rules", {
        "name": f"{username} -> {to}",
        "enabled": True,
        "matchers": [{"type": "literal", "field": "to", "value": address}],
        "actions": [{"type": "forward", "value": [to]}],
    })
    print(f"Created {address}  ->  forwards to {to}")
    if not verified:
        print(f"\nOne more step: Cloudflare just sent a verification email to {to}.")
        print("Click the link in it, otherwise mail won't be forwarded there yet.")


def list_addresses():
    rules = cf_list(f"/zones/{zone()}/email/routing/rules")
    rows = []
    for r in rules:
        addr = rule_address(r)
        if not addr:
            continue
        dests = [v for a in r.get("actions", []) if a.get("type") == "forward" for v in a.get("value", [])]
        rows.append((addr, ", ".join(dests) or "(no forward)", "" if r.get("enabled") else "  [disabled]"))
    if not rows:
        print("No addresses yet.")
    for addr, dest, flag in sorted(rows):
        print(f"{addr:40}  ->  {dest}{flag}")


def delete(username):
    address = f"{clean_username(username)}@{domain()}"
    rule = find_rule(address)
    if not rule:
        sys.exit(f"{address} doesn't exist.")
    cf("DELETE", f"/zones/{zone()}/email/routing/rules/{rule['id']}")
    print(f"Deleted {address}")


def main():
    load_env()
    p = argparse.ArgumentParser(description="Create email addresses on your domain via Cloudflare Email Routing.")
    sub = p.add_subparsers(dest="cmd")
    c = sub.add_parser("create", help="create username@yourdomain")
    c.add_argument("username")
    c.add_argument("--to", help="inbox to forward to (default: CF_DEFAULT_DESTINATION)")
    sub.add_parser("list", help="show all addresses")
    d = sub.add_parser("delete", help="remove an address")
    d.add_argument("username")
    args = p.parse_args()

    if args.cmd == "create":
        create(args.username, args.to)
    elif args.cmd == "list":
        list_addresses()
    elif args.cmd == "delete":
        delete(args.username)
    else:
        name = input(f"Username to create (@{domain()}): ")
        to = input(f"Forward to [{setting('CF_DEFAULT_DESTINATION')}]: ").strip()
        create(name, to or None)


if __name__ == "__main__":
    main()

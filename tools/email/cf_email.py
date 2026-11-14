#!/usr/bin/env python3
"""
Create email addresses on your own domains with Cloudflare Email Routing.

Type a username -> it creates  username@yourdomain  and forwards its mail
to an inbox you already have. Works with several domains.
No extra installs needed (standard library only).

Usage:
  python3 cf_email.py                         # asks for username + domain
  python3 cf_email.py create alex             # uses the first domain in CF_DOMAINS
  python3 cf_email.py create alex@second.com  # pick the domain by typing it
  python3 cf_email.py create alex -d second.com --to friend@example.com
  python3 cf_email.py list                    # all domains
  python3 cf_email.py list -d second.com
  python3 cf_email.py delete alex@second.com

Settings are read from a .env file next to this script (see .env.example).
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
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


def setting(name):
    val = os.environ.get(name, "").strip()
    if not val:
        sys.exit(f"Missing setting {name}. Add it to {os.path.join(HERE, '.env')} (see .env.example).")
    return val


def domains():
    ds = [d.strip().lower().lstrip("@") for d in setting("CF_DOMAINS").split(",") if d.strip()]
    if not ds:
        sys.exit("CF_DOMAINS is empty.")
    return ds


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


_zones = {}


def zone_for(domain):
    """Look up a domain's zone ID and account ID (cached)."""
    if domain not in _zones:
        res = cf("GET", "/zones?name=" + urllib.parse.quote(domain)).get("result") or []
        if not res:
            sys.exit(f"Couldn't find {domain} in Cloudflare. Is it added to your account, "
                     "and does the API token include it with Zone -> Zone -> Read?")
        _zones[domain] = (res[0]["id"], res[0]["account"]["id"])
    return _zones[domain]


def rule_address(rule):
    for m in rule.get("matchers", []):
        if m.get("type") == "literal" and m.get("field") == "to":
            return m.get("value", "").lower()
    return None


def rules(domain):
    zone_id, _ = zone_for(domain)
    return cf_list(f"/zones/{zone_id}/email/routing/rules")


def find_rule(domain, address):
    for r in rules(domain):
        if rule_address(r) == address:
            return r
    return None


def ensure_destination(domain, email):
    """Destination inboxes must be verified once per account. Returns True if already verified."""
    _, account_id = zone_for(domain)
    for d in cf_list(f"/accounts/{account_id}/email/routing/addresses"):
        if d.get("email", "").lower() == email.lower():
            return bool(d.get("verified"))
    cf("POST", f"/accounts/{account_id}/email/routing/addresses", {"email": email})
    return False


# ---------- helpers ----------

def pick_domain(given):
    allowed = domains()
    if not given:
        return allowed[0]
    given = given.strip().lower().lstrip("@")
    if given not in allowed:
        sys.exit(f"{given} isn't in CF_DOMAINS ({', '.join(allowed)}).")
    return given


def split_address(text, domain_opt=None):
    """'alex' or 'alex@domain.com' -> (username, domain)."""
    text = text.strip().lower()
    dom = domain_opt
    if "@" in text:
        text, at_dom = text.split("@", 1)
        if domain_opt and domain_opt.strip().lower().lstrip("@") != at_dom:
            sys.exit(f"You typed @{at_dom} but also -d {domain_opt}. Pick one.")
        dom = at_dom
    if not USERNAME_RE.match(text):
        sys.exit("Usernames can use letters, numbers, dots, dashes and underscores "
                 "(must start and end with a letter or number, max 64 characters).")
    return text, pick_domain(dom)


# ---------- commands ----------

def create(name, domain_opt, to):
    username, domain = split_address(name, domain_opt)
    to = (to or setting("CF_DEFAULT_DESTINATION")).strip()
    if not EMAIL_RE.match(to):
        sys.exit(f"'{to}' doesn't look like an email address.")
    address = f"{username}@{domain}"

    if find_rule(domain, address):
        sys.exit(f"{address} already exists.")

    verified = ensure_destination(domain, to)
    zone_id, _ = zone_for(domain)
    cf("POST", f"/zones/{zone_id}/email/routing/rules", {
        "name": f"{username} -> {to}",
        "enabled": True,
        "matchers": [{"type": "literal", "field": "to", "value": address}],
        "actions": [{"type": "forward", "value": [to]}],
    })
    print(f"Created {address}  ->  forwards to {to}")
    if not verified:
        print(f"\nOne more step: Cloudflare just sent a verification email to {to}.")
        print("Click the link in it, otherwise mail won't be forwarded there yet.")


def list_addresses(domain_opt):
    targets = [pick_domain(domain_opt)] if domain_opt else domains()
    for domain in targets:
        print(f"== {domain} ==")
        rows = []
        for r in rules(domain):
            addr = rule_address(r)
            if not addr:
                continue
            dests = [v for a in r.get("actions", []) if a.get("type") == "forward" for v in a.get("value", [])]
            flag = "" if r.get("enabled") else "  [disabled]"
            rows.append(f"  {addr:40}  ->  {', '.join(dests) or '(no forward)'}{flag}")
        print("\n".join(sorted(rows)) if rows else "  (no addresses yet)")


def delete(name, domain_opt):
    username, domain = split_address(name, domain_opt)
    address = f"{username}@{domain}"
    rule = find_rule(domain, address)
    if not rule:
        sys.exit(f"{address} doesn't exist.")
    zone_id, _ = zone_for(domain)
    cf("DELETE", f"/zones/{zone_id}/email/routing/rules/{rule['id']}")
    print(f"Deleted {address}")


def interactive():
    ds = domains()
    name = input("Username to create: ").strip()
    if "@" in name:
        domain = None
    elif len(ds) == 1:
        domain = ds[0]
    else:
        for i, d in enumerate(ds, 1):
            print(f"  {i}) {d}")
        choice = input(f"Which domain? [1-{len(ds)}, default 1]: ").strip() or "1"
        if not choice.isdigit() or not 1 <= int(choice) <= len(ds):
            sys.exit("Please pick one of the numbers shown.")
        domain = ds[int(choice) - 1]
    to = input(f"Forward to [{setting('CF_DEFAULT_DESTINATION')}]: ").strip()
    create(name, domain, to or None)


def main():
    load_env()
    p = argparse.ArgumentParser(description="Create email addresses on your domains via Cloudflare Email Routing.")
    sub = p.add_subparsers(dest="cmd")
    c = sub.add_parser("create", help="create username@domain")
    c.add_argument("username", help="alex  or  alex@yourdomain.com")
    c.add_argument("-d", "--domain", help="which domain (default: first in CF_DOMAINS)")
    c.add_argument("--to", help="inbox to forward to (default: CF_DEFAULT_DESTINATION)")
    l = sub.add_parser("list", help="show addresses")
    l.add_argument("-d", "--domain", help="only this domain")
    d = sub.add_parser("delete", help="remove an address")
    d.add_argument("username", help="alex  or  alex@yourdomain.com")
    d.add_argument("-d", "--domain")
    args = p.parse_args()

    if args.cmd == "create":
        create(args.username, args.domain, args.to)
    elif args.cmd == "list":
        list_addresses(args.domain)
    elif args.cmd == "delete":
        delete(args.username, args.domain)
    else:
        interactive()


if __name__ == "__main__":
    main()

# jpfdevs.pentest — Instagram auto-poster

Publishes branded pentest-sales posts to **@jpfdevs.pentest** on a schedule, alternating
between a **USA (English)** and a **Brasil (Português)** content track. It uses Instagram's
official Content Publishing API, so there's no scraping or password automation that could get the account
flagged.

```
content/posts.yaml ──► render card (1080×1350) ──► host image publicly ──► Instagram API
        ▲                                                                       │
        └────────────── state/posted.json (what went out, when) ◄───────────────┘
```

Runs free on **GitHub Actions**: no server needed.

| Track | Default schedule | Local time |
|---|---|---|
| 🇺🇸 US / EN | Tue & Thu 14:00 UTC | 9 AM New York |
| 🇧🇷 BR / PT | Mon, Wed & Fri 22:00 UTC | 19h Brasília · 18h Campo Grande |

24 posts are included (12 per market, about 6 weeks of content). After that the bot recycles
posts that haven't run in 60+ days, or you can add more to `content/posts.yaml`.

---

## 1 · Instagram account prerequisites

* @jpfdevs.pentest must be a **Professional** account (Business or Creator).
  Instagram app → Settings → Account type and tools → *Switch to professional account*.
* A Facebook Page is **not** required (this uses *Instagram API with Instagram Login*).

## 2 · Create the Meta app and get a token (≈10 min)

1. Go to <https://developers.facebook.com/apps> → **Create app** → use case
   **"Manage messaging & content on Instagram"** → app type *Business*.
2. In the app dashboard open **Instagram → API setup with Instagram login**.
3. Under *Generate access tokens* click **Add account** and log in as `jpfdevs.pentest`.
   Make sure the permissions **instagram_business_basic** and
   **instagram_business_content_publish** are granted.
4. Click **Generate token**. Copy:
   * the **access token** (long-lived, valid 60 days) → `IG_ACCESS_TOKEN`
   * the numeric **Instagram user ID** shown next to the account → `IG_USER_ID`

> The app can stay in **Development mode**. You're only publishing to your own account,
> which has a role on the app, so App Review isn't needed.

## 3 · Put the bot on GitHub

```bash
cd jpfdevs-igbot
git init && git add . && git commit -m "Instagram auto-poster"
gh repo create jpfdevs-igbot --public --source . --push
```

**The repository must be public**, because Instagram downloads each image from its
`raw.githubusercontent.com` URL. Only marketing images and captions are public; the token
lives in encrypted secrets. (Prefer a private repo? See *Alternative image hosting* below.)

Add the secrets (Settings → Secrets and variables → Actions, or via CLI):

```bash
gh secret set IG_ACCESS_TOKEN   # paste token
gh secret set IG_USER_ID        # paste numeric id
gh secret set GH_PAT            # fine-grained PAT: this repo only, "Secrets: read & write"
```

`GH_PAT` lets the weekly *Refresh Instagram token* workflow renew the 60-day token
automatically, so the bot never goes silent.

## 4 · Test, then go live

1. **Actions → Instagram auto-post → Run workflow** with `dry_run = true`. This renders the card
   and prints the caption without publishing.
2. Run it again with `dry_run = false` and market `br` (or `us`). The post goes live and its
   permalink is recorded in `state/posted.json`.
3. Done. The schedule takes over from here.

Local check (optional):

```bash
pip install -r requirements.txt
export IG_ACCESS_TOKEN=... IG_USER_ID=...
python -m bot check              # account, quota, next post per market
python -m bot preview            # render every card + caption into ./preview/
python -m bot next --market us
```

---

## Before going live, edit these

* `config.yaml → contact.email`: currently a placeholder.
* `config.yaml → markets.*.cta`: the call-to-action appended to every caption.
* Your **link in bio** should point to a booking page (Calendly, cal.com) or WhatsApp
  link, since every CTA says "link in bio".
* Read every caption in `./preview/*.txt` and make sure each claim matches what you actually
  deliver (e.g. "free retest included", "fixed price").

## Adding content

Append to `content/posts.yaml`:

```yaml
- id: br-013-phishing          # unique, never reuse
  market: br                   # us | br
  style: statement             # statement | list | stat
  command: "gophish --campaign q4"
  headline: "Seu time clicaria?"
  sub: "Simulação de phishing com relatório por área"
  bullets: []                  # up to 4 for style: list
  caption: |
    Texto da legenda...

    {cta}
  hashtags: "#phishing #pentest #segurancadainformacao"
  alt: "Descrição da imagem para acessibilidade"
```

Run `python -m bot preview --id br-013-phishing` to see the card. Posts are published in file
order per market, so reorder to change the queue. To force a specific post now, use
*Run workflow* with `post_id`.

## Changing the schedule

Edit the two `cron:` lines in `.github/workflows/post.yml` (UTC). If you change the US
line, change the matching string in the *Decide market* step too. GitHub may start scheduled
runs a few minutes late, which is normal.

## Alternative image hosting (private repo)

Serve the `published/` folder from any public URL (S3/R2 bucket, your website, etc.) and set
`IMAGE_HOSTING=base_url` and `IMAGE_BASE_URL=https://your-host/path` in the workflow env.
You'll need to add an upload step for your host before `python -m bot post`.

## Limits & troubleshooting

* Instagram allows 50–100 API posts per account per 24 h, far above this schedule.
* Captions: max 2,200 chars and 30 hashtags (the bot checks both).
* `Image is not publicly reachable`: the repo is private, or GitHub's CDN is slow. Re-run.
* `OAuthException code 190`: token expired. Generate a new one (step 2) and update the secret.
* `(#10) Application does not have permission`: content_publish permission wasn't granted
  when generating the token. Regenerate and tick it.

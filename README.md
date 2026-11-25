# LM Studio family proxy

Gives family devices safe, logged access to the model running in LM Studio
("Bionic") on this Mac. The proxy, logging and review run here in Docker Compose;
the chat UI (Open WebUI with voice) runs on a separate Docker host and is reached
over Tailscale (see [Chat UI](#chat-ui)). Nothing is installed on this Mac itself.

```
Phones / laptops ──Tailscale──▶ Open WebUI + Kokoro (Docker host, "DMZ")
                                       │ HTTPS :8443 (only this one LAN hop is allowed)
Coding tools / SDKs ───────────────────┤
   (HTTPS :8443, Caddy local CA)       ▼
                              Caddy ──/v1/*──▶ LiteLLM :4000 ──▶ LM Studio (host 127.0.0.1:1234)
                                                  │ per-user API keys, model allow-list,
                                                  │ rate limits, full prompt/response logs
                                                  ▼
                                              Postgres (30-day retention)
```

Only Caddy is published on the network (`<LAN_IP>:8443`), and it serves `/v1/*`
only (anything else is a 404). LiteLLM's admin UI is bound to `127.0.0.1:4000`
(this Mac only). Postgres has no published port.

## Chat UI

Open WebUI (with Whisper speech-to-text and Kokoro text-to-speech) runs on the
Docker host described in <https://github.com/Spoonman1091/media-center-docker>
(`stacks/open-webui`), not on this Mac. It reaches this proxy at
`https://<LAN_IP>:8443/v1` with its own LiteLLM key (alias `openwebui-dmz`,
one model, rate limited), and the host's firewall lets that stack reach nothing
else on the LAN. Family devices open it through Tailscale Serve.

The `openwebui` and `kokoro` services remain in `compose.yml` under the
`local-ui` profile as a rollback: `docker compose --profile local-ui up -d`,
and restore the catch-all `reverse_proxy openwebui:8080` route in the
`Caddyfile`. They are not started by default. Their data volume
(`lmstudio-proxy_openwebui_data`) is the pre-migration backup.

## Files

| File | Purpose |
|------|---------|
| `compose.yml` | The stack (caddy, litellm, postgres, reviewer); kokoro/openwebui under the `local-ui` rollback profile |
| `Caddyfile` | TLS (`tls internal`) and routing: `/v1/*` → LiteLLM, rest → 404 |
| `litellm_config.yaml` | Model list, prompt logging, 30-day log retention |
| `reviewer/` | Prompt-review service: source, tests, Dockerfile (see "Prompt review") |
| `.env` | Secrets, LAN IP and SMTP settings (mode 600, git-ignored). Never share or commit |
| `caddy-root.crt` | Caddy's root CA, for installing on client devices (git-ignored) |

Kid API keys are kept outside this folder: `~/lmstudio-proxy-keys/kid-keys.txt`.

## Day to day

Run these from this folder.

```sh
docker compose ps                  # status
docker compose up -d               # start / apply compose.yml changes
docker compose restart litellm     # required after editing litellm_config.yaml
docker compose logs -f litellm     # follow logs (also: caddy, reviewer)
docker compose down                # stop (data volumes are kept)
```

Docker Desktop must be running. Enable "Start Docker Desktop when you sign in"
for an always-on setup. Containers use `restart: unless-stopped`.

## Endpoints

- Chat UI: `https://<LAN_IP>:8443`
- API (coding tools): base URL `https://<LAN_IP>:8443/v1` plus a LiteLLM key
- LiteLLM admin and prompt logs: `http://localhost:4000/ui` (user `admin`,
  password = `LITELLM_MASTER_KEY` in `.env`)

The Mac's IP is a DHCP reservation. If it changes, update `LAN_IP` in `.env`
and re-issue the certificate (`docker compose up -d`, then re-export the CA if
needed).

## Clients: trust the certificate

Caddy's local CA must be trusted on every device, or browsers warn and the
microphone is blocked (browsers require HTTPS for mic access).

- **macOS:** Keychain Access → login keychain → Certificates → import
  `caddy-root.crt` → double-click → expand Trust → "Always Trust". Or:
  `security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db caddy-root.crt`
  Restart the browser afterwards. (Firefox has its own store.)
- **Android:** Settings → Security → Install a certificate → CA certificate.

Re-export the CA if ever needed:
`docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt`

## Users and keys

**Open WebUI accounts** (on the Docker host's instance). Signup is disabled.
Admin Panel → Users → Add User; give kids the role *User*, not Admin.

**LiteLLM keys** (API access, prompt logging). Create one per person:

```sh
set -a; . ./.env; set +a
curl -s -X POST http://127.0.0.1:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H 'Content-Type: application/json' \
  -d '{"key_alias":"NAME","user_id":"NAME","models":["qwen3.6-35b-a3b"],"rpm_limit":30,"max_parallel_requests":2}'
```

Revoke a key from the LiteLLM admin UI (Virtual Keys) or `POST /key/delete`.
Prompts and responses are logged per key; review them in the admin UI. The
prompt text is stored in the log row's `proxy_server_request.messages`.

## Models

Only `qwen3.6-35b-a3b` is exposed (it is faster than `qwen3.8-27b` here).
Access is enforced by the model list on each LiteLLM key, and Open WebUI has
`BYPASS_MODEL_ACCESS_CONTROL=True` so every user sees whatever LiteLLM allows.

**Memory:** LM Studio rejects requests ("prefill memory guard") when two large
models are loaded. Keep `qwen3.8-27b` unloaded (`lms unload qwen/qwen3.8-27b`).
Any request for a model that is not exposed to the key is blocked with 403.

**Thinking:** this is a reasoning model and can spend hundreds of tokens
thinking before answering. Per-request switches do not work through LM
Studio's API (`enable_thinking`, `chat_template_kwargs`, `reasoning_effort`,
`/no_think` and system-prompt instructions were all tested with no reliable
effect). The supported control is LM Studio's per-model **Enable Thinking**
setting in its UI (model settings for Qwen3.6-35B-A3B); reload the model after
changing it. Turning it off makes replies faster but may reduce quality on
hard coding or maths questions.

## Voice

Both run on the Docker host with Open WebUI, not on this Mac.

- **Speech to text:** Open WebUI's built-in Whisper (`base`), runs locally in
  the Open WebUI container. The model downloads on first use.
- **Text to speech:** the `kokoro` container, OpenAI-compatible at
  `http://kokoro:8880/v1`, default voice `bf_emma` (British, female). Other
  British voices: `bf_isabella`, `bf_alice`, `bf_lily`; male `bm_george`,
  `bm_lewis`, `bm_daniel`, `bm_fable`.
- Users' own Open WebUI audio settings must use the **server default** engine.
  The "browser Kokoro" engine runs a model in the browser, downloads for a long
  time, and stays silent with server voice names.

## Prompt review and email alerts

The `reviewer` container (code in `reviewer/`) watches what the children type
and emails a parent when something looks risky.

- Every 5 minutes it reads new rows from LiteLLM's Postgres log through a
  **read-only** database role (`reviewer`; it cannot modify logs or read API
  keys).
- It reviews only what a child actually typed. Open WebUI's background jobs
  (titles, tags, follow-up suggestions) and repeated prompts are skipped.
- Each prompt is classified by the local model (`REVIEWER_MODEL`, called directly
  on LM Studio so its own calls are not logged as a child's). Categories:
  self_harm, sexual_content, violence_weapons, drugs_alcohol,
  bullying_harassment, personal_info, stranger_contact, dangerous_activities,
  bypass_safeguards, hate_extremism, other. Severity 1 = mild, 2 = concerning,
  3 = urgent.
- **Immediate email** at severity >= `ALERT_MIN_SEVERITY` (default 2; subject
  says URGENT at 3). **Daily digest** at `DIGEST_HOUR` (default 20:00, local
  time) with per-child counts and every flagged item, including mild ones.
- Alert only: nothing is blocked.
- Each alert names the child (Open WebUI user name, or the API key alias such as
  `kid1`). LiteLLM's `user_header_name` setting also records the Open WebUI user
  as the log row's end user, so logs can be filtered per child in its UI.
- Review state lives in the `reviewer_data` volume (`state.db`), retained 30
  days. Alert text is sent to the address in `ALERT_TO`, so choose a mailbox you
  trust.

**Turning on email.** Until `SMTP_HOST`, `ALERT_FROM` and `ALERT_TO` are all set
in `.env`, the reviewer runs in dry-run mode and writes alerts to
`/data/alerts.log` inside the container instead of sending them. After editing
`.env`:

```sh
docker compose up -d reviewer                      # recreate with new settings
docker compose exec reviewer python -m watch.selftest   # sends a harmless test email
```

Use the SMTP service of a mailbox you control (an app password, port 587
`starttls` or 465 `ssl`). The SMTP password sits in `.env` and in the
container's environment.

Useful commands:

```sh
docker compose logs -f reviewer                    # one "Cycle:" line per pass
docker compose exec reviewer cat /data/alerts.log  # dry-run alerts
```

Limits: the classifier makes mistakes in both directions, covers only traffic
through this proxy, and its reply can be slow when the 35B model is busy
(a pass is a few seconds per new prompt). Tests: `cd reviewer && python -m pytest`
(or run them in a `python:3.12-slim` container).

## Gotchas learned

- **Open WebUI saves settings in its database after first launch.** Environment
  variables (e.g. `DEFAULT_MODELS`, audio engine) only apply the first time.
  Change them in the UI, or edit the `config` table in `webui.db`.
- **Editing the database:** stop Open WebUI first, copy `webui.db`,
  `webui.db-wal` and `webui.db-shm` somewhere, make the change, then start it
  again. The live data is `/opt/docker/open-webui/data` on the Docker host.
- **Per-user audio settings** live in `user.settings` (`ui.audio.tts`) and
  override the server config.
- LiteLLM only reads `litellm_config.yaml` at startup; restart it after edits.
- The logged client IP is Caddy's container address; attribute by key/user.

## Security notes

- Keep `.env`, the kid key file and the Postgres volume private. They hold the
  master key and the kids' prompts.
- Do not enable Open WebUI's "realtime" audio settings; they point at OpenAI's
  API and would send audio outside the network.
- Logs are retained 30 days (`maximum_spend_logs_retention_period`).
- Keep the logs and `reviewer_data` volume out of cloud or managed backups: they
  contain the children's prompts.

## Backup and restore

Named volumes: `lmstudio-proxy_pg_data` (LiteLLM logs/keys),
`lmstudio-proxy_openwebui_data` (accounts, chats), `lmstudio-proxy_caddy_data`
(the CA; losing it means re-trusting a new certificate on every device).
Back up Postgres with:
`docker compose exec postgres pg_dump -U litellm litellm > litellm-backup.sql`

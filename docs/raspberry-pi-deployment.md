# Deploying to a Raspberry Pi

How to run the published Docker image on a Raspberry Pi in
`/home/pi4/Workspace/expenses-to-spreadsheet`. The image contains **no** secrets: they
live in files next to the Compose file on the Pi and are mounted when the container
starts.

Two files in [`deploy/`](../deploy/) do the work:

- [`copy-to-pi.sh`](../deploy/copy-to-pi.sh) — run on your computer; copies the
  secrets, config, state and Compose file to the Pi.
- [`docker-compose.yml`](../deploy/docker-compose.yml) — run on the Pi; starts the
  container (auto-restart, log rotation).

## Prerequisites

- **64-bit** Raspberry Pi OS: `uname -m` must print `aarch64`. The published image is
  `linux/amd64` + `linux/arm64` only.
- The Pi user is **`pi4` with uid 1000** (`id -u` prints `1000`; the first user Raspberry
  Pi OS creates). The container runs as uid 1000 and must be able to read the copied
  secrets; the script stops if the uid differs.
- Docker on the Pi:

  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker pi4   # then log out and back in
  ```

- `rsync` on both machines (`sudo apt install rsync` if missing), and SSH access from
  your computer to the Pi. An SSH key saves typing the password.

## 1. Stop the app everywhere else

Only **one** instance may run at a time. Two instances would both poll the bank and
write duplicate rows, and Telegram allows only one poller per bot token (the second
fails with a `Conflict` error). Stop any `uv run expenses-serve` or local container
first; the script refuses to run while one is up on your computer.

## 2. Copy the files

From the project folder on your computer:

```bash
deploy/copy-to-pi.sh
```

By default it connects as `pi4@192.168.0.125` with the key `~/.ssh/id_pi4access`
(`IdentitiesOnly=yes`), i.e. the same as
`ssh -i ~/.ssh/id_pi4access -o IdentitiesOnly=yes pi4@192.168.0.125`. If the Pi's
address or key changes: `deploy/copy-to-pi.sh -i <key> pi4@<new-address>` (or set
`PI_HOST` / `PI_SSH_KEY`).

It copies, into `/home/pi4/Workspace/expenses-to-spreadsheet`:

| File | What it is | Secret? |
|------|------------|---------|
| `.env` | All configuration, including the Telegram bot token | **Yes** |
| `secrets/*.pem` | Enable Banking private key | **Yes** |
| `secrets/*.json` | Google service-account key | **Yes** |
| `docker-compose.yml` | From `deploy/` | No |
| `state/processed_transactions.log` | Ids of transactions already handled | No, but required |

Secrets and `.env` land with `600` permissions (owner-only).

**The state file is copied only if the Pi doesn't have one yet.** Once the app runs on
the Pi, the Pi's copy is the newer one; replacing it with your computer's older copy
would reprocess transactions and write duplicate rows. So re-running the script later
(e.g. after changing `.env`) is safe. Pass `--overwrite-state` only if you really want
to replace the Pi's history.

Without any state file, the Pi reprocesses the whole lookback window
(`EXPENSES_POLL_LOOKBACK_DAYS`) once, so do the first copy *after* step 1.

Keep the key paths in `.env` relative (`./secrets/...`): inside the container the app
runs from `/app`, where `secrets/` is mounted. Don't quote values in `.env`; Docker
passes quotes through literally.

## 3. Start

On the Pi:

```bash
cd /home/pi4/Workspace/expenses-to-spreadsheet
docker compose pull
docker compose up -d
```

The container restarts by itself after a reboot or crash. Check it's working:

```bash
docker compose ps           # STATUS shows "(healthy)" after ~15 s
docker compose logs -f      # look for "cache refreshed" and the first poll
```

## Updating to a new version

After a new image is pushed to Docker Hub, on the Pi:

```bash
cd /home/pi4/Workspace/expenses-to-spreadsheet
docker compose pull
docker compose up -d
```

## Changing the configuration

Edit `.env` (on your computer, then re-run `deploy/copy-to-pi.sh`, or directly on the
Pi), then recreate the container so it reads the new values:

```bash
docker compose up -d --force-recreate
```

## Renewing the bank consent (~every 90 days)

When the bot reports that bank access expired, run the consent flow on the Pi with the
same config and secrets as the app:

```bash
cd /home/pi4/Workspace/expenses-to-spreadsheet
docker compose run --rm expenses expenses-consent banks --country IT
docker compose run --rm expenses expenses-consent authorize --aspsp "<exact Revolut name>" --country IT
```

Use the bank name exactly as the first command lists it. If `authorize` prints a
different `EXPENSES_EB_ACCOUNT_UID`, update it in `.env` and recreate the container (see
above). See [enable-banking-setup.md](enable-banking-setup.md) for details on the
consent flow.

# Setup Checklist

Use this file as the single checklist for setting up the project. Complete the boxes in order.

## A. Create the ChatGPT Project

- [ ] In ChatGPT, create a new Project named **Event-Market Quant Bot**.
- [ ] Open the Project settings/instructions area.
- [ ] Copy the contents of `CHATGPT_PROJECT_INSTRUCTIONS.md` into the Project instructions.
- [ ] Upload these four files first:
  - [ ] `docs/PROJECT_CHARTER.md`
  - [ ] `docs/PROJECT_STATE.md`
  - [ ] `docs/AI_HANDOFF.md`
  - [ ] `docs/DECISIONS.md`
- [ ] Move this conversation into the Project if the interface offers that option.
- [ ] Create a new Project chat named **00 — Setup and Repository**.

Do not upload `.env`, private keys, raw credentials, or account screenshots containing sensitive information.

## B. Install the local tools

- [ ] Install Python 3.11 or newer.
- [ ] Install Visual Studio Code.
- [ ] Install GitHub Desktop.
- [ ] Create or sign in to a GitHub account.
- [ ] In VS Code, install the official Python extension.

Verify Python in PowerShell:

```powershell
python --version
```

If `python` is not recognized, try:

```powershell
py --version
```

## C. Put the project in a permanent local folder

- [ ] Extract this project to a stable location, for example:

```text
C:\Users\YOUR_NAME\Documents\GitHub\event-market-quant-bot
```

- [ ] Do not run the project directly from Downloads or from inside the ZIP file.
- [ ] Open VS Code.
- [ ] Choose **File → Open Folder** and select `event-market-quant-bot`.

## D. Create the Python environment

Open **Terminal → New Terminal** in VS Code and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation, use Command Prompt:

```bat
.venv\Scripts\activate.bat
```

Then select the interpreter in VS Code:

```text
Ctrl+Shift+P → Python: Select Interpreter → .venv
```

## E. Verify the code

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected result:

```text
Ran 2 tests
OK
```

Then run:

```powershell
python scan_btc_markets.py
```

This command is read-only and does not access your account.

## F. Create the private GitHub repository with GitHub Desktop

- [ ] Open GitHub Desktop and sign in.
- [ ] Choose **File → Add Local Repository**.
- [ ] Select the local `event-market-quant-bot` folder.
- [ ] If GitHub Desktop says it is not yet a Git repository, choose the option to create one there.
- [ ] Confirm that `.env`, `.venv`, raw data, logs, and key files are not listed as files to commit.
- [ ] Enter the first commit summary:

```text
Initialize read-only event-market bot project
```

- [ ] Click **Commit to main**.
- [ ] Click **Publish repository**.
- [ ] Repository name: `event-market-quant-bot`
- [ ] Description: `Education-first event-market trading research and paper-trading system`
- [ ] Keep **Private repository** selected.
- [ ] Publish.

## G. Verify GitHub safety

On GitHub.com:

- [ ] Confirm the repository shows **Private**.
- [ ] Confirm `.env` is absent.
- [ ] Confirm no `.pem`, `.key`, or credential files exist.
- [ ] Confirm `data/raw/` and `logs/` contain only `.gitkeep`.
- [ ] Open `docs/PROJECT_STATE.md` and verify it is visible.

## H. Create the working routine

At the start of a session:

1. Open `docs/PROJECT_STATE.md`.
2. Open `docs/AI_HANDOFF.md`.
3. Pull the latest changes in GitHub Desktop.
4. Activate `.venv`.
5. State the session goal in the relevant ChatGPT Project chat.

At the end of a session:

1. Update `PROJECT_STATE.md`.
2. Add any accepted choices to `DECISIONS.md`.
3. Add test results to `EXPERIMENT_LOG.md` when applicable.
4. Update `BACKLOG.md`.
5. Refresh `AI_HANDOFF.md`.
6. Commit and push through GitHub Desktop.

## First stopping point

Stop after all of these are true:

- [ ] ChatGPT Project exists.
- [ ] Local folder opens in VS Code.
- [ ] Virtual environment works.
- [ ] Tests pass.
- [ ] Scanner runs.
- [ ] Private GitHub repository is published.
- [ ] No secrets are committed.

Do not create Kalshi API credentials yet. The current phase does not need them.

# Put MemoryBank on GitHub

Create an empty repository on GitHub first.

For sensitive infrastructure like MemoryBank, a **private repository** is recommended.

Then:

```bash
cd memorybank

git init
git add .
git commit -m "Initial MemoryBank v2.0.1"
git branch -M main

git remote add origin git@github.com:YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

Before pushing, verify that `.env` is ignored:

```bash
git status --ignored
```

You should see `.env` under ignored files and it should **not** appear in staged changes.

Optional safety check:

```bash
git grep -nE 'mem_live_|CLOUDFLARE_TUNNEL_TOKEN=ey|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY' || true
```

## Recommended GitHub settings

- repository visibility: Private
- enable Dependabot alerts
- enable secret scanning if available
- enable push protection if available
- protect `main`
- require pull requests if multiple people contribute
- enable Private Vulnerability Reporting

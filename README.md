Host file locally with CORS headers

```bash
uv run python cors_server.py
```

Upgrade timestamp with the following command:

```bash
sed -E -i '' "s/(\"dateLastModified\"[[:space:]]*:[[:space:]]*)[0-9]+/\1$(date +%s)/" ./private/5bb-private.json
sed -E -i '' "s/(\"dateLastModified\"[[:space:]]*:[[:space:]]*)[0-9]+/\1$(date +%s)/" ./public/5bb-public.json
```

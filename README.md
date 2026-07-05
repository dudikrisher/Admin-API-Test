# Exberry Admin API — Documentation Site

Branded, interactive API reference powered by [Scalar](https://github.com/scalar/scalar) (open source, MIT),
hosted for free on GitHub Pages.

## Repository layout

```
docs/
  index.html         # Branded Scalar page (edit BRAND TOKENS block for colors/logo/fonts)
  openapi.json       # The published OpenAPI 3.0.3 spec (generated — do not hand-edit)
spec/
  postman_to_openapi_generator.py   # Postman collection → OpenAPI generator
  spec_overrides.json               # Hand-written description amendments (survives regeneration)
.github/workflows/
  deploy-docs.yml    # Validate spec → deploy to GitHub Pages on every push to main
```

## One-time setup

1. Create a GitHub repository and push these files.
2. Repo **Settings → Pages → Source: GitHub Actions**.
3. Push to `main` — the workflow validates the spec and deploys.
   Docs go live at `https://<org>.github.io/<repo>/`.

### Custom domain (optional, free)

1. Add a file `docs/CNAME` containing e.g. `docs.exberry.io`.
2. In your DNS, add a CNAME record: `docs → <org>.github.io`.
3. Repo Settings → Pages → set the custom domain, enable *Enforce HTTPS*.

## Updating the docs

**API changed (new Postman export):**
```bash
# 1. Update SRC path at the top of the generator (or drop the export in place)
python3 spec/postman_to_openapi_generator.py docs/openapi.json
# 2. Review the diff, commit, push — CI validates and deploys
```

**Fixing/improving a description (no API change):**
Edit `spec/spec_overrides.json` — it supports:
- `info` — API-level description
- `tags` — section intros (by tag name)
- `operations` — summary/description per `operationId`
- `schema_descriptions` — dotted paths into components, e.g. `Instrument.properties.symbol`

Then regenerate (same command). Never hand-edit `docs/openapi.json`; your change would be
lost on the next regeneration.

**Branding:** edit the `BRAND TOKENS` block at the top of `docs/index.html` —
colors, fonts, logo URL. Everything else is rendered by Scalar.

## CI behaviour

Every push touching `docs/` or `spec/`:
1. **Validates** the OpenAPI document (`swagger-cli validate`) — broken specs never deploy.
2. **Diffs** against the previous version (`oasdiff`) — the Action log shows added/removed
   endpoints and breaking changes, ready to paste into a changelog.
3. **Deploys** the `docs/` folder to GitHub Pages.

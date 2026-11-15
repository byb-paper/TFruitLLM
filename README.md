# TropicalfruitLLM Species Lab

**TFruitLLM 1.0: A knowledge- and omics-driven large language model for tropical fruit biology and breeding**

An English-language research portal for thirteen tropical fruit species. The static site integrates species navigation, biologically themed omics discovery and a browser-based TropicalfruitLLM research assistant.

The visual system is independently designed for TropicalfruitLLM and draws general inspiration from contemporary plant-science research portals.

## Local preview

```powershell
python -m http.server 4173 --directory dist
```

Open <http://localhost:4173> in a browser.

## Publish with GitHub Pages

The workflow in `.github/workflows/pages.yml` publishes the `dist/` directory whenever the `main` branch is updated.

1. Open the GitHub repository's **Settings → Pages** page.
2. Set **Source** to **GitHub Actions**.
3. Push to `main` or run the workflow manually from the **Actions** page.

## Connect a Tencent Cloud domain

For a subdomain such as `www.example.cn` or `ai.example.cn`:

1. Open **Settings → Pages → Custom domain** in GitHub and enter the final domain.
2. Open Tencent Cloud DNSPod and create the following DNS record:

   | Host record | Record type | Record value |
   | --- | --- | --- |
   | `www` or `ai` | `CNAME` | `YOUR_GITHUB_USERNAME.github.io` |

3. Wait for GitHub's DNS check to pass, then enable **Enforce HTTPS**.

If the root domain itself is used, configure GitHub Pages' documented apex-domain `A` records instead of the `CNAME` record. Domain registration, real-name verification and ICP filing requirements are handled in Tencent Cloud separately.

## Security

This repository contains only browser-facing static files. Never commit Tencent Cloud keys, model API keys, SMS credentials or RAG service secrets. Authentication and RAG requests must be handled by a protected backend service.

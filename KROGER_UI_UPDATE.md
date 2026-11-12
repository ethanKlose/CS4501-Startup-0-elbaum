# Kroger shopping UI update

This incremental patch applies after `KS_Kroger_Integration.patch`. It changes the
shopping interface at `/grocery/kroger` and includes the illustration, styles,
JavaScript, tests and documentation. No changes to `.env` or Python dependencies
are needed.

## What's different

- Collapsible ingredient sections with food icons, recipe amounts and a clear
  selected state; filter the list to ingredients still needing a choice.
- Product cards show real Kroger photos when supplied by the product API, full
  product names, package sizes, prominent prices and package quantity controls.
- A desktop basket summary shows matching progress, consolidated products,
  quantities and an estimated subtotal. Unknown prices are explicitly excluded
  and called out. Mobile layouts have a fixed review button and subtotal.
- A locally bundled grocery illustration adds a friendly header. Product photos
  are never generated or inferred from a product number. Missing or failed photos
  use a neutral, labeled placeholder.
- Native forms and the final review/confirmation step continue to control cart
  additions. The new JavaScript only controls the display and quantity inputs.

The page does not use an OpenAI or Anthropic key, generate images at runtime,
make background cart transfers or place orders. Kroger product searches and real
product photo downloads still require network access. Photo URLs must be HTTPS
on `kroger.com` or a subdomain, without credentials or a nonstandard port.

## Install in Windows Git Bash

Download `KS_Kroger_UI_Update.patch` to Downloads. Stop the running server with
Ctrl+C, then run each command separately:

```bash
cd ~/OneDrive/Desktop/KS_LLM
git branch --show-current
git apply --check "$HOME/Downloads/KS_Kroger_UI_Update.patch"
git apply "$HOME/Downloads/KS_Kroger_UI_Update.patch"
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

The branch should be `KS_Work`. If the check reports an error, stop before the
apply command; do not force it over a different integration version. This patch
does not create commits or push anything.

Open <http://127.0.0.1:8000/grocery/kroger> and press Ctrl+F5. Previously saved
search results still work but do not gain photos until you search again. The
existing search action clears that ingredient's previous selection; choose the
desired product again after searching.

## Validation on 2026-11-12

| Check | Result |
| --- | --- |
| Full Python suite | 738 passed, 0 failed, 1071 warnings, 215.99 seconds |
| Python application statement/line coverage | 3376 of 3537 measured statements, 95.45% |
| New integration/security/rendering cases | 14 passed; included in the 738 |
| JavaScript DOM interaction tests | 10 passed, 0 failed; separate from the Python count |
| JavaScript syntax and Git whitespace checks | Passed |
| Desktop static layout review | Rendered locally and inspected |
| Native browser checks for this update | Not executed: Chromium launch was blocked by the environment |

The 10 DOM tests exercise the actual JavaScript with jsdom; they do not establish
browser layout, mobile rendering or real Kroger availability. The integration
tests run real application routes with controlled external provider responses,
including the reviewed cart payload. No paid model calls, real account tokens,
live cart additions or purchases were used for this validation.

The full suite emits existing dependency/application deprecation warnings; the
test run was successful. Coverage is measured for Python `app/` only, not the
templates, CSS, JavaScript or third-party services.

Reproduce checks:

```bash
.venv/Scripts/python.exe -m pytest -q
npm ci
npm run test:ui
```

The normal application does not require npm. jsdom is a development dependency
used only by the DOM tests; CI now runs them after `npm ci`.

## Local visual check to run

These are suggested manual checks, not recorded as executed:

1. Open a current review and expand/collapse ingredients with the keyboard.
2. Search for banana again. Compare real product photos, names and package sizes;
   verify an unavailable photo shows its labeled placeholder.
3. Use both quantity controls and typed quantities. Choose a product and confirm
   its saved count and basket estimate; no transfer should occur yet.
4. Filter to Still to choose, restore All ingredients, and remove a selection.
5. At phone width, check readable names, quantity controls and the fixed Review
   basket button. Also check the app's dark theme.
6. Review the final product list. Only deliberately confirm a real cart addition
   if you want it; otherwise stop at review. Unselected ingredients stay excluded.

## Illustration provenance

Bundled asset: `app/static/images/grocery-basket.webp` (600 x 400, transparent).
Created with ChatGPT's built-in image generation, then resized and converted to
WebP. It uses no user API key. It is decorative and is not a retail product photo.

Generation prompt:

> Use case: illustration-story. Asset type: a small decorative illustration for
> the header of a student grocery-shopping web app. A single charming woven
> grocery basket containing a neat bunch of ripe yellow bananas, two carrots, a
> small leafy bunch, a plain glass pantry jar and an unbranded cream carton,
> arranged as one coherent still life. Editorial hand-painted gouache and softly
> textured colored pencil, restrained sage green, warm cream, ochre, muted
> terracotta. Friendly and polished, clean silhouette with a little soft grounding
> shadow, transparent background, no surrounding scene, centered composition with
> plenty of breathing room. No words, labels, logos, numbers, UI, badges, borders
> or typography. It is a general grocery illustration, never a depiction of an
> exact branded retail product.

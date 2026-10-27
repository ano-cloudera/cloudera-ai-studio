# Accelerator frontend design patterns

## Shell

- Sidebar sections: **Navigation**, **Build**, **Context**, **Monitor**; Settings in utility area.
- Page header: title + subtitle + primary action (orange) aligned right on management pages.
- Max width: ~1000–1200px management; Ask Data uses dedicated chat rail (~720px without panel).

## States

- **Empty**: `EmptyState` — icon, title, description, one CTA.
- **Loading**: skeleton rows on lists; centered copy only for first boot.
- **Error**: `ServiceErrorState` — safe title/message, Retry, optional technical details (status/code/request id). Never raw `404 Not Found` as headline.

## Buttons

- Primary: orange (`btn-primary`)
- Secondary: outlined / `btn-secondary`
- Destructive: red border/text
- One primary CTA per Semantic Layer lifecycle step

## API errors

- Central `AppApiError` from `lib/apiError.ts`; `api.request` throws normalized errors.

## Configuration

- Branding and footer: `NEXT_PUBLIC_APP_*`, `NEXT_PUBLIC_PROJECT_NAME`, `NEXT_PUBLIC_SIDEBAR_FOOTER_CAPTION`.
- Features: `NEXT_PUBLIC_FEATURE_*` booleans.

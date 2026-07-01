# Strava API Access Notes

`mcp-strava` is a local mirror over Strava data. Its live refresh path depends
on Strava's public API and the account/application access that Strava currently
allows.

## Current Access Requirement

As of Strava's June 2026 Developer Program changes, Standard Tier developers
need an active Strava subscription, or a Strava-provided grace period, to keep
API access. Extended Access Tier applications are not subscription-gated in the
same way, but require Strava review and are aimed at larger integrations.

For this project that means:

- API refresh works only while the configured Strava application is active.
- A free Strava account without active API access can still use an existing local
  mirror, but cannot refresh that mirror from the public API.
- `strava_application_inactive` in the container healthcheck means Strava is
  rejecting requests at the application-status layer, not that DuckDB or MCP is
  broken.

Check the application tier and subscription/grace status in the Strava API
settings dashboard: <https://www.strava.com/settings/api>.

## Endpoints Used

The refresh path uses:

- `GET /athlete/activities`
- `GET /activities/{id}`
- `GET /activities/{id}/streams`
- `GET /activities/{id}/kudos`

The project does not use the Club Activities, Club Administrators, Club Members,
or Segment Explore endpoints that Strava scheduled for September 1, 2026
deprecation.

## 2027 Base URL Migration

Strava announced that the API base URL will move from
`https://www.strava.com/api/v3` to `https://api-v3.strava.com`.

Do not switch early. Strava's changelog says the new base URL becomes available
on January 4, 2027, and the old base URL is due for retirement on June 1, 2027.
Until the new host is available, keep the current base URL.

The data-fetch transport already sends access tokens in the
`Authorization: Bearer ...` header, which is the required direction for the
2027 change. OAuth token refresh still uses Strava's OAuth endpoint and should be
reviewed separately when Strava publishes final OAuth migration instructions.

## No Supported Non-API Refresh Path

Live refresh is API-only. If Strava disables API access for the configured
application, the existing local DuckDB mirror remains usable for read-only
analytics, but it cannot be refreshed through a documented alternative path.

The project does not currently support importing Strava website exports or any
other non-API source into the mirror. Any future ingest path would need an
explicit design, tests, and operator documentation before being treated as
supported behavior.

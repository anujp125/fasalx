# FasalX Frontend — Admin Dashboard

> **Status**: Planned

Web-based admin dashboard for platform administrators.

## Planned Features

- Monitor active user crop timelines
- Manage crop templates and GDD thresholds
- View platform-wide telemetry and sensor health
- Manage farmer accounts and permissions

## Dashboard Visibility Controls

Open `index.html` in a browser to manage which modules appear on the farmer
dashboard. Paste a Firebase admin ID token with `dashboard:manage` permission,
then load or save the global visibility policy.

The page calls:

- `GET /api/v1/admin/dashboard/visibility`
- `PUT /api/v1/admin/dashboard/visibility`
- `PATCH /api/v1/admin/dashboard/visibility/toggle`

## Setup (Coming Soon)

```bash
npm install
npm run dev
```

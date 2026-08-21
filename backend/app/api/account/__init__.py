"""Self-service account API (``/account/*``).

This is the entire surface a normal (``user``-scoped) session is allowed to reach: the
caller's own profile, API keys, projects, usage/analytics, request history, quota and
billing. Every endpoint is strictly scoped to the authenticated user and their personal
organization — there is no cross-account access and no ``all_users`` escape hatch.

The administrative control plane lives under ``/admin/*`` and requires an admin-scoped
session (minted only by the admin console). A user-scoped token is rejected from every
``/admin/*`` endpoint, so a normal account can never read another account's data or any
platform-wide view even by tampering with requests (§2, separation of user from admin).
"""

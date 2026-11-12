#!/usr/bin/env python3
"""Retrieve fresh Zaptec Service Bus messaging connection details."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any


API_BASE_URL = "https://api.zaptec.com"
TOKEN_URL = f"{API_BASE_URL}/oauth/token"


class ZaptecApiError(RuntimeError):
    """Raised when Zaptec returns an unsuccessful or invalid response."""


def _request_json(
    request: urllib.request.Request, timeout: float, operation: str
) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        detail = ""
        if body:
            try:
                error = json.loads(body)
                detail = error.get("error_description") or error.get("message") or ""
            except (json.JSONDecodeError, AttributeError):
                detail = body[:300]
        suffix = f": {detail}" if detail else ""
        guidance = ""
        if operation == "messaging connection details" and exc.code == 500:
            guidance = (
                ". Verify that the UUID is a User Group ID (not an installation "
                "or charger ID), messaging subscriptions are enabled for that group, "
                "and the account has Owner or Service permission"
            )
        raise ZaptecApiError(
            f"Zaptec API returned HTTP {exc.code} while requesting "
            f"{operation}{suffix}{guidance}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ZaptecApiError(f"Could not connect to Zaptec API: {exc.reason}") from exc

    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ZaptecApiError("Zaptec API returned a non-JSON response") from exc
    if not isinstance(result, dict):
        raise ZaptecApiError("Zaptec API returned an unexpected JSON response")
    return result


def get_access_token(username: str, password: str, timeout: float) -> str:
    form = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "username": username,
            "password": password,
            "scope": "openid",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        TOKEN_URL,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    response = _request_json(request, timeout, "OAuth access token")
    token = response.get("access_token")
    if not isinstance(token, str) or not token:
        raise ZaptecApiError("Token response did not contain an access_token")
    return token


def get_messaging_connection_details(
    user_group_id: str, access_token: str, timeout: float
) -> dict[str, Any]:
    endpoint = (
        f"{API_BASE_URL}/api/userGroups/{user_group_id}/messagingConnectionDetails"
    )
    request = urllib.request.Request(
        endpoint,
        headers={
            # This is the media type used in Zaptec's Service Bus guide example.
            "Accept": "text/plain",
            "Authorization": f"Bearer {access_token}",
        },
        method="GET",
    )
    return _request_json(request, timeout, "messaging connection details")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Get fresh Zaptec AMQP/Service Bus connection credentials."
    )
    parser.add_argument(
        "user_group_id",
        nargs="?",
        default=os.getenv("ZAPTEC_USER_GROUP_ID"),
        help="Zaptec user group UUID (or set ZAPTEC_USER_GROUP_ID)",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("ZAPTEC_USERNAME"),
        help="Zaptec service-account username (or set ZAPTEC_USERNAME)",
    )
    parser.add_argument(
        "--access-token",
        default=os.getenv("ZAPTEC_ACCESS_TOKEN"),
        help="Existing bearer token; skips the username/password token request",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds (default: 30)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.user_group_id:
        print(
            "error: provide user_group_id or set ZAPTEC_USER_GROUP_ID",
            file=sys.stderr,
        )
        return 2
    try:
        user_group_id = str(uuid.UUID(args.user_group_id))
    except ValueError:
        print("error: user_group_id must be a valid UUID", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("error: --timeout must be greater than zero", file=sys.stderr)
        return 2

    try:
        access_token = args.access_token
        if not access_token:
            username = args.username or input("Zaptec username: ").strip()
            if not username:
                print("error: Zaptec username is required", file=sys.stderr)
                return 2
            password = os.getenv("ZAPTEC_PASSWORD") or getpass.getpass(
                "Zaptec password: "
            )
            if not password:
                print("error: Zaptec password is required", file=sys.stderr)
                return 2
            access_token = get_access_token(username, password, args.timeout)

        details = get_messaging_connection_details(
            user_group_id, access_token, args.timeout
        )
    except (ZaptecApiError, KeyboardInterrupt) as exc:
        if isinstance(exc, KeyboardInterrupt):
            print("\nCancelled.", file=sys.stderr)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(details, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

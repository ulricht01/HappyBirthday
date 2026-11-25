"""
Microsoft Entra ID (Azure AD) SSO and User Profile Extraction for SPŠUL.
Complies with SPŠUL Handbook standards (https://github.com/Jaqquca/spsul-handbook).
"""

import os
import urllib.request
import urllib.parse
import json
import logging

logger = logging.getLogger("entra_auth")


def get_tenant_id() -> str:
    return os.getenv("ENTRA_TENANT_ID", "").strip()


def get_client_id() -> str:
    return os.getenv("ENTRA_CLIENT_ID", "").strip()


def get_client_secret() -> str:
    return os.getenv("ENTRA_CLIENT_SECRET", "").strip()


def is_entra_configured() -> bool:
    tenant = get_tenant_id()
    client = get_client_id()
    if not tenant or not client:
        return False
    if "your-" in tenant or "your-" in client or "change-me" in client:
        return False
    return True


def build_authorization_url(redirect_uri: str, state: str = "entra_login") -> str:
    tenant = get_tenant_id() or "common"
    client_id = get_client_id()
    
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": "openid profile email User.Read",
        "state": state,
    }
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{urllib.parse.urlencode(params)}"


def exchange_code_for_user_info(code: str, redirect_uri: str) -> dict:
    """
    Exchanges authorization code for tokens and calls Microsoft Graph /me.
    Returns extracted user profile (name, given_name, surname, email, birthday, hire_date).
    """
    tenant = get_tenant_id() or "common"
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    
    data = {
        "client_id": get_client_id(),
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "scope": "openid profile email User.Read",
    }
    
    secret = get_client_secret()
    if secret:
        data["client_secret"] = secret

    encoded_data = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(token_url, data=encoded_data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            token_res = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.error("Failed to exchange code for token: %s", exc)
        raise RuntimeError(f"Chyba při komunikaci s Microsoft Entra ID: {exc}")

    access_token = token_res.get("access_token")
    if not access_token:
        raise RuntimeError("Microsoft Entra ID nevrátil přístupový token.")

    # Call Microsoft Graph /me
    graph_url = "https://graph.microsoft.com/v1.0/me?$select=id,displayName,givenName,surname,mail,userPrincipalName,birthday,employeeHireDate"
    graph_req = urllib.request.Request(graph_url)
    graph_req.add_header("Authorization", f"Bearer {access_token}")
    graph_req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(graph_req, timeout=10) as response:
            user_data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.error("Failed to fetch user data from Graph: %s", exc)
        raise RuntimeError(f"Chyba při čtení profilu z Microsoft Graph: {exc}")

    given_name = user_data.get("givenName") or ""
    surname = user_data.get("surname") or ""
    display_name = user_data.get("displayName") or f"{given_name} {surname}".strip()
    email = user_data.get("mail") or user_data.get("userPrincipalName") or ""
    birthday = user_data.get("birthday")  # e.g. "0000-03-19" or ISO date
    hire_date = user_data.get("employeeHireDate")

    formatted_dob = None
    if birthday:
        # Normalize birthday if provided
        parts = birthday.split("T")[0].split("-")
        if len(parts) == 3:
            formatted_dob = f"{parts[0]}-{parts[1]}-{parts[2]}"

    formatted_hire = None
    if hire_date:
        parts = hire_date.split("T")[0].split("-")
        if len(parts) == 3:
            formatted_hire = f"{parts[0]}-{parts[1]}-{parts[2]}"

    return {
        "oid": user_data.get("id"),
        "name": display_name,
        "first_name": given_name,
        "last_name": surname,
        "email": email.lower(),
        "date_of_birth": formatted_dob,
        "first_day_job": formatted_hire,
    }

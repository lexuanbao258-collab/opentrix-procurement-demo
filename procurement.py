"""Manage OpenTrix procurement requests using the Platform v1 HTTPS API."""
import argparse
import base64
import http.client
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

APP = "opentrix-procurement"
ENTITY = "purchaseRequest"
APPS = "/api/v1/apps"
RECORDS = f"{APPS}/{APP}/entities/{ENTITY}/records"


class ApiError(Exception):
    def __init__(self, status, code):
        self.status = status
        self.code = code
        super().__init__(f"HTTP {status} {code}")


class TransportError(Exception):
    pass


class UnknownOutcome(Exception):
    def __init__(self, record_id):
        self.record_id = record_id
        super().__init__(f"Write outcome unknown for {record_id}. Run reconcile {record_id}.")


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def https_url(value, *, origin=False):
    url = urllib.parse.urlsplit(value)
    if (url.scheme != "https" or not url.hostname or url.username is not None
            or url.query or url.fragment or (origin and url.path not in ("", "/"))):
        raise ValueError("Set an HTTPS URL without credentials, query, or fragment.")
    return value.rstrip("/")


class Client:
    def __init__(self, api_url, token_url, client_id, secret, ca_file=None):
        self.url = https_url(api_url, origin=True)
        self.token_url = https_url(token_url)
        self.client_id = client_id
        self.secret = secret
        tls = ssl.create_default_context(cafile=ca_file)
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=tls), NoRedirects(),
        )
        self.token = None

    def _send(self, method, url, headers, data=None):
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=15) as response:
                return None if response.status == 204 else json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                try:
                    body = json.load(error)
                except (ValueError, OSError, http.client.HTTPException):
                    body = None
                code = body.get("code") if isinstance(body, dict) else None
                if not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", code):
                    code = "HTTP_ERROR"
                raise ApiError(error.code, code) from None
        except (OSError, ValueError, http.client.HTTPException) as error:
            raise TransportError(f"HTTPS request failed ({type(error).__name__}).") from None

    def authenticate(self):
        client = urllib.parse.quote_plus(self.client_id)
        secret = urllib.parse.quote_plus(self.secret)
        credential = base64.b64encode(f"{client}:{secret}".encode("ascii")).decode("ascii")
        response = self._send("POST", self.token_url, {
            "Authorization": f"Basic {credential}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }, b"grant_type=client_credentials")
        if (not isinstance(response, dict) or not response.get("access_token")
                or str(response.get("token_type", "")).lower() != "bearer"):
            raise TransportError("OAuth2 server did not return a bearer token.")
        self.token = response["access_token"]

    def request(self, method, path, *, query=None, body=None, write_id=None):
        if self.token is None:
            self.authenticate()
        url = self.url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.token}"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, allow_nan=False).encode("utf-8")
        try:
            return self._send(method, url, headers, data)
        except ApiError as error:
            if write_id is None or not (
                error.code == "COMMIT_OUTCOME_UNKNOWN"
                or (error.status >= 500 and error.code != "STORE_UNAVAILABLE")
            ):
                raise
        except TransportError:
            if write_id is None:
                raise
        raise UnknownOutcome(write_id) from None

    def reconcile(self, record_id):
        path = f"{RECORDS}/{record_id}"
        try:
            record = self.request("GET", path)
            history = self.request("GET", path + "/history")
        except ApiError as error:
            if error.status != 404:
                raise
            return {"id": record_id, "visibility": "missing_or_hidden"}
        return {"id": record_id, "record": record, "history": history}


def fields(args):
    return {
        "itemName": args.item,
        "quantity": args.quantity,
        "estimatedUnitPriceMinor": args.unit_price_minor,
        "justification": args.justification,
    }


def run(client, args):
    command = args.command
    if command in ("apps", "app", "entity"):
        path = {"apps": APPS, "app": f"{APPS}/{APP}", "entity": RECORDS.removesuffix("/records")}
        return client.request("GET", path[command])
    if command in ("list", "search", "audit"):
        query = {"limit": args.limit, "offset": args.offset}
        if command == "search":
            query["q"] = args.query
        if command == "audit":
            if args.id:
                query["recordId"] = args.id
            return client.request("GET", RECORDS.removesuffix("/records") + "/audit", query=query)
        return client.request("GET", RECORDS, query=query)
    if command == "create":
        record_id = args.id or str(uuid.uuid4())
        print(f"Request UUID {record_id}", file=sys.stderr, flush=True)
        return client.request("POST", RECORDS, write_id=record_id,
                              body={"id": record_id, "data": fields(args)})
    if command == "reconcile":
        return client.reconcile(args.id)
    path = f"{RECORDS}/{args.id}"
    if command == "read":
        return client.request("GET", path)
    if command in ("workflow", "history"):
        return client.request("GET", f"{path}/{command}")
    version = {"expectedVersion": args.version}
    if command == "update":
        return client.request("PUT", path, body={**version, "data": fields(args)}, write_id=args.id)
    if command == "delete":
        return client.request("DELETE", path, query=version, write_id=args.id)
    return client.request("POST", f"{path}/transitions/{command}", body=version, write_id=args.id)


def uuid_arg(value):
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise argparse.ArgumentTypeError("expected a UUID") from None


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("apps", "app", "entity"):
        sub.add_parser(name)
    for name in ("list", "search", "audit"):
        action = sub.add_parser(name)
        action.add_argument("--limit", type=int, default=20)
        action.add_argument("--offset", type=int, default=0)
        if name == "search":
            action.add_argument("query")
        if name == "audit":
            action.add_argument("--id", type=uuid_arg)
    for name in ("create", "read", "update", "delete", "workflow", "history",
                 "submit", "approve", "reject", "reconcile"):
        action = sub.add_parser(name)
        action.add_argument("--id" if name == "create" else "id", type=uuid_arg)
        if name in ("update", "delete", "submit", "approve", "reject"):
            action.add_argument("--version", required=True, type=int)
        if name in ("create", "update"):
            action.add_argument("--item", required=True)
            action.add_argument("--quantity", required=True, type=int)
            action.add_argument("--unit-price-minor", required=True, type=int)
            action.add_argument("--justification", required=True)
    return parser.parse_args()


def main():
    args = arguments()
    try:
        api_url = os.environ["PROCUREMENT_API_URL"]
        token_url = os.environ.get("PROCUREMENT_TOKEN_URL") or (
            api_url.rstrip("/") + "/realms/tricore/protocol/openid-connect/token"
        )
        client = Client(api_url, token_url, os.environ["PROCUREMENT_CLIENT_ID"],
                        os.environ["PROCUREMENT_CLIENT_SECRET"], os.environ.get("PROCUREMENT_CA_FILE"))
        result = run(client, args)
        if result is not None:
            print(json.dumps(result, indent=2))
        return 0
    except KeyError as error:
        print(f"Set {error.args[0]} in the environment.", file=sys.stderr)
    except ApiError as error:
        print(error, file=sys.stderr)
        if error.code == "VERSION_CONFLICT":
            print("Read the current version and review it before repeating the operation.", file=sys.stderr)
            return 3
    except UnknownOutcome as error:
        print(error, file=sys.stderr)
        if args.command == "create":
            print("If replay is needed, repeat the original create with the same --id and original fields.",
                  file=sys.stderr)
        return 4
    except (TransportError, OSError, ValueError) as error:
        print(error, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

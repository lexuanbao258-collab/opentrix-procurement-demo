"""Run acceptance checks against the isolated M5 Keycloak and Platform."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import uuid

from deploy.stack import LOCAL
from procurement import APPS, APP, RECORDS, ApiError, Client, TransportError, UnknownOutcome

ROOT = Path(__file__).resolve().parents[1]
AUDIT = f"{RECORDS.removesuffix('/records')}/audit"
ORIGIN = f"https://localhost:{os.getenv('M5_PORT', '18444')}"
TOKEN = ORIGIN + "/realms/tricore/protocol/openid-connect/token"
CERT = LOCAL / "caddy-root.crt"
SNAPSHOT = LOCAL / "persistence.json"


def accounts():
    secrets = json.loads((LOCAL / "accounts.json").read_text(encoding="utf-8"))
    return {name: Client(ORIGIN, TOKEN, f"m5-{name}", secret, str(CERT))
            for name, secret in secrets.items()}


def wait_for_api(client):
    for _ in range(60):
        try:
            client.request("GET", APPS)
            return
        except TransportError:
            pass
        except ApiError as error:
            if error.status not in (502, 503, 504):
                raise
        time.sleep(2)
    raise RuntimeError("M5 API was unavailable after 60 readiness reads.")


def token_claims(client):
    return json.loads(base64.urlsafe_b64decode(client.token.split(".")[1] + "==="))


def actor_id(client):
    claims = token_claims(client)
    parts = [base64.urlsafe_b64encode(claims[key].encode()).decode().rstrip("=")
             for key in ("iss", "sub")]
    return "oidc:" + ".".join(parts)


def item(**changes):
    return {"itemName": f"Desk fixture {uuid.uuid4().hex}", "quantity": 2,
            "estimatedUnitPriceMinor": 1250, "justification": f"synthetic-{uuid.uuid4()}", **changes}


def create(client, data, record_id=None, path=RECORDS):
    record_id = record_id or str(uuid.uuid4())
    return client.request("POST", path, body={"id": record_id, "data": data}, write_id=record_id)


def mutate(client, record, method, *, suffix="", data=None, version=None):
    record_id = record["id"]
    path = f"{RECORDS}/{record_id}{suffix}"
    fields = {"expectedVersion": record["version"] if version is None else version}
    if method == "DELETE":
        return client.request(method, path, query=fields, write_id=record_id)
    if data is not None:
        fields["data"] = data
    return client.request(method, path, body=fields, write_id=record_id)


def transition(client, record, action, **options):
    return mutate(client, record, "POST", suffix=f"/transitions/{action}", **options)


def persisted(clients, record_id):
    return {
        **clients["requester"].reconcile(record_id),
        "audit": clients["auditor"].request("GET", AUDIT, query={"recordId": record_id}),
    }


class Live(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clients = accounts()
        cls.requester = cls.clients["requester"]
        cls.approver = cls.clients["approver"]
        cls.auditor = cls.clients["auditor"]
        wait_for_api(cls.requester)

    def denied(self, status, operation, *args, code=None, **kwargs):
        with self.assertRaises(ApiError) as caught:
            operation(*args, **kwargs)
        self.assertEqual(caught.exception.status, status, str(caught.exception))
        if code:
            self.assertEqual(caught.exception.code, code)

    def workflow(self, client, record):
        return client.request("GET", f"{RECORDS}/{record['id']}/workflow")

    def test_manifest_registration_discovery_and_role_scopes(self):
        expected = {
            "requester": (APP, "1.0.0", ["requester"]),
            "approver": (APP, "1.0.0", ["approver"]),
            "auditor": (APP, "1.0.0", ["auditor"]),
            "dual": (APP, "1.0.0", ["approver", "requester"]),
            "hr": ("hr-leave", "1.1.0", ["employee"]),
            "it": ("it-helpdesk", "1.0.0", ["admin"]),
        }
        for name, client in self.clients.items():
            with self.subTest(name=name):
                self.assertEqual([
                    (app["id"], app["version"], sorted(app["callerRoles"]))
                    for app in client.request("GET", APPS)
                ], [expected[name]])
                claims = token_claims(client)
                self.assertEqual((claims.get("client_id"), claims.get("azp")),
                                 (client.client_id, client.client_id))
        schema = self.requester.request("GET", RECORDS.removesuffix("/records"))
        self.assertEqual(schema["key"], "purchaseRequest")
        self.assertEqual(schema["searchFields"], ["itemName"])
        self.assertEqual(schema["allowedOperations"],
                         {"read": "own", "create": "own", "update": "own", "delete": "own"})

    def test_create_list_search_read_update_delete_and_input_validation(self):
        data = item()
        self.denied(400, create, self.requester, {**data, "quantity": 0})
        draft = create(self.requester, data)
        self.assertEqual((draft["state"], draft["version"], draft["data"]), ("DRAFT", 0, data))
        self.assertEqual(draft["createdBy"], actor_id(self.requester))
        path = f"{RECORDS}/{draft['id']}"
        self.assertEqual(self.requester.request("GET", path), draft)
        visible = self.requester.request("GET", RECORDS, query={"limit": 1, "offset": 0})
        self.assertEqual(len(visible["items"]), 1)
        hit = self.requester.request("GET", RECORDS, query={"q": data["itemName"].upper()})
        self.assertEqual((hit["total"], hit["items"]), (1, [draft]))
        updated = mutate(self.requester, draft, "PUT", data={**data, "quantity": 3})
        self.assertEqual((updated["version"], updated["data"]["quantity"]), (1, 3))
        self.assertIsNone(mutate(self.requester, updated, "DELETE"))
        self.denied(404, self.requester.request, "GET", path)
        self.assertEqual(self.requester.request("GET", RECORDS, query={"q": data["itemName"]})["total"], 0)

    def test_distinct_requester_and_approver_approve_and_reject(self):
        for action, state in (("approve", "APPROVED"), ("reject", "REJECTED")):
            with self.subTest(action=action):
                draft = create(self.requester, item())
                pending = transition(self.requester, draft, "submit")
                self.assertEqual(pending["state"], "PENDING")
                self.assertEqual({entry["id"] for entry in self.workflow(self.approver, pending)["allowedActions"]},
                                 {"approve", "reject"})
                finished = transition(self.approver, pending, action)
                self.assertEqual((finished["state"], finished["version"]), (state, 2))
                self.assertEqual(finished["createdBy"], actor_id(self.requester))
                self.assertEqual(finished["updatedBy"], actor_id(self.approver))
                self.assertNotEqual(finished["createdBy"], finished["updatedBy"])
                self.assertTrue(self.workflow(self.requester, finished)["terminal"])
                history = self.requester.reconcile(finished["id"])["history"]
                self.assertEqual([event["toState"] for event in history], ["DRAFT", "PENDING", state])
                self.assertEqual(history[-1]["actorId"], actor_id(self.approver))
                self.denied(409, mutate, self.requester, finished, "PUT", data=draft["data"])
                self.denied(409, mutate, self.requester, finished, "DELETE")
                if action == "approve":
                    SNAPSHOT.write_text(json.dumps(persisted(self.clients, finished["id"])), encoding="utf-8")

    def test_self_approval_and_self_rejection_denied_with_no_audit_write(self):
        dual = self.clients["dual"]
        pending = transition(dual, create(dual, item()), "submit")
        self.assertEqual(self.workflow(dual, pending)["allowedActions"], [])
        before = self.auditor.request("GET", AUDIT, query={"recordId": pending["id"]})
        history = dual.reconcile(pending["id"])
        for action in ("approve", "reject"):
            self.denied(403, transition, dual, pending, action)
        self.assertEqual(dual.reconcile(pending["id"]), history)
        self.assertEqual(self.auditor.request("GET", AUDIT, query={"recordId": pending["id"]}), before)

    def test_forbidden_operations_and_owner_filtered_results(self):
        draft = create(self.requester, item())
        self.denied(403, create, self.auditor, item())
        self.denied(403, create, self.approver, item())
        self.denied(403, mutate, self.auditor, draft, "PUT", data=draft["data"])
        self.denied(403, mutate, self.auditor, draft, "DELETE")
        self.denied(403, transition, self.approver, draft, "submit")
        pending = transition(self.requester, draft, "submit")
        self.denied(403, transition, self.requester, pending, "approve")
        self.denied(403, transition, self.auditor, pending, "reject")
        for client in (self.requester, self.approver):
            self.denied(403, client.request, "GET", AUDIT, query={"recordId": draft["id"]})
        other = create(self.clients["dual"], item())
        self.denied(404, self.requester.request, "GET", f"{RECORDS}/{other['id']}")
        self.denied(404, self.requester.request, "GET", f"{RECORDS}/{other['id']}/history")
        self.assertEqual(self.requester.request(
            "GET", RECORDS, query={"q": other["data"]["itemName"]},
        )["total"], 0)

    def test_cross_app_access_denied_in_both_directions(self):
        draft = create(self.requester, item())
        fixtures = {
            "hr": ("hr-leave", "leaveRequest", {
                "kind": "ANNUAL", "startDate": "2030-01-01", "days": 1, "reason": "Synthetic leave",
            }),
            "it": ("it-helpdesk", "category", {
                "code": "M5_" + uuid.uuid4().hex[:16].upper(), "name": "Synthetic category", "active": True,
            }),
        }
        for name, (app, entity, data) in fixtures.items():
            with self.subTest(app=app):
                other = self.clients[name]
                other_path = f"{APPS}/{app}/entities/{entity}/records"
                fixture = create(other, data, path=other_path)
                for client, app_id, path, record in (
                    (self.requester, app, other_path, fixture),
                    (other, APP, RECORDS, draft),
                ):
                    for target in (f"{APPS}/{app_id}", path.removesuffix("/records"), path,
                                   f"{path}/{record['id']}"):
                        self.denied(404, client.request, "GET", target)
                    self.denied(404, create, client, record["data"], path=path)
                self.assertEqual(other.request("GET", f"{other_path}/{fixture['id']}"), fixture)
        self.assertEqual(self.requester.reconcile(draft["id"])["record"], draft)

    def test_stale_update_delete_and_transition_rejected(self):
        draft = create(self.requester, item())
        changed = mutate(self.requester, draft, "PUT", data={**draft["data"], "quantity": 4})
        for method in ("PUT", "DELETE"):
            self.denied(409, mutate, self.requester, draft, method,
                        data=draft["data"], code="VERSION_CONFLICT")
        self.denied(409, transition, self.requester, draft, "submit", code="VERSION_CONFLICT")
        self.assertEqual(self.requester.reconcile(draft["id"])["record"], changed)
        self.assertEqual(transition(self.requester, changed, "submit")["state"], "PENDING")

    def test_duplicate_create_replays_original_and_never_resurrects(self):
        data = item()
        draft = create(self.requester, data)
        record_id = draft["id"]
        self.assertEqual(create(self.requester, data, record_id), draft)
        self.denied(409, create, self.requester, {**data, "quantity": 10}, record_id,
                    code="CREATE_ID_CONFLICT")
        self.denied(404, create, self.clients["dual"], data, record_id)
        changed = mutate(self.requester, draft, "PUT", data={**data, "quantity": 7})
        self.assertEqual(create(self.requester, data, record_id), changed)
        audit = self.auditor.request("GET", AUDIT, query={"recordId": record_id})
        self.assertEqual(sum(event["action"] == "CREATE" for event in audit["items"]), 1)
        mutate(self.requester, changed, "DELETE")
        self.denied(404, create, self.requester, data, record_id)

    def test_unknown_outcome_reconciles_a_lost_live_ack_without_retry(self):
        record_id = str(uuid.uuid4())
        data = item()
        original = self.requester._send

        def lose_ack(*args, **kwargs):
            response = original(*args, **kwargs)
            self.assertEqual(response["id"], record_id)
            raise TransportError("Test discards a successful response from the live server.")

        with patch.object(self.requester, "_send", side_effect=lose_ack) as sent:
            with self.assertRaises(UnknownOutcome) as caught:
                create(self.requester, data, record_id)
            self.assertEqual(caught.exception.record_id, record_id)
            self.assertEqual(sent.call_count, 1)
        result = self.requester.reconcile(record_id)
        self.assertEqual(result["record"]["data"], data)
        self.assertEqual(create(self.requester, data, record_id), result["record"])
        self.assertEqual(self.requester.reconcile(str(uuid.uuid4()))["visibility"], "missing_or_hidden")

    def test_authorized_audit_redacts_before_and_after(self):
        data = item()
        draft = create(self.requester, data)
        changed_data = {**data, "justification": f"replacement-{uuid.uuid4()}"}
        mutate(self.requester, draft, "PUT", data=changed_data)
        audit = self.auditor.request("GET", AUDIT, query={"recordId": draft["id"]})
        events = {event["action"]: event for event in audit["items"]}
        self.assertEqual(set(events), {"CREATE", "UPDATE"})
        encoded = json.dumps(audit)
        self.assertNotIn(data["justification"], encoded)
        self.assertNotIn(changed_data["justification"], encoded)
        for snapshot in (events["CREATE"]["after"], events["UPDATE"]["before"], events["UPDATE"]["after"]):
            self.assertIn('"justification": "[REDACTED]"', json.dumps(snapshot))
            self.assertIn(data["itemName"], json.dumps(snapshot))
        self.assertEqual(events["CREATE"]["actorId"], actor_id(self.requester))
        self.assertEqual(events["CREATE"]["actorType"], "MACHINE")

    def test_tls_untrusted_certificate_and_missing_token_denied(self):
        isolated_trust = Client(ORIGIN, TOKEN, self.requester.client_id, self.requester.secret)
        with self.assertRaises(urllib.error.URLError) as refused:
            isolated_trust.opener.open(ORIGIN + APPS, timeout=5)
        self.assertIn("CERTIFICATE_VERIFY_FAILED", str(refused.exception.reason))
        with self.assertRaises(urllib.error.HTTPError) as denied:
            self.requester.opener.open(ORIGIN + APPS, timeout=5)
        self.assertEqual(denied.exception.code, 401)
        denied.exception.close()

    def cli(self, account, *args, exit_code=0):
        client = self.clients[account]
        env = dict(os.environ, PROCUREMENT_API_URL=ORIGIN, PROCUREMENT_TOKEN_URL=TOKEN,
                   PROCUREMENT_CA_FILE=str(CERT), PROCUREMENT_CLIENT_ID=client.client_id,
                   PROCUREMENT_CLIENT_SECRET=client.secret)
        result = subprocess.run([sys.executable, str(ROOT / "procurement.py"), *args],
                                env=env, text=True, capture_output=True, timeout=25)
        self.assertEqual(result.returncode, exit_code, result.stderr)
        return result

    def test_cli_entry_points(self):
        self.assertEqual(json.loads(self.cli("requester", "apps").stdout)[0]["id"], APP)
        self.assertEqual(json.loads(self.cli("requester", "app").stdout)["id"], APP)
        self.assertEqual(json.loads(self.cli("requester", "entity").stdout)["key"], "purchaseRequest")
        record_id = str(uuid.uuid4())
        fields = ("--item", "CLI synthetic fixture", "--quantity", "1",
                  "--unit-price-minor", "250", "--justification", "CLI synthetic")
        created = self.cli("requester", "create", "--id", record_id, *fields)
        self.assertIn(record_id, created.stderr)
        self.assertEqual(json.loads(created.stdout)["id"], record_id)
        self.cli("requester", "list")
        self.cli("requester", "search", "CLI synthetic fixture")
        self.cli("requester", "read", record_id)
        self.cli("requester", "update", record_id, "--version", "0", *fields)
        self.cli("requester", "delete", record_id, "--version", "0", exit_code=3)
        self.cli("requester", "submit", record_id, "--version", "1")
        self.cli("approver", "workflow", record_id)
        self.cli("approver", "reject", record_id, "--version", "2")
        self.cli("requester", "history", record_id)
        self.cli("requester", "reconcile", record_id)
        self.cli("auditor", "audit", "--id", record_id)
        temporary = self.cli("requester", "create", *fields)
        self.cli("requester", "delete", json.loads(temporary.stdout)["id"], "--version", "0")


def verify_restart():
    before = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    clients = accounts()
    wait_for_api(clients["requester"])
    after = persisted(clients, before["id"])
    if before != after or after["record"]["state"] != "APPROVED":
        raise SystemExit("FAIL: persisted record, workflow history, or audit changed after restart")
    print("PASS: record, workflow history, and audit preserved after restart")


if __name__ == "__main__":
    if sys.argv[1:] == ["verify-restart"]:
        verify_restart()
    else:
        unittest.main()

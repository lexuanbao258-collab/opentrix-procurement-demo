"""Provision and operate only the isolated M5 Compose project."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import time

PIN = "f401b6e79930a1386e71e92a91ae6a909cfa1e59"
ROOT = Path(__file__).resolve().parents[1]
PROJECT = os.environ.get("M5_PROJECT", "opentrix-procurement-m5-verified")
LOCAL = ROOT / ".local" / PROJECT
RUNTIME = LOCAL / "platform"
ROLES = {
    "requester": ["opentrix-procurement:requester"],
    "approver": ["opentrix-procurement:approver"],
    "auditor": ["opentrix-procurement:auditor"],
    "dual": ["opentrix-procurement:requester", "opentrix-procurement:approver"],
    "hr": ["hr-leave:employee"],
    "it": ["it-helpdesk:admin"],
}
VARIABLES = (
    "HELPDESK_SETUP_PASSWORD HELPDESK_RUNTIME_PASSWORD PLATFORM_OWNER_PASSWORD "
    "KEYCLOAK_ADMIN_PASSWORD PORTAL_OIDC_CLIENT_SECRET GATEWAY_MONITOR_CLIENT_SECRET "
    "EXTERNAL_EMPLOYEE_SECRET EXTERNAL_APPROVER_SECRET DEMO_EMPLOYEE_PASSWORD "
    "DEMO_COORDINATOR_PASSWORD DEMO_WORKER_PASSWORD"
).split()


def save_private(path, content):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
        file.write(content)


def prepare(source):
    LOCAL.mkdir(mode=0o700, parents=True, exist_ok=True)
    marker = RUNTIME / ".m5-pin"
    if not marker.exists():
        RUNTIME.mkdir(exist_ok=True)
        archive = LOCAL / "platform.tar"
        subprocess.run([
            "git", "-c", f"safe.directory={source.as_posix()}", "-C", str(source),
            "archive", "--format=tar", f"--output={archive}", PIN,
        ], check=True)
        subprocess.run(["tar", "-xf", str(archive), "-C", str(RUNTIME)], check=True)
        archive.unlink()
        marker.write_text(PIN, encoding="ascii")
    if marker.read_text(encoding="ascii") != PIN:
        raise SystemExit("The local Platform archive has a different pin.")

    apps = LOCAL / "apps"
    for directory in (RUNTIME / "apps", ROOT / "manifests"):
        for manifest in directory.glob("*/app.json"):
            destination = apps / manifest.parent.name / "app.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(manifest, destination)

    environment = LOCAL / "compose.env"
    if not environment.exists():
        save_private(environment, "".join(f"{key}={secrets.token_hex(24)}\n" for key in VARIABLES))

    accounts = LOCAL / "accounts.json"
    if not accounts.exists():
        save_private(accounts, json.dumps({name: secrets.token_hex(32) for name in ROLES}))

    realm_file = LOCAL / "realm.json"
    if not realm_file.exists():
        realm = json.loads((RUNTIME / "infra/keycloak/tricore-realm.json").read_text(encoding="utf-8"))
        template = next(client for client in realm["clients"] if client["clientId"] == "hr-employee-bot")
        realm["clients"] = [client for client in realm["clients"] if client["clientId"] == "tricore-api"]
        realm["users"] = []
        realm["clientScopeMappings"] = {"tricore-api": []}
        for role in ROLES["requester"] + ROLES["approver"] + ROLES["auditor"]:
            realm["roles"]["client"]["tricore-api"].append({"name": role})
        credentials = json.loads(accounts.read_text(encoding="utf-8"))
        for name, roles in ROLES.items():
            client_id = f"m5-{name}"
            client = copy.deepcopy(template)
            client.update(clientId=client_id, name=client_id, description="M5 test service account",
                          secret=credentials[name])
            client["defaultClientScopes"] = ["basic", "roles", "service_account"]
            realm["clients"].append(client)
            realm["clientScopeMappings"]["tricore-api"].append({"client": client_id, "roles": roles})
            realm["users"].append({
                "username": f"service-account-{client_id}", "enabled": True,
                "serviceAccountClientId": client_id, "clientRoles": {"tricore-api": roles},
            })
        save_private(realm_file, json.dumps(realm))


def compose(*args, capture=False, check=True):
    infra = RUNTIME / "infra"
    # Use the generated DB credentials even if similarly named variables exist on the host.
    env = {key: value for key, value in os.environ.items() if key not in VARIABLES}
    env.update(M5_ROOT=ROOT.as_posix(), M5_LOCAL=LOCAL.as_posix())
    return subprocess.run([
        "docker", "compose", "-p", PROJECT, "--project-directory", str(infra),
        "--env-file", str(LOCAL / "compose.env"), "-f", str(infra / "compose.demo.yml"),
        "-f", str(ROOT / "deploy/compose.yml"), *args,
    ], check=check, env=env, stdout=subprocess.PIPE if capture else None)


def export_ca():
    for _ in range(60):
        result = compose("exec", "-T", "ingress", "cat",
                         "/data/caddy/pki/authorities/local/root.crt", capture=True, check=False)
        if result.returncode == 0 and result.stdout.startswith(b"-----BEGIN CERTIFICATE-----"):
            (LOCAL / "caddy-root.crt").write_bytes(result.stdout)
            return
        time.sleep(1)
    raise SystemExit("Caddy did not create the M5 CA.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["up", "restart", "stop", "ps", "logs"])
    parser.add_argument("--platform", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"opentrix-procurement-[a-z0-9-]+", PROJECT):
        parser.error("M5_PROJECT must start with opentrix-procurement-.")
    if args.action == "up":
        if args.platform is None:
            parser.error("--platform must point to a Git checkout containing the pinned SHA.")
        prepare(args.platform.resolve(strict=True))
        compose("config", "--quiet")
        compose("up", "-d", "--build", "backend", "ingress")
        export_ca()
    elif args.action == "restart":
        compose("restart", "--no-deps", "postgres", "keycloak", "backend", "ingress")
        export_ca()
    elif args.action == "stop":
        compose("stop", "backend", "ingress", "keycloak", "postgres")
    elif args.action == "logs":
        compose("logs", "--tail=50", "platform-migrate", "backend", "ingress", "keycloak", "db-init")
    else:
        compose("ps", "--all")


if __name__ == "__main__":
    main()

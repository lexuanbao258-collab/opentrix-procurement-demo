<!--
SPDX-FileCopyrightText: 2026 OpenTrix Procurement contributors
SPDX-License-Identifier: Apache-2.0
-->

# Third-party notices

Procurement uses the standard library of the developer's Python installation
under the [Python Software Foundation license and bundled notices](https://docs.python.org/3.14/license.html).
The repository ships no Python interpreter, Python packages, Docker images,
JARs or dependency binaries.

| Referenced image | Purpose | Project-level license |
| --- | --- | --- |
| [`postgres:17.11-alpine`](https://hub.docker.com/_/postgres) | Database and bootstrap | [PostgreSQL License](https://www.postgresql.org/about/licence/) |
| [`quay.io/keycloak/keycloak:26.8.0`](https://quay.io/repository/keycloak/keycloak) | OAuth2 identity provider | [Apache-2.0](https://github.com/keycloak/keycloak/blob/26.8.0/LICENSE.txt) |
| [`caddy:2.10.2-alpine`](https://hub.docker.com/_/caddy) | HTTPS ingress, digest pinned in Compose | [Apache-2.0](https://github.com/caddyserver/caddy/blob/v2.10.2/LICENSE) |
| [`gradle:8.14.3-jdk21`](https://hub.docker.com/_/gradle) | Platform build stage | [Apache-2.0](https://github.com/gradle/gradle/blob/v8.14.3/LICENSE) |
| [`eclipse-temurin:21-jre`](https://hub.docker.com/_/eclipse-temurin) | Platform JVM | [GPL-2.0 with Classpath Exception](https://openjdk.org/legal/gplv2+ce.html) |

The demo retrieves external images and builds the Platform locally from the frozen
checkout. Its generated manifests and copied deployment assets stay under ignored
`.local/`. Adapted source attribution is in [NOTICE](NOTICE). Platform dependencies
and its own notices are listed in
[Platform THIRD-PARTY-NOTICES.md at the runtime baseline](https://github.com/lexuanbao258-collab/opentrix-v1-candidate/blob/f401b6e79930a1386e71e92a91ae6a909cfa1e59/THIRD-PARTY-NOTICES.md).

The table covers the named projects. Container base OS packages and bundled components
may carry additional licenses and notices. Before distributing an image, inventory its
exact contents and satisfy the relevant notice, source and other distribution
obligations. The Procurement source distribution does not include these images.

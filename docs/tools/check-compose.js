#!/usr/bin/env node
/* Runs the Docker Compose builder's own code (landing/compose/compose.js) over the choices it offers and fails when a
   file it writes is not what the choice calls for.

       node tools/check-compose.js

   With Docker on the machine, every file is also read by `docker compose config`, which is what catches a file that
   is not valid at all (CHECK_COMPOSE_DOCKER=0 skips it; =1 fails when Docker is missing). build.sh runs this. */
"use strict";
const path = require("path"), fs = require("fs"), os = require("os"), cp = require("child_process");
const C = require(path.join(__dirname, "..", "landing", "compose", "compose.js"));

let n = 0;
const pw = () => "pw" + (++n) + "Abcdefghijkl";
const none = () => Object.fromEntries(C.APPS.map(a => [a.key, false]));
function answers(change) {
  const s = C.defaults(pw, "Europe/Brussels");
  s.admin.password = 'It\'s $ecret "1"';
  s.iopix.photos = "/srv/photos";
  return C.merge(s, change || {});
}
const failures = [];
function check(name, ok, detail) { if (!ok) failures.push(name + (detail ? ": " + detail : "")); }
const has = (y, line) => y.split("\n").some(l => l.trim().startsWith(line));

const CASES = {
  "the default: every app, MariaDB, plain HTTP": [answers(), (y, s) => {
    check("the three ports are published", (y.match(/^ {6}- "[\d.:]+"/gm) || []).join() === '      - "80:80",      - "8443:8443",      - "8444:8444"');
    check("one container runs the apps", has(y, 'APPS: "' + C.APPS.filter(a => s.apps[a.key]).map(a => a.key).join(",") + '"') && !/^  iopix:/m.test(y));
    check("the databases are made", has(y, '- "--db-admin=root"'));
    check("the admin's password is quoted with $ doubled", has(y, 'ADMIN_PASSWORD: "It\'s $$ecret \\"1\\""'));
    check("no address is stored when none was given", !y.includes("--set=suite."));
    check("no proxy is believed", has(y, '- "--proxies="') && !has(y, "networks:"));
    check("the photos folder", has(y, '- "/srv/photos:/library/photos"') && has(y, '- "--set=iopix.PHOTOS_ROOT=/library/photos"'));
    check("the image with ioPix's AI packages, and its models", has(y, "image: " + C.IMAGE + ":ai") && has(y, '- "--set=iopix.AUTO_MODELS=siglip2,yolox,geonames"'));
    check("no demo data unless asked", !y.includes('"--demo"'));
    check("it serves once the stack is set up", y.includes('      - "--"\n      - "iosuite"\n      - "serve"\n'));
  }],
  "the data in a folder of the server": [answers({data: "/srv/io suite/", apps: {iobackup: true}, reach: {https: "caddy", domain: "home.example.com"}}), (y, s) => {
    check("no Docker volumes at all", !/^volumes:/m.test(y) && !/^\s+- [a-z-]+:\//m.test(y));
    for (const m of ["db:/var/lib/mysql", "data:/data", "backups:/backups", "caddy/data:/data", "caddy/config:/config"])
      check("bind mounted: " + m, y.includes('- "/srv/io suite/' + m + '"'));
    const prep = "sudo mkdir -p '/srv/io suite/data' '/srv/io suite/backups' && sudo chown 1000:1000 '/srv/io suite/data' '/srv/io suite/backups'";
    check("the folders the suite writes to are made its own, in the file", y.includes("#   " + prep));
    check("and in the steps", C.build(s).steps.some(st => (st.code || "").startsWith(prep)));
    check("ioBackup is told its folder", has(y, '- "--set=iobackup.BACKUP_DIR=/backups"'));
  }],
  "with demo data": [answers({demo: true}), y => {
    check("the setup adds the demo", y.includes('      - "--proxies="\n      - "--demo"\n      - "--"\n'));
  }],
  "everything, with the admin tools": [answers({apps: {iodns: true, iobackup: true}, iobackup: {folder: "/srv/backups"}, iocontact: {ldap: true}}), y => {
    check("ldap is published", y.includes('- "389:3890"'));
    check("the backups folder is mounted", y.includes('- "/srv/backups:/backups"'));
    check("the backups folder given is not made in the data folder", !y.includes("/opt/iosuite/backups"));
    check("every app is in the container", has(y, 'APPS: "' + C.APPS.map(a => a.key).join(",") + '"'));
  }],
  "one app, its address given": [answers({apps: Object.assign(none(), {iocalendar: true}), reach: {address: "192.168.1.10"}}), (y, s, out) => {
    check("no Docker volumes: the database is in the data folder", !/^volumes:/m.test(y) && has(y, '- "/opt/iosuite/db:/var/lib/mysql"'));
    check("only that app", has(y, 'APPS: "iocalendar"') && !y.includes("/library/photos"));
    check("the plain image", has(y, "image: " + C.IMAGE + ":latest"));
    check("its address is stored", has(y, '- "--set=suite.PUBLIC_URL=http://192.168.1.10"') && !y.includes("SYNC_URL"));
    check("the three addresses are given", out.addresses.apps.iocalendar === "http://192.168.1.10/calendar/" && out.addresses.sync === "http://192.168.1.10:8443" && out.addresses.mcp === "http://192.168.1.10:8444");
    check("no network of its own without a proxy", !has(y, "networks:"));
  }],
  "other ports on the server": [answers({reach: {address: "nas.lan", port: "8080", syncPort: "9443"}}), y => {
    check("the pages' port", y.includes('- "8080:80"') && has(y, '- "--set=suite.PUBLIC_URL=http://nas.lan:8080"'));
    check("the program listens on the devices' port people type", y.includes('- "9443:9443"') && has(y, 'SYNC_PORT: "9443"'));
    check("the MCP port is left as it is", y.includes('- "8444:8444"') && !y.includes("MCP_PORT"));
  }],
  "caddy, one name": [answers({reach: {https: "caddy", domain: "Home.Example.com"}}), y => {
    check("caddy passes each kind of traffic on", y.includes("      home.example.com {\n          reverse_proxy iosuite:80\n      }\n      home.example.com:8443 {\n          reverse_proxy iosuite:8443\n      }\n      home.example.com:8444 {\n          reverse_proxy iosuite:8444\n      }\n"));
    check("only caddy is published", (y.match(/^ {6}- "[\d.:/udp]+"/gm) || []).map(l => l.trim()).join() === '- "80:80",- "443:443",- "443:443/udp",- "8443:8443",- "8444:8444"');
    check("caddy is believed", has(y, '- "--proxies=10.186.30.11"') && y.includes("ipv4_address: 10.186.30.11"));
    check("the three addresses are stored", has(y, '- "--set=suite.PUBLIC_URL=https://home.example.com"') && has(y, '- "--set=suite.SYNC_URL=https://home.example.com:8443"') && has(y, '- "--set=suite.MCP_URL=https://home.example.com:8444"'));
    check("no name per app", !y.includes("COOKIE_DOMAIN") && !y.includes("iocalendar.PUBLIC_URL"));
  }],
  "caddy, names for devices and for each app, its own certificates": [answers({reach: {https: "caddy", domain: "home.example.com", devices: "names", own: true, internalCert: true, names: {iopix: "pix"}}}), y => {
    check("devices and MCP have their names", y.includes("      sync.example.com {\n          tls internal\n          reverse_proxy iosuite:8443\n      }\n      mcp.example.com {\n          tls internal\n          reverse_proxy iosuite:8444\n      }\n"));
    check("an app's name: its pages", y.includes("      pix.example.com {\n          tls internal\n          reverse_proxy /mcp* iosuite:8444\n          reverse_proxy iosuite:80\n      }"));
    check("an app's name: its paths for devices", y.includes("      calendar.example.com {\n          tls internal\n          @devices path /dav /dav/* /.well-known/* /ics/*\n          reverse_proxy @devices iosuite:8443\n          reverse_proxy /mcp* iosuite:8444\n          reverse_proxy iosuite:80\n      }"));
    check("the start page is the suite's own name", !y.includes("      home.example.com {\n          tls internal\n          @devices"));
    check("one sign-in", has(y, '- "--set=suite.COOKIE_DOMAIN=example.com"'));
    check("the names are stored", has(y, '- "--set=iopix.PUBLIC_URL=https://pix.example.com"') && has(y, '- "--set=suite.SYNC_URL=https://sync.example.com"') && has(y, '- "--set=suite.MCP_URL=https://mcp.example.com"'));
    check("only port 443 is needed", !y.includes('- "8443:8443"'));
  }],
  "the names under another domain": [answers({reach: {https: "caddy", domain: "example.com", devices: "names", zone: "home.example.com", syncName: "Devices"}}), y => {
    check("the domain typed", has(y, '- "--set=suite.SYNC_URL=https://devices.home.example.com"') && has(y, '- "--set=suite.MCP_URL=https://mcp.home.example.com"'));
  }],
  "own proxy on this server": [answers({reach: {https: "proxy", domain: "home.example.com"}}), (y, s, out) => {
    check("open on this machine only, clear of the proxy's ports", y.includes('- "127.0.0.1:8630:80"') && y.includes('- "127.0.0.1:8631:8443"') && y.includes('- "127.0.0.1:8632:8444"'));
    check("the gateway is believed", has(y, '- "--proxies=10.186.30.1"'));
    check("the proxy's sites are given", out.steps.some(t => t.code && t.code.includes("home.example.com {\n    reverse_proxy 127.0.0.1:8630\n}\nhome.example.com:8443 {\n    reverse_proxy 127.0.0.1:8631\n}")));
    check("no caddy in the stack", !y.includes("caddy"));
  }],
  "own proxy elsewhere, names on port 443": [answers({reach: {https: "proxy", domain: "home.example.com", devices: "names", own: true, proxyAt: "other", proxyIp: "192.168.1.2", address: "192.168.1.10"}}), (y, s, out) => {
    check("open on the network", y.includes('- "80:80"') && y.includes('- "8443:8443"'));
    check("the proxy's address is believed", has(y, '- "--proxies=192.168.1.2"'));
    check("upstreams at the server's address", out.steps.some(t => t.code && t.code.includes("sync.example.com {\n    reverse_proxy 192.168.1.10:8443\n}") && t.code.includes("    reverse_proxy @devices 192.168.1.10:8443")));
  }],
  "ioPix in a container of its own": [answers({iopix: {apart: true}, reach: {address: "192.168.1.10"}}), (y, s) => {
    const [first, second] = y.split(/^  iopix:.*$/m);
    check("two containers", !!second && has(first, 'APPS: "' + C.APPS.filter(a => s.apps[a.key] && a.key !== "iopix").map(a => a.key).join(",") + '"') && has(second, 'APPS: "iopix"'));
    check("the photos are ioPix's", !first.includes(":/library/photos\"") && has(second, '- "/srv/photos:/library/photos"'));
    check("only ioPix has the AI packages", has(first, "image: " + C.IMAGE + ":latest") && has(second, "image: " + C.IMAGE + ":ai"));
    check("the first one says what the stack file says", has(first, '- "--set=iopix.PHOTOS_ROOT=/library/photos"') && !second.includes("--set="));
    check("ioPix waits for it, and makes its own database", second.includes("      iosuite:\n        condition: service_healthy") && second.includes('"--db-admin=root"') && has(second, "DB_ADMIN_PASSWORD:"));
    check("nothing of ioPix is published", !has(second, "ports:"));
    check("a log of its own", has(second, 'LOG_FILE: "/data/iosuite-pix.log"') && has(second, 'INTERNAL_URL: "http://iopix"'));
  }],
  "ioPix alone has nothing to be apart from": [answers({apps: Object.assign(none(), {iopix: true}), iopix: {apart: true, ai: false}}), y => {
    check("one container", !/^  iopix:/m.test(y) && has(y, 'APPS: "iopix"') && has(y, "image: " + C.IMAGE + ":latest") && !y.includes("AUTO_MODELS"));
  }],
  "a database server that exists, made by an administrator": [answers({db: {mode: "existing", host: "host.docker.internal", port: "3307", adminPassword: "r$t", user: "fam", name: "famsuite"}}), y => {
    check("no database container", !has(y, "db:") && !y.includes("mariadb:11"));
    check("this machine is reachable", (y.match(/host\.docker\.internal:host-gateway/g) || []).length === 1);
    check("the administrator is used", has(y, '- "--db-admin=root"') && has(y, 'DB_ADMIN_PASSWORD: "r$$t"'));
    check("the suite's login", has(y, 'IOSUITE_DB_USER: "fam"') && has(y, 'IOSUITE_DB_NAME: "famsuite"') && has(y, 'IOSUITE_DB_PORT: "3307"'));
  }],
  "a database server that exists, databases made by hand": [answers({db: {mode: "existing", create: "manual", host: "db.lan", password: "it's"}}), (y, s, out) => {
    check("no administrator in the file", !y.includes("--db-admin") && !y.includes("DB_ADMIN_PASSWORD"));
    const sql = (out.steps.find(t => t.title === "Create the databases") || {}).code || "";
    check("the sql is given, quoted", sql.includes("CREATE USER IF NOT EXISTS 'iosuite'@'%' IDENTIFIED BY 'it''s';") && sql.includes("GRANT ALL PRIVILEGES ON `iomoney`.* TO 'iosuite'@'%';") && sql.includes("CREATE DATABASE IF NOT EXISTS `iosuite` "));
  }],
  "a pinned version and another network": [answers({tag: "v4.0.0", subnet: "172.29.7.0/24", iopix: {apart: true}, reach: {https: "caddy", domain: "home.example.com"}}), y => {
    check("the version on every image of the suite", !y.includes(":latest") && !y.includes(":ai") && has(y, "image: " + C.IMAGE + ":v4.0.0") && has(y, "image: " + C.IMAGE + ":v4.0.0-ai"));
    check("the network", y.includes("subnet: 172.29.7.0/24") && has(y, '- "--proxies=172.29.7.11"'));
  }],
};

const docker = process.env.CHECK_COMPOSE_DOCKER !== "0" && cp.spawnSync("docker", ["compose", "version"], {stdio: "ignore"}).status === 0;
if (!docker && process.env.CHECK_COMPOSE_DOCKER === "1") failures.push("docker compose is not on this machine");
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "check-compose-"));
let files = 0;
for (const [name, [s, test, expected]] of Object.entries(CASES)) {
  const before = failures.length;
  const out = C.build(s, "2026-01-01");
  const wrong = out.problems.map(p => p.at);
  check("nothing is missing", JSON.stringify(wrong) === JSON.stringify(expected || []), JSON.stringify(out.problems));
  check("no tabs, no trailing spaces", !/\t| +$/m.test(out.yaml));
  const back = C.answersIn(out.yaml, pw, "UTC");
  check("the answers come back from the file", back && JSON.stringify(back) === JSON.stringify(s));
  check("the file made from them is the same", back && C.build(back, "2026-01-01").yaml === out.yaml);
  test(out.yaml, s, out);
  if (docker) {
    const f = path.join(tmp, "docker-compose.yml");
    fs.writeFileSync(f, out.yaml);
    const r = cp.spawnSync("docker", ["compose", "-f", f, "config", "--format", "json"], {encoding: "utf8", env: Object.assign({}, process.env, {ADMIN_PASSWORD: "", DB_PASSWORD: ""})});
    check("docker compose reads it", r.status === 0, (r.stderr || "").trim().split("\n").pop());
    if (r.status === 0) {
      const cfg = JSON.parse(r.stdout);
      const suite = cfg.services.iosuite, pix = cfg.services.iopix;
      check("the suite's container sets the stack up, then serves", !!suite && suite.command.slice(0, 2).join(" ") === "iosuite stack" && suite.command.slice(-3).join(" ") === "-- iosuite serve");
      check("no service that stops when its work is done", Object.keys(cfg.services).every(k => cfg.services[k].restart === "unless-stopped"));
      check("the admin's password reaches the setup as typed", !!suite && suite.environment.ADMIN_PASSWORD === s.admin.password.replace(/\$/g, "$$$$"));  // config prints $ doubled again
      check("only that container holds the admin's password", !pix || !("ADMIN_PASSWORD" in pix.environment));
      check("a container for ioPix only when it runs apart", !!pix === C.apart(s));
      check("ioPix waits until the suite's container is healthy", !pix || ((pix.depends_on || {}).iosuite || {}).condition === "service_healthy");
      check("every app is in a container", C.APPS.filter(a => s.apps[a.key]).every(a => (suite.environment.APPS + "," + (pix ? pix.environment.APPS : "")).split(",").includes(a.key)));
    }
    files++;
  }
  failures.slice(before).forEach((f, i) => { failures[before + i] = name + " — " + f; });
}
fs.rmSync(tmp, {recursive: true, force: true});

/* what must be refused */
const REFUSED = [
  [{apps: none()}, "apps"], [{admin: {password: "short"}}, "admin.password"], [{iopix: {photos: "photos"}}, "iopix.photos"],
  [{db: {mode: "existing", host: "localhost"}}, "db.host"], [{db: {mode: "existing", host: "db.lan", user: "a b"}}, "db.user"],
  [{db: {mode: "existing", host: "db.lan", adminPassword: "x", name: "io-suite"}}, "db.name"],
  [{reach: {https: "caddy"}}, "reach.domain"], [{reach: {https: "caddy", domain: "home"}}, "reach.domain"],
  [{reach: {address: "http://nas"}}, "reach.address"], [{reach: {port: "http"}}, "reach.port"], [{reach: {syncPort: "80"}}, "reach.syncPort"],
  [{reach: {https: "caddy", domain: "home.example.com", own: true, names: {ionote: "calendar"}}}, "reach.names.iocalendar"],
  [{reach: {https: "caddy", domain: "home.example.com", own: true, names: {ionote: "home"}}}, "reach.names.ionote"],
  [{reach: {https: "caddy", domain: "home.example.com", devices: "names", mcpName: "sync"}}, "reach.mcpName"],
  [{reach: {https: "caddy", domain: "home.example.com", devices: "names", zone: "example"}}, "reach.zone"],
  [{reach: {https: "proxy", domain: "home.example.com", proxyAt: "other"}}, "reach.proxyIp"], [{subnet: "10.0.0.0/8"}, "subnet"], [{tz: "Brussels time"}, "tz"], [{data: "iosuite"}, "data"],
];
for (const [change, at] of REFUSED) {
  check("refused: " + JSON.stringify(change), C.problems(answers(change)).some(p => p.at === at), "no problem at " + at);
}

console.log(`checked ${Object.keys(CASES).length} stack files and ${REFUSED.length} wrong answers` + (docker ? `; docker compose read ${files} files` : "; docker compose is not here, so the files were not read by it"));
if (failures.length) {
  console.log(`\n${failures.length} wrong:`);
  failures.forEach(f => console.log("  - " + f));
  process.exit(1);
}
console.log("every file is what its answers call for");

/* The Docker Compose file builder of iosuite.iothing.net/compose/: build(answers) writes the stack file and what to
   do with it. Nothing here touches the page or the network, so tools/check-compose.js runs the same code under Node.

   The stack it writes: one container of the suite's one image that runs the apps that were picked (a second one for
   ioPix when it is to run apart), and MariaDB (or a server that exists). Before it serves, at every start, the
   container sets the stack up (`iosuite stack … -- iosuite serve`): it makes the databases, the first admin, and
   writes what this file says about the suite (its addresses, the reverse proxy, the photos folder) into the Shared
   ioSuite database. No service of its own for that: a container that stops when its work is done has Dockge and
   Portainer show the whole stack as exited. So the file is the whole install: nothing to edit, nothing to click
   afterwards.

   A container listens on three ports: the pages (80), phones, native apps and devices (8443), MCP clients (8444).
   The apps, their folders at the suite's address and their paths for devices come from the apps' manifests
   (<app>/app.json); tools/check-facts.py holds the list below to them. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ioCompose = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // >>> suite: apps (from the apps' app.json, in their order)
  var APPS = [
    {key:"iostart", name:"ioStart", folder:"", sub:"home", what:"start page", sync:["/dav/"]},
    {key:"iopix", name:"ioPix", folder:"pix", sub:"photos", what:"photos"},
    {key:"ionote", name:"ioNote", folder:"notes", sub:"notes", what:"notes"},
    {key:"iocalendar", name:"ioCalendar", folder:"calendar", sub:"calendar", what:"calendar", sync:["/dav","/.well-known/","/ics/"]},
    {key:"iotask", name:"ioTask", folder:"tasks", sub:"tasks", what:"tasks", sync:["/dav","/.well-known/"]},
    {key:"iorecipe", name:"ioRecipe", folder:"recipes", sub:"recipes", what:"recipes"},
    {key:"iothings", name:"ioThings", folder:"things", sub:"things", what:"inventory"},
    {key:"iomoney", name:"ioMoney", folder:"money", sub:"money", what:"finances"},
    {key:"iodocs", name:"ioDocs", folder:"docs", sub:"docs", what:"papers"},
    {key:"iocontact", name:"ioContact", folder:"contacts", sub:"contacts", what:"contacts", sync:["/dav","/.well-known/","/cal/"]},
    {key:"iohealth", name:"ioHealth", folder:"health", sub:"health", what:"health", sync:["/v1/"]},
    {key:"iodns", name:"ioDNS", folder:"dns", sub:"dns", what:"DNS records", tool:true},
    {key:"iobackup", name:"ioBackup", folder:"backup", sub:"backup", what:"backups", tool:true}
  ];
  // <<< suite: apps
  var IMAGE = "ghcr.io/avandeputte/iosuite2";
  var SITE = "https://iosuite.iothing.net/compose/";
  var MARK = "# answers: ";  // the line the page reads a file back from
  var DOORS = {web: "80", sync: "8443", mcp: "8444"};  // what a container listens on, and the ports people use
  var MODELS = "siglip2,yolox,geonames";

  /* ---- the answers ---- */
  function defaults(password, tz) {
    var apps = {}, names = {};
    APPS.forEach(function (a) { apps[a.key] = !a.tool; if (a.folder) names[a.key] = a.sub; });
    return {
      apps: apps,
      db: {mode: "bundled", rootPassword: password(), host: "", port: "3306", create: "admin", adminUser: "root", adminPassword: "",
           name: "iosuite", user: "iosuite", password: password()},
      admin: {user: "admin", password: ""},
      tz: tz || "Europe/Brussels",
      data: "/opt/iosuite",
      reach: {https: "none", address: "", domain: "", devices: "ports", syncName: "sync", mcpName: "mcp", internalCert: false,
              proxyAt: "here", proxyIp: "", own: false, zone: "", names: names, port: "", syncPort: "", mcpPort: ""},
      iopix: {photos: "", ai: true, apart: false},
      iocontact: {ldap: false, ldapPort: "389"},
      iobackup: {folder: ""},
      demo: false,
      tag: "latest",
      subnet: "10.186.30.0/24"
    };
  }

  /* answers read back from a file may be older or hand-edited: only what defaults() knows is taken, with its type */
  function merge(base, given) {
    Object.keys(base).forEach(function (k) {
      var b = base[k], g = given ? given[k] : undefined;
      if (g === undefined || g === null) return;
      if (b !== null && typeof b === "object") { if (typeof g === "object") merge(b, g); }
      else if (typeof b === "boolean") base[k] = g === true;
      else if (typeof g === "string" || typeof g === "number") base[k] = String(g);
    });
    return base;
  }

  function b64(s) {
    if (typeof btoa === "function") return btoa(unescape(encodeURIComponent(s)));
    return Buffer.from(s, "utf8").toString("base64");
  }
  function unb64(s) {
    if (typeof atob === "function") return decodeURIComponent(escape(atob(s)));
    return Buffer.from(s, "base64").toString("utf8");
  }

  /* the answers a file made here holds, or null */
  function answersIn(text, password, tz) {
    var m = /^# answers: ([A-Za-z0-9+/=]+)\s*$/m.exec(text || "");
    if (!m) return null;
    try { return merge(defaults(password, tz), JSON.parse(unb64(m[1]))); } catch (e) { return null; }
  }

  /* ---- what the answers come to ---- */
  var IDENT = /^[A-Za-z0-9_]+$/;
  var HOSTNAME = /^(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$/;
  var IPV4 = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/;
  var LABEL = /^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/;
  var FULL = /^(\/|[A-Za-z]:[\\/])/;  // a full path on the server
  var SUBNET = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.0\/24$/;

  function port(v) { return /^\d{1,5}$/.test(v) && +v >= 1 && +v <= 65535; }
  function picked(s) { return APPS.filter(function (a) { return s.apps[a.key]; }); }
  function apart(s) { return !!(s.apps.iopix && s.iopix.apart && picked(s).length > 1); }  // ioPix in a container of its own
  function secure(s) { return s.reach.https !== "none"; }
  function proxyHere(s) { return s.reach.https === "proxy" && s.reach.proxyAt === "here"; }
  function low(v) { return String(v || "").trim().toLowerCase(); }
  function domain(s) { return low(s.reach.domain); }
  /* the domain the other names are under: the one typed, else the suite's name without its first part */
  function zone(s) {
    var z = low(s.reach.zone), d = domain(s).split(".");
    return z || (d.length > 2 ? d.slice(1).join(".") : d.join("."));
  }
  /* the apps with a name of their own beside their folder (calendar.example.com) */
  function named(s) { return secure(s) && s.reach.own ? picked(s).filter(function (a) { return a.folder; }) : []; }
  /* the three ports on the server: those people use, unless a reverse proxy on this same server has them */
  function hostPorts(s) {
    var r = s.reach, here = proxyHere(s);
    return {web: r.port.trim() || (here ? "8630" : DOORS.web), sync: r.syncPort.trim() || (here ? "8631" : DOORS.sync), mcp: r.mcpPort.trim() || (here ? "8632" : DOORS.mcp)};
  }
  function under(s, sub) { return s.data.trim().replace(/[\\/]+$/, "") + "/" + sub; }  // a folder of the stack's data folder
  /* the folders of the data folder that the suite writes to as uid 1000 (MariaDB and Caddy see to their own) */
  function userFolders(s) {
    var out = [under(s, "data")];
    if (s.apps.iobackup && !s.iobackup.folder.trim()) out.push(under(s, "backups"));
    return out;
  }
  function shq(p) { return /^[A-Za-z0-9_\/.:\\-]+$/.test(p) ? p : "'" + p.replace(/'/g, "'\\''") + "'"; }
  /* the one command to run before the first start: the folders the suite writes to, its own */
  function prepare(s) {
    var f = userFolders(s).map(shq).join(" ");
    return "sudo mkdir -p " + f + " && sudo chown 1000:1000 " + f;
  }
  function loopback(h) { return /^(localhost|127(\.\d+){3}|::1|\[::1\])$/i.test(h); }
  function image(s, ai) {
    var t = s.tag.trim() || "latest";
    return IMAGE + ":" + (ai ? (t === "latest" ? "ai" : t + "-ai") : t);
  }

  /* [{at: the field (its data-k), text}] : what is still missing or wrong; empty when the file can be used */
  function problems(s) {
    var out = [], sel = picked(s), r = s.reach, d = s.db;
    function bad(at, text) { out.push({at: at, text: text}); }
    if (!sel.length) bad("apps", "Pick at least one app.");
    if (d.mode === "existing") {
      if (!d.host.trim()) bad("db.host", "The database server: its name or address.");
      else if (loopback(d.host.trim())) bad("db.host", "Inside a container, " + d.host.trim() + " is the container itself. For a database on this same machine, enter host.docker.internal; otherwise the server's name or address on your network.");
      else if (!HOSTNAME.test(d.host.trim()) && !IPV4.test(d.host.trim())) bad("db.host", "The database server is a name (db.example.lan) or an address (192.168.1.5), without http:// or a port.");
      if (!port(d.port)) bad("db.port", "The database server's port is a number (3306).");
      if (d.create === "admin") {
        if (!d.adminUser.trim()) bad("db.adminUser", "The database administrator's name (root, or an account that may create databases and users).");
        if (!d.adminPassword) bad("db.adminPassword", "The database administrator's password.");
      }
      if (!IDENT.test(d.name)) bad("db.name", "The Shared ioSuite database's name: letters, digits and _ only.");
      if (!IDENT.test(d.user)) bad("db.user", "The suite's database login: letters, digits and _ only.");
      if (!d.password) bad("db.password", "A password for the suite's database login.");
    }
    var name = s.admin.user.trim();
    if (!name || name.length > 64) bad("admin.user", "A name for the first admin (up to 64 characters).");
    if (s.admin.password.length < 8) bad("admin.password", "A password of 8 characters or more for the admin.");
    if (!/^[A-Za-z0-9_+\-]+(\/[A-Za-z0-9_+\-]+)*$/.test(s.tz.trim())) bad("tz", "A time zone such as Europe/Brussels or America/New_York.");
    if (!secure(s)) {
      var addr = r.address.trim();
      if (addr && !HOSTNAME.test(addr) && !IPV4.test(addr)) bad("reach.address", "The server's name or address on your network (192.168.1.10 or nas.lan), without http:// or a port.");
    } else {
      var dom = domain(s);
      if (!dom) bad("reach.domain", "The name the suite is reached at (home.example.com).");
      else if (!HOSTNAME.test(dom) || dom.indexOf(".") < 0) bad("reach.domain", "A name such as home.example.com, without https:// or a path.");
      var z = low(r.zone), seen = {};
      if (z && (!HOSTNAME.test(z) || z.indexOf(".") < 0)) bad("reach.zone", "The domain the other names are under, such as example.com.");
      if (dom) seen[dom] = "the suite";
      function another(at, label, who) {
        var n = low(label), full = n + "." + (zone(s) || "example.com");
        if (!LABEL.test(n)) bad(at, who + "'s name: letters, digits and - only.");
        else if (seen[full]) bad(at, who + " and " + seen[full] + " cannot both be " + full + ".");
        else seen[full] = who;
      }
      if (r.devices === "names") {
        another("reach.syncName", r.syncName, "The address for devices");
        another("reach.mcpName", r.mcpName, "The address for MCP");
      }
      named(s).forEach(function (a) { another("reach.names." + a.key, r.names[a.key], a.name); });
      if (r.https === "proxy" && r.proxyAt === "other" && !IPV4.test(r.proxyIp.trim())) bad("reach.proxyIp", "The address the reverse proxy connects from (192.168.1.2).");
      if (r.https === "proxy" && r.proxyAt === "other" && r.address.trim() && !HOSTNAME.test(r.address.trim()) && !IPV4.test(r.address.trim())) bad("reach.address", "This server's name or address, as the proxy reaches it (192.168.1.10).");
    }
    if (r.https !== "caddy") {
      var hp = hostPorts(s), taken = {};
      [["port", "web", "the pages"], ["syncPort", "sync", "devices"], ["mcpPort", "mcp", "MCP"]].forEach(function (p) {
        var v = hp[p[1]];
        if (!port(v)) bad("reach." + p[0], "The port for " + p[2] + " is a number (" + DOORS[p[1]] + ").");
        else if (taken[v]) bad("reach." + p[0], "The ports for " + taken[v] + " and " + p[2] + " cannot both be " + v + ".");
        else taken[v] = p[2];
      });
    }
    if (s.apps.iopix && !FULL.test(s.iopix.photos.trim())) bad("iopix.photos", "ioPix: the folder with the photos on this server, as a full path (/srv/photos).");
    if (s.apps.iocontact && s.iocontact.ldap && !port(s.iocontact.ldapPort)) bad("iocontact.ldapPort", "ioContact: the LDAP port is a number (389).");
    if (!FULL.test(s.data.trim())) bad("data", "The folder for the stack's data, as a full path on this server (/opt/iosuite).");
    if (s.apps.iobackup && s.iobackup.folder.trim() && !FULL.test(s.iobackup.folder.trim())) bad("iobackup.folder", "ioBackup: the backups folder as a full path (/srv/backups), or empty for the stack's data folder.");
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(s.tag.trim())) bad("tag", "The version is latest, or a release such as v4.0.0.");
    var m = SUBNET.exec(s.subnet.trim());
    if (!m || +m[1] > 255 || +m[2] > 255 || +m[3] > 255) bad("subnet", "The stack's own network is written like 10.186.30.0/24.");
    return out;
  }

  /* ---- where everything is ---- */
  function net(s) {
    var m = SUBNET.exec(s.subnet.trim()) || [0, 10, 186, 30];
    var base = m[1] + "." + m[2] + "." + m[3] + ".";
    return {subnet: base + "0/24", range: base + "128/25", gateway: base + "1", caddy: base + "11"};
  }

  /* the addresses people and devices use: {web, sync, mcp: the suite's three, "" when not known ahead of time;
     apps: {key: its folder at the suite's address}; own: {key: its own name, for the apps that have one}} */
  function addresses(s) {
    var r = s.reach, out = {web: "", sync: "", mcp: "", apps: {}, own: {}};
    if (!secure(s)) {
      var addr = r.address.trim(), hp = hostPorts(s);
      if (addr) {
        out.web = "http://" + addr + (hp.web === "80" ? "" : ":" + hp.web);
        out.sync = "http://" + addr + ":" + hp.sync;
        out.mcp = "http://" + addr + ":" + hp.mcp;
      }
    } else if (domain(s)) {
      out.web = "https://" + domain(s);
      if (r.devices === "names") {
        out.sync = "https://" + low(r.syncName) + "." + zone(s);
        out.mcp = "https://" + low(r.mcpName) + "." + zone(s);
      } else {
        out.sync = out.web + ":" + DOORS.sync;
        out.mcp = out.web + ":" + DOORS.mcp;
      }
      named(s).forEach(function (a) { out.own[a.key] = "https://" + (low(r.names[a.key]) || a.sub) + "." + zone(s); });
    }
    picked(s).forEach(function (a) { out.apps[a.key] = !out.web ? "" : out.web + "/" + (a.folder ? a.folder + "/" : ""); });
    return out;
  }

  /* the addresses the suite believes a reverse proxy's headers from */
  function proxies(s) {
    var n = net(s), r = s.reach;
    if (r.https === "caddy") return [n.caddy];
    if (r.https === "proxy") return [r.proxyAt === "here" ? n.gateway : r.proxyIp.trim()].filter(Boolean);  // a proxy on this server comes in through the stack's gateway
    return [];
  }

  /* what the stack file says about the suite, kept in the Shared ioSuite database: [[APP.NAME, value]]. Only what
     is not the default: a setting an earlier file said and this one does not is put back by `iosuite stack`. */
  function settings(s) {
    var a = addresses(s), sec = secure(s), out = [];
    out.push(["suite.PUBLIC_URL", a.web], ["suite.SYNC_URL", sec ? a.sync : ""], ["suite.MCP_URL", sec ? a.mcp : ""],
             ["suite.COOKIE_DOMAIN", named(s).length ? zone(s) : ""]);
    named(s).forEach(function (app) { out.push([app.key + ".PUBLIC_URL", a.own[app.key]]); });
    if (s.apps.iopix) out.push(["iopix.PHOTOS_ROOT", "/library/photos"], ["iopix.DIGIKAM_CHECK", "none"],  // a container cannot see whether digiKam is open
                               ["iopix.AUTO_MODELS", s.iopix.ai ? MODELS : ""]);
    if (s.apps.iobackup) out.push(["iobackup.BACKUP_DIR", "/backups"]);
    return out.filter(function (kv) { return kv[1]; });
  }

  function hostOf(url) { return url.replace(/^https?:\/\//, ""); }
  /* Caddy's matcher for an app's device paths: /dav is the path itself and what is under it, /ics/ what is under it */
  function devicePaths(app) {
    var out = [];
    (app.sync || []).forEach(function (p) { if (p.slice(-1) === "/") out.push(p + "*"); else out.push(p, p + "/*"); });
    return out;
  }
  /* the sites of a Caddy in front of the suite; up(door) is where that door's traffic goes */
  function caddyfile(s, up) {
    var r = s.reach, a = addresses(s), lines = [];
    var tls = r.https === "caddy" && r.internalCert ? ["    tls internal"] : [];
    function site(url, body) { lines = lines.concat([hostOf(url) + " {"], tls, body, ["}"]); }
    site(a.web, ["    reverse_proxy " + up("web")]);
    site(a.sync, ["    reverse_proxy " + up("sync")]);
    site(a.mcp, ["    reverse_proxy " + up("mcp")]);
    named(s).forEach(function (app) {
      var body = [], paths = devicePaths(app);
      if (paths.length) body.push("    @devices path " + paths.join(" "), "    reverse_proxy @devices " + up("sync"));
      body.push("    reverse_proxy /mcp* " + up("mcp"), "    reverse_proxy " + up("web"));
      site(a.own[app.key], body);
    });
    return lines;
  }

  /* ---- YAML ---- */
  function q(v) { return JSON.stringify(String(v)).replace(/\$/g, "$$$$"); }   // a quoted scalar; $ doubled so compose leaves it alone
  function sqlq(v) { return "'" + String(v).replace(/\\/g, "\\\\").replace(/'/g, "''") + "'"; }

  function build(s, when) {
    var sel = picked(s), r = s.reach, d = s.db, n = net(s), two = apart(s), hp = hostPorts(s);
    var urls = addresses(s), trusted = proxies(s), bundled = d.mode !== "existing";
    var dbHost = bundled ? "db" : d.host.trim(), dbPort = bundled ? "3306" : d.port;
    var dbName = bundled ? "iosuite" : d.name, dbUser = bundled ? "iosuite" : d.user;
    var admin = bundled ? "root" : (d.create === "admin" ? d.adminUser.trim() : "");
    var adminPassword = bundled ? d.rootPassword : d.adminPassword;
    var hostGateway = !bundled && /^host\.docker\.internal$/i.test(dbHost);
    var bind = proxyHere(s) ? "127.0.0.1:" : "";
    var main = sel.filter(function (a) { return !(two && a.key === "iopix"); });
    var photos = q(s.iopix.photos.trim() + ":/library/photos") + "   # the photos (read and write: ioPix keeps sidecar files beside them)";
    var data = q(under(s, "data") + ":/data") + "   # what the apps write on their own, and the log";
    var L = [];
    function add() { for (var i = 0; i < arguments.length; i++) L.push(arguments[i]); }

    add("# ioSuite in one Docker stack: " + sel.map(function (a) { return a.name; }).join(", ") + (bundled ? ", and MariaDB." : ", on the database server " + dbHost + "."),
        "# Made" + (when ? " on " + when : "") + " at " + SITE,
        "#",
        "#   docker compose up -d        # in the folder that holds this file; or paste it as a stack in Dockge or Portainer",
        "#",
        "# Nothing to edit. One container runs " + (sel.length === 1 ? "the app" : two ? "the apps, a second one ioPix" : "every app") + ". Before it serves, at every start, it makes the databases" + (admin ? "" : "' tables") + ",",
        "# the first admin and writes how the suite is reached into the Shared ioSuite database.",
        "# This file holds passwords: keep it private.",
        "# The data is in " + s.data.trim() + ". Before the first start:",
        "#   " + prepare(s) + "   # the suite writes as user 1000",
        "# To add or remove an app later, open this file on that page (Open a file), change the answers and start it again.",
        "",
        "name: iosuite",
        "",
        "x-suite: &suite",
        "  restart: unless-stopped",
        "  logging: &logging                    # what Docker keeps of a container's output: at most 3 files of 5 MB",
        "    driver: json-file",
        "    options: {max-size: 5m, max-file: \"3\"}");
    if (hostGateway) add("  extra_hosts: [\"host.docker.internal:host-gateway\"]   # the database server is this machine");
    add("",
        "x-env: &env                            # the machine's file of a container: where the Shared ioSuite database is. Every app's",
        "  TZ: " + q(s.tz.trim()) + "                 # own database is on the same server, under the same login",
        "  IOSUITE_DB_HOST: " + q(dbHost),
        "  IOSUITE_DB_PORT: " + q(dbPort),
        "  IOSUITE_DB_NAME: " + q(dbName),
        "  IOSUITE_DB_USER: " + q(dbUser),
        "  IOSUITE_DB_PASSWORD: " + q(d.password),
        "",
        "services:");

    if (bundled) {
      add("  db:",
          "    image: mariadb:11",
          "    container_name: iosuite-db",
          "    restart: unless-stopped",
          "    logging: *logging",
          "    environment:",
          "      MARIADB_ROOT_PASSWORD: " + q(d.rootPassword),
          "    volumes:",
          "      - " + q(under(s, "db") + ":/var/lib/mysql") + "   # the databases",
          "    healthcheck:",
          "      test: [\"CMD\", \"healthcheck.sh\", \"--connect\", \"--innodb_initialized\"]",
          "      interval: 10s",
          "      timeout: 5s",
          "      start_period: 30s",
          "      retries: 6",
          "");
    }

    /* the suite's container */
    var ports = [], vols = [data], env = [];
    if (r.https !== "caddy") {
      var plain = !secure(s);  // without a proxy the port asked for is the port people type: the program listens on it
      ports.push(q(bind + hp.web + ":" + DOORS.web) + "   # the pages");
      ports.push(q(bind + hp.sync + ":" + (plain ? hp.sync : DOORS.sync)) + "   # phones, native apps and devices: CalDAV, CardDAV, bookmark sync, ioHealth, widgets");
      ports.push(q(bind + hp.mcp + ":" + (plain ? hp.mcp : DOORS.mcp)) + "   # MCP clients");
      if (plain && hp.sync !== DOORS.sync) env.push("SYNC_PORT: " + q(hp.sync));
      if (plain && hp.mcp !== DOORS.mcp) env.push("MCP_PORT: " + q(hp.mcp));
    }
    if (s.apps.iocontact && s.iocontact.ldap) ports.push(q(s.iocontact.ldapPort + ":3890") + "   # ioContact's LDAP directory for mail apps (read-only)");
    if (s.apps.iopix && !two) vols.push(photos);
    if (s.apps.iobackup) vols.push(q((s.iobackup.folder.trim() || under(s, "backups")) + ":/backups") + "   # where a local destination keeps the backups");
    var cmd = ["iosuite", "stack"];
    if (admin) cmd.push("--db-admin=" + admin);
    settings(s).forEach(function (kv) { cmd.push("--set=" + kv[0] + "=" + kv[1]); });
    cmd.push("--proxies=" + trusted.join(","));
    if (s.demo) cmd.push("--demo");  // the made-up Calloway family's accounts, and every app fills itself at its first start
    cmd = cmd.concat(["--", "iosuite", "serve"]);

    add("  iosuite:                               # the suite: " + (main.length === sel.length && sel.length > 1 ? "every app picked" : main.map(function (a) { return a.name; }).join(", ")),
        "    <<: *suite",
        "    image: " + image(s, s.apps.iopix && !two && s.iopix.ai),
        "    container_name: iosuite");
    if (bundled) add("    depends_on:", "      db:", "        condition: service_healthy");
    if (ports.length) { add("    ports:"); ports.forEach(function (p) { add("      - " + p); }); }
    add("    volumes:");
    vols.forEach(function (v) { add("      - " + v); });
    add("    environment:", "      <<: *env",
        "      APPS: " + q(main.map(function (a) { return a.key; }).join(",")),
        "      INTERNAL_URL: \"http://iosuite\"       # where another container of the stack calls this one");
    env.forEach(function (e) { add("      " + e); });
    add("      ADMIN_USER: " + q(s.admin.user.trim()) + "               # the first admin: made when there is no account yet",
        "      ADMIN_PASSWORD: " + q(s.admin.password));
    if (admin) add("      DB_ADMIN_PASSWORD: " + q(adminPassword) + "   # the database administrator " + admin + ": creates the databases and the login that are missing");
    add("    # sets the stack up, then serves (no container of its own for that, so none is left stopped). What follows --set",
        "    # is kept in the Shared ioSuite database, where Settings shows it",
        "    command:");
    cmd.forEach(function (c) { add("      - " + q(c)); });
    if (two) add("    healthcheck:", "      interval: 10s                      # ioPix's container starts as soon as this one answers");
    add("");

    if (two) {
      add("  iopix:                                 # ioPix apart, so that its scans never slow the others. It is reached through",
          "    <<: *suite                           # the first container, at the same addresses: nothing of it is published",
          "    image: " + image(s, s.iopix.ai),
          "    container_name: iosuite-pix",
          "    depends_on:",
          "      iosuite:",
          "        condition: service_healthy       # the first container sets the stack up",
          "    volumes:",
          "      - " + data,
          "      - " + photos,
          "    environment:",
          "      <<: *env",
          "      APPS: \"iopix\"",
          "      INTERNAL_URL: \"http://iopix\"",
          "      LOG_FILE: \"/data/iosuite-pix.log\"");
      if (admin) add("      DB_ADMIN_PASSWORD: " + q(adminPassword) + "   # makes ioPix's database when it is missing");
      add("    command: [" + ["iosuite", "stack"].concat(admin ? ["--db-admin=" + admin] : [], ["--", "iosuite", "serve"]).map(q).join(", ") + "]",
          "");
    }

    if (r.https === "caddy") {
      var names = 1 + (r.devices === "names" ? 2 : 0) + named(s).length;
      add("  caddy:                                 # HTTPS: gets and renews the certificate" + (names > 1 ? "s" : "") + " by itself",
          "    image: caddy:2",
          "    container_name: iosuite-caddy",
          "    restart: unless-stopped",
          "    logging: *logging",
          "    ports:",
          "      - \"80:80\"",
          "      - \"443:443\"",
          "      - \"443:443/udp\"");
      if (r.devices !== "names") add("      - " + q(DOORS.sync + ":" + DOORS.sync) + "   # phones, native apps and devices", "      - " + q(DOORS.mcp + ":" + DOORS.mcp) + "   # MCP clients");
      add("    networks:",
          "      default:",
          "        ipv4_address: " + n.caddy + "      # the address the suite knows the proxy by",
          "    configs:",
          "      - source: caddyfile",
          "        target: /etc/caddy/Caddyfile",
          "    volumes:",
          "      - " + q(under(s, "caddy/data") + ":/data") + "   # the certificates",
          "      - " + q(under(s, "caddy/config") + ":/config"),
          "");
      add("configs:", "  caddyfile:", "    content: |");
      caddyfile(s, function (door) { return "iosuite:" + DOORS[door]; }).forEach(function (l) { add("      " + l.replace(/\$/g, "$$$$")); });
      add("");
    }

    if (trusted.length) {
      add("networks:",
          "  default:                               # a network of its own, so the proxy's address is known ahead of time",
          "    ipam:",
          "      config:",
          "        - subnet: " + n.subnet,
          "          ip_range: " + n.range + "    # what Docker hands out by itself, clear of the address set above",
          "          gateway: " + n.gateway,
          "");
    }
    add("# The answers this file was made from, for " + SITE + " to read back (Open a file):", MARK + b64(JSON.stringify(s)), "");

    return {yaml: L.join("\n"), steps: steps(s), problems: problems(s), addresses: urls};
  }

  /* ---- what to do with the file: [{title, text, code?, head?}] ---- */
  function steps(s) {
    var sel = picked(s), r = s.reach, d = s.db, urls = addresses(s), hp = hostPorts(s), out = [];
    var local = proxyHere(s), multi = (r.devices === "names" ? 2 : 0) + named(s).length > 0;

    if (d.mode === "existing" && d.create !== "admin") {
      var sql = ["CREATE USER IF NOT EXISTS '" + d.user + "'@'%' IDENTIFIED BY " + sqlq(d.password) + ";"];
      [d.name].concat(sel.map(function (a) { return a.key; })).forEach(function (name) {
        sql.push("CREATE DATABASE IF NOT EXISTS `" + name + "` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
                 "GRANT ALL PRIVILEGES ON `" + name + "`.* TO '" + d.user + "'@'%';");
      });
      sql.push("FLUSH PRIVILEGES;");
      out.push({title: "Create the databases", head: "sql, on " + (d.host.trim() || "the database server") + " as an administrator",
                text: "On the database server, once, before the first start: the Shared ioSuite database, a database per app, and the one login for them all. What exists already is left as it is.", code: sql.join("\n")});
    }

    var notes = [];
    if (d.mode === "existing") notes.push("The database server has to accept connections from this machine (its bind-address, its firewall).");
    if (s.apps.iopix) notes.push("ioPix runs as user 1000: the photos folder has to be readable by it, and writable for the sidecar files (chown -R 1000 on a new folder).");
    if (s.apps.iopix && s.iopix.ai) notes.push("The image with ioPix's AI packages is for Intel and AMD servers: on an ARM one (a Raspberry Pi), untick ioPix's search by content.");
    if (secure(s)) {
      var hosts = [urls.web].concat(r.devices === "names" ? [urls.sync, urls.mcp] : [], named(s).map(function (a) { return urls.own[a.key]; })).filter(Boolean).map(function (u) { return hostOf(u); });
      var ports = r.devices === "names" ? "80 and 443" : "80, 443, " + DOORS.sync + " and " + DOORS.mcp;
      if (r.https === "caddy" && !r.internalCert) notes.push("For the certificate" + (multi ? "s" : "") + ", " + (hosts.length === 1 ? hosts[0] + " has" : hosts.join(", ") + " have") + " to lead to this server from the internet (DNS), with ports " + ports + " open to it.");
      if (r.https === "caddy" && r.internalCert) notes.push((hosts.length === 1 ? hosts[0] + " has" : hosts.join(", ") + " have") + " to lead to this server on your network (DNS). Caddy signs the certificate" + (multi ? "s" : "") + " itself: browsers and phones warn until its root certificate is trusted on each device (docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt .).");
    }
    out.push({title: "Start it", head: "on the server",
              text: "Save the file as docker-compose.yml in a folder of its own, then start it there. The first start pulls the image and takes a minute or two." +
                    (notes.length ? " " + notes.join(" ") : ""),
              code: prepare(s) + "   # the folders the suite writes to, as user 1000\ndocker compose up -d\ndocker compose logs iosuite     # what was set up (its first lines, up to ok)"});

    if (r.https === "proxy") {
      var at = local ? "127.0.0.1" : (r.address.trim() || "<this server>");
      var lines = caddyfile(s, function (door) { return at + ":" + hp[door]; });
      out.push({title: "Point your reverse proxy at it", head: "caddyfile" + (local ? "" : ", on the proxy"),
                text: "One upstream for each kind of traffic, whatever the number of apps: the pages, phones and devices, MCP clients" +
                      (named(s).length ? "; an app's own name goes to the same three, its paths for devices to the devices' port" : "") + "." +
                      " For Caddy; the guide has the same for nginx (Running it › Reverse proxy and HTTPS), and a Cloudflare Tunnel takes the same upstreams." +
                      (local ? " The ports are open on this server only (127.0.0.1): the proxy is the one way in." : " The suite takes the visitor's address from " + (r.proxyIp.trim() || "the proxy") + " only."),
                code: lines.join("\n")});
    }

    var open = [], pad = function (t) { return (t + "                            ").slice(0, 28); };
    if (urls.web) {
      open.push(pad("The suite") + urls.web);
      sel.forEach(function (a) { if (a.folder) open.push(pad(a.name) + urls.apps[a.key] + (urls.own[a.key] ? "   and " + urls.own[a.key] : "")); });
      open.push(pad("Phones, apps and devices") + urls.sync, pad("AI assistants (MCP)") + urls.mcp);
    }
    var first = sel.filter(function (a) { return a.folder; }).slice(0, 2).map(function (a) { return "/" + a.folder + "/"; });
    var where = urls.web ? "" : " The suite is at http://<this server>" + (hp.web === "80" ? "" : ":" + hp.web) + (first.length ? ", each app in its folder (" + first.join(", ") + (sel.length > 3 ? " and so on" : "") + ")" : "") +
                               "; phones, native apps and devices use port " + hp.sync + ", MCP clients port " + hp.mcp + ".";
    out.push({title: "Sign in", head: "addresses",
              text: "Sign in as " + (s.admin.user.trim() || "the admin") + " with the password you chose: it is a suite admin, an admin of every app. " +
                    (s.demo ? "The demo family signs in as morgan, riley, ava or theo, password calloway (Morgan is a suite admin too)." : "Add the family under Settings › Security › People.") + where +
                    " Calendar, reminders and contacts accounts, the native apps and widgets use the address for devices, with an app password; each app's Settings › Apps and devices shows what to type." +
                    (s.apps.iocontact && s.iocontact.ldap ? " ioContact's LDAP directory is on port " + s.iocontact.ldapPort + "." : ""),
              code: open.join("\n")});

    out.push({title: "Later", head: "on the server",
              text: "Update by pulling the image. To add or remove an app, or change an answer, open your file on this page (Open a file), change it and start the new file the same way: the data stays in " + s.data.trim() + (d.mode === "existing" ? " and on your database server" : "") + "." +
                    (d.mode !== "existing" ? " To start over from nothing, stop the stack and empty " + under(s, "db") + "." : "") +
                    (d.mode === "existing" && d.create === "admin" ? " Once it has started, the administrator's password can be taken out of the file (DB_ADMIN_PASSWORD and --db-admin) until you add an app." : ""),
              code: "docker compose pull && docker compose up -d"});
    return out;
  }

  return {APPS: APPS, IMAGE: IMAGE, quoted: q, prepare: prepare, MARK: MARK, defaults: defaults, merge: merge, answersIn: answersIn, problems: problems, build: build,
          addresses: addresses, proxies: proxies, settings: settings, apart: apart, zone: zone, hostPorts: hostPorts, net: net};
});

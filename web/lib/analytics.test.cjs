const assert = require("node:assert/strict");
const { test } = require("node:test");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const ts = require("typescript");

// No browser or network: script insertion is recorded, never executed.
function harness(saved = new Map(), blockedStorage = false) {
  const scripts = [],
    cookies = [],
    listeners = new Map(),
    exports = {};
  const window = {
    location: new URL(
      "https://rushes.example/app/workspaces/private-workspace/projects/private-project?filename=secret.mov#private-note",
    ),
    addEventListener: (name, handler) => listeners.set(name, handler),
    removeEventListener: (name) => listeners.delete(name),
  };
  const document = {
    title: "Confidential film",
    referrer: "https://example.com/?email=private@example.com",
    createElement: (tag) => {
      assert.equal(tag, "script");
      const script = {
        remove() {
          const index = scripts.indexOf(script);
          if (index >= 0) scripts.splice(index, 1);
        },
      };
      return script;
    },
    head: { appendChild: (script) => scripts.push(script) },
    get cookie() {
      return "rushes_gtest123456_ga=sample; session=essential";
    },
    set cookie(value) {
      cookies.push(value);
    },
  };
  const localStorage = {
    getItem: (key) => {
      if (blockedStorage) throw Error("blocked");
      return saved.get(key) ?? null;
    },
    setItem: (key, value) => {
      if (blockedStorage) throw Error("blocked");
      saved.set(key, value);
    },
  };
  const source = ts.transpileModule(
    readFileSync(__dirname + "/analytics.ts", "utf8"),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2020,
      },
    },
  ).outputText;
  vm.runInNewContext(source, { exports, window, document, localStorage });
  const commands = () =>
    Array.from(window.rushesDataLayer || [], (args) => Array.from(args));
  return { api: exports, scripts, cookies, saved, window, listeners, commands };
}

test("missing, malformed and injection-shaped IDs never insert a tag", () => {
  for (const id of [
    undefined,
    "",
    "G-123",
    "G-test123456",
    "G-TEST123456&x=secret",
    "<script>",
  ]) {
    const h = harness();
    const controller = h.api.createAnalyticsController(id);
    controller.choose("accepted");
    h.api.track("export_started");
    assert.equal(controller.configured, false);
    assert.equal(h.scripts.length, 0);
    assert.equal(h.commands().length, 0);
  }
});
test("consent is denied until opt-in and loading uses denied-first configuration", () => {
  const h = harness();
  const controller = h.api.createAnalyticsController(" G-TEST123456 ");
  h.api.track("export_started");
  assert.equal(h.scripts.length, 0);
  assert.equal(h.commands().length, 0);
  controller.choose("declined");
  assert.equal(h.scripts.length, 0);
  controller.choose("accepted");
  assert.equal(h.scripts.length, 1);
  assert.equal(h.scripts[0].referrerPolicy, "no-referrer");
  assert.equal(h.commands()[0][0], "consent");
  assert.equal(h.commands()[0][1], "default");
  assert.equal(h.commands()[0][2].analytics_storage, "denied");
  const config = h.commands().find((command) => command[0] === "config")[2];
  assert.equal(config.send_page_view, false);
  assert.equal(config.allow_google_signals, false);
  assert.equal(config.allow_ad_personalization_signals, false);
});
test("only allowlisted events and fixed route metadata enter the adapter", () => {
  const h = harness();
  h.api.createAnalyticsController("G-TEST123456").choose("accepted");
  h.api.track("export_started", {
    filename: "secret.mov",
    user_id: "private-user",
  });
  h.api.track("private-user");
  const events = h.commands().filter((command) => command[0] === "event");
  assert.equal(events.length, 1);
  assert.equal(events[0][1], "export_started");
  assert.equal(events[0][2].page_location, "https://rushes.example/app");
  assert.equal(events[0][2].page_referrer, "");
  assert.equal(events[0][2].page_title, "RUSHES");
  assert.doesNotMatch(
    JSON.stringify(h.commands()),
    /secret\.mov|private-workspace|private-project|private-note|private-user|Confidential|private@example/,
  );
});
test("revocation drops queued events, removes the tag and only clears owned cookies", () => {
  const h = harness();
  const controller = h.api.createAnalyticsController("G-TEST123456");
  controller.choose("accepted");
  h.api.track("project_created");
  controller.choose("declined");
  assert.equal(h.window["ga-disable-G-TEST123456"], true);
  assert.equal(h.scripts.length, 0);
  assert.equal(
    h.commands().filter((command) => command[0] === "event").length,
    0,
  );
  const count = h.commands().length;
  h.api.track("export_started");
  assert.equal(h.commands().length, count);
  assert.ok(
    h.cookies.some((cookie) => cookie.startsWith("rushes_gtest123456_ga=")),
  );
  assert.ok(h.cookies.every((cookie) => !cookie.startsWith("session=")));
});
test("consent is scoped to the measurement ID, synchronizes revocation, and survives blocked storage safely", () => {
  const h = harness(
    new Map([["rushes.analytics.G-OTHER12345.v1", "accepted"]]),
  );
  const controller = h.api.createAnalyticsController("G-TEST123456");
  assert.equal(h.scripts.length, 0);
  controller.choose("accepted");
  h.listeners.get("storage")({
    key: "rushes.analytics.G-TEST123456.v1",
    newValue: "declined",
  });
  assert.equal(controller.choice, "declined");
  assert.equal(h.scripts.length, 0);
  controller.dispose();
  controller.choose("accepted");
  assert.equal(h.scripts.length, 0);
  const blocked = harness(new Map(), true);
  const blockedController =
    blocked.api.createAnalyticsController("G-TEST123456");
  assert.equal(blocked.scripts.length, 0);
  blockedController.choose("accepted");
  assert.equal(blocked.scripts.length, 1);
  blockedController.choose("declined");
  assert.equal(blocked.scripts.length, 0);
});

test("blocked tag loading disables telemetry without interrupting product actions", () => {
  const h = harness();
  const controller = h.api.createAnalyticsController("G-TEST123456");
  controller.choose("accepted");
  h.scripts[0].onerror();
  const count = h.commands().length;
  assert.doesNotThrow(() => h.api.track("export_started"));
  assert.equal(h.scripts.length, 0);
  assert.equal(h.commands().length, count);
  assert.equal(h.window["ga-disable-G-TEST123456"], true);
});

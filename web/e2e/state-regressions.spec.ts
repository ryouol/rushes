import { test, expect, type Page } from "@playwright/test";
import { modelEvidence } from "../lib/model-evidence";

const workspaces = ["a", "b"].map((id) => ({
  id,
  name: `Workspace ${id}`,
  role: "owner",
  balance_milli: 0,
}));
const projects = Array.from({ length: 41 }, (_, i) => ({
  id: `p${i}`,
  name: `Project ${i}`,
  description: "Synthetic browser fixture",
  created_at: "2026-09-10T00:00:00Z",
}));

test("model search evidence stays bounded with escaped multilingual text", () => {
  const output = modelEvidence({
    mode: "keyword",
    notice: "Semantic search timed out; showing keyword evidence.",
    incomplete_processing: true,
    results: Array.from({ length: 60 }, (_, i) => ({
      asset_id: `a${i}`,
      asset_name: "Synthetic",
      start_us: 0,
      end_us: 1_000_000,
      processing_status: "partial",
      has_thumbnail: false,
      evidence: Array.from({ length: 60 }, (_, j) => ({
        observation_id: `o${i}-${j}`,
        description: '\\"漢字🙂'.repeat(800),
        kind: "speech",
        start_us: 0,
        end_us: 1_000_000,
      })),
    })),
  });
  expect(
    new TextEncoder().encode(JSON.stringify(output)).length,
  ).toBeLessThanOrEqual(8000);
  expect(output.truncated).toBe(true);
  expect(output.incomplete_processing).toBe(true);
  expect(output.mode).toBe("keyword");
  expect(output.notice).toContain("Semantic search timed out");
  expect(output.results[0].evidence[0].observation_id).toBe("o0-0");
});

async function fixture(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    let body: unknown = [];
    if (url.pathname.endsWith("/auth/me"))
      body = { id: "u", name: "Synthetic QA", email: "fixture@example.com" };
    else if (url.pathname.endsWith("/workspaces")) body = workspaces;
    else if (url.pathname.endsWith("/projects")) {
      const offset = Number(url.searchParams.get("offset") || 0);
      body = {
        items: projects.slice(offset, offset + 40),
        total: projects.length,
      };
    } else if (url.pathname.endsWith("/assets")) body = { items: [], total: 0 };
    else if (url.pathname.endsWith("/exports")) body = { items: [], total: 0 };
    else if (url.pathname.endsWith("/events")) {
      await route.fulfill({
        contentType: "text/event-stream",
        body: "data: []\n\n",
      });
      return;
    }
    await route.fulfill({ json: body });
  });
  await page.goto("/");
}

test("collection additions reject stale refreshes and preserve processing warnings", async ({
  page,
}) => {
  await fixture(page);
  const collection = {
    id: "c",
    name: "Synthetic selects",
    instructions: "Find color changes",
    item_count: 0,
  };
  const suggestions = ["first", "second"].map((id) => ({
    asset_id: id,
    asset_name: id,
    start_us: 0,
    end_us: 1_000_000,
    evidence: [{ description: "Synthetic evidence" }],
  }));
  const items: object[] = [];
  let heldRequest: import("@playwright/test").Request | undefined;
  let heldAborted = false;
  page.on("requestfailed", (request) => {
    if (
      request === heldRequest &&
      request.failure()?.errorText.includes("ERR_ABORTED")
    )
      heldAborted = true;
  });
  let gets = 0,
    posts = 0;
  let release!: () => void, requested!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  const started = new Promise<void>((resolve) => {
    requested = resolve;
  });
  await page.route("**/projects/p0/collections", (route) =>
    route.fulfill({ json: [collection] }),
  );
  await page.route("**/collections/c/suggest", (route) =>
    route.fulfill({
      json: {
        suggestions,
        notice: "Semantic search timed out; showing keyword evidence.",
        incomplete_processing: true,
      },
    }),
  );
  await page.route("**/collections/c/items", async (route) => {
    if (route.request().method() === "POST") {
      posts++;
      const input = route.request().postDataJSON();
      items.push({
        ...input,
        id: input.asset_id,
        asset_name: input.asset_id,
        note: "",
      });
      await route.fulfill({ json: items.at(-1) });
      return;
    }
    gets++;
    const snapshot = [...items];
    if (gets === 2) {
      heldRequest = route.request();
      requested();
      await pending;
    }
    await route.fulfill({ json: snapshot }).catch(() => {});
  });
  await page.locator(".project-card").first().click();
  await page.getByRole("tab", { name: "Collections", exact: true }).click();
  await page.locator(".collection-card").first().click();
  await expect(
    page.getByText("No selects yet.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Suggest ranges" }).click();
  await expect(page.locator(".suggestion")).toHaveCount(2);
  await expect(
    page.getByText("Semantic search timed out; showing keyword evidence."),
  ).toBeVisible();
  await expect(
    page.getByText("Some footage is still unprocessed.", { exact: false }),
  ).toBeVisible();
  await page
    .locator(".suggestion")
    .first()
    .getByRole("button")
    .evaluate((button: HTMLButtonElement) => {
      button.click();
      button.click();
    });
  await started;
  await page.locator(".suggestion").first().getByRole("button").click();
  await expect(page.locator(".select-row")).toHaveCount(2);
  await expect.poll(() => heldAborted).toBe(true);
  release();
  await expect(page.locator(".select-row")).toHaveCount(2);
  expect(posts).toBe(2);
});

test("projects past the first page remain accessible", async ({ page }) => {
  await fixture(page);
  await expect(page.locator(".project-card")).toHaveCount(40);
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.locator(".project-card")).toHaveCount(1);
  await page.getByRole("button", { name: /Project 40/ }).click();
  await expect(
    page.getByRole("heading", { name: "Project 40", exact: true }),
  ).toBeVisible();
});

test("an open player receives preview and worklog updates without losing an edit", async ({
  page,
}) => {
  await fixture(page);
  let stage = 0,
    observation = {
      id: "o",
      asset_id: "video",
      kind: "speech",
      start_us: 0,
      end_us: 1_000_000,
      description: "Synthetic transcript",
      producer: "fixture",
      uncertainty: "high",
      version: 1,
      review_status: "unreviewed",
    };
  const asset = () => ({
    id: "video",
    project_id: "p0",
    name: "Synthetic player",
    status: stage === 0 ? "queued" : stage === 1 ? "preview_ready" : "ready",
    duration_us: 12_000_000,
    has_preview: stage > 0,
    has_thumbnail: false,
    source_size: 100,
    timelines: [],
  });
  await page.route("**/projects/p0/assets?**", (route) =>
    route.fulfill({ json: { items: [asset()], total: 1 } }),
  );
  await page.route("**/assets/video", (route) =>
    route.fulfill({ json: asset() }),
  );
  await page.route("**/assets/video/observations?**", (route) =>
    route.fulfill({
      json: {
        items: stage > 0 ? [observation] : [],
        total: stage > 0 ? 1 : 0,
        offset: 0,
      },
    }),
  );
  await page.route("**/observations/o", async (route) => {
    observation = {
      ...observation,
      ...route.request().postDataJSON(),
      version: 2,
      review_status: "corrected",
    };
    await route.fulfill({ json: observation });
  });
  await page.locator(".project-card").first().click();
  await page.locator(".asset-open").first().click();
  await expect(page.getByText("No observations yet")).toBeVisible();
  stage = 1;
  await page.waitForResponse((response) =>
    response.url().includes("/assets/video/observations?"),
  );
  await expect(page.locator("video")).toBeVisible();
  await expect(page.locator(".worklog-item")).toHaveCount(1);
  await page.getByRole("button", { name: /Edit observation at/ }).click();
  await page
    .getByRole("textbox", { name: "Description", exact: true })
    .fill("Unsaved human correction");
  await (
    await page.waitForResponse((response) =>
      response.url().includes("/assets/video/observations?"),
    )
  ).finished();
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
  await expect(
    page.getByRole("textbox", { name: "Description", exact: true }),
  ).toHaveValue("Unsaved human correction");
  stage = 2;
  const finalPoll = await page.waitForResponse((response) =>
    response.url().endsWith("/assets/video"),
  );
  expect((await finalPoll.json()).status).toBe("ready");
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
  await expect(
    page.getByRole("textbox", { name: "Description", exact: true }),
  ).toHaveValue("Unsaved human correction");
  await page
    .getByRole("button", { name: "Save correction", exact: true })
    .click();
  await expect(page.getByText("Edited by user", { exact: true })).toBeVisible();
  await expect(page.locator(".worklog-item")).toContainText(
    "Unsaved human correction",
  );
  await expect(page.locator(".worklog-item")).toContainText("v2");
});

test("clearing search aborts a late response; upload validation remains readable", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await fixture(page);
  await page.locator(".project-card").first().click();
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  let requested!: () => void;
  const started = new Promise<void>((resolve) => {
    requested = resolve;
  });
  await page.route("**/search?**", async (route) => {
    requested();
    await pending;
    await route
      .fulfill({
        json: {
          results: [],
          notice: "Stale result",
          incomplete_processing: false,
        },
      })
      .catch(() => {});
  });
  await page.getByLabel("Search footage").fill("old query");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await started;
  await page.getByLabel("Uncategorized sources").check();
  release();
  await expect(page.getByLabel("Search footage")).toHaveValue("");
  await expect(page.getByText("Stale result")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Search", exact: true }),
  ).toBeEnabled();
  await page.route("**/upload?**", (route) =>
    route.fulfill({
      status: 422,
      json: {
        detail: [
          {
            loc: ["query", "filename"],
            msg: "Invalid filename",
            type: "value_error",
          },
        ],
      },
    }),
  );
  await page
    .getByRole("button", { name: "Import footage", exact: true })
    .first()
    .click();
  await page
    .locator("input[type=file]")
    .first()
    .setInputFiles({
      name: "synthetic.mp4",
      mimeType: "video/mp4",
      buffer: Buffer.from("synthetic validation request"),
    });
  await expect(
    page.getByText("Invalid filename", { exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("switching workspaces discards delayed settings", async ({ page }) => {
  await fixture(page);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  let requested!: () => void;
  const started = new Promise<void>((resolve) => {
    requested = resolve;
  });
  await page.route("**/settings", async (route) => {
    const old = route.request().url().includes("/workspaces/a/");
    if (old) {
      requested();
      await pending;
    }
    await route
      .fulfill({
        json: {
          storage_root: old ? "/fixture/old" : "/fixture/new",
          output_root: "/fixture/exports",
          disk_free_bytes: 1024 ** 3,
          source_roots: [],
          gemini_configured: false,
          gemini_model: "synthetic",
          transcription_model: "tiny",
          embedding_model: "synthetic",
          temporal_connected: true,
          media_tools_available: true,
          balance_milli: 0,
          credits_per_minute: 1,
          max_analysis_credits: 120,
        },
      })
      .catch(() => {});
  });
  await page.route("**/usage", (route) =>
    route.fulfill({
      json: { unique_source_duration_us: 0, metrics: [], ledger: [] },
    }),
  );
  await page.getByRole("button", { name: "Settings & usage" }).click();
  await started;
  await page
    .getByRole("combobox", { name: "WORKSPACE", exact: true })
    .selectOption("b");
  await expect(page.getByText("/fixture/new", { exact: true })).toBeVisible();
  release();
  await expect(page.getByText("/fixture/old", { exact: true })).toHaveCount(0);
  await expect(page.getByText("/fixture/new", { exact: true })).toBeVisible();
});

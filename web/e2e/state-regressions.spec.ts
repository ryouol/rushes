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

function fixtureAsset(
  id: string,
  categories: { id: string; name: string }[] = [],
) {
  return {
    id,
    project_id: "p0",
    name: `Synthetic ${id}`,
    status: "ready",
    duration_us: 12_000_000,
    has_preview: false,
    has_thumbnail: false,
    source_size: 100,
    can_retry: false,
    timelines: [],
    organization: {
      state: "organized",
      categories: categories.map((category) => ({
        ...category,
        evidence_count: 1,
      })),
      category_total: categories.length,
      has_more: false,
      run_id: "synthetic-run",
    },
  };
}

function fixtureSettings(storageRoot = "/fixture/storage") {
  return {
    storage_root: storageRoot,
    output_root: "/fixture/exports",
    disk_free_bytes: 1024 ** 3,
    minimum_free_bytes: 256 * 1024 ** 2,
    usable_storage_bytes: 768 * 1024 ** 2,
    export_disk_free_bytes: 1024 ** 3,
    export_usable_storage_bytes: 768 * 1024 ** 2,
    export_storage_separate_volume: false,
    workspace_file_count: 4,
    workspace_project_count: 2,
    workspace_uploaded_file_count: 3,
    workspace_uploaded_source_bytes: 300_000_000,
    source_roots: [],
    gemini_configured: false,
    gemini_model: "synthetic",
    transcription_model: "tiny",
    embedding_model: "synthetic",
    compute_backend: "local",
    temporal_connected: true,
    media_tools_available: true,
    balance_milli: 0,
    credits_per_minute: 1,
    max_analysis_credits: 120,
  };
}

async function fixture(
  page: Page,
  library: ReturnType<typeof fixtureAsset>[] = [],
) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    let body: unknown = [];
    if (url.pathname.endsWith("/auth/me"))
      body = { id: "u", name: "Synthetic QA", email: "fixture@example.com" };
    else if (url.pathname.endsWith("/workspaces")) body = workspaces;
    else if (url.pathname.endsWith("/projects")) {
      const offset = Number(url.searchParams.get("offset") || 0);
      const limit = Number(url.searchParams.get("limit") || 40);
      body = {
        items: projects.slice(offset, offset + limit),
        total: projects.length,
      };
    } else if (url.pathname.endsWith("/assets")) {
      const category = url.searchParams.get("category");
      const matching = library.filter((asset) =>
        category === "uncategorized"
          ? asset.organization.categories.length === 0
          : !category ||
            asset.organization.categories.some((item) => item.id === category),
      );
      const offset = Number(url.searchParams.get("offset") || 0);
      const limit = Number(url.searchParams.get("limit") || 40);
      body = {
        items: matching.slice(offset, offset + limit),
        total: matching.length,
      };
    } else if (url.pathname.endsWith("/organization")) {
      const categories = new Map<
        string,
        { id: string; name: string; asset_count: number }
      >();
      for (const asset of library) {
        for (const category of asset.organization.categories) {
          const current = categories.get(category.id);
          categories.set(category.id, {
            id: category.id,
            name: category.name,
            asset_count: (current?.asset_count || 0) + 1,
          });
        }
      }
      const categorized = library.filter(
        (asset) => asset.organization.categories.length > 0,
      ).length;
      body = {
        categories: [...categories.values()],
        category_total: categories.size,
        has_more: false,
        total_assets: library.length,
        categorized_assets: categorized,
        uncategorized_assets: library.length - categorized,
        processing_assets: 0,
        partial_assets: 0,
        not_analyzed_assets: 0,
        analysis_configured: true,
      };
    } else if (url.pathname.endsWith("/exports"))
      body = { items: [], total: 0 };
    else if (url.pathname.endsWith("/settings")) body = fixtureSettings();
    else if (url.pathname.endsWith("/usage"))
      body = { unique_source_duration_us: 0, metrics: [], ledger: [] };
    else if (url.pathname.endsWith("/events")) {
      await route.fulfill({
        contentType: "text/event-stream",
        body: "data: []\n\n",
      });
      return;
    }
    await route.fulfill({ json: body });
  });
  await page.goto("/app");
}

for (const kind of ["project", "workspace"] as const) {
  test(`${kind} deletion requires its name, submits once, and retains a rejected item`, async ({
    page,
  }) => {
    await fixture(page);
    const name = kind === "project" ? "Project 0" : "Workspace a";
    const path = `/api/workspaces/a${kind === "project" ? "/projects/p0" : ""}`;
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    let requests = 0;
    await page.route(`**${path}`, async (route) => {
      if (route.request().method() !== "DELETE") return route.fallback();
      requests += 1;
      await pending;
      await route.fulfill({
        status: 409,
        json: { detail: "Processing is still active. Wait for it to finish." },
      });
    });
    if (kind === "project")
      await page.locator(".workspace-project-row").first().click();
    else await page.getByRole("link", { name: "Settings & usage" }).click();
    await page
      .getByRole("button", { name: `Delete ${kind}`, exact: true })
      .click();
    const dialog = page.getByRole("dialog", {
      name: `Delete ${kind}?`,
      exact: true,
    });
    const confirmation = dialog.getByLabel(`Type the ${kind} name to confirm`);
    const submit = dialog.getByRole("button", {
      name: `Delete ${kind}`,
      exact: true,
    });
    await expect(submit).toBeDisabled();
    await confirmation.fill("A different name");
    await expect(submit).toBeDisabled();
    expect(requests).toBe(0);
    await confirmation.fill(name);
    await expect(submit).toBeEnabled();
    try {
      await submit.dblclick();
      await expect.poll(() => requests).toBe(1);
      await expect(
        dialog.getByRole("button", { name: "Deleting…", exact: true }),
      ).toBeDisabled();
      await expect(
        dialog.getByRole("button", { name: `Keep ${kind}`, exact: true }),
      ).toBeDisabled();
    } finally {
      release();
    }
    await expect(dialog.getByRole("alert")).toContainText(
      "Processing is still active",
    );
    await expect(dialog).toBeVisible();
    await expect(confirmation).toHaveValue(name);
    await expect(submit).toBeEnabled();
    expect(requests).toBe(1);
    await dialog
      .getByRole("button", { name: `Keep ${kind}`, exact: true })
      .click();
    await expect(
      page.getByRole("heading", {
        name: kind === "project" ? name : "Settings & usage",
        exact: true,
      }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: `Delete ${kind}`, exact: true })
      .click();
    await expect(confirmation).toHaveValue("");
    await expect(submit).toBeDisabled();
    expect(requests).toBe(1);
  });
}

test("a completed deletion cannot redirect a newer project after browser Back", async ({
  page,
}) => {
  await fixture(page);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  let requests = 0;
  await page.route("**/api/workspaces/a/projects/p0", async (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    requests += 1;
    await pending;
    await route.fulfill({
      json: { deleted: true, reclaimed_bytes: 0, deleted_files: 0 },
    });
  });
  await page.locator(".workspace-project-row").first().click();
  await page
    .getByRole("button", { name: "Delete project", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Delete project?",
    exact: true,
  });
  await dialog.getByLabel("Type the project name to confirm").fill("Project 0");
  await dialog
    .getByRole("button", { name: "Delete project", exact: true })
    .click();
  await expect.poll(() => requests).toBe(1);
  try {
    await page.goBack();
    await page.getByRole("link", { name: /Project 1\b/ }).click();
    await expect(
      page.getByRole("heading", { name: "Project 1", exact: true }),
    ).toBeVisible();
    const destination = page.url();
    const completed = page.waitForResponse(
      (response) =>
        response.request().method() === "DELETE" &&
        new URL(response.url()).pathname === "/api/workspaces/a/projects/p0",
    );
    release();
    await (await completed).finished();
    // Let the completed fetch and any resulting route update commit before checking.
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        ),
    );
    await expect(page).toHaveURL(destination);
    await expect(
      page.getByRole("heading", { name: "Project 1", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Project deleted.", { exact: false }),
    ).toHaveCount(0);
    expect(requests).toBe(1);
  } finally {
    release();
  }
});

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
  await page.locator(".workspace-project-row").first().click();
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
  await expect(page.locator(".workspace-project-row")).toHaveCount(40);
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.locator(".workspace-project-row")).toHaveCount(1);
  await page.getByRole("link", { name: /Project 40/ }).click();
  await expect(
    page.getByRole("heading", { name: "Project 40", exact: true }),
  ).toBeVisible();
});

test("choosing an AI category filters whole files and cancels a pending search", async ({
  page,
}) => {
  await fixture(page, [
    fixtureAsset("coast", [
      { id: "coastline", name: "Coastline" },
      { id: "waves", name: "Waves" },
    ]),
    fixtureAsset("interview", [{ id: "interviews", name: "Interviews" }]),
    fixtureAsset("unlabeled"),
  ]);
  await page.locator(".workspace-project-row").first().click();
  await expect(page.locator(".asset-card")).toHaveCount(3);
  let release!: () => void;
  let requested!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  const started = new Promise<void>((resolve) => {
    requested = resolve;
  });
  let heldRequest: import("@playwright/test").Request | undefined;
  let aborted = false;
  page.on("requestfailed", (request) => {
    if (
      request === heldRequest &&
      request.failure()?.errorText.includes("ERR_ABORTED")
    )
      aborted = true;
  });
  await page.route("**/search?**", async (route) => {
    heldRequest = route.request();
    requested();
    await pending;
    await route
      .fulfill({
        json: {
          results: [],
          notice: "Stale search must stay hidden",
          incomplete_processing: false,
        },
      })
      .catch(() => {});
  });
  await page.getByLabel("Search footage").fill("spoken interview");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await started;
  const category = page.getByRole("button", { name: /^Coastline\b/ });
  const [response] = await Promise.all([
    page.waitForResponse((response) => {
      const url = new URL(response.url());
      return (
        url.pathname.endsWith("/assets") &&
        url.searchParams.get("category") === "coastline"
      );
    }),
    category.click(),
  ]);
  expect(
    (await response.json()).items.map((item: { id: string }) => item.id),
  ).toEqual(["coast"]);
  await expect(category).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByLabel("Search footage")).toHaveValue("");
  await expect(page.locator(".asset-card")).toHaveCount(1);
  await expect(page.locator(".asset-card h2")).toHaveText("Synthetic coast");
  await expect.poll(() => aborted).toBe(true);
  release();
  await expect(page.getByText("Stale search must stay hidden")).toHaveCount(0);
  await expect(page.locator(".search-result")).toHaveCount(0);
  await page.getByRole("button", { name: /^Uncategorized\b/ }).click();
  await expect(page.locator(".asset-card h2")).toHaveText(
    "Synthetic unlabeled",
  );
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
    ...fixtureAsset("video"),
    id: "video",
    project_id: "p0",
    name: "Synthetic player",
    status: stage === 0 ? "queued" : stage === 1 ? "preview_ready" : "ready",
    duration_us: 12_000_000,
    has_preview: stage > 0,
    has_thumbnail: false,
    source_size: 100,
    timelines: [],
    organization: {
      ...fixtureAsset(
        "video",
        stage < 2
          ? []
          : [
              { id: "coastline", name: "Coastline" },
              { id: "waves", name: "Waves" },
            ],
      ).organization,
      state: stage < 2 ? "processing" : "organized",
    },
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
  await page.locator(".workspace-project-row").first().click();
  await page.locator(".asset-open").first().click();
  await page.getByRole("button", { name: /^Worklog\b/ }).click();
  await expect(page.getByText("No observations yet")).toBeVisible();
  stage = 1;
  await page.waitForResponse((response) =>
    response.url().includes("/assets/video/observations?"),
  );
  await expect(page.locator("video")).toBeVisible();
  await expect(page.locator(".worklog-item")).toHaveCount(1);
  const selectionToggle = page.getByText("Save a selection or export a range", {
    exact: true,
  });
  await expect(page.getByLabel("Selection in seconds")).toBeHidden();
  await expect(page.getByLabel("Seek footage")).toBeHidden();
  await selectionToggle.click();
  await page.getByLabel("Selection in seconds").fill("2");
  await page.getByLabel("Selection out seconds").fill("4");
  await selectionToggle.click();
  await expect(page.getByLabel("Selection in seconds")).toBeHidden();
  await selectionToggle.click();
  await expect(page.getByLabel("Selection in seconds")).toHaveValue("2");
  await expect(page.getByLabel("Selection out seconds")).toHaveValue("4");
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
  await expect(page.locator(".player-categories")).toContainText(
    "Coastline · Waves",
  );
  await expect(page.getByLabel("Selection in seconds")).toHaveValue("2");
  await expect(page.getByLabel("Selection out seconds")).toHaveValue("4");
  await page
    .getByRole("button", { name: "Save correction", exact: true })
    .click();
  await expect(page.getByText("Edited by user", { exact: true })).toBeVisible();
  await expect(page.locator(".worklog-item")).toContainText(
    "Unsaved human correction",
  );
  await expect(page.locator(".worklog-item")).toContainText("v2");
});

test("Worklog drafts survive collapse and filtering; Save, Cancel, and asset changes reset them", async ({
  page,
}) => {
  await fixture(page);
  const asset = {
    ...fixtureAsset("video"),
    id: "video",
    project_id: "p0",
    name: "Synthetic worklog draft",
    status: "partial",
    duration_us: 12_000_000,
    has_preview: false,
    has_thumbnail: false,
    source_size: 100,
    timelines: [],
    organization: { ...fixtureAsset("video").organization, state: "partial" },
  };
  const otherAsset = fixtureAsset("other");
  let observation = {
    id: "o",
    asset_id: "video",
    kind: "speech",
    start_us: 0,
    end_us: 1_000_000,
    description: "Original synthetic transcript",
    producer: "fixture",
    uncertainty: "high",
    version: 1,
    review_status: "unreviewed",
  };
  const corrections: unknown[] = [];
  await page.route("**/projects/p0/assets?**", (route) =>
    route.fulfill({ json: { items: [asset, otherAsset], total: 2 } }),
  );
  await page.route("**/assets/video", (route) =>
    route.fulfill({ json: asset }),
  );
  await page.route("**/assets/video/observations?**", (route) => {
    const kind = new URL(route.request().url()).searchParams.get("kind");
    const items = kind === "visual" ? [] : [observation];
    return route.fulfill({ json: { items, total: items.length, offset: 0 } });
  });
  await page.route("**/assets/other", (route) =>
    route.fulfill({ json: otherAsset }),
  );
  await page.route("**/assets/other/observations?**", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            ...observation,
            id: "other-observation",
            asset_id: "other",
            description: "Different source transcript",
            start_us: 0,
            end_us: 1_000_000,
          },
        ],
        total: 1,
        offset: 0,
      },
    }),
  );
  await page.route("**/observations/o", async (route) => {
    const correction = route.request().postDataJSON();
    corrections.push(correction);
    observation = {
      ...observation,
      ...correction,
      version: 2,
      review_status: "corrected",
    };
    await route.fulfill({ json: observation });
  });
  await page.locator(".workspace-project-row").first().click();
  await page.locator(".asset-open").first().click();
  const toggle = page.getByRole("button", { name: /^Worklog\b/ });
  await toggle.click();
  await page.getByRole("button", { name: /Edit observation at/ }).click();
  const description = page.getByRole("textbox", {
    name: "Description",
    exact: true,
  });
  await description.fill("Unsaved timing correction");
  await page.getByLabel("Start seconds", { exact: true }).fill("2");
  await page.getByLabel("End seconds", { exact: true }).fill("3.5");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(description).toBeHidden();
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(description).toHaveValue("Unsaved timing correction");
  await expect(page.getByLabel("Start seconds", { exact: true })).toHaveValue(
    "2",
  );
  await expect(page.getByLabel("End seconds", { exact: true })).toHaveValue(
    "3.5",
  );
  await page.getByLabel("Worklog type").selectOption("visual");
  await expect(
    page.getByRole("heading", { name: "No observations yet" }),
  ).toBeVisible();
  await page.getByLabel("Worklog type").selectOption("speech");
  await expect(description).toHaveValue("Unsaved timing correction");
  await expect(page.getByLabel("Start seconds", { exact: true })).toHaveValue(
    "2",
  );
  await expect(page.getByLabel("End seconds", { exact: true })).toHaveValue(
    "3.5",
  );
  expect(corrections).toHaveLength(0);
  await page
    .getByRole("button", { name: "Save correction", exact: true })
    .click();
  await expect
    .poll(() => corrections)
    .toEqual([
      expect.objectContaining({
        description: "Unsaved timing correction",
        start_us: 2_000_000,
        end_us: 3_500_000,
      }),
    ]);
  await expect(page.locator(".worklog-item")).toContainText(
    "Unsaved timing correction",
  );
  await expect(description).toHaveCount(0);
  await page.getByRole("button", { name: /Edit observation at/ }).click();
  await description.fill("Discard this correction");
  await page.getByLabel("Start seconds", { exact: true }).fill("4");
  await page.getByLabel("End seconds", { exact: true }).fill("5");
  await page
    .locator(".correction-form")
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await page.getByRole("button", { name: /Edit observation at/ }).click();
  await expect(description).toHaveValue("Unsaved timing correction");
  await expect(page.getByLabel("Start seconds", { exact: true })).toHaveValue(
    "2",
  );
  await expect(page.getByLabel("End seconds", { exact: true })).toHaveValue(
    "3.5",
  );
  await description.fill("Do not carry this to another source");
  await page
    .getByRole("button", { name: "Close media review", exact: true })
    .click();
  await page.locator(".asset-open").nth(1).click();
  await page.getByRole("button", { name: /^Worklog\b/ }).click();
  await expect(description).toHaveCount(0);
  await page.getByRole("button", { name: /Edit observation at/ }).click();
  await expect(description).toHaveValue("Different source transcript");
  await expect(page.getByLabel("Start seconds", { exact: true })).toHaveValue(
    "0",
  );
  await expect(page.getByLabel("End seconds", { exact: true })).toHaveValue(
    "1",
  );
  expect(corrections).toHaveLength(1);
});

test("clearing search aborts a late response; upload validation remains readable", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await fixture(page, [fixtureAsset("uncategorized")]);
  await page.locator(".workspace-project-row").first().click();
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
  await page.getByRole("button", { name: /^Uncategorized\b/ }).click();
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
        json: fixtureSettings(old ? "/fixture/old" : "/fixture/new"),
      })
      .catch(() => {});
  });
  await page.route("**/usage", (route) =>
    route.fulfill({
      json: { unique_source_duration_us: 0, metrics: [], ledger: [] },
    }),
  );
  await page.getByRole("link", { name: "Settings & usage" }).click();
  await started;
  await page
    .getByRole("combobox", { name: "Choose workspace", exact: true })
    .selectOption("b");
  await page.getByRole("link", { name: "Settings & usage" }).click();
  await expect(
    page.getByRole("heading", { name: "Storage", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("available for new uploads", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("/fixture/new", { exact: true })).toBeHidden();
  await page.getByText("Support details", { exact: true }).click();
  await expect(page.getByText("/fixture/new", { exact: true })).toBeVisible();
  release();
  await expect(page.getByText("/fixture/old", { exact: true })).toHaveCount(0);
  await expect(page.getByText("/fixture/new", { exact: true })).toBeVisible();
});

test("footage paging preserves focus and stale category rows stay inactive after failure", async ({
  page,
}) => {
  const coast = { id: "coast", name: "Coastline" };
  const aerial = { id: "aerial", name: "Aerials" };
  const library = Array.from({ length: 41 }, (_, index) =>
    fixtureAsset(`video-${index}`, [index < 40 ? coast : aerial]),
  );
  await fixture(page, library);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  let failCategory = true;
  await page.route("**/projects/p0/assets?**", async (route) => {
    const query = new URL(route.request().url()).searchParams;
    const offset = Number(query.get("offset") || 0);
    const category = query.get("category");
    if (offset === 40) await pending;
    if (category === coast.id && failCategory) {
      await route
        .fulfill({ status: 503, json: { detail: "Temporary footage failure" } })
        .catch(() => {});
      return;
    }
    const matching = library.filter(
      (asset) =>
        !category ||
        asset.organization.categories.some((item) => item.id === category),
    );
    await route
      .fulfill({
        json: {
          items: matching.slice(offset, offset + 40),
          total: matching.length,
        },
      })
      .catch(() => {});
  });
  await page.locator(".workspace-project-row").first().click();
  const grid = page.locator(".organization-asset-grid");
  await expect(grid.locator(".asset-card")).toHaveCount(40);
  const next = page.getByRole("button", { name: "Next", exact: true });
  const mountedGrid = await grid.elementHandle();
  const mountedNext = await next.elementHandle();
  await next.focus();
  try {
    await next.press("Enter");
    await expect(grid).toHaveAttribute("inert", "");
    await expect(grid.locator(".asset-card")).toHaveCount(40);
    await expect(next).toBeFocused();
    await expect(next).toBeDisabled();
    expect(await mountedGrid!.evaluate((element) => element.isConnected)).toBe(
      true,
    );
    expect(await mountedNext!.evaluate((element) => element.isConnected)).toBe(
      true,
    );
  } finally {
    release();
  }
  await expect(grid.locator(".asset-card")).toHaveCount(1);
  await expect(next).toBeFocused();
  await expect(grid).not.toHaveAttribute("inert", "");
  await page.getByRole("button", { name: "Coastline 40", exact: true }).click();
  await expect(
    page.getByText("This footage view could not load."),
  ).toBeVisible();
  await expect(grid).toHaveAttribute("inert", "");
  await expect(grid.locator(".asset-card")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: /Synthetic video-40/ }),
  ).toHaveCount(0);
  failCategory = false;
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(grid).not.toHaveAttribute("inert", "");
  await expect(grid.locator(".asset-card")).toHaveCount(40);
  await expect(
    page.getByText("Temporary footage failure", { exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText("This footage view could not load.")).toHaveCount(
    0,
  );
});

test("collection adjustment stays beside its row and restores focus after cancel and save", async ({
  page,
}) => {
  await fixture(page);
  const items = Array.from({ length: 25 }, (_, index) => ({
    id: `select-${index}`,
    asset_id: `asset-${index}`,
    asset_name: `Footage ${index}`,
    start_us: 0,
    end_us: 1_000_000,
    note: "",
  }));
  await page.route("**/projects/p0/collections", (route) =>
    route.fulfill({
      json: [
        {
          id: "c",
          name: "Synthetic selects",
          instructions: "",
          item_count: items.length,
        },
      ],
    }),
  );
  await page.route("**/collections/c/items", (route) =>
    route.fulfill({ json: items }),
  );
  let savedNote = "";
  await page.route("**/collection-items/select-24", (route) => {
    savedNote = route.request().postDataJSON().note;
    items[24].note = savedNote;
    return route.fulfill({ json: items[24] });
  });
  await page.locator(".workspace-project-row").first().click();
  await page.getByRole("tab", { name: "Collections", exact: true }).click();
  await page.locator(".collection-card").first().click();
  const row = page.locator(".select-row").last();
  const adjust = row.getByRole("button", { name: "Adjust", exact: true });
  await adjust.click();
  const form = page.getByRole("form", {
    name: "Adjust Footage 24",
    exact: true,
  });
  await expect(
    form.getByRole("checkbox", { name: "Use full source file" }),
  ).toBeFocused();
  await expect(form).toBeInViewport();
  expect(
    await row.evaluate((element) => element.nextElementSibling?.tagName),
  ).toBe("FORM");
  await form.getByRole("button", { name: "Cancel adjustment" }).click();
  await expect(adjust).toBeFocused();
  await expect(form).toHaveCount(0);
  await adjust.press("Enter");
  await form.getByLabel("Select note").fill("Keep the final frame");
  await form.getByRole("button", { name: "Save range", exact: true }).click();
  await expect(form).toHaveCount(0);
  await expect(adjust).toBeFocused();
  expect(savedNote).toBe("Keep the final frame");
});

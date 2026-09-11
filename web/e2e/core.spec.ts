import { test, expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";
import path from "node:path";
import { readFile } from "node:fs/promises";

async function openWorklog(page: Page) {
  const toggle = page.getByRole("button", { name: /^Worklog\b/ });
  if ((await toggle.getAttribute("aria-expanded")) === "false")
    await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
}

test("real account → import → persistent worklog → select → rendered export", async ({
  page,
  context,
}) => {
  const email = `browser-${randomUUID()}@example.com`;
  const password = `Synthetic-${randomUUID()}`;
  await page.goto("/signup");
  await page.getByLabel("Name", { exact: true }).fill("Synthetic QA");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page).toHaveURL(/\/onboarding$/);
  await page.getByLabel("Project name").fill("Synthetic timing shoot");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(page).toHaveURL(/\/app\?.*project=/);
  await page
    .getByRole("button", { name: "Import footage", exact: true })
    .first()
    .click();
  await page
    .locator("input[type=file]")
    .first()
    .setInputFiles(
      path.resolve("../.local/fixtures/SYNTHETIC-red-blue-speech.mp4"),
    );
  await expect(
    page.getByText("Queued for processing", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "Return to footage" }).click();
  await expect(page.locator(".asset-card").first()).toHaveAttribute(
    "data-processing-state",
    process.env.RUSHES_TEST_LIVE_GEMINI === "1" ? "ready" : "partial",
    { timeout: 150000 },
  );
  await page.getByRole("tab", { name: "Collections", exact: true }).click();
  await page
    .getByRole("button", { name: "New collection", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("Name", { exact: true })
    .fill("Selected moments");
  await page
    .getByRole("button", { name: "Create collection", exact: true })
    .click();
  await page.getByRole("tab", { name: "Library", exact: true }).click();
  await page.locator(".asset-open").first().click();
  await openWorklog(page);
  await expect(page.locator(".worklog-item")).not.toHaveCount(0, {
    timeout: 30000,
  });
  await expect(page.locator("video")).toBeVisible();
  await expect(page.getByLabel("Selection in seconds")).toBeHidden();
  await page.keyboard.press("l");
  await expect
    .poll(() =>
      page
        .locator("video")
        .evaluate((node: HTMLVideoElement) => node.currentTime),
    )
    .toBeGreaterThan(0.3);
  await page.keyboard.press("k");
  await expect
    .poll(() =>
      page.locator("video").evaluate((node: HTMLVideoElement) => node.paused),
    )
    .toBeTruthy();
  await page.keyboard.press("i");
  await expect(page.getByLabel("Selection in seconds")).toBeVisible();
  expect(
    Number(await page.getByLabel("Selection in seconds").inputValue()),
  ).toBeGreaterThan(0.3);
  await page
    .getByRole("button", { name: /Edit observation at/ })
    .first()
    .click();
  await page
    .getByRole("textbox", { name: "Description", exact: true })
    .fill("Human-verified synthetic red and blue timing fixture.");
  await page
    .getByRole("button", { name: "Save correction", exact: true })
    .click();
  await expect(
    page.getByText("Human-verified synthetic red and blue timing fixture."),
  ).toBeVisible();
  await page.getByLabel("Selection in seconds").fill("2");
  await page.getByLabel("Selection out seconds").fill("4");
  await page.getByLabel("Save to collection").selectOption({
    label: "Selected moments",
  });
  await page.getByRole("button", { name: "Save select", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Saved", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../.local/qa/player-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Export range", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Review export", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Start export", exact: true }).click();
  await expect(page.locator(".download-links a")).toHaveCount(1, {
    timeout: 60000,
  });
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.locator(".download-links a").click(),
  ]);
  await download.saveAs(path.resolve("../.local/qa/exported-select.mp4"));
  await page.screenshot({
    path: "../.local/qa/exports-desktop.png",
    fullPage: true,
  });
  const second = await context.newPage();
  await page.close();
  await second.goto("/app");
  await second
    .locator(".workspace-project-row")
    .filter({ hasText: "Synthetic timing shoot" })
    .click();
  await second.locator(".asset-open").first().click();
  await openWorklog(second);
  await expect(
    second.getByText("Human-verified synthetic red and blue timing fixture."),
  ).toBeVisible();
  await second
    .getByRole("button", { name: "Close media review", exact: true })
    .click();
  await second
    .getByRole("textbox", { name: "Search footage", exact: true })
    .fill("Human-verified synthetic");
  await second.getByRole("button", { name: "Search", exact: true }).click();
  await expect(second.locator(".search-result")).not.toHaveCount(0, {
    timeout: 30000,
  });
  await second
    .getByRole("button", { name: "Save this search", exact: true })
    .click();
  await expect(
    second.getByText("Search saved. Open it again from Collections."),
  ).toBeVisible();
  await second.locator(".search-result").first().click();
  await openWorklog(second);
  await second.locator(".observation-history summary").first().click();
  await expect(
    second.getByText("Version 1 → 2", { exact: true }),
  ).toBeVisible();
  await second
    .getByText("Save a selection or export a range", { exact: true })
    .click();
  await second.getByLabel("Selection in seconds").fill("2");
  await second.getByLabel("Selection out seconds").fill("4");
  await second.getByText("Add a worklog note", { exact: true }).click();
  await second
    .getByLabel("New worklog note")
    .fill("Manual synthetic red frame evidence.");
  await second.getByRole("button", { name: "Save note", exact: true }).click();
  await expect(
    second.getByText("Manual synthetic red frame evidence.", { exact: true }),
  ).toBeVisible();
  await second.getByText("Footage details & analysis", { exact: true }).click();
  await second
    .getByRole("button", { name: "Check source availability", exact: true })
    .click();
  await expect(second.getByText(/Source available · checked by/)).toBeVisible();
  await second
    .getByRole("button", { name: "Review analysis estimate", exact: true })
    .click();
  const startAnalysis = second.getByRole("button", {
    name: "Start new analysis",
    exact: true,
  });
  if (process.env.RUSHES_TEST_LIVE_GEMINI === "1") {
    await expect(startAnalysis).toBeEnabled();
  } else {
    await expect(startAnalysis).toBeDisabled();
  }
  await second
    .getByRole("button", { name: "Close media review", exact: true })
    .click();
  await second.getByRole("tab", { name: "Library", exact: true }).focus();
  await second.keyboard.press("ArrowRight");
  await expect(
    second.getByRole("tab", { name: "Collections", exact: true }),
  ).toBeFocused();
  await second.getByRole("button", { name: /Selected moments/ }).click();
  await second.getByRole("button", { name: "Adjust", exact: true }).click();
  await second.getByLabel("Collection in seconds").fill("3");
  await second.getByLabel("Collection out seconds").fill("5");
  await second.getByRole("button", { name: "Save range", exact: true }).click();
  await expect(second.locator(".select-row .timecode")).toHaveText(
    "00:00:03 — 00:00:05",
  );
  await second
    .getByText("Experimental editor interchange", { exact: true })
    .click();
  await second
    .getByRole("button", { name: "Preview FCP7 XML", exact: true })
    .click();
  await expect(
    second.getByRole("heading", { name: "Review export", exact: true }),
  ).toBeVisible();
  await second
    .getByRole("button", { name: "Start export", exact: true })
    .click();
  await expect(second.getByRole("link", { name: /selects.xml/ })).toBeVisible({
    timeout: 30000,
  });
  for (const format of ["JSON", "CSV"]) {
    await second.getByRole("tab", { name: "Collections", exact: true }).click();
    await second.getByText("Selection data", { exact: true }).click();
    await second
      .getByRole("button", { name: `Selection ${format}`, exact: true })
      .click();
    await second
      .getByRole("button", { name: "Start export", exact: true })
      .click();
    const link = second.getByRole("link", {
      name: `selections.${format.toLowerCase()}`,
    });
    await expect(link).toBeVisible({ timeout: 30000 });
    const [dataDownload] = await Promise.all([
      second.waitForEvent("download"),
      link.click(),
    ]);
    const target = path.resolve(
      `../.local/qa/selections.${format.toLowerCase()}`,
    );
    await dataDownload.saveAs(target);
    const data = await readFile(target, "utf8");
    expect(data).toContain("SYNTHETIC-red-blue-speech.mp4");
    expect(data).toContain("import_relative_path");
    if (format === "JSON")
      expect(JSON.parse(data).selections[0].start_us).toBe(3000000);
  }
  await second
    .getByRole("link", { name: "Settings & usage", exact: true })
    .click();
  await expect(
    second.getByRole("heading", { name: "Settings & usage", exact: true }),
  ).toBeVisible();
  await second.screenshot({
    path: "../.local/qa/settings-desktop.png",
    fullPage: true,
  });
  await second.evaluate(() => {
    document.body.style.zoom = "2";
  });
  expect(
    await second.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await second.evaluate(() => {
    document.body.style.zoom = "1";
  });
  await second.setViewportSize({ width: 390, height: 844 });
  await second.screenshot({
    path: "../.local/qa/settings-mobile.png",
    fullPage: true,
  });
  expect(
    await second.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await second
    .getByRole("button", { name: "Open navigation", exact: true })
    .click();
  await second
    .getByRole("dialog")
    .getByRole("button", { name: "Sign out", exact: true })
    .click();
  await expect(
    second.getByRole("heading", { name: "Welcome back.", exact: true }),
  ).toBeVisible();
});

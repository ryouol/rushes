import { test, expect, type Page } from "@playwright/test";

test("Back restores the landing page after section navigation and Privacy", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("link", { name: "See how it works", exact: true })
    .click();
  await expect(page).toHaveURL(/\/#workflow$/);
  await page.getByRole("link", { name: "Privacy", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Your footage and data." }),
  ).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/#workflow$/);
  await expect(
    page.getByRole("heading", { name: "Your footage. Organized by AI." }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Your footage and data." }),
  ).toHaveCount(0);
});

async function authFixture(page: Page, signedIn = false) {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/providers") {
      await route.fulfill({ json: { google: true } });
    } else if (path === "/api/auth/me") {
      await route.fulfill({
        status: signedIn ? 200 : 401,
        json: signedIn
          ? { id: "u", name: "Synthetic account", email: "account@example.com" }
          : { detail: "Not signed in" },
      });
    } else if (path === "/api/workspaces") {
      await route.fulfill({
        json: [
          {
            id: "w",
            name: "Synthetic workspace",
            role: "owner",
            balance_milli: 0,
          },
        ],
      });
    } else if (path.endsWith("/projects")) {
      await route.fulfill({ json: { items: [], total: 0 } });
    } else if (path === "/api/auth/google/account") {
      await route.fulfill({
        json: { available: true, connected: false, email: null },
      });
    } else {
      // Account access must remain usable even if workspace settings fail.
      await route.fulfill({
        status: 503,
        json: { detail: "Synthetic workspace service unavailable" },
      });
    }
  });
}

for (const scenario of [
  {
    path: "/login?next=%2Fapp%3Fworkspace%3Dw%26project%3Dp",
    next: "/app?workspace=w&project=p",
  },
  {
    path: "/login?next=https%3A%2F%2Fexample.com%2Fsteal",
    next: "/onboarding",
  },
  { path: "/signup", next: "/onboarding" },
]) {
  test(`Google starts a real authorization navigation from ${scenario.path}`, async ({
    page,
  }) => {
    await authFixture(page);
    let authorizationUrl = "";
    await page.route("**/api/auth/google/authorize?**", async (route) => {
      authorizationUrl = route.request().url();
      await route.fulfill({
        contentType: "text/html",
        body: "<h1>Synthetic Google authorization</h1>",
      });
    });
    await page.goto(scenario.path);
    await page.getByRole("button", { name: "Continue with Google" }).click();
    await expect(
      page.getByRole("heading", { name: "Synthetic Google authorization" }),
    ).toBeVisible();
    expect(new URL(authorizationUrl).searchParams.get("next")).toBe(
      scenario.next,
    );
  });
}

test("email sign-in remains usable when Google is unavailable", async ({
  page,
}) => {
  await authFixture(page);
  await page.route("**/api/auth/providers", (route) =>
    route.fulfill({ json: { google: false } }),
  );
  let submitted = "";
  await page.route("**/api/auth/login", async (route) => {
    submitted = route.request().postData() || "";
    await route.fulfill({ json: { ok: true } });
  });
  await page.goto("/login");
  await expect(
    page.getByText(
      "Google sign-in is unavailable right now. Continue with email.",
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Continue with Google" }),
  ).toHaveCount(0);
  await page.getByLabel("Email", { exact: true }).fill("account@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("  significant spaces  ");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect.poll(() => submitted).not.toBe("");
  expect(new URLSearchParams(submitted).get("password")).toBe(
    "  significant spaces  ",
  );
});

test("provider discovery can recover without losing typed email", async ({
  page,
}) => {
  await authFixture(page);
  let available = false;
  await page.route("**/api/auth/providers", (route) =>
    available
      ? route.fulfill({ json: { google: true } })
      : route.fulfill({ status: 503, json: { detail: "Synthetic outage" } }),
  );
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill("account@example.com");
  await expect(
    page.getByText("Google sign-in couldn’t load.", { exact: false }),
  ).toBeVisible();
  available = true;
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Continue with Google" }),
  ).toBeEnabled();
  await expect(page.getByLabel("Email", { exact: true })).toHaveValue(
    "account@example.com",
  );
});

test("Google cancellation and existing-account recovery use explicit messages", async ({
  page,
}) => {
  await authFixture(page);
  await page.goto("/login?error=google_cancelled");
  await expect(page.getByRole("alert")).toContainText(
    "Google sign-in was canceled",
  );
  await expect(
    page.getByRole("button", { name: "Continue with Google" }),
  ).toBeEnabled();
  await page.goto("/login?error=google_link_required");
  await expect(page.getByRole("alert")).toContainText(
    "Sign in with your password, then connect Google in Settings",
  );
  await page.goto("/login?error=%3Cscript%3Euntrusted-error%3C%2Fscript%3E");
  await expect(
    page.getByRole("button", { name: "Continue with Google" }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("signed-in public and auth logos lead to the dashboard", async ({
  page,
}) => {
  await authFixture(page, true);
  await page.goto("/");
  await expect(
    page.getByRole("link", { name: "RUSHES dashboard", exact: true }),
  ).toHaveAttribute("href", "/app");
  await page.goto("/login");
  await expect(
    page.getByRole("link", { name: "RUSHES dashboard", exact: true }),
  ).toHaveAttribute("href", "/app");
});

test("password sign-in after a Google email match opens connection settings", async ({
  page,
}) => {
  await authFixture(page, true);
  await page.route("**/api/auth/login", (route) =>
    route.fulfill({ json: { ok: true } }),
  );
  await page.goto("/login?error=google_link_required");
  await page.getByLabel("Email", { exact: true }).fill("account@example.com");
  await page.getByLabel("Password", { exact: true }).fill("synthetic password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page
      .getByRole("region", { name: "Your sign-in" })
      .getByRole("button", { name: "Connect Google", exact: true }),
  ).toBeVisible();
  expect(new URL(page.url()).searchParams.get("view")).toBe("settings");
});

test("a failed account connection can retry and an expired session has a sign-in destination", async ({
  page,
}) => {
  await authFixture(page, true);
  let expired = false;
  await page.route("**/api/auth/google/link", (route) =>
    route.fulfill({
      status: expired ? 401 : 503,
      json: { detail: "Synthetic failure" },
    }),
  );
  await page.goto("/app?workspace=w&view=settings");
  const account = page.getByRole("region", { name: "Your sign-in" });
  const connect = account.getByRole("button", {
    name: "Connect Google",
    exact: true,
  });
  await connect.click();
  await expect(account.getByRole("alert")).toContainText(
    "Google couldn’t open",
  );
  await expect(connect).toBeEnabled();
  expired = true;
  await connect.click();
  await expect(account.getByRole("alert")).toContainText("Sign in again");
  await expect(
    account.getByRole("link", { name: "Sign in again", exact: true }),
  ).toHaveAttribute("href", "/login?next=%2Fapp%3Fview%3Dsettings");
  await expect(connect).toBeDisabled();
});

test("connecting an account submits once and navigates to the returned Google URL", async ({
  page,
}) => {
  await authFixture(page, true);
  let calls = 0;
  let finish: (() => void) | undefined;
  const responseReady = new Promise<void>((resolve) => {
    finish = resolve;
  });
  await page.route("**/api/auth/google/link", async (route) => {
    expect(route.request().method()).toBe("POST");
    calls += 1;
    await responseReady;
    await route.fulfill({
      json: {
        authorization_url:
          "https://accounts.google.com/o/oauth2/v2/auth?state=synthetic",
      },
    });
  });
  await page.route("https://accounts.google.com/**", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: "<h1>Synthetic Google connection</h1>",
    }),
  );
  await page.goto("/app?workspace=w&view=settings");
  const account = page.getByRole("region", { name: "Your sign-in" });
  const connect = account.getByRole("button", {
    name: "Connect Google",
    exact: true,
  });
  await expect(connect).toBeEnabled();
  await connect.evaluate((button: HTMLButtonElement) => {
    button.click();
    button.click();
  });
  await expect(
    account.getByRole("button", { name: "Opening Google…" }),
  ).toBeDisabled();
  await expect.poll(() => calls).toBe(1);
  finish!();
  await expect(
    page.getByRole("heading", { name: "Synthetic Google connection" }),
  ).toBeVisible();
  expect(calls).toBe(1);
});

test("Settings verifies linked state and preserves a canceled connection", async ({
  page,
}) => {
  await authFixture(page, true);
  await page.goto("/app?workspace=w&view=settings&google=linked");
  const account = page.getByRole("region", { name: "Your sign-in" });
  await expect(
    account.getByRole("button", { name: "Connect Google", exact: true }),
  ).toBeVisible();
  await expect(
    account.getByText("Google is connected.", { exact: false }),
  ).toHaveCount(0);
  await page.goto("/app?workspace=w&view=settings&google=cancelled");
  await expect(account.getByRole("status")).toContainText(
    "Connecting Google was canceled",
  );
  await expect(
    account.getByRole("button", { name: "Connect Google", exact: true }),
  ).toBeEnabled();
  await page.route("**/api/auth/google/account", (route) =>
    route.fulfill({
      json: {
        available: true,
        connected: true,
        email: "connected@example.com",
      },
    }),
  );
  await page.goto("/app?view=settings&google=linked");
  await expect(account.getByRole("status")).toContainText(
    "Google is connected",
  );
  await expect(
    account.getByText("connected@example.com", { exact: true }),
  ).toBeVisible();
  await expect(
    account.getByRole("button", { name: "Connect Google", exact: true }),
  ).toHaveCount(0);
});

test("a delayed Google link response cannot navigate after leaving Settings", async ({
  page,
}) => {
  await authFixture(page, true);
  let calls = 0;
  let finish: (() => void) | undefined;
  const responseReady = new Promise<void>((resolve) => {
    finish = resolve;
  });
  await page.route("**/api/auth/google/link", async (route) => {
    calls += 1;
    await responseReady;
    await route
      .fulfill({
        json: {
          authorization_url:
            "https://accounts.google.com/o/oauth2/v2/auth?state=late",
        },
      })
      .catch(() => {});
  });
  let navigations = 0;
  await page.route("https://accounts.google.com/**", async (route) => {
    navigations += 1;
    await route.fulfill({ body: "Unexpected navigation" });
  });
  await page.goto("/app?workspace=w&view=settings");
  await page
    .getByRole("button", { name: "Connect Google", exact: true })
    .click();
  await expect.poll(() => calls).toBe(1);
  const aborted = page.waitForEvent(
    "requestfailed",
    (request) => new URL(request.url()).pathname === "/api/auth/google/link",
  );
  await page
    .getByRole("link", { name: "RUSHES dashboard", exact: true })
    .click();
  await aborted;
  await expect(page).toHaveURL(/\/app\?workspace=w$/);
  finish!();
  await expect(
    page.getByRole("heading", { name: "Projects", exact: true }),
  ).toBeVisible();
  expect(navigations).toBe(0);
});

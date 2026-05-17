/** @type {import("dependency-cruiser").IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      severity: "error",
      comment: "Disallow circular dependencies.",
      from: {},
      to: { circular: true },
    },
    {
      name: "no-orphans",
      severity: "warn",
      comment: "Warn when modules are not reachable from any entrypoint.",
      from: {
        orphan: true,
        pathNot: "^src/app/|^src/components/agent/types\\.ts$",
      },
      to: {},
    },
    {
      name: "landing-not-to-admin",
      severity: "error",
      comment: "Landing UI must not depend on admin modules.",
      from: { path: "^src/components/landing/" },
      to: { path: "^src/components/admin/" },
    },
    {
      name: "admin-not-to-landing",
      severity: "error",
      comment: "Admin UI must stay isolated from landing modules.",
      from: { path: "^src/components/admin/" },
      to: { path: "^src/components/landing/" },
    },
    {
      name: "agent-not-to-landing",
      severity: "error",
      comment: "Reusable agent module must not depend on landing modules.",
      from: { path: "^src/components/agent/" },
      to: { path: "^src/components/landing/" },
    },
  ],
  options: {
    includeOnly: "^src",
    tsConfig: {
      fileName: "tsconfig.json",
    },
    doNotFollow: {
      path: "(^node_modules|^vendor/|^\\.next/)",
    },
    reporterOptions: {
      dot: {
        collapsePattern: "^src/[^/]+",
      },
    },
  },
};

export type ProductBentoCard = {
  color: string;
  title: string;
  description: string;
  label: string;
  fullText: string;
};

export const DEFAULT_PRODUCT_BENTO: ProductBentoCard[] = [
  {
    color: "#0c0d12",
    title: "Platform",
    description: "Unified stack for agents, memory, and orchestration.",
    label: "Core",
    fullText: "Router, skills, and knowledge in one control plane.",
  },
  {
    color: "#0c0d12",
    title: "Use Cases",
    description: "Support, ops, and internal copilots that execute work.",
    label: "Teams",
    fullText: "From triage to transactions across channels.",
  },
  {
    color: "#0c0d12",
    title: "Integrations",
    description: "CRM, tickets, data warehouses, and custom APIs.",
    label: "Connect",
    fullText: "Tool calls and webhooks to your real systems.",
  },
  {
    color: "#0c0d12",
    title: "Architecture",
    description: "RAG, routing layers, and observable agent flows.",
    label: "Design",
    fullText: "Composable graph with guardrails and audit trails.",
  },
  {
    color: "#0c0d12",
    title: "Voice AI",
    description: "Natural speech with low-latency models and voice UX.",
    label: "Speak",
    fullText: "Turn-taking, tools, and branded audio experiences.",
  },
  {
    color: "#0c0d12",
    title: "Automation",
    description: "Triggers, schedules, and end-to-end workflows.",
    label: "Run",
    fullText: "Agents that complete tasks, not only answer prompts.",
  },
];

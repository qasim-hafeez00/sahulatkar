// Mirrors the backend's RBACService._ROLE_MAP (apps/gateway/src/services/rbac.py) —
// the 8 canonical roles from Module 12's consolidation, plus "admin" as the
// defensive fallback for admin_users rows with no role assigned (never an
// assignable role via the Team & Access UI).
export type AdminRole =
  | "super_admin"
  | "operations_manager"
  | "risk_officer"
  | "compliance_officer"
  | "finance_analyst"
  | "cs_agent"
  | "analyst"
  | "marketing_manager"
  | "admin";

export type AdminModule = {
  id: string;
  label: string;
  href: string;
  roles: AdminRole[];
  group: string;
};

const ALL_ROLES: AdminRole[] = [
  "super_admin", "operations_manager", "risk_officer", "compliance_officer",
  "finance_analyst", "cs_agent", "analyst", "marketing_manager", "admin",
];

export const adminModules: AdminModule[] = [
  { id: "AD-01", label: "Dashboard Home", href: "/dashboard", roles: ALL_ROLES, group: "Command Center" },
  { id: "AD-02", label: "Users", href: "/dashboard/users", roles: ["super_admin", "operations_manager", "risk_officer", "cs_agent", "compliance_officer"], group: "Operations" },
  { id: "AD-03", label: "User Profiles", href: "/dashboard/users", roles: ["super_admin", "operations_manager", "risk_officer", "cs_agent", "compliance_officer"], group: "Operations" },
  { id: "AD-04", label: "Orders", href: "/dashboard/orders", roles: ["super_admin", "operations_manager", "cs_agent"], group: "Operations" },
  { id: "AD-05", label: "Order Detail", href: "/dashboard/orders", roles: ["super_admin", "operations_manager", "cs_agent"], group: "Operations" },
  { id: "AD-06", label: "Payments", href: "/dashboard/payments", roles: ["super_admin", "operations_manager", "finance_analyst"], group: "Operations" },
  { id: "AD-07", label: "Payment Restructuring", href: "/dashboard/payments", roles: ["super_admin", "operations_manager"], group: "Operations" },
  { id: "AD-08", label: "HITL Queue", href: "/dashboard/hitl", roles: ["super_admin", "operations_manager"], group: "Operations" },
  { id: "AD-09", label: "Case Detail", href: "/dashboard/hitl", roles: ["super_admin", "operations_manager"], group: "Operations" },
  { id: "AD-10", label: "Risk Alerts", href: "/dashboard/risk", roles: ["super_admin", "risk_officer", "analyst"], group: "Risk" },
  { id: "AD-11", label: "Manual Underwriting", href: "/dashboard/risk", roles: ["super_admin", "risk_officer", "analyst"], group: "Risk" },
  { id: "AD-12", label: "Blacklist & Monitoring", href: "/dashboard/risk", roles: ["super_admin", "risk_officer"], group: "Risk" },
  { id: "AD-13", label: "Finance", href: "/dashboard/finance", roles: ["super_admin", "finance_analyst", "analyst"], group: "Finance" },
  { id: "AD-14", label: "Shariah Compliance", href: "/dashboard/finance", roles: ["super_admin", "compliance_officer", "finance_analyst"], group: "Finance" },
  { id: "AD-15", label: "Reconciliation", href: "/dashboard/finance", roles: ["super_admin", "finance_analyst", "analyst"], group: "Finance" },
  { id: "AD-16", label: "Support Tickets", href: "/dashboard/support", roles: ["super_admin", "cs_agent"], group: "Support" },
  { id: "AD-17", label: "Ticket Detail", href: "/dashboard/support", roles: ["super_admin", "cs_agent"], group: "Support" },
  { id: "AD-18", label: "Compliance", href: "/dashboard/compliance", roles: ["super_admin", "compliance_officer"], group: "Compliance" },
  { id: "AD-19", label: "Audit Trail", href: "/dashboard/compliance", roles: ["super_admin", "compliance_officer"], group: "Compliance" },
  { id: "AD-20", label: "KYC Review", href: "/dashboard/compliance", roles: ["super_admin", "compliance_officer"], group: "Compliance" },
  { id: "AD-21", label: "Analytics", href: "/dashboard/analytics", roles: ["super_admin", "finance_analyst", "marketing_manager", "analyst"], group: "Analytics" },
  { id: "AD-22", label: "Cohorts & Funnels", href: "/dashboard/analytics", roles: ["super_admin", "marketing_manager", "analyst"], group: "Analytics" },
  { id: "AD-23", label: "Custom Reports", href: "/dashboard/analytics", roles: ["super_admin", "marketing_manager", "analyst"], group: "Analytics" },
  { id: "AD-24", label: "Merchants", href: "/dashboard/partners", roles: ["super_admin", "operations_manager", "marketing_manager"], group: "Platform" },
  { id: "AD-25", label: "Team & Access", href: "/dashboard/admins", roles: ["super_admin"], group: "Platform" },
  { id: "AD-26", label: "System Settings", href: "/dashboard/settings", roles: ["super_admin", "operations_manager"], group: "Platform" },
  { id: "AD-27", label: "Platform Operations", href: "/dashboard/platform", roles: ["super_admin", "operations_manager", "risk_officer"], group: "Platform" },
  { id: "AD-28", label: "System Health", href: "/dashboard/platform", roles: ["super_admin", "operations_manager", "risk_officer"], group: "Platform" },

  // Phase 4 — thin-spec modules (minimal-but-real, built against existing schema)
  { id: "AD-29", label: "Marketing & Growth", href: "/dashboard/marketing", roles: ["super_admin", "marketing_manager"], group: "Growth & Tools" },
  { id: "AD-30", label: "API & Developer Tools", href: "/dashboard/developer", roles: ["super_admin", "operations_manager"], group: "Growth & Tools" },
  { id: "AD-31", label: "Notification Center", href: "/dashboard/notifications", roles: ["super_admin", "operations_manager", "marketing_manager"], group: "Growth & Tools" },
  { id: "AD-32", label: "Document Management", href: "/dashboard/documents", roles: ["super_admin", "compliance_officer", "cs_agent"], group: "Growth & Tools" },
  { id: "AD-33", label: "Logs & Audit Trail", href: "/dashboard/logs", roles: ["super_admin", "operations_manager"], group: "Growth & Tools" },
  { id: "AD-34", label: "Reporting Engine", href: "/dashboard/reports", roles: ["super_admin", "finance_analyst", "compliance_officer", "analyst"], group: "Growth & Tools" },
  { id: "AD-35", label: "Help & Documentation", href: "/dashboard/help", roles: ALL_ROLES, group: "Growth & Tools" },
];

export function getVisibleModules(role: AdminRole) {
  return adminModules.filter((module) => module.roles.includes(role));
}

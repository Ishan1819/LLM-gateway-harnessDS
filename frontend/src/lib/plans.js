/**
 * Plan metadata for the UI. The backend is the source of truth for what a plan
 * unlocks (it serves `features` on the session), so this file only carries
 * presentation concerns: ordering, accent colour, and marketing copy.
 */

export const PLAN_ORDER = ['free', 'standard', 'premium']

export const PLAN_META = {
  free: { name: 'Free', price: 0, accent: '#94a3b8', tagline: 'See where the money goes.' },
  standard: { name: 'Standard', price: 49, accent: '#3b82f6', tagline: 'Control it, team by team.' },
  premium: { name: 'Premium', price: 199, accent: '#8b5cf6', tagline: 'Spend less for the same work.' },
}

/** Feature keys — must match app/utils/plans.py. */
export const FEATURES = {
  DASHBOARD: 'dashboard',
  USER_CAPS: 'user_caps',
  TEAM_CAPS: 'team_caps',
  ALERTS: 'alerts',
  SAVINGS: 'savings',
  OPTIMIZER: 'optimizer',
  CUSTOM_PRICING: 'custom_pricing',
}

export const FEATURE_LABELS = {
  [FEATURES.DASHBOARD]: 'Usage dashboard',
  [FEATURES.USER_CAPS]: 'Per-user caps',
  [FEATURES.TEAM_CAPS]: 'Team caps',
  [FEATURES.ALERTS]: 'Budget alerts',
  [FEATURES.SAVINGS]: 'Savings report',
  [FEATURES.OPTIMIZER]: 'Cost Optimizer',
  [FEATURES.CUSTOM_PRICING]: 'Custom pricing table',
}

/** Cheapest plan that includes a feature — drives "available on X" copy. */
export function requiredPlanFor(feature) {
  const membership = {
    free: [FEATURES.DASHBOARD, FEATURES.USER_CAPS],
    standard: [
      FEATURES.DASHBOARD,
      FEATURES.USER_CAPS,
      FEATURES.TEAM_CAPS,
      FEATURES.ALERTS,
      FEATURES.SAVINGS,
    ],
    premium: Object.values(FEATURES),
  }
  return PLAN_ORDER.find((plan) => membership[plan].includes(feature)) || 'premium'
}

export function hasFeature(organization, feature) {
  return (organization?.features || []).includes(feature)
}

/** Comparison matrix rendered on upgrade screens and in Settings. */
export const COMPARISON = [
  { label: 'Tracked developers', free: 'Up to 5', standard: 'Up to 50', premium: 'Unlimited' },
  { label: 'Usage history', free: '7 days', standard: '90 days', premium: 'Unlimited' },
  { label: 'Spend dashboard', free: true, standard: true, premium: true },
  { label: 'Per-user caps', free: true, standard: true, premium: true },
  { label: 'Teams & team caps', free: false, standard: true, premium: true },
  { label: 'Budget alerts (80% / 90%)', free: false, standard: true, premium: true },
  { label: 'Savings report & projections', free: false, standard: true, premium: true },
  { label: 'Cost Optimizer', free: false, standard: false, premium: true },
  { label: 'Model right-sizing estimates', free: false, standard: false, premium: true },
  { label: 'Repeat-prompt detection', free: false, standard: false, premium: true },
  { label: 'Editable pricing table', free: false, standard: false, premium: true },
]

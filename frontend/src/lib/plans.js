/**
 * Plan metadata for the Plans & pricing page.
 *
 * Plans are presentational: they describe what each tier includes so a buyer
 * can compare them. They do not gate anything — every page of the product is
 * reachable regardless of tier.
 */

export const PLAN_ORDER = ['free', 'standard', 'premium']

export const PLAN_META = {
  free: { name: 'Free', price: 0, accent: '#94a3b8', tagline: 'See where the money goes.' },
  standard: { name: 'Standard', price: 49, accent: '#3b82f6', tagline: 'Control it, team by team.' },
  premium: { name: 'Premium', price: 199, accent: '#8b5cf6', tagline: 'Spend less for the same work.' },
}

/** Comparison matrix rendered on the Plans & pricing page. */
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

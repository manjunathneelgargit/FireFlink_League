export type DailyStatus =
  | 'Not Started' | 'In Progress' | 'Target Pending Today' | 'Target Achieved' | 'Target Missed'
  | 'Carry-Forward Pending'

export interface DayEntry {
  date: string; required: number; done: number; pending_before: number; closed: boolean
  status: DailyStatus; pending_after: number | null; projected_pending?: number
}

export interface DailyBD {
  bd_id: number; bd_name: string; days: DayEntry[]; today: DayEntry | null; current_pending: number
  next_target_date: string | null; next_required: number | null; targets_assigned: number
  targets_achieved: number; targets_missed: number; achievement_rate: number | null
  current_streak: number; best_streak: number; outstanding_carry_forward: number | null
}

export interface Daily {
  today: string; is_working_day: boolean; within_league: boolean; league_over: boolean
  today_closed: boolean | null; manually_closed_today: boolean; cutoff: string
  per_bd: Record<string, DailyBD>
}

export interface OverallRow {
  bd_id: number; bd_name: string; total: number; f2f: number; virtual: number; untyped: number; rank: number
  previous_rank: number | null; movement: number; achievement_rate: number | null; current_pending: number
  revenue_inr: number; scheduled: number; is_leader: boolean; is_lowest: boolean
}

export interface F2FRow { bd_id: number; bd_name: string; f2f: number; scheduled_f2f: number; rank: number }

export interface F2F {
  target: number; achieved: number; remaining: number; percent: number
  milestones: { value: number; reached: boolean }[]
  per_region: Record<string, number>; leaderboard: F2FRow[]; leaders: F2FRow[]
  scheduled_pipeline: { total: number; by_region: Record<string, number> }
  completed_unqualified_in_regions: number; qualified_f2f_outside_regions: number
  windows: { regions: string[]; start: string; end: string }[]
}

export interface RevenueBD {
  bd_id: number; bd_name: string; total_inr: number; signed_inr: number; credited_inr: number; records: number
  pending_conversion: number; rank: number; award_eligible: boolean; gap_to_leader: number; gap_to_threshold: number
}

export interface RevenueSummary {
  total_inr: number; threshold_inr: number; per_bd: RevenueBD[]
  champions: { bd_id: number; bd_name: string; total_inr: number; prize_share_inr: number }[]
  tie: boolean; by_country: Record<string, number>; by_domain?: Record<string, number>
  by_status: Record<string, number>; by_currency: Record<string, number>; pending_conversion_count: number
}

export interface Finalized { id: number; result: any; notes: string | null; finalized_at: string; finalized_by: string }

export interface Week {
  week_no: number; key: string; start: string; end: string; announce_on: string; label: string
  state: 'upcoming' | 'in_progress' | 'awaiting_finalization' | 'finalized'
  standings: { bd_id: number; bd_name: string; total: number; f2f: number; virtual: number; rank: number }[]
  leaders: { bd_id: number; bd_name: string; total: number }[]; tie: boolean; finalized: Finalized | null
}

export interface Leader { bd_id: number; bd_name: string; total?: number; f2f?: number }

export interface Awards {
  weekly_demo: {
    title: string; prize: string | null
    current_week: Pick<Week, 'key' | 'label' | 'start' | 'end' | 'announce_on'> | null
    provisional_leaders: Leader[]; current_tie: boolean
    previous_week: (Pick<Week, 'key' | 'label' | 'start' | 'end' | 'announce_on' | 'state' | 'leaders' | 'tie' | 'finalized'>) | null
  }
  league_champion: { title: string; prize: string | null; leaders: Leader[]; tie: boolean; state: string; finalized: Finalized | null }
  revenue: {
    title: string; prize: string | null; champions: RevenueSummary['champions']; tie: boolean; threshold_inr: number
    eligible_count: number; state: string; finalized: Finalized | null
  }
  f2f: { title: string; prize: string | null; leaders: Leader[]; tie: boolean; tie_note: string | null; state: string; finalized: Finalized | null }
}

export interface Activity { id: number; at: string; kind: string; message: string; bd_id: number | null; actor: string | null; meta: any }

export interface League {
  name: string; start: string; end: string; end_at: string; now: string; days_left: number
  working_days_total: number; working_days_left: number; phase: 'before' | 'live' | 'after'; f2f_target: number
  timezone: string; cutoff: string; office_login: string; standup: string; motivational_messages: string[]
  arena_refresh_seconds: number
}

export interface Kpis {
  qualified_completed: number; qualified_f2f: number; qualified_virtual: number; scheduled: number
  scheduled_f2f: number; scheduled_virtual: number; completed_unqualified: number; targets_assigned: number
  targets_achieved: number; targets_missed: number; target_achievement_rate: number | null
  outstanding_carry_forward: number; on_target_today: number; f2f_progress: number; total_revenue_inr: number
  bd_count: number
}

export interface Snapshot {
  league: League; kpis: Kpis; daily: Daily; overall: OverallRow[]; f2f: F2F; revenue: RevenueSummary
  weeks: Week[]; awards: Awards; activity: Activity[]; sync?: SyncInfo
}

export interface SyncInfo {
  enabled: boolean; url?: string; interval?: number; last_success: string | null; last_attempt?: string | null
  last_change?: string | null; error: string | null
}

export interface Demo {
  id: string; sl_no: number | null; bd_id: number; bd_name: string; customer_name: string; domain: string | null
  country: string | null; city: string | null; demo_type: 'F2F' | 'Virtual' | null; effective_type: 'F2F' | 'Virtual' | null
  demo_on: string | null; demo_date: string | null
  demo_time: string | null; time_zone: string | null; time_remaining: string; time_remaining_seconds: number | null
  demo_at: string | null; status: string; qualified: 'Yes' | 'No' | null; counts: boolean; counts_f2f: boolean
  achieved: boolean; in_league: boolean; region: string | null; poc_started_on: string | null
  poc_status_updated_at: string | null; poc_remarks: string | null; source: string; created_at: string
  updated_at: string; deleted_at: string | null
}

export interface RevenueEval {
  eligible: boolean; reason: string | null; inr_value: number | null; rate_used: number | null
  rate_date: string | null; rate_basis: string | null; pending_conversion: boolean; eligibility_date: string | null
}

export interface Revenue {
  id: string; sl_no: number | null; bd_id: number; bd_name: string; customer_name: string; country: string | null
  domain: string | null; opportunity_name: string; contract_status: 'Signed' | 'Amount Credited'; currency: string
  contract_value: number; contract_signed_date: string | null; amount_credited_date: string | null
  customer_onboarding_date: string | null; remarks: string | null; fx_rate_override: number | null
  fx_rate_override_date: string | null; evaluation: RevenueEval; source: string; created_at: string
  updated_at: string; deleted_at: string | null
}

export interface Meta {
  bds: { id: number; name: string; active: boolean }[]; demo_types: string[]; demo_statuses: string[]
  poc_statuses: string[]; demo_on_options: string[]; contract_statuses: string[]; opportunity_options: string[]
  currencies: string[]; domains: string[]; countries: string[]; regions: string[]; timezone: string
  live_mode: boolean; sheet_url: string | null
}

export interface Team { id: number; name: string; slug: string; active: boolean }
export interface Me { username: string; role: 'super_admin' | 'team_admin'; is_super: boolean; team: Team; teams: Team[] }

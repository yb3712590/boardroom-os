import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { InboxWell } from '../../../components/dashboard/InboxWell'

describe('InboxWell', () => {
  it('routes review and incident items to their matching callbacks', async () => {
    const user = userEvent.setup()
    const onOpenReview = vi.fn()
    const onOpenIncident = vi.fn()

    render(
      <InboxWell
        loading={false}
        onOpenReview={onOpenReview}
        onOpenIncident={onOpenIncident}
        items={[
          {
            inbox_item_id: 'inbox_review',
            workflow_id: 'wf_001',
            item_type: 'review',
            priority: 'high',
            status: 'PENDING',
            created_at: '2026-04-04T12:00:00+08:00',
            title: 'Board review ready',
            summary: 'Open the review room.',
            source_ref: 'brp_001',
            route_target: {
              view: 'review_room',
              review_pack_id: 'brp_001',
            },
            badges: ['Review'],
          },
          {
            inbox_item_id: 'inbox_incident',
            workflow_id: 'wf_001',
            item_type: 'incident',
            priority: 'critical',
            status: 'PENDING',
            created_at: '2026-04-04T12:01:00+08:00',
            title: 'Incident open',
            summary: 'Open the incident drawer.',
            source_ref: 'inc_001',
            route_target: {
              view: 'incident_detail',
              incident_id: 'inc_001',
            },
            badges: ['Incident'],
          },
        ]}
      />,
    )

    await user.click(screen.getByRole('button', { name: /Board review ready/i }))
    await user.click(screen.getByRole('button', { name: /Incident open/i }))

    expect(onOpenReview).toHaveBeenCalledWith('brp_001')
    expect(onOpenIncident).toHaveBeenCalledWith('inc_001')
  })
})

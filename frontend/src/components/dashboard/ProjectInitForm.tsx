import { useState } from 'react'

import { Button } from '../shared/Button'

type ProjectInitFormProps = {
  submitting: boolean
  onSubmit: (payload: {
    northStarGoal: string
    hardConstraints: string[]
    budgetCap: number
  }) => Promise<void>
}

function normalizeConstraints(value: string) {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function ProjectInitForm({ submitting, onSubmit }: ProjectInitFormProps) {
  const [goal, setGoal] = useState('Ship the thinnest governance shell from dashboard to review room.')
  const [constraints, setConstraints] = useState(
    'Keep governance explicit.\nDo not move workflow truth into the browser.',
  )
  const [budgetCap, setBudgetCap] = useState('500000')

  return (
    <section className="project-init-panel" aria-labelledby="project-init-title">
      <div className="project-init-copy">
        <p className="eyebrow">Workflow Init</p>
        <h1 id="project-init-title">Launch workflow to first review</h1>
        <p>
          The backend still owns workflow truth. This entry now opens the next workflow, drafts the first scope
          decision, and pushes it through to the first board review.
        </p>
      </div>
      <form
        className="project-init-form"
        onSubmit={(event) => {
          event.preventDefault()
          void onSubmit({
            northStarGoal: goal.trim(),
            hardConstraints: normalizeConstraints(constraints),
            budgetCap: Number.parseInt(budgetCap, 10) || 0,
          })
        }}
      >
        <label>
          <span className="field-label">North star goal</span>
          <textarea value={goal} onChange={(event) => setGoal(event.target.value)} rows={4} />
        </label>
        <label>
          <span className="field-label">Hard constraints</span>
          <textarea value={constraints} onChange={(event) => setConstraints(event.target.value)} rows={5} />
        </label>
        <label>
          <span className="field-label">Budget cap</span>
          <input type="number" min="0" value={budgetCap} onChange={(event) => setBudgetCap(event.target.value)} />
        </label>
        <Button type="submit" variant="primary" loading={submitting} disabled={goal.trim().length === 0}>
          {submitting ? 'Advancing to first review...' : 'Launch to first review'}
        </Button>
      </form>
    </section>
  )
}

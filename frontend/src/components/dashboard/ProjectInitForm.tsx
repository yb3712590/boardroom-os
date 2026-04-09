import { useState } from 'react'

import { Button } from '../shared/Button'
import { normalizeConstraints } from '../../utils/format'

type ProjectInitFormProps = {
  submitting: boolean
  onSubmit: (payload: {
    northStarGoal: string
    hardConstraints: string[]
    budgetCap: number
    forceRequirementElicitation: boolean
  }) => Promise<void>
}

export function ProjectInitForm({ submitting, onSubmit }: ProjectInitFormProps) {
  const [goal, setGoal] = useState('Ship the thinnest governance shell from dashboard to review room.')
  const [constraints, setConstraints] = useState(
    'Keep governance explicit.\nDo not move workflow truth into the browser.',
  )
  const [budgetCap, setBudgetCap] = useState('500000')
  const [forceRequirementElicitation, setForceRequirementElicitation] = useState(false)

  return (
    <section className="project-init-panel" aria-labelledby="project-init-title">
      <div className="project-init-copy">
        <p className="eyebrow">Workflow init</p>
        <h1 id="project-init-title">Launch workflow to first review</h1>
        <p>
          The backend still owns workflow truth. This creates a new workflow, generates the first scope decision, and pushes it to the first board review gate.
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
            forceRequirementElicitation,
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
        <label>
          <span className="field-label">Startup route</span>
          <span className="checkbox-field">
            <input
              type="checkbox"
              aria-label="Route through requirement elicitation first"
              checked={forceRequirementElicitation}
              onChange={(event) => setForceRequirementElicitation(event.target.checked)}
            />
            <span>Route through requirement elicitation first</span>
          </span>
        </label>
        <Button type="submit" variant="primary" loading={submitting} disabled={goal.trim().length === 0}>
          {submitting ? 'Launching to first review…' : 'Launch to first review'}
        </Button>
      </form>
    </section>
  )
}

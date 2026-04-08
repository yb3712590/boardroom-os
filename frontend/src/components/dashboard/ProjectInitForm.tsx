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
  const [goal, setGoal] = useState('从仪表盘到评审室，交付最薄可用的治理壳。')
  const [constraints, setConstraints] = useState(
    '治理流程必须显式可审计。\n工作流真相不得迁移到浏览器。',
  )
  const [budgetCap, setBudgetCap] = useState('500000')
  const [forceRequirementElicitation, setForceRequirementElicitation] = useState(false)

  return (
    <section className="project-init-panel" aria-labelledby="project-init-title">
      <div className="project-init-copy">
        <p className="eyebrow">工作流初始化</p>
        <h1 id="project-init-title">启动到首个董事会评审</h1>
        <p>
          后端仍然负责工作流真相。这里会创建新工作流、生成首个范围决议，并推进到第一道董事会评审闸门。
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
          <span className="field-label">北极星目标</span>
          <textarea value={goal} onChange={(event) => setGoal(event.target.value)} rows={4} />
        </label>
        <label>
          <span className="field-label">硬约束</span>
          <textarea value={constraints} onChange={(event) => setConstraints(event.target.value)} rows={5} />
        </label>
        <label>
          <span className="field-label">预算上限</span>
          <input type="number" min="0" value={budgetCap} onChange={(event) => setBudgetCap(event.target.value)} />
        </label>
        <label>
          <span className="field-label">启动路由</span>
          <span className="checkbox-field">
            <input
              type="checkbox"
              aria-label="先进入需求澄清回合"
              checked={forceRequirementElicitation}
              onChange={(event) => setForceRequirementElicitation(event.target.checked)}
            />
            <span>先进入需求澄清回合</span>
          </span>
        </label>
        <Button type="submit" variant="primary" loading={submitting} disabled={goal.trim().length === 0}>
          {submitting ? '正在推进到首评审…' : '启动并推进到首评审'}
        </Button>
      </form>
    </section>
  )
}

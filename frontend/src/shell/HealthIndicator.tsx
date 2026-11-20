import { useHealth } from '../api/health'
import { DOT, modelStatusText, type State } from './modelStatus'

function Item({ state, text, title }: { state: State; text: string; title?: string }) {
  return (
    <span className={`health health-${state}`} title={title}>
      <span aria-hidden="true">{DOT[state]}</span> {text}
    </span>
  )
}

/** Backend connected / not connected, plus the local model's status from /health. */
export function HealthIndicator() {
  const health = useHealth()
  if (health.isPending) {
    return (
      <p className="health-bar" role="status">
        <Item state="checking" text="Checking backend…" />
      </p>
    )
  }
  if (health.isError) {
    return (
      <p className="health-bar" role="status">
        <Item state="down" text="Backend not connected" />
      </p>
    )
  }
  const model = health.data.model
  const modelStatus = model ? modelStatusText(model) : null
  return (
    <p className="health-bar" role="status">
      <Item state="ok" text="Backend connected" />
      {modelStatus && <Item state={modelStatus.state} text={modelStatus.text} title={model?.error ?? undefined} />}
      {model?.error && !model.reachable && <span className="health-error">{model.error}</span>}
    </p>
  )
}

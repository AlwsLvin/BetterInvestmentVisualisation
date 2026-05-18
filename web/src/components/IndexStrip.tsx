import { MiniIndexCard } from './MiniIndexCard'

export interface StripIndex {
  code: string
  label: string
}

interface Props {
  indices: StripIndex[]
  onSelect: (code: string) => void
}

export function IndexStrip({ indices, onSelect }: Props) {
  return (
    <div className="grid grid-flow-col auto-cols-fr gap-2">
      {indices.map(idx => (
        <MiniIndexCard
          key={idx.code}
          symbol={idx.code}
          label={idx.label}
          onClick={() => onSelect(idx.code)}
        />
      ))}
    </div>
  )
}

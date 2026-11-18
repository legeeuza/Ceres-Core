import { useState } from 'react'
import TacticaKareem from './TacticaKareem'
import TableroEmilio from './TableroEmilio'

type Pestana = 'kareem' | 'emilio'

export default function App() {
  const [pestana, setPestana] = useState<Pestana>('emilio')
  const clase = (p: Pestana) =>
    `px-4 py-2 rounded-t font-medium ${pestana === p ? 'bg-green-700 text-white' : 'bg-gray-200 text-gray-700'}`
  return (
    <main className="p-4">
      <h1 className="text-2xl font-bold mb-3">Hackathon NFL UNAM</h1>
      <nav className="flex gap-1 border-b border-green-700 mb-4">
        <button className={clase('kareem')} onClick={() => setPestana('kareem')}>Táctica + IA</button>
        <button className={clase('emilio')} onClick={() => setPestana('emilio')}>Tablero y Fatiga</button>
      </nav>
      {pestana === 'kareem' ? <TacticaKareem /> : <TableroEmilio />}
    </main>
  )
}

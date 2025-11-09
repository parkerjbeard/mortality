import { ChangeEvent, useState } from 'react'
import { NormalizedBundle, parseBundle } from '@/lib/bundle'

interface BundleLoaderProps {
  onLoaded: (bundle: NormalizedBundle) => void
}

const samples = [
  { label: 'Countdown Solo', path: '/samples/demo-countdown-self.json' },
  { label: 'Staggered Town', path: '/samples/demo-staggered-deaths.json' },
]

export const BundleLoader = ({ onLoaded }: BundleLoaderProps) => {
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const [message, setMessage] = useState<string>('')

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setStatus('loading')
    setMessage(`Loading ${file.name}…`)
    try {
      const text = await file.text()
      const bundle = parseBundle(text)
      onLoaded(bundle)
      setMessage(`Loaded ${file.name}`)
      setStatus('idle')
    } catch (error) {
      console.error(error)
      setStatus('error')
      setMessage(`Failed to load bundle: ${(error as Error).message}`)
    } finally {
      event.target.value = ''
    }
  }

  const loadSample = async (path: string) => {
    setStatus('loading')
    setMessage(`Fetching ${path}…`)
    try {
      const response = await fetch(path)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const json = await response.json()
      const bundle = parseBundle(json)
      onLoaded(bundle)
      setStatus('idle')
      setMessage(`Loaded sample "${path.split('/').pop()}"`)
    } catch (error) {
      console.error(error)
      setStatus('error')
      setMessage(`Failed to load sample: ${(error as Error).message}`)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <label className="relative inline-flex cursor-pointer items-center justify-center rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-sm font-medium text-slate-100 transition hover:border-white/30 hover:bg-white/10">
        <input type="file" accept="application/json" className="absolute inset-0 cursor-pointer opacity-0" onChange={handleFile} />
        Upload Bundle
      </label>
      <div className="flex flex-wrap gap-2">
        {samples.map((sample) => (
          <button
            key={sample.path}
            type="button"
            onClick={() => loadSample(sample.path)}
            className="rounded-full bg-slate-800/40 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:bg-slate-700/60"
          >
            Load {sample.label}
          </button>
        ))}
      </div>
      <span
        className={`text-xs ${status === 'error' ? 'text-rose-300' : status === 'loading' ? 'text-slate-300' : 'text-slate-500'}`}
        aria-live="polite"
      >
        {message || 'Drop in a telemetry bundle to begin'}
      </span>
    </div>
  )
}

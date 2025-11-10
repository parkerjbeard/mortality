import { ChangeEvent, useState } from 'react'
import { NormalizedBundle, parseBundle } from '@/lib/bundle'

interface BundleLoaderProps {
  onLoaded: (bundle: NormalizedBundle) => void
}

export const BundleLoader = ({ onLoaded }: BundleLoaderProps) => {
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const [message, setMessage] = useState<string>(
    'Drop an emergent-timers bundle (.json) to begin',
  )

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

  return (
    <div className="flex flex-wrap items-center gap-3">
      <label className="relative inline-flex cursor-pointer items-center justify-center rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-sm font-medium text-slate-100 transition hover:border-white/30 hover:bg-white/10">
        <input
          type="file"
          accept="application/json"
          className="absolute inset-0 cursor-pointer opacity-0"
          onChange={handleFile}
        />
        Upload Emergent Run
      </label>
      <p className="text-xs text-slate-500">
        Tip: run <code>just emergent-run</code> to emit a new bundle in{' '}
        <code>runs/</code>.
      </p>
      <span
        className={`text-xs ${status === 'error' ? 'text-rose-300' : status === 'loading' ? 'text-slate-300' : 'text-slate-500'}`}
        aria-live="polite"
      >
        {message}
      </span>
    </div>
  )
}

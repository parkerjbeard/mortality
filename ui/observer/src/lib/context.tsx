import { createContext, useContext } from 'react'
import { NormalizedBundle } from './bundle'

interface BundleContextValue {
  bundle: NormalizedBundle | null
  setBundle: (value: NormalizedBundle | null) => void
}

export const BundleContext = createContext<BundleContextValue | undefined>(undefined)

export const useBundle = (): BundleContextValue => {
  const context = useContext(BundleContext)
  if (!context) {
    throw new Error('useBundle must be used within a BundleProvider')
  }
  return context
}

import { createContext, useContext } from 'react'
import { useGranaliaData } from './granalia/useGranaliaData'

const GranaliaContext = createContext(null)

export function GranaliaProvider({ children }) {
  const value = useGranaliaData()
  return <GranaliaContext.Provider value={value}>{children}</GranaliaContext.Provider>
}

export function useGranalia() {
  const context = useContext(GranaliaContext)
  if (!context) {
    throw new Error('useGranalia must be used within a GranaliaProvider')
  }
  return context
}

import React from 'react'
import { PropertyEvaluator } from './components/PropertyEvaluator'

export const App: React.FC = () => {
  return (
    <div className="min-h-screen bg-[#fafafa] flex flex-col justify-between p-4 sm:p-8 md:p-12 selection:bg-neutral-200">
      {/* Top Header - Ultra Minimalist */}
      <header className="max-w-4xl w-full mx-auto flex items-center justify-between py-2">
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-neutral-900" />
          <span className="font-semibold text-sm tracking-tight text-neutral-900">valuer.ca</span>
        </div>
        <span className="text-xs text-neutral-400">In-Browser ML</span>
      </header>

      {/* Main Spacious Canvas */}
      <main className="flex-1 max-w-4xl w-full mx-auto flex flex-col justify-center py-12 sm:py-20">
        <div className="text-center max-w-lg mx-auto mb-10 sm:mb-14">
          <h1 className="text-3xl sm:text-4xl md:text-5xl font-semibold tracking-tight text-neutral-900">
            Real estate discount finder.
          </h1>
          <p className="text-sm sm:text-base text-neutral-400 mt-3 font-normal">
            Enter any address in Greater Vancouver or Fraser Valley to see if it is priced at a discount.
          </p>
        </div>

        {/* Central Component */}
        <PropertyEvaluator />
      </main>

      {/* Footer - Minimal */}
      <footer className="max-w-4xl w-full mx-auto text-center py-6 text-xs text-neutral-400 border-t border-neutral-100/80">
        <p>100% In-browser machine learning inference • No backend API calls • Greater Vancouver & Fraser Valley</p>
      </footer>
    </div>
  )
}

export default App

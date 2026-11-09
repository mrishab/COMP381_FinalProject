import React, { useState } from 'react'
import { SlidersHorizontal, ChevronDown, ChevronUp } from 'lucide-react'
import { PropertySpecs } from '../services/propertyLookup'
import { Input } from './ui/input'
import { Button } from './ui/button'

interface SpecsDisplayProps {
  specs: PropertySpecs
  onChange: (updated: PropertySpecs) => void
}

export const SpecsDisplay: React.FC<SpecsDisplayProps> = ({ specs, onChange }) => {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div className="w-full">
      {/* Minimalistic Inline Stats Bar */}
      <div className="flex flex-wrap items-center justify-between text-xs sm:text-sm text-neutral-500 py-3 border-y border-neutral-100">
        <div className="flex items-center gap-3 sm:gap-5 flex-wrap">
          <span><strong className="text-neutral-800 font-medium">{specs.bedrooms}</strong> beds</span>
          <span>•</span>
          <span><strong className="text-neutral-800 font-medium">{specs.bathrooms}</strong> baths</span>
          <span>•</span>
          <span><strong className="text-neutral-800 font-medium">{specs.squareFootage.toLocaleString()}</strong> sqft</span>
          <span>•</span>
          <span><strong className="text-neutral-800 font-medium">{specs.propertyType}</strong></span>
          <span className="hidden sm:inline">•</span>
          <span className="hidden sm:inline">Built <strong className="text-neutral-800 font-medium">{specs.yearBuilt}</strong></span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setIsOpen(!isOpen)}
          className="h-7 px-2 text-xs text-neutral-500 hover:text-neutral-800 gap-1 mt-2 sm:mt-0"
        >
          <SlidersHorizontal className="w-3.5 h-3.5" />
          <span>{isOpen ? 'Close' : 'Fine-Tune Specs'}</span>
          {isOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </Button>
      </div>

      {/* Subtle Collapsible Adjustment Panel */}
      {isOpen && (
        <div className="mt-4 p-4 rounded-2xl bg-neutral-50/70 border border-neutral-200/60 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div>
            <label className="block text-neutral-500 mb-1 font-medium">Bedrooms</label>
            <Input
              type="number"
              min={1}
              max={10}
              value={specs.bedrooms}
              onChange={e => onChange({ ...specs, bedrooms: Number(e.target.value) || 1 })}
              className="h-8 text-xs bg-white"
            />
          </div>
          <div>
            <label className="block text-neutral-500 mb-1 font-medium">Bathrooms</label>
            <Input
              type="number"
              min={1}
              max={10}
              value={specs.bathrooms}
              onChange={e => onChange({ ...specs, bathrooms: Number(e.target.value) || 1 })}
              className="h-8 text-xs bg-white"
            />
          </div>
          <div>
            <label className="block text-neutral-500 mb-1 font-medium">Square Footage</label>
            <Input
              type="number"
              step={50}
              value={specs.squareFootage}
              onChange={e => onChange({ ...specs, squareFootage: Number(e.target.value) || 100 })}
              className="h-8 text-xs bg-white"
            />
          </div>
          <div>
            <label className="block text-neutral-500 mb-1 font-medium">Asking Price ($)</label>
            <Input
              type="number"
              step={10000}
              value={specs.listedPrice}
              onChange={e => onChange({ ...specs, listedPrice: Number(e.target.value) || 10000 })}
              className="h-8 text-xs bg-white"
            />
          </div>
        </div>
      )}
    </div>
  )
}

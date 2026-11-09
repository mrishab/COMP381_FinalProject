import React, { useState, useMemo, useEffect, useRef } from 'react'
import { Search, MapPin, Sparkles, Building2, Cpu, TrendingUp } from 'lucide-react'
import {
  PropertySpecs,
  resolvePropertyByAddress,
  getAddressSuggestions,
  VERIFIED_LISTINGS,
} from '../services/propertyLookup'
import { predictPropertyDiscount, ModelAlgorithm } from '../ml/browserModel'
import { DiscountBadge } from './DiscountBadge'
import { SpecsDisplay } from './SpecsDisplay'
import { Card, CardContent } from './ui/card'
import { Badge } from './ui/badge'
import { Button } from './ui/button'

export const PropertyEvaluator: React.FC = () => {
  const [addressInput, setAddressInput] = useState('1188 W Pender St, Unit 2102, Vancouver, BC')
  const [activeSpecs, setActiveSpecs] = useState<PropertySpecs>(() =>
    resolvePropertyByAddress('1188 W Pender St, Unit 2102, Vancouver, BC')
  )
  const [selectedAlgo, setSelectedAlgo] = useState<ModelAlgorithm>('ensemble')
  const [showDropdown, setShowDropdown] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Autocomplete suggestions
  const suggestions = useMemo(() => getAddressSuggestions(addressInput), [addressInput])

  // In-browser ML prediction executes synchronously on activeSpecs or algo change
  const prediction = useMemo(
    () => predictPropertyDiscount(activeSpecs, selectedAlgo),
    [activeSpecs, selectedAlgo]
  )

  const handleSelectAddress = (addr: string) => {
    setAddressInput(addr)
    const resolved = resolvePropertyByAddress(addr)
    setActiveSpecs(resolved)
    setShowDropdown(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const resolved = resolvePropertyByAddress(addressInput)
      setActiveSpecs(resolved)
      setShowDropdown(false)
    }
  }

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (evt: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(evt.target as Node)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6">
      {/* Model Selection Toggle */}
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-1.5 text-xs text-neutral-400">
          <Cpu className="w-3.5 h-3.5" />
          <span>Active In-Browser Engine:</span>
        </div>
        <div className="inline-flex rounded-xl bg-neutral-200/50 p-0.5 text-xs">
          <button
            onClick={() => setSelectedAlgo('ensemble')}
            className={`px-2.5 py-1 rounded-lg font-medium transition ${
              selectedAlgo === 'ensemble'
                ? 'bg-white text-neutral-900 shadow-sm'
                : 'text-neutral-500 hover:text-neutral-900'
            }`}
          >
            Random Forest (R² 0.86)
          </button>
          <button
            onClick={() => setSelectedAlgo('ridge')}
            className={`px-2.5 py-1 rounded-lg font-medium transition ${
              selectedAlgo === 'ridge'
                ? 'bg-white text-neutral-900 shadow-sm'
                : 'text-neutral-500 hover:text-neutral-900'
            }`}
          >
            Ridge Linear (R² 0.66)
          </button>
        </div>
      </div>

      {/* Search Input Section */}
      <div className="relative" ref={dropdownRef}>
        <div className="relative flex items-center bg-white rounded-2xl border border-neutral-200/80 shadow-sm focus-within:border-neutral-400 focus-within:shadow transition-all duration-200">
          <div className="pl-4 text-neutral-400">
            <Search className="w-5 h-5" />
          </div>
          <input
            type="text"
            value={addressInput}
            onChange={e => {
              setAddressInput(e.target.value)
              setShowDropdown(true)
            }}
            onFocus={() => setShowDropdown(true)}
            onKeyDown={handleKeyDown}
            placeholder="Type or select a property address..."
            className="w-full py-4 pl-3 pr-12 bg-transparent text-neutral-900 text-sm sm:text-base placeholder:text-neutral-400 focus:outline-none"
          />
          {addressInput && (
            <Button
              size="sm"
              onClick={() => {
                const resolved = resolvePropertyByAddress(addressInput)
                setActiveSpecs(resolved)
                setShowDropdown(false)
              }}
              className="mr-3 text-xs"
            >
              Analyze
            </Button>
          )}
        </div>

        {/* Dropdown Suggestions */}
        {showDropdown && suggestions.length > 0 && (
          <div className="absolute z-30 left-0 right-0 mt-2 bg-white rounded-2xl border border-neutral-200 shadow-xl overflow-hidden py-1">
            <div className="px-4 py-2 text-[11px] font-semibold text-neutral-400 uppercase tracking-wider">
              Verified Properties (GVA & Fraser Valley)
            </div>
            {suggestions.map((item, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => handleSelectAddress(item.address)}
                className="w-full text-left px-4 py-2.5 hover:bg-neutral-50 flex items-center justify-between text-sm transition"
              >
                <div className="flex items-center gap-2.5 truncate">
                  <MapPin className="w-4 h-4 text-neutral-400 shrink-0" />
                  <span className="truncate text-neutral-800">{item.address}</span>
                </div>
                <span className="text-xs text-neutral-400 shrink-0 ml-2 font-medium">
                  ${(item.listedPrice / 1000).toFixed(0)}k
                </span>
              </button>
            ))}
          </div>
        )}

        {/* Quick Suggestion Pills */}
        <div className="flex flex-wrap items-center gap-2 mt-3 pt-1">
          <span className="text-xs text-neutral-400 mr-1 flex items-center gap-1">
            <Sparkles className="w-3 h-3" /> Quick pick:
          </span>
          {VERIFIED_LISTINGS.slice(0, 5).map((p, i) => (
            <button
              key={i}
              onClick={() => handleSelectAddress(p.address)}
              className="text-xs px-2.5 py-1 rounded-full bg-white border border-neutral-200/80 text-neutral-600 hover:text-neutral-900 hover:border-neutral-400 transition"
            >
              {p.city} (${(p.listedPrice / 1000).toFixed(0)}k)
            </button>
          ))}
        </div>
      </div>

      {/* Valuation & Discount Output Card */}
      <Card className="p-6 sm:p-8 space-y-6">
        <CardContent className="p-0 space-y-6">
          {/* Address Header */}
          <div className="flex items-start justify-between gap-4 flex-wrap sm:flex-nowrap">
            <div>
              <div className="inline-flex items-center gap-1.5 text-xs font-medium text-neutral-400 uppercase tracking-wider mb-1">
                <Building2 className="w-3.5 h-3.5" />
                <span>{activeSpecs.city}, {activeSpecs.province}</span>
              </div>
              <h2 className="text-base sm:text-lg font-semibold text-neutral-900 leading-snug">
                {activeSpecs.address}
              </h2>
            </div>
            <DiscountBadge
              dealStatus={prediction.dealStatus}
              percentDiscount={prediction.percentDiscount}
              dollarDiscount={prediction.dollarDiscount}
            />
          </div>

          {/* Price Comparison Big Numbers */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
            {/* Asking Listed Price */}
            <div className="p-4 rounded-2xl bg-neutral-50/70 border border-neutral-100">
              <div className="text-xs text-neutral-400 font-medium uppercase tracking-wide">
                Current Asking Price
              </div>
              <div className="text-2xl sm:text-3xl font-bold text-neutral-900 mt-1">
                ${prediction.listedPrice.toLocaleString()}
              </div>
              <div className="text-xs text-neutral-400 mt-0.5">
                ${Math.round(prediction.listedPrice / activeSpecs.squareFootage)} / sqft
              </div>
            </div>

            {/* ML Calculated Fair Market Price */}
            <div className="p-4 rounded-2xl bg-neutral-50/70 border border-neutral-100">
              <div className="flex items-center justify-between">
                <div className="text-xs text-neutral-400 font-medium uppercase tracking-wide">
                  ML Calculated Fair Value
                </div>
                <Badge variant="outline" className="text-[10px] bg-neutral-100 font-normal py-0">
                  {prediction.modelName}
                </Badge>
              </div>
              <div className="text-2xl sm:text-3xl font-bold text-neutral-900 mt-1">
                ${prediction.fairMarketPrice.toLocaleString()}
              </div>
              <div className="text-xs text-neutral-400 mt-0.5">
                ${Math.round(prediction.fairMarketPrice / activeSpecs.squareFootage)} / sqft model target
              </div>
            </div>
          </div>

          {/* Value Drivers Insight (from ML interactions) */}
          {prediction.featureContributions.length > 0 && (
            <div className="p-4 rounded-2xl bg-neutral-50/50 border border-neutral-100 space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-neutral-500 uppercase tracking-wider">
                <TrendingUp className="w-3.5 h-3.5" />
                <span>Key Valuation Drivers</span>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                {prediction.featureContributions.map((fc, i) => (
                  <span
                    key={i}
                    className={`px-2.5 py-1 rounded-lg border ${
                      fc.impact > 0
                        ? 'bg-emerald-50/50 text-emerald-800 border-emerald-100'
                        : 'bg-rose-50/50 text-rose-800 border-rose-100'
                    }`}
                  >
                    {fc.name.replace(/_/g, ' ')}: {fc.impact > 0 ? '+' : ''}${fc.impact.toLocaleString()}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Specs Display and Optional Fine-Tuning */}
          <SpecsDisplay
            specs={activeSpecs}
            onChange={updated => setActiveSpecs(updated)}
          />
        </CardContent>
      </Card>
    </div>
  )
}

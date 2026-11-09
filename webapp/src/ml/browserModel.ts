/**
 * In-Browser Pandas and Scikit-Learn Inference Engine
 *
 * Implements client-side feature generation, polynomial & interaction expansion,
 * RobustScaler transformation, and dual-model inference:
 * 1. Random Forest Tree Ensemble (R² 0.86, non-linear multi-tree voting)
 * 2. Ridge Regularized Regression (R² 0.66, linear feature attribution)
 */

import modelData from './modelData.json'
import { PropertySpecs } from '../services/propertyLookup'

export type ModelAlgorithm = 'ensemble' | 'ridge'

export interface ModelPrediction {
  listedPrice: number
  fairMarketPrice: number
  dollarDiscount: number
  percentDiscount: number
  dealStatus: 'great_deal' | 'fair_price' | 'overpriced'
  confidenceScore: number
  modelName: string
  modelR2: number
  featureContributions: Array<{ name: string; impact: number }>
}

interface DecisionTree {
  feature: number[]
  threshold: number[]
  left: number[]
  right: number[]
  val: number[]
}

interface ForestData {
  trees: DecisionTree[]
}

// Major Canadian metropolitan coordinates (Lat, Lon)
const METRO_COORDS: Record<string, [number, number]> = {
  vancouver: [49.2827, -123.1207],
  toronto: [43.6532, -79.3832],
  montreal: [45.5017, -73.5673],
  calgary: [51.0447, -114.0719],
  ottawa: [45.4215, -75.6972],
}

/**
 * In-browser feature transformer mimicking pandas / scikit-learn
 */
export function buildFeatureVector(specs: PropertySpecs): Record<string, number> {
  const feats: Record<string, number> = {}

  // 1. Numeric Baselines
  feats['Bedrooms'] = specs.bedrooms
  feats['Bathrooms'] = specs.bathrooms
  feats['Square Footage'] = specs.squareFootage
  feats['Acreage'] = specs.acreage
  feats['Latitude'] = specs.latitude
  feats['Longitude'] = specs.longitude

  // 2. Amenities
  feats['Garage'] = specs.garage
  feats['Parking'] = specs.parking
  feats['Fireplace'] = specs.fireplace
  feats['Waterfront'] = specs.waterfront
  feats['Pool'] = specs.pool
  feats['Garden'] = specs.garden
  feats['Balcony'] = specs.balcony

  // 3. Interactions and Ratios (with non-zero denominator protection)
  const bedCount = Math.max(0, specs.bedrooms)
  const bathCount = Math.max(0, specs.bathrooms)
  const sqft = Math.max(50, specs.squareFootage)

  feats['sqft_per_bedroom'] = sqft / (bedCount + 1)
  feats['sqft_per_room'] = sqft / (bedCount + bathCount + 1)
  feats['bath_bed_ratio'] = bathCount / (bedCount + 1)
  feats['sqft_x_bedrooms'] = sqft * bedCount
  feats['sqft_x_bathrooms'] = sqft * bathCount
  feats['bed_bath_product'] = bedCount * bathCount
  feats['luxury_score'] = specs.fireplace + specs.waterfront + specs.pool + specs.garden + specs.balcony
  feats['amenity_density'] = feats['luxury_score'] / (sqft / 1000.0 + 1.0)

  // 4. Metropolitan Distances
  const distVan = Math.sqrt((specs.latitude - METRO_COORDS.vancouver[0]) ** 2 + (specs.longitude - METRO_COORDS.vancouver[1]) ** 2)
  const distTor = Math.sqrt((specs.latitude - METRO_COORDS.toronto[0]) ** 2 + (specs.longitude - METRO_COORDS.toronto[1]) ** 2)
  const distMtl = Math.sqrt((specs.latitude - METRO_COORDS.montreal[0]) ** 2 + (specs.longitude - METRO_COORDS.montreal[1]) ** 2)
  const distCal = Math.sqrt((specs.latitude - METRO_COORDS.calgary[0]) ** 2 + (specs.longitude - METRO_COORDS.calgary[1]) ** 2)
  const distOtt = Math.sqrt((specs.latitude - METRO_COORDS.ottawa[0]) ** 2 + (specs.longitude - METRO_COORDS.ottawa[1]) ** 2)

  feats['dist_to_vancouver'] = distVan
  feats['dist_to_toronto'] = distTor
  feats['dist_to_montreal'] = distMtl
  feats['dist_to_calgary'] = distCal
  feats['dist_to_ottawa'] = distOtt
  feats['min_dist_to_metro'] = Math.min(distVan, distTor, distMtl, distCal, distOtt)

  // 5. Polynomial Features
  feats['sqft_squared'] = sqft ** 2
  feats['bedrooms_squared'] = bedCount ** 2
  feats['bathrooms_squared'] = bathCount ** 2

  // 6. One-hot categories with proper domain mapping
  const propTypeMap: Record<string, string> = {
    Apartment: 'Condo/Townhome',
    Condo: 'Condo/Townhome',
    'Condo/Townhome': 'Condo/Townhome',
    Townhouse: 'Townhome',
    Townhome: 'Townhome',
    'Single Family': 'Single Family',
    Duplex: 'Duplex',
    MultiFamily: 'MultiFamily',
    'Mobile Home': 'Mobile Home',
    'Manufactured Home': 'Manufactured Home',
    'Vacant Land': 'Vacant Land',
  }
  const mappedPropType = propTypeMap[specs.propertyType] || 'Single Family'

  const propTypes = [
    'Condo/Townhome',
    'Duplex',
    'Manufactured Home',
    'Mobile Home',
    'MultiFamily',
    'Single Family',
    'Townhome',
    'Vacant Land',
  ]
  for (const pt of propTypes) {
    feats[`Property Type_${pt}`] = mappedPropType === pt ? 1 : 0
  }

  const provinces = ['BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'ON', 'PE', 'QC', 'SK', 'YT']
  for (const pv of provinces) {
    feats[`Province_${pv}`] = specs.province === pv ? 1 : 0
  }

  return feats
}

/**
 * Traverses a single decision tree recursively/iteratively in browser memory.
 */
function evaluateSingleTree(tree: DecisionTree, scaledFeatures: number[]): number {
  let node = 0
  while (tree.left[node] !== -1 && tree.left[node] !== undefined) {
    const fIdx = tree.feature[node]
    const thresh = tree.threshold[node]
    if (scaledFeatures[fIdx] <= thresh) {
      node = tree.left[node]
    } else {
      node = tree.right[node]
    }
  }
  return tree.val[node]
}

/**
 * Evaluates an entire Random Forest ensemble by averaging individual tree votes.
 */
function evaluateRandomForest(forest: ForestData, scaledFeatures: number[]): number {
  let sum = 0
  const treeCount = forest.trees.length
  for (let i = 0; i < treeCount; i++) {
    sum += evaluateSingleTree(forest.trees[i], scaledFeatures)
  }
  return sum / treeCount
}

/**
 * Evaluates the trained model against property specs entirely within the browser.
 */
export function predictPropertyDiscount(
  specs: PropertySpecs,
  algorithm: ModelAlgorithm = 'ensemble'
): ModelPrediction {
  const featMap = buildFeatureVector(specs)
  const features: string[] = (modelData as any).features || []
  const center: number[] = (modelData as any).scaler?.center || []
  const scale: number[] = (modelData as any).scaler?.scale || []

  // Build scaled vector
  const scaledVector: number[] = new Array(features.length)
  for (let i = 0; i < features.length; i++) {
    const rawVal = featMap[features[i]] ?? 0.0
    const c = center[i] ?? 0.0
    const s = scale[i] && scale[i] !== 0 ? scale[i] : 1.0
    scaledVector[i] = (rawVal - c) / s
  }

  // Feature contributions via Ridge linear coefficients
  const coefs: number[] = (modelData as any).coefficients || (modelData as any).ridge?.coefficients || []
  const intercept: number = (modelData as any).intercept || (modelData as any).ridge?.intercept || 0

  let ridgePred = intercept
  const contributions: Array<{ name: string; impact: number }> = []

  for (let i = 0; i < features.length; i++) {
    const fName = features[i]
    const impact = (coefs[i] ?? 0.0) * scaledVector[i]
    ridgePred += impact

    if (Math.abs(impact) > 10000) {
      contributions.push({ name: fName, impact: Math.round(impact) })
    }
  }

  // Inference calculation
  let rawPrediction = ridgePred
  let modelName = 'Ridge Regression (L2 Linear)'
  let modelR2 = (modelData as any).metrics?.ridge_r2 || (modelData as any).metrics?.R2_Score || 0.664

  const forest: ForestData | undefined = (modelData as any).forest
  if (algorithm === 'ensemble' && forest && forest.trees && forest.trees.length > 0) {
    rawPrediction = evaluateRandomForest(forest, scaledVector)
    modelName = `Random Forest Ensemble (${forest.trees.length} Trees)`
    modelR2 = (modelData as any).metrics?.random_forest_r2 || 0.862
  }

  // Realistic GVA / Fraser Valley market boundary enforcement
  const fairMarketPrice = Math.max(150000, Math.round(rawPrediction / 1000) * 1000)
  const listedPrice = specs.listedPrice
  const dollarDiscount = fairMarketPrice - listedPrice
  const percentDiscount = Number(((dollarDiscount / fairMarketPrice) * 100).toFixed(1))

  let dealStatus: 'great_deal' | 'fair_price' | 'overpriced' = 'fair_price'
  if (percentDiscount >= 4.0) {
    dealStatus = 'great_deal'
  } else if (percentDiscount <= -4.0) {
    dealStatus = 'overpriced'
  }

  return {
    listedPrice,
    fairMarketPrice,
    dollarDiscount,
    percentDiscount,
    dealStatus,
    confidenceScore: Math.min(0.95, Math.max(0.60, modelR2)),
    modelName,
    modelR2,
    featureContributions: contributions.sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact)).slice(0, 5),
  }
}
